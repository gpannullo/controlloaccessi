from django.contrib import admin
from .models import RegistrazioneProtocollo


@admin.register(RegistrazioneProtocollo)
class RegistrazioneProtocolloAdmin(admin.ModelAdmin):
    list_display = ['chiave','stato','creato_il','operatore','numero_protocollo']
    list_filter = ['stato','backend','creato_il']
    search_fields = ['chiave','oggetto']
    readonly_fields = [f.name for f in RegistrazioneProtocollo._meta.fields]

    @admin.display(description='Protocollo')
    def numero_protocollo(self,obj):
        return f"{obj.esito.get('numero','-')}/{obj.esito.get('anno','-')}"

    def has_add_permission(self,request):
        return False

    def has_change_permission(self,request,obj=None):
        return False

    def has_delete_permission(self,request,obj=None):
        return False
