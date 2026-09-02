from django.contrib import admin, messages
from django.contrib.auth.models import Group
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


class UfficioGruppiOrganizzativiFilter(admin.SimpleListFilter):
    title = "Collegamento a Gruppo organizzativo"
    parameter_name = "gruppi_organizzativi"

    def lookups(self, request, model_admin):
        return (("collegati", "Collegati"), ("non_collegati", "Non collegati"))

    def queryset(self, request, queryset):
        if self.value() == "collegati":
            return queryset.filter(gruppi__isnull=False).distinct()
        if self.value() == "non_collegati":
            return queryset.filter(gruppi__isnull=True)
        return queryset


class UfficioDipendentiFilter(admin.SimpleListFilter):
    title = "Dipendenti attivi"
    parameter_name = "dipendenti"

    def lookups(self, request, model_admin):
        return (("con_dipendenti", "Con dipendenti"), ("senza_dipendenti", "Senza dipendenti"))

    def queryset(self, request, queryset):
        if self.value() == "con_dipendenti":
            return queryset.filter(gruppi__django_group__user__is_active=True).distinct()
        if self.value() == "senza_dipendenti":
            return queryset.exclude(gruppi__django_group__user__is_active=True).distinct()
        return queryset


@admin.register(Ufficio)
class UfficioAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "prefisso_coda",
        "responsabile",
        "riceve_pubblico",
        "gruppi_organizzativi",
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
    )

    inlines = [
        CalendarioAperturaInline,
    ]

    actions = ("disabilita_uffici", "crea_gruppi_active_directory")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "gruppi__django_group__user_set",
            "unita_organizzative_wordpress",
        )

    @admin.display(description="Gruppi organizzativi")
    def gruppi_organizzativi(self, obj):
        return ", ".join(sorted((gruppo.nome for gruppo in obj.gruppi.all()), key=str.casefold)) or "—"

    @admin.display(description="Unità organizzative WordPress")
    def unita_organizzative_wordpress(self, obj):
        return ", ".join(
            sorted((unita.nome for unita in obj.unita_organizzative_wordpress.all()), key=str.casefold)
        ) or "—"

    def numero_dipendenti(self, obj):
        utenti_ids = set()

        for gruppo in obj.gruppi.all():
            utenti_ids.update(
                utente.pk for utente in gruppo.django_group.user_set.all() if utente.is_active
            )

        return len(utenti_ids)

    numero_dipendenti.short_description = "Dipendenti"

    def dipendenti_agganciati(self, obj):
        utenti = {}

        for gruppo in obj.gruppi.all():
            for utente in gruppo.django_group.user_set.all():
                if not utente.is_active:
                    continue
                utenti[utente.pk] = utente

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
            gruppo_esistente = ufficio.gruppi.filter(
                tipo=GruppoOrganizzativo.Tipo.ORGANIZZATIVO
            ).first()
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
            if gruppo_locale and gruppo_locale.ufficio_id not in {None, ufficio.pk}:
                errori.append(
                    f"{ufficio.nome}: il gruppo locale '{nome_gruppo}' è già collegato a un altro ufficio."
                )
                continue
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
                        gruppo_locale.ufficio = ufficio
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
                            ufficio=ufficio,
                            attivo=True,
                            sincronizzato=True,
                        )
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
        "ufficio",
        "numero_utenti",
        "dipendenti_collegati",
        "attivo",
        "sincronizzato",
    )

    autocomplete_fields = (
        "ufficio",
        "django_group",
    )

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
