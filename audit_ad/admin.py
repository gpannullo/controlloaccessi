from django.contrib import admin
from django.utils import timezone
from zoneinfo import ZoneInfo
from .models import Event, Alert

def rome_time(value):
    if value is None:
        return '—'
    return timezone.localtime(value, ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y %H:%M:%S %Z (UTC%z)')

class RestrictedAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser
    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

@admin.register(Event)
class EventAdmin(RestrictedAdmin):
    list_display = ('occurred_rome', 'source', 'event_id', 'username', 'client_ip', 'workstation', 'protocol', 'logon_type')
    list_filter = ('source', 'event_id', 'protocol')
    search_fields = ('username', 'client_ip', 'computer', 'workstation')
    date_hierarchy = 'occurred_at'
    readonly_fields = tuple(f.name for f in Event._meta.fields if f.name not in ('occurred_at', 'received_at')) + ('occurred_rome', 'received_rome')
    exclude = ('occurred_at', 'received_at')
    show_full_result_count = False

    @admin.display(description='Data evento (Roma)', ordering='occurred_at')
    def occurred_rome(self, obj):
        return rome_time(obj.occurred_at)

    @admin.display(description='Ricevuto il (Roma)', ordering='received_at')
    def received_rome(self, obj):
        return rome_time(obj.received_at)

@admin.register(Alert)
class AlertAdmin(RestrictedAdmin):
    list_display = ('created_rome', 'rule', 'severity', 'event', 'reviewed')
    list_filter = ('reviewed', 'severity', 'rule')
    readonly_fields = ('key', 'event', 'rule', 'severity', 'description', 'evidence', 'created_rome')
    exclude = ('created_at',)

    @admin.display(description='Segnalazione creata il (Roma)', ordering='created_at')
    def created_rome(self, obj):
        return rome_time(obj.created_at)
