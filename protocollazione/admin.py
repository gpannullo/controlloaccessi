from django.contrib import admin, messages
from .models import RegistrazioneProtocollo, ReportGiornaliero
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone


@admin.register(ReportGiornaliero)
class ReportGiornalieroAdmin(admin.ModelAdmin):
    list_display = ['giorno', 'tipo', 'generato_il', 'scarica_pdf']
    list_filter = ['tipo', 'giorno']
    exclude = ['documento']
    readonly_fields = ['chiave', 'giorno', 'tipo', 'parametri', 'generato_il', 'scarica_pdf']

    def get_urls(self):
        return [path('<int:pk>/pdf/', self.admin_site.admin_view(self.pdf), name='protocollazione_reportgiornaliero_pdf')] + super().get_urls()

    def pdf(self, request, pk):
        obj = get_object_or_404(ReportGiornaliero, pk=pk)
        if not self.has_view_permission(request, obj):
            raise PermissionDenied
        response = HttpResponse(bytes(obj.documento), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report-{obj.tipo}-{obj.giorno:%Y%m%d}.pdf"'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    @admin.display(description='Documento conservato')
    def scarica_pdf(self, obj):
        return format_html('<a href="{}">Scarica PDF</a>', reverse('admin:protocollazione_reportgiornaliero_pdf', args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegistrazioneProtocollo)
class RegistrazioneProtocolloAdmin(admin.ModelAdmin):
    list_display = ['chiave','stato','creato_il','operatore','numero_protocollo']
    list_filter = ['stato','backend','creato_il']
    search_fields = ['chiave','oggetto']
    readonly_fields = [f.name for f in RegistrazioneProtocollo._meta.fields]
    actions = ('autorizza_reinvio',)

    @admin.action(description='Autorizza nuovo invio dopo verifica Cityware')
    def autorizza_reinvio(self, request, queryset):
        selezionati = queryset.filter(stato__in=[
            RegistrazioneProtocollo.Stato.IN_CORSO,
            RegistrazioneProtocollo.Stato.INCERTO,
            RegistrazioneProtocollo.Stato.ERRORE,
        ])
        count = selezionati.update(reinvio_autorizzato=True, reinvio_autorizzato_il=timezone.now())
        esclusi = queryset.exclude(stato__in=[RegistrazioneProtocollo.Stato.IN_CORSO, RegistrazioneProtocollo.Stato.INCERTO]).count()
        if count:
            self.message_user(request, f'{count} registrazione/i autorizzata/e al reinvio. Verificare prima Cityware.', messages.WARNING)
        if esclusi:
            self.message_user(request, f'{esclusi} registrazione/i già completata/e non modificata/e.', messages.INFO)

    @admin.display(description='Protocollo')
    def numero_protocollo(self,obj):
        return f"{obj.esito.get('numero','-')}/{obj.esito.get('anno','-')}"

    def has_add_permission(self,request):
        return False

    def has_change_permission(self,request,obj=None):
        return False

    def has_delete_permission(self,request,obj=None):
        return False
