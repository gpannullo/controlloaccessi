from django.contrib import admin, messages

from .models import AppuntamentoWordPress, MappaturaUfficioWordPress, Prenotazione, SedeWordPress, StatoSincronizzazioneWordPress
from .wordpress_connector import WordPressConnectorError, pubblica_calendario_wordpress, sincronizza_anagrafiche_wordpress


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
    autocomplete_fields = ("ufficio", "sede")
    actions = ("scarica_anagrafiche_da_wordpress", "sincronizza_ufficio_su_wordpress",)

    @admin.action(description="Scarica sedi e calendari da WordPress")
    def scarica_anagrafiche_da_wordpress(self, request, queryset):
        try:
            risultato = sincronizza_anagrafiche_wordpress()
        except WordPressConnectorError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        else:
            self.message_user(request, f"Importate/aggiornate {risultato['sedi']} sedi e {risultato['mappature']} associazioni.", messages.SUCCESS)

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
            self.message_user(request, f"Importate/aggiornate {risultato['sedi']} sedi e {risultato['mappature']} associazioni.", messages.SUCCESS)


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
