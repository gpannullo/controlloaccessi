from django.contrib import admin
from .models import AccountSEC, Comune, Sottocommissione, Verbale

@admin.register(Sottocommissione)
class SottocommissioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "nome", "attiva", "numero_comuni"); search_fields = ("codice", "nome"); list_filter = ("attiva",)
    @admin.display(description="Comuni")
    def numero_comuni(self, obj): return obj.comuni.count()

@admin.register(Comune)
class ComuneAdmin(admin.ModelAdmin):
    list_display = ("nome", "sottocommissione", "codice_istat", "attivo", "numero_account"); list_filter = ("sottocommissione", "attivo"); search_fields = ("nome", "codice_istat")
    @admin.display(description="Account")
    def numero_account(self, obj): return obj.account.filter(attivo=True).count()

@admin.register(AccountSEC)
class AccountSECAdmin(admin.ModelAdmin):
    list_display = ("user", "comune", "attivo", "solo_locale"); list_filter = ("comune__sottocommissione", "comune", "attivo"); search_fields = ("user__username", "user__first_name", "user__last_name", "comune__nome"); readonly_fields = ("solo_locale",)
    def save_model(self, request, obj, form, change):
        obj.user.autenticazione_locale = True
        obj.user.save(update_fields=["autenticazione_locale"])
        super().save_model(request, obj, form, change)

@admin.register(Verbale)
class VerbaleAdmin(admin.ModelAdmin):
    list_display = ("numero", "comune", "tipologia", "tornata", "data_verbale", "elettori", "caricato_da"); list_filter = ("tipologia", "tornata", "comune__sottocommissione", "comune", "data_verbale"); search_fields = ("comune__nome", "caricato_da__username"); readonly_fields = ("elettori", "caricato_da", "creato_il")
    def save_model(self, request, obj, form, change):
        if not obj.caricato_da_id: obj.caricato_da = request.user
        super().save_model(request, obj, form, change)
