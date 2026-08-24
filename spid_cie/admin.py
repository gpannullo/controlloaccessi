from django.contrib import admin

from .models import IdentitaDigitale, MessaggioIO


@admin.register(IdentitaDigitale)
class IdentitaDigitaleAdmin(admin.ModelAdmin):
    list_display = ("provider", "codice_fiscale", "cognome", "nome", "email", "autenticato_il")
    list_filter = ("provider",)
    search_fields = ("codice_fiscale", "cognome", "nome", "email", "subject")
    readonly_fields = ("provider", "subject", "autenticato_il", "creato_il")


@admin.register(MessaggioIO)
class MessaggioIOAdmin(admin.ModelAdmin):
    list_display = ("creato_il", "codice_fiscale", "oggetto", "stato", "riferimento_esterno", "messaggio_io_id")
    list_filter = ("stato",)
    search_fields = ("codice_fiscale", "oggetto", "riferimento_esterno", "messaggio_io_id")
    readonly_fields = ("codice_fiscale", "oggetto", "contenuto", "riferimento_esterno", "messaggio_io_id", "stato", "risposta", "creato_il")
