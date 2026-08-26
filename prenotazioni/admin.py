from django.contrib import admin

from .models import AppuntamentoWordPress, MappaturaUfficioWordPress, Prenotazione, StatoSincronizzazioneWordPress


@admin.register(Prenotazione)
class PrenotazioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "cognome", "nome", "ufficio", "data_ora", "stato")
    list_filter = ("stato", "ufficio")
    search_fields = ("codice", "codice_fiscale", "cognome", "nome", "email")
    readonly_fields = ("codice", "creato_il")


@admin.register(MappaturaUfficioWordPress)
class MappaturaUfficioWordPressAdmin(admin.ModelAdmin):
    list_display = ("unita_organizzativa", "unita_organizzativa_id", "luogo_id", "ufficio", "aggiornato_il")
    list_filter = ("ufficio",)
    search_fields = ("unita_organizzativa", "unita_organizzativa_id", "luogo_id", "ufficio__nome")


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
