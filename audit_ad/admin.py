from django.contrib import admin
from .models import Event, Alert

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
    list_display = ('occurred_at', 'source', 'event_id', 'username', 'client_ip', 'workstation', 'protocol', 'logon_type')
    list_filter = ('source', 'event_id', 'protocol')
    search_fields = ('username', 'client_ip', 'computer', 'workstation')
    date_hierarchy = 'occurred_at'
    readonly_fields = tuple(f.name for f in Event._meta.fields)
    show_full_result_count = False

@admin.register(Alert)
class AlertAdmin(RestrictedAdmin):
    list_display = ('created_at', 'rule', 'severity', 'event', 'reviewed')
    list_filter = ('reviewed', 'severity', 'rule')
    readonly_fields = ('key', 'event', 'rule', 'severity', 'description', 'evidence', 'created_at')
