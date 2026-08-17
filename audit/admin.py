from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):

    list_display = (
        "timestamp",
        "tipo",
        "user",
        "oggetto",
        "ip_address",
    )

    list_filter = ("tipo", "timestamp")
    search_fields = ("oggetto", "descrizione", "user__username")