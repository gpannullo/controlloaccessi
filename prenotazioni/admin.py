import re
import unicodedata

from django.contrib import admin, messages
from django.contrib.auth import get_user_model

from access_control.models import Ufficio
from accounts.services.directory_admin_service import DirectoryAdminException, DirectoryAdminService
from audit.services.audit_service import AuditService

from .models import AssegnazionePersonaleWordPress, AppuntamentoWordPress, MappaturaUfficioWordPress, PersonaleWordPress, Prenotazione, SedeWordPress, StatoSincronizzazioneWordPress, UnitaOrganizzativaWordPress
from .people_linking import collega_persone_pubbliche
from .wordpress_connector import WordPressConnectorError, pubblica_calendario_wordpress, pubblica_persona_pubblica_wordpress, pubblica_unita_organizzativa_wordpress, sincronizza_anagrafiche_wordpress


User = get_user_model()


def _username_da_persona_pubblica(nome, cognome, servizio):
    """Propone iniziale.nome, aggiungendo un numero se necessario."""
    def normalizza(valore):
        valore = unicodedata.normalize("NFKD", valore or "").encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]", "", valore.lower())

    nome_normalizzato = normalizza(nome)
    cognome_normalizzato = normalizza(cognome)
    if not nome_normalizzato or not cognome_normalizzato:
        raise DirectoryAdminException("Nome e cognome della persona pubblica sono obbligatori.")

    base = f"{nome_normalizzato[0]}.{cognome_normalizzato}"
    suffisso = 1
    while True:
        username = base if suffisso == 1 else f"{base}{suffisso}"
        if not User.objects.filter(username__iexact=username).exists() and not servizio.username_esiste(username):
            return username
        suffisso += 1


@admin.register(Prenotazione)
class PrenotazioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "cognome", "nome", "ufficio", "data_ora", "stato")
    list_filter = ("stato", "ufficio")
    search_fields = ("codice", "codice_fiscale", "cognome", "nome", "email")
    readonly_fields = ("codice", "creato_il")


@admin.register(MappaturaUfficioWordPress)
class MappaturaUfficioWordPressAdmin(admin.ModelAdmin):
    list_display = ("unita_organizzativa", "unita_organizzativa_id", "sede", "luogo_id", "ufficio", "calendario_wordpress_id", "aggiornato_il")
    list_filter = ("ufficio", "sede")
    search_fields = ("unita_organizzativa", "unita_organizzativa_id", "luogo_id", "sede__nome", "ufficio__nome")
    autocomplete_fields = ("ufficio", "sede", "unita_organizzativa_wordpress")
    fields = ("ufficio", "unita_organizzativa_wordpress", "sede", "calendario_wordpress_id", "aggiornato_il")
    readonly_fields = ("calendario_wordpress_id", "aggiornato_il")
    actions = ("scarica_anagrafiche_da_wordpress", "sincronizza_ufficio_su_wordpress",)

    @admin.action(description="Scarica sedi e calendari da WordPress")
    def scarica_anagrafiche_da_wordpress(self, request, queryset):
        try:
            risultato = sincronizza_anagrafiche_wordpress()
        except WordPressConnectorError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        else:
            self.message_user(request, f"Importate {risultato['sedi']} sedi, {risultato['unita_organizzative']} unità organizzative, {risultato['personale']} persone e {risultato['mappature']} calendari.", messages.SUCCESS)

    @admin.action(description="Sincronizza calendario dell'ufficio selezionato su WordPress")
    def sincronizza_ufficio_su_wordpress(self, request, queryset):
        eseguiti = 0
        for mappatura in queryset.select_related("ufficio", "sede"):
            try:
                pubblica_calendario_wordpress(mappatura)
            except WordPressConnectorError as exc:
                self.message_user(request, f"{mappatura}: {exc}", messages.ERROR)
            else:
                eseguiti += 1
        if eseguiti:
            self.message_user(request, f"Sincronizzati {eseguiti} calendari su WordPress.", messages.SUCCESS)


@admin.register(SedeWordPress)
class SedeWordPressAdmin(admin.ModelAdmin):
    list_display = ("nome", "origine_id", "stato", "aggiornato_il")
    list_filter = ("stato",)
    search_fields = ("nome", "origine_id")
    readonly_fields = ("origine_id", "aggiornato_il")
    actions = ("sincronizza_sedi_da_wordpress",)

    @admin.action(description="Scarica sedi e unità organizzative da WordPress")
    def sincronizza_sedi_da_wordpress(self, request, queryset):
        try:
            risultato = sincronizza_anagrafiche_wordpress()
        except WordPressConnectorError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        else:
            self.message_user(request, f"Importate {risultato['sedi']} sedi, {risultato['unita_organizzative']} unità organizzative, {risultato['personale']} persone e {risultato['mappature']} calendari.", messages.SUCCESS)


class CollegamentoUfficioFilter(admin.SimpleListFilter):
    title = "Ufficio locale"
    parameter_name = "ufficio_collegato"

    def lookups(self, request, model_admin):
        return (
            ("collegato", "Collegato"),
            ("non_collegato", "Non collegato"),
        )

    def queryset(self, request, queryset):
        collegamento = self.value()
        if collegamento == "collegato":
            return queryset.filter(ufficio__isnull=False)
        if collegamento == "non_collegato":
            return queryset.filter(ufficio__isnull=True)
        return queryset


@admin.register(UnitaOrganizzativaWordPress)
class UnitaOrganizzativaWordPressAdmin(admin.ModelAdmin):
    list_display = ("nome", "origine_id", "ufficio", "stato", "aggiornato_il")
    list_filter = ("stato", CollegamentoUfficioFilter, "ufficio")
    search_fields = ("nome", "origine_id", "ufficio__nome")
    autocomplete_fields = ("ufficio",)
    readonly_fields = ("origine_id", "aggiornato_il")
    actions = ("crea_uffici_locali", "allinea_unita_organizzative_su_wordpress")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            return
        try:
            pubblica_unita_organizzativa_wordpress(obj)
        except WordPressConnectorError as exc:
            self.message_user(request, f"Unità salvata localmente, ma non aggiornata su WordPress: {exc}", messages.ERROR)
        else:
            self.message_user(request, "Unità organizzativa aggiornata anche su WordPress.", messages.SUCCESS)

    @staticmethod
    def _codice_ufficio(unita):
        base = f"WP-UO-{unita.pk}"[:20]
        codice = base
        suffisso = 2
        while Ufficio.objects.filter(codice=codice).exists():
            codice = f"{base[:20 - len(str(suffisso))]}{suffisso}"
            suffisso += 1
        return codice

    @admin.action(description="Crea uffici locali dalle unità organizzative selezionate")
    def crea_uffici_locali(self, request, queryset):
        creati = collegati = gia_collegati = 0
        for unita in queryset.select_related("ufficio"):
            if unita.ufficio_id:
                gia_collegati += 1
                continue
            ufficio = Ufficio.objects.filter(nome__iexact=unita.nome).first()
            if ufficio:
                unita.ufficio = ufficio
                unita.save(update_fields=["ufficio", "aggiornato_il"])
                collegati += 1
                continue
            ufficio = Ufficio.objects.create(
                codice=self._codice_ufficio(unita),
                nome=unita.nome,
                attivo=unita.stato == "publish",
                riceve_pubblico=False,
                note=f"Creato dall'Unità organizzativa WordPress {unita.origine_id}.",
            )
            unita.ufficio = ufficio
            unita.save(update_fields=["ufficio", "aggiornato_il"])
            creati += 1
        self.message_user(
            request,
            f"Creati: {creati}; collegati a un ufficio esistente: {collegati}; già collegati: {gia_collegati}.",
            messages.SUCCESS,
        )

    @admin.action(description="Allinea forzatamente le unità organizzative selezionate su WordPress")
    def allinea_unita_organizzative_su_wordpress(self, request, queryset):
        aggiornate = errori = 0
        for unita in queryset:
            try:
                pubblica_unita_organizzativa_wordpress(unita)
            except WordPressConnectorError as exc:
                errori += 1
                self.message_user(request, f"{unita.nome}: {exc}", messages.ERROR)
            else:
                aggiornate += 1
        livello = messages.WARNING if errori else messages.SUCCESS
        self.message_user(
            request,
            f"Unità aggiornate su WordPress: {aggiornate}; errori: {errori}.",
            livello,
        )


class AssegnazionePersonaleWordPressInline(admin.TabularInline):
    model = AssegnazionePersonaleWordPress
    extra = 0
    autocomplete_fields = ("unita_organizzativa",)


class StatoUtenteDjangoFilter(admin.SimpleListFilter):
    title = "Utente Django"
    parameter_name = "utente_django_stato"

    def lookups(self, request, model_admin):
        return (
            ("attivo", "Attivo"),
            ("non_attivo", "Non attivo"),
            ("non_associato", "Non associato"),
        )

    def queryset(self, request, queryset):
        stato = self.value()
        if stato == "attivo":
            return queryset.filter(utente__is_active=True)
        if stato == "non_attivo":
            return queryset.filter(utente__isnull=False, utente__is_active=False)
        if stato == "non_associato":
            return queryset.filter(utente__isnull=True)
        return queryset


@admin.register(PersonaleWordPress)
class PersonaleWordPressAdmin(admin.ModelAdmin):
    list_display = ("titolo", "cognome", "nome", "competenze_brevi", "attivo", "uffici_assegnati", "utente", "utente_django_attivo", "aggiornato_il")
    list_filter = ("attivo", StatoUtenteDjangoFilter, "unita_organizzative")
    search_fields = ("titolo", "nome", "cognome", "competenze", "utente__username")
    autocomplete_fields = ("utente",)
    list_select_related = ("utente",)
    readonly_fields = ("origine_id", "aggiornato_il")
    inlines = (AssegnazionePersonaleWordPressInline,)
    actions = (
        "crea_utenti_ldap",
        "collega_utenti_django",
        "pubblica_persone_su_wordpress",
        "rimuovi_persone_non_attive_dalle_unita_organizzative",
    )

    @admin.action(description="Crea gli account LDAP disabilitati per le persone selezionate")
    def crea_utenti_ldap(self, request, queryset):
        creati = gia_associati = non_attive = errori = 0
        servizio = DirectoryAdminService()

        for persona in queryset.select_related("utente"):
            if persona.utente_id:
                gia_associati += 1
                continue
            if not persona.attivo:
                non_attive += 1
                continue
            try:
                username = _username_da_persona_pubblica(persona.nome, persona.cognome, servizio)
                servizio.crea_utente(
                    username=username,
                    first_name=persona.nome,
                    last_name=persona.cognome,
                    email="",
                    personal_email="",
                    mobile="",
                )
                utente = User(username=username, first_name=persona.nome, last_name=persona.cognome, is_active=False)
                utente.set_unusable_password()
                utente.save()
                persona.utente = utente
                persona.save(update_fields=["utente"])
                AuditService.log(
                    user=request.user,
                    tipo="CREATE",
                    oggetto=f"ActiveDirectory:{username}",
                    descrizione=f"Creato account LDAP disabilitato dalla persona pubblica {persona}.",
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
            except Exception as exc:
                errori += 1
                self.message_user(request, f"{persona}: {exc}", messages.ERROR)
            else:
                creati += 1

        livello = messages.WARNING if errori else messages.SUCCESS
        self.message_user(
            request,
            "Account LDAP creati e collegati: %s; già associati: %s; persone non attive saltate: %s; errori: %s. "
            "I nuovi account sono disabilitati e privi di password: completare anagrafica e recapiti, impostare la password e abilitarli dalla Gestione account."
            % (creati, gia_associati, non_attive, errori),
            livello,
        )

    @admin.action(description="Collega automaticamente agli utenti Django corrispondenti")
    def collega_utenti_django(self, request, queryset):
        risultato = collega_persone_pubbliche(queryset)
        self.message_user(
            request,
            "Collegati: {collegati}; già associati: {gia_collegati}; senza corrispondenza: {nessuna_corrispondenza}; ambigui: {ambigui}.".format(**risultato),
            messages.SUCCESS,
        )

    @admin.display(description="Uffici WordPress")
    def uffici_assegnati(self, obj):
        return ", ".join(obj.unita_organizzative.values_list("nome", flat=True)) or "—"

    @admin.display(description="Competenze")
    def competenze_brevi(self, obj):
        return obj.competenze[:80] + ("…" if len(obj.competenze) > 80 else "")

    @admin.display(description="Utente Django attivo", boolean=True)
    def utente_django_attivo(self, obj):
        if not obj.utente_id:
            return None
        return obj.utente.is_active

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not form.instance.attivo:
            AssegnazionePersonaleWordPress.objects.filter(personale=form.instance).delete()
        try:
            pubblica_persona_pubblica_wordpress(form.instance)
        except WordPressConnectorError as exc:
            self.message_user(request, f"Persona salvata in Django, ma non pubblicata su WordPress: {exc}", messages.ERROR)
        else:
            self.message_user(request, "Persona pubblica aggiornata anche su WordPress.", messages.SUCCESS)

    @admin.action(description="Rimuovi dalle unità organizzative le persone pubbliche non attive selezionate")
    def rimuovi_persone_non_attive_dalle_unita_organizzative(self, request, queryset):
        aggiornate = associazioni_rimosse = errori = 0
        for persona in queryset.filter(attivo=False):
            associazioni_rimosse += AssegnazionePersonaleWordPress.objects.filter(
                personale=persona
            ).delete()[0]
            try:
                pubblica_persona_pubblica_wordpress(persona)
            except WordPressConnectorError as exc:
                errori += 1
                self.message_user(request, f"{persona}: {exc}", messages.ERROR)
            else:
                aggiornate += 1
        livello = messages.WARNING if errori else messages.SUCCESS
        self.message_user(
            request,
            f"Persone non attive aggiornate: {aggiornate}; associazioni rimosse: {associazioni_rimosse}; errori: {errori}.",
            livello,
        )

    @admin.action(description="Pubblica le persone selezionate su WordPress")
    def pubblica_persone_su_wordpress(self, request, queryset):
        eseguiti = 0
        for persona in queryset.prefetch_related("unita_organizzative"):
            try:
                pubblica_persona_pubblica_wordpress(persona)
            except WordPressConnectorError as exc:
                self.message_user(request, f"{persona}: {exc}", messages.ERROR)
            else:
                eseguiti += 1
        if eseguiti:
            self.message_user(request, f"Pubblicate {eseguiti} persone pubbliche su WordPress.", messages.SUCCESS)


@admin.register(AppuntamentoWordPress)
class AppuntamentoWordPressAdmin(admin.ModelAdmin):
    list_display = ("origine_id", "data_ora_inizio", "servizio", "unita_organizzativa", "ufficio", "origine_stato")
    list_filter = ("origine_stato", "ufficio")
    search_fields = ("origine_id", "email", "codice_fiscale", "servizio", "unita_organizzativa")
    readonly_fields = ("acquisito_il", "sincronizzato_il", "dati_origine")


@admin.register(StatoSincronizzazioneWordPress)
class StatoSincronizzazioneWordPressAdmin(admin.ModelAdmin):
    list_display = ("chiave", "cursore", "ultima_esecuzione_il")
    readonly_fields = ("ultima_esecuzione_il",)
