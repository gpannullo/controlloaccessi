from django.contrib import admin

from .models import Prenotazione


@admin.register(Prenotazione)
class PrenotazioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "cognome", "nome", "ufficio", "data_ora", "stato")
    list_filter = ("stato", "ufficio")
    search_fields = ("codice", "codice_fiscale", "cognome", "nome", "email")
    readonly_fields = ("codice", "creato_il")
