from django.contrib import admin

from .models import PDNDAuditLog


@admin.register(PDNDAuditLog)
class PDNDAuditLogAdmin(admin.ModelAdmin):
    list_display = ("eseguita_il", "servizio", "operatore", "esito", "request_id")
    list_filter = ("servizio", "esito")
    search_fields = ("operatore__username", "request_id", "identificativo_hash")
    readonly_fields = ("operatore", "servizio", "identificativo_hash", "esito", "request_id", "dettaglio_errore", "eseguita_il")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
