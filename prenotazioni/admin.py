from django.contrib import admin, messages

from .models import AssegnazionePersonaleWordPress, AppuntamentoWordPress, MappaturaUfficioWordPress, PersonaleWordPress, Prenotazione, SedeWordPress, StatoSincronizzazioneWordPress, UnitaOrganizzativaWordPress
from .wordpress_connector import WordPressConnectorError, pubblica_calendario_wordpress, pubblica_uffici_personale_wordpress, sincronizza_anagrafiche_wordpress


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


@admin.register(UnitaOrganizzativaWordPress)
class UnitaOrganizzativaWordPressAdmin(admin.ModelAdmin):
    list_display = ("nome", "origine_id", "ufficio", "stato", "aggiornato_il")
    list_filter = ("stato", "ufficio")
    search_fields = ("nome", "origine_id", "ufficio__nome")
    autocomplete_fields = ("ufficio",)
    readonly_fields = ("origine_id", "aggiornato_il")


class AssegnazionePersonaleWordPressInline(admin.TabularInline):
    model = AssegnazionePersonaleWordPress
    extra = 0
    autocomplete_fields = ("unita_organizzativa",)


@admin.register(PersonaleWordPress)
class PersonaleWordPressAdmin(admin.ModelAdmin):
    list_display = ("username", "cognome", "nome", "email", "attivo", "uffici_assegnati", "utente", "aggiornato_il")
    list_filter = ("attivo", "unita_organizzative")
    search_fields = ("username", "nome", "cognome", "email", "utente__username")
    autocomplete_fields = ("utente",)
    readonly_fields = ("origine_id", "aggiornato_il")
    inlines = (AssegnazionePersonaleWordPressInline,)
    actions = ("pubblica_uffici_su_wordpress",)

    @admin.display(description="Uffici WordPress")
    def uffici_assegnati(self, obj):
        return ", ".join(obj.unita_organizzative.values_list("nome", flat=True)) or "—"

    @admin.action(description="Pubblica le assegnazioni ufficio selezionate su WordPress")
    def pubblica_uffici_su_wordpress(self, request, queryset):
        eseguiti = 0
        for persona in queryset.prefetch_related("unita_organizzative"):
            try:
                pubblica_uffici_personale_wordpress(persona)
            except WordPressConnectorError as exc:
                self.message_user(request, f"{persona}: {exc}", messages.ERROR)
            else:
                eseguiti += 1
        if eseguiti:
            self.message_user(request, f"Pubblicate le assegnazioni di {eseguiti} persone su WordPress.", messages.SUCCESS)


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
