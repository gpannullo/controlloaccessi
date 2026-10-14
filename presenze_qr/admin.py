from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Postazione, Timbratura, Attivita


@admin.register(Postazione)
class PostazioneAdmin(admin.ModelAdmin):
    list_display = ('nome', 'attiva', 'scade_il', 'apri_monitor')
    fields = ('nome', 'attiva')

    def apri_monitor(self, obj):
        return format_html('<a href="{}">Apri monitor</a>', reverse('monitor_presenze', args=[obj.pk]))


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Timbratura)
class TimbraturaAdmin(ReadOnlyAdmin):
    list_display = ('utente', 'registrata_il', 'verso', 'origine', 'badge', 'causale', 'verso_originale', 'postazione')
    list_filter = ('origine', 'verso', 'postazione')
    search_fields = ('utente__username',)


@admin.register(Attivita)
class AttivitaAdmin(ReadOnlyAdmin):
    list_display = ('registrata_il', 'utente', 'azione', 'postazione', 'ip', 'verso_prima', 'verso_dopo')
    list_filter = ('azione', 'postazione')
    search_fields = ('utente__username',)
