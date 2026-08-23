from django.contrib import admin

from .models import IdentitaDigitale


@admin.register(IdentitaDigitale)
class IdentitaDigitaleAdmin(admin.ModelAdmin):
    list_display = ("provider", "codice_fiscale", "cognome", "nome", "email", "autenticato_il")
    list_filter = ("provider",)
    search_fields = ("codice_fiscale", "cognome", "nome", "email", "subject")
    readonly_fields = ("provider", "subject", "autenticato_il", "creato_il")
