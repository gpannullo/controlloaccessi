from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group
from django.contrib.admin.sites import NotRegistered
from django.db import transaction
from django.db.models import Count, Q

from accounts.services.directory_admin_service import (
    DirectoryAdminException,
    DirectoryAdminService,
)
from .models import (
    CalendarioApertura,
    GruppoOrganizzativo,
    Ufficio,
)
from .services.office_service import OfficeService


class CalendarioAperturaInline(admin.TabularInline):
    model = CalendarioApertura

    extra = 0

    ordering = (
        "giorno",
        "ora_inizio",
    )


class GruppoOperativoInline(admin.StackedInline):
    """Estensione organizzativa visualizzata nella scheda del Gruppo Django."""

    model = GruppoOrganizzativo
    fk_name = "django_group"
    extra = 1
    max_num = 1
    can_delete = False
    readonly_fields = ("directory_sid",)
    fieldsets = (
        (
            "Configurazione Gruppo Operativo",
            {
                "fields": (
                    "nome",
                    "directory_name",
                    "directory_sid",
                    "tipo",
                    "attivo",
                    "sincronizzato",
                    "note",
                ),
            },
        ),
    )


try:
    admin.site.unregister(Group)
except NotRegistered:
    pass


@admin.register(Group)
class GruppoDjangoAdmin(GroupAdmin):
    """Gruppo Django con la sua estensione operativa nella stessa scheda."""

    inlines = (GruppoOperativoInline,)
    list_display = ("name", "uffici_operativi", "directory_name", "attivo_operativo")
    search_fields = ("name", "gruppo_organizzativo__directory_name")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("gruppo_organizzativo__uffici")

    @admin.display(description="Uffici")
    def uffici_operativi(self, obj):
        gruppo = getattr(obj, "gruppo_organizzativo", None)
        if not gruppo:
            return "—"
        return ", ".join(ufficio.nome for ufficio in gruppo.uffici.all()) or "—"

    @admin.display(description="Directory name")
    def directory_name(self, obj):
        gruppo = getattr(obj, "gruppo_organizzativo", None)
        return gruppo.directory_name if gruppo else "—"

    @admin.display(description="Attivo", boolean=True)
    def attivo_operativo(self, obj):
        gruppo = getattr(obj, "gruppo_organizzativo", None)
        return gruppo.attivo if gruppo else None


class UfficioGruppiOrganizzativiFilter(admin.SimpleListFilter):
    title = "Collegamento a Gruppo organizzativo"
    parameter_name = "gruppi_organizzativi"

    def lookups(self, request, model_admin):
        return (("collegati", "Collegati"), ("non_collegati", "Non collegati"))

    def queryset(self, request, queryset):
        if self.value() == "collegati":
            return queryset.filter(gruppo_operativo__isnull=False)
        if self.value() == "non_collegati":
            return queryset.filter(gruppo_operativo__isnull=True)
        return queryset


class UfficioDipendentiFilter(admin.SimpleListFilter):
    title = "Dipendenti attivi"
    parameter_name = "dipendenti"

    def lookups(self, request, model_admin):
        return (("con_dipendenti", "Con dipendenti"), ("senza_dipendenti", "Senza dipendenti"))

    def queryset(self, request, queryset):
        if self.value() == "con_dipendenti":
            return queryset.filter(
                assegnazioni_personale__attiva=True,
                assegnazioni_personale__utente__is_active=True,
            ).distinct()
        if self.value() == "senza_dipendenti":
            return queryset.exclude(
                assegnazioni_personale__attiva=True,
                assegnazioni_personale__utente__is_active=True,
            ).distinct()
        return queryset


@admin.register(Ufficio)
class UfficioAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "prefisso_coda",
        "responsabile",
        "riceve_pubblico",
        "gruppo_operativo",
        "unita_organizzative_wordpress",
        "numero_dipendenti",
        "dipendenti_agganciati",
        "attivo",
    )

    list_filter = (
        "attivo",
        "riceve_pubblico",
        UfficioGruppiOrganizzativiFilter,
        UfficioDipendentiFilter,
    )

    search_fields = (
        "nome",
    )

    ordering = (
        "nome",
    )

    autocomplete_fields = (
        "responsabile",
        "gruppo_operativo",
    )

    inlines = [
        CalendarioAperturaInline,
    ]

    actions = ("disabilita_uffici", "crea_gruppi_active_directory")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "gruppo_operativo__django_group",
        ).prefetch_related(
            "assegnazioni_personale__utente",
            "unita_organizzative_wordpress",
        )

    @admin.display(description="Gruppo operativo")
    def gruppo_operativo(self, obj):
        return obj.gruppo_operativo or "—"

    @admin.display(description="Unità organizzative WordPress")
    def unita_organizzative_wordpress(self, obj):
        return ", ".join(
            sorted((unita.nome for unita in obj.unita_organizzative_wordpress.all()), key=str.casefold)
        ) or "—"

    def numero_dipendenti(self, obj):
        return sum(
            1
            for assegnazione in obj.assegnazioni_personale.all()
            if assegnazione.attiva and assegnazione.utente.is_active
        )

    numero_dipendenti.short_description = "Dipendenti"

    def dipendenti_agganciati(self, obj):
        utenti = {
            assegnazione.utente.pk: assegnazione.utente
            for assegnazione in obj.assegnazioni_personale.all()
            if assegnazione.attiva and assegnazione.utente.is_active
        }

        if not utenti:
            return "—"

        def etichetta(utente):
            nome_completo = (
                utente.get_full_name().strip()
            )

            return (
                nome_completo
                or utente.username
            )

        return ", ".join(
            sorted(
                (
                    etichetta(utente)
                    for utente
                    in utenti.values()
                ),
                key=str.casefold,
            )
        )

    dipendenti_agganciati.short_description = (
        "Dipendenti agganciati"
    )

    @admin.action(description="Disabilita gli uffici selezionati")
    def disabilita_uffici(self, request, queryset):
        aggiornati = queryset.filter(attivo=True).update(attivo=False)
        self.message_user(request, f"Uffici disabilitati: {aggiornati}.", messages.SUCCESS)

    @admin.action(
        description="Crea gruppi Active Directory per gli uffici selezionati"
    )
    def crea_gruppi_active_directory(self, request, queryset):
        """Crea/collega il gruppo AD e la relativa configurazione locale.

        Per evitare associazioni ambigue, ogni ufficio usa il proprio nome
        come CN e directory name. Un ufficio che possiede gia' un gruppo di
        tipo organizzativo non viene modificato.
        """
        creati, collegati, saltati, errori = 0, 0, 0, []
        directory = DirectoryAdminService()

        for ufficio in queryset.order_by("nome"):
            gruppo_esistente = ufficio.gruppo_operativo
            if gruppo_esistente:
                saltati += 1
                continue

            nome_gruppo = ufficio.nome.strip()
            if not nome_gruppo or len(nome_gruppo) > 150:
                errori.append(f"{ufficio.nome}: nome non valido per un gruppo AD.")
                continue

            gruppo_locale = GruppoOrganizzativo.objects.filter(
                directory_name=nome_gruppo
            ).first()
            if not gruppo_locale and GruppoOrganizzativo.objects.filter(nome=nome_gruppo).exists():
                errori.append(
                    f"{ufficio.nome}: esiste già un Gruppo Organizzativo con questo nome."
                )
                continue

            try:
                risultato = directory.crea_gruppo(
                    nome_gruppo,
                    descrizione=f"Gruppo organizzativo dell'ufficio {ufficio.nome}",
                )
                with transaction.atomic():
                    django_group, _ = Group.objects.get_or_create(name=nome_gruppo)
                    if gruppo_locale:
                        gruppo_locale.django_group = django_group
                        gruppo_locale.tipo = GruppoOrganizzativo.Tipo.ORGANIZZATIVO
                        gruppo_locale.directory_sid = risultato["sid"] or gruppo_locale.directory_sid
                        gruppo_locale.attivo = True
                        gruppo_locale.sincronizzato = True
                        gruppo_locale.save()
                    else:
                        GruppoOrganizzativo.objects.create(
                            nome=nome_gruppo,
                            directory_name=nome_gruppo,
                            directory_sid=risultato["sid"] or None,
                            django_group=django_group,
                            tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO,
                            attivo=True,
                            sincronizzato=True,
                        )
                    ufficio.gruppo_operativo = gruppo_locale or GruppoOrganizzativo.objects.get(
                        directory_name=nome_gruppo
                    )
                    ufficio.save(update_fields=["gruppo_operativo"])
                if risultato["created"]:
                    creati += 1
                else:
                    collegati += 1
            except DirectoryAdminException as exc:
                errori.append(f"{ufficio.nome}: {exc}")
            except Exception as exc:
                errori.append(f"{ufficio.nome}: errore locale durante il collegamento ({exc}).")

        if creati or collegati or saltati:
            self.message_user(
                request,
                "Gruppi AD creati: %s. Gruppi AD già esistenti collegati: %s. Uffici già configurati: %s."
                % (creati, collegati, saltati),
                messages.SUCCESS,
            )
        for errore in errori:
            self.message_user(request, errore, messages.ERROR)


@admin.register(GruppoOrganizzativo)
class GruppoOrganizzativoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tipo",
        "uffici_collegati",
        "numero_utenti",
        "dipendenti_collegati",
        "attivo",
        "sincronizzato",
    )

    autocomplete_fields = ("django_group",)

    list_filter = (
        "tipo",
        "attivo",
        "sincronizzato",
    )

    search_fields = (
        "nome",
        "directory_name",
        "note",
    )

    ordering = (
        "nome",
    )

    readonly_fields = (
        "numero_utenti",
    )

    actions = (
        "attiva_gruppi",
        "disattiva_gruppi",
        "imposta_organizzativi",
        "imposta_tecnici",
        "genera_uffici",
    )

    def get_queryset(self, request):
        """
        Aggiunge al queryset il numero di utenti attivi
        appartenenti al gruppo Django.

        L'annotazione rende ordinabile la colonna
        'Dipendenti' direttamente dalla changelist.
        """
        queryset = super().get_queryset(
            request
        )

        return (
            queryset.annotate(
                numero_utenti_attivi=Count(
                    "django_group__user",
                    filter=Q(
                        django_group__user__is_active=True,
                    ),
                    distinct=True,
                )
            )
            .prefetch_related("django_group__user_set")
        )

    @admin.display(
        description="Dipendenti",
        ordering="numero_utenti_attivi",
    )
    def numero_utenti(self, obj):
        return obj.numero_utenti_attivi

    @admin.display(description="Dipendenti collegati")
    def dipendenti_collegati(self, obj):
        utenti = obj.django_group.user_set.all()
        nominativi = []
        for utente in utenti:
            nominativo = " ".join(
                valore for valore in (utente.first_name, utente.last_name) if valore
            )
            nominativi.append(nominativo or utente.username)
        return ", ".join(sorted(nominativi, key=str.casefold)) or "—"

    @admin.display(description="Uffici")
    def uffici_collegati(self, obj):
        return ", ".join(ufficio.nome for ufficio in obj.uffici.all()) or "—"

    @admin.action(
        description="Attiva gruppi selezionati"
    )
    def attiva_gruppi(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            attivo=True
        )

    @admin.action(
        description="Disattiva gruppi selezionati"
    )
    def disattiva_gruppi(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            attivo=False
        )

    @admin.action(
        description="Imposta come Organizzativo"
    )
    def imposta_organizzativi(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO
        )

    @admin.action(
        description="Imposta come Tecnico"
    )
    def imposta_tecnici(self, request, queryset):
        ids = list(
            queryset.values_list("pk", flat=True)
        )

        GruppoOrganizzativo.objects.filter(
            pk__in=ids
        ).update(
            tipo=GruppoOrganizzativo.Tipo.TECNICO
        )

    def genera_uffici(
        self,
        request,
        queryset,
    ):
        OfficeService().generate_from_groups(
            queryset
        )
