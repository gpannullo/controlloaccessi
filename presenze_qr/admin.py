from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Postazione, Timbratura, Attivita, GruppoPresenze, GiustificativoPresenza, AutodichiarazioneTimbratura


@admin.register(GiustificativoPresenza)
class GiustificativoPresenzaAdmin(admin.ModelAdmin):
    list_display = ('utente', 'gruppo', 'dal', 'al', 'causale', 'stato', 'creato_il')
    list_filter = ('stato', 'gruppo')
    search_fields = ('utente__username', 'utente__last_name', 'causale')
    readonly_fields = ('creato_il', 'approvato_il', 'approvato_da')


@admin.register(AutodichiarazioneTimbratura)
class AutodichiarazioneTimbraturaAdmin(admin.ModelAdmin):
    list_display = ('utente', 'gruppo', 'registrata_il', 'verso', 'stato', 'creata_il')
    list_filter = ('stato', 'verso', 'gruppo')
    search_fields = ('utente__username', 'utente__last_name')
    readonly_fields = ('token_approvazione', 'creata_il', 'approvata_il', 'approvata_da', 'timbratura')


@admin.register(GruppoPresenze)
class GruppoPresenzeAdmin(admin.ModelAdmin):
    list_display = ('gruppo_ad', 'referente', 'numero_utenti', 'attivo')
    list_filter = ('attivo', 'gruppo_ad')
    search_fields = ('gruppo_ad__name', 'referente__username', 'referente__first_name', 'referente__last_name')
    autocomplete_fields = ('gruppo_ad', 'referente')
    filter_horizontal = ('utenti',)
    actions = ('sincronizza_utenti',)

    def get_exclude(self, request, obj=None):
        return ('utenti',) if obj is None else ()

    def get_form(self, request, obj=None, **kwargs):
        """In modifica propone esclusivamente gli utenti del gruppo selezionato."""
        form = super().get_form(request, obj, **kwargs)
        if obj is not None and obj.gruppo_ad_id:
            form.base_fields['utenti'].queryset = obj.gruppo_ad.user_set.filter(active=True).order_by(
                'last_name', 'first_name', 'username'
            )
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj.sincronizza_utenti()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Anche se arrivasse una richiesta manipolata, non conserviamo utenti
        # che non appartengono al gruppo AD/Django collegato.
        obj = form.instance
        appartenenti = obj.gruppo_ad.user_set.all()
        obj.utenti.set(obj.utenti.filter(pk__in=appartenenti.values('pk')))

    @admin.display(description='Utenti proposti')
    def numero_utenti(self, obj):
        return obj.utenti.count()

    @admin.action(description='Sincronizza utenti dal gruppo AD/Django')
    def sincronizza_utenti(self, request, queryset):
        totale = sum(gruppo.sincronizza_utenti() for gruppo in queryset)
        self.message_user(request, f'Utenti proposti sincronizzati: {totale}.')


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
class TimbraturaAdmin(admin.ModelAdmin):
    list_display = ('utente', 'registrata_il', 'verso', 'origine', 'badge', 'causale', 'verso_originale', 'postazione')
    list_filter = ('origine', 'verso', 'postazione')
    search_fields = ('utente__username',)
    readonly_fields = ('utente', 'registrata_il', 'origine', 'badge', 'causale', 'verso_originale', 'ip', 'postazione')


@admin.register(Attivita)
class AttivitaAdmin(ReadOnlyAdmin):
    list_display = ('registrata_il', 'utente', 'azione', 'postazione', 'ip', 'verso_prima', 'verso_dopo')
    list_filter = ('azione', 'postazione')
    search_fields = ('utente__username',)
