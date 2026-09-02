from django.contrib import admin, messages

from .models import ComunicazioneEmail, DestinatarioComunicazioneEmail
from .services import ComunicazioneEmailError, accoda_comunicazione


class DestinatarioComunicazioneInline(admin.TabularInline):
    model = DestinatarioComunicazioneEmail
    extra = 0
    can_delete = False
    readonly_fields = ("utente", "indirizzo_email", "accodato_il")


@admin.register(ComunicazioneEmail)
class ComunicazioneEmailAdmin(admin.ModelAdmin):
    list_display = ("oggetto", "destinazione", "stato", "numero_destinatari", "creata_da", "creato_il", "accodata_il")
    list_filter = ("stato", "destinazione", "tutti_gli_utenti_attivi")
    search_fields = ("oggetto", "messaggio")
    autocomplete_fields = ("destinatari", "gruppi", "uffici")
    readonly_fields = ("stato", "creata_da", "creato_il", "accodata_il", "numero_destinatari")
    inlines = (DestinatarioComunicazioneInline,)
    actions = ("accoda_per_invio",)

    def save_model(self, request, obj, form, change):
        if not change and not obj.creata_da_id:
            obj.creata_da = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Destinatari accodati")
    def numero_destinatari(self, obj):
        return obj.invii.count()

    @admin.action(description="Accoda le comunicazioni selezionate per l'invio")
    def accoda_per_invio(self, request, queryset):
        inviati = errori = 0
        for comunicazione in queryset:
            try:
                inviati += accoda_comunicazione(comunicazione, autore=request.user)
            except ComunicazioneEmailError as exc:
                errori += 1
                self.message_user(request, f"{comunicazione}: {exc}", messages.ERROR)
        if inviati:
            self.message_user(request, f"E-mail accodate: {inviati}.", messages.SUCCESS)
        if not inviati and not errori:
            self.message_user(request, "Nessuna e-mail accodata.", messages.WARNING)


@admin.register(DestinatarioComunicazioneEmail)
class DestinatarioComunicazioneEmailAdmin(admin.ModelAdmin):
    list_display = ("comunicazione", "utente", "indirizzo_email", "accodato_il")
    list_filter = ("comunicazione",)
    search_fields = ("indirizzo_email", "utente__username", "utente__first_name", "utente__last_name")
    readonly_fields = ("comunicazione", "utente", "indirizzo_email", "accodato_il")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
