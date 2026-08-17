from django.contrib import admin
from django.utils import timezone
from .models import Visitatore, AccessoVisitatore, Appuntamento, Badge, SessioneRicevimento, EventoAccesso


@admin.register(Visitatore)
class VisitatoreAdmin(admin.ModelAdmin):
    list_display = ("nome", "cognome", "telefono")
    search_fields = ("nome", "cognome")


@admin.register(AccessoVisitatore)
class AccessoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_coda_visualizzato",
        "visitatore",
        "ufficio_destinazione",
        "tipo_accesso",
        "badge",
        "ingresso",
        "uscita",
        "permanenza_complessiva",
        "stato",
    )

    list_filter = (
        "tipo_accesso",
        "stato",
        "ufficio_destinazione",
        "ingresso",
    )

    search_fields = (
        "visitatore__nome",
        "visitatore__cognome",
        "badge__codice",
    )

    @admin.display(
        description="Coda",
        ordering="numero_coda",
    )
    def numero_coda_visualizzato(self, obj):
        return obj.numero_coda_formattato


    @admin.display(description="Permanenza complessiva")
    def permanenza_complessiva(self, obj):
        if not obj.ingresso:
            return "—"

        fine = obj.uscita or timezone.now()
        durata = fine - obj.ingresso

        secondi = max(0, int(durata.total_seconds()))
        minuti_totali = secondi // 60
        ore, minuti = divmod(minuti_totali, 60)

        if ore:
            return f"{ore} h {minuti} min"

        return f"{minuti} min"


@admin.register(Appuntamento)
class AppuntamentoAdmin(admin.ModelAdmin):
    list_display = (
        "nome_cittadino",
        "cognome_cittadino",
        "ufficio",
        "data_ora",
        "stato",
    )

    list_filter = ("ufficio", "stato")
    search_fields = ("nome_cittadino", "cognome_cittadino")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = (
        "codice",
        "attivo",
        "stato_disponibilita",
    )

    list_filter = (
        "attivo",
    )

    search_fields = (
        "codice",
    )

    ordering = (
        "codice",
    )

    @admin.display(
        description="Disponibilità",
        boolean=True,
    )
    def stato_disponibilita(self, obj):
        return obj.disponibile

@admin.register(SessioneRicevimento)
class SessioneRicevimentoAdmin(admin.ModelAdmin):
    list_display = (
        "ufficio",
        "operatore",
        "iniziata_il",
        "terminata_il",
        "attiva",
    )

    list_filter = (
        "attiva",
        "ufficio",
        "iniziata_il",
    )

    search_fields = (
        "operatore__username",
        "operatore__first_name",
        "operatore__last_name",
        "ufficio__nome",
    )

    autocomplete_fields = (
        "ufficio",
        "operatore",
    )

    ordering = (
        "-iniziata_il",
    )

    readonly_fields = (
        "iniziata_il",
        "terminata_il",
    )

@admin.register(EventoAccesso)
class EventoAccessoAdmin(admin.ModelAdmin):

    list_display = (
        "timestamp",
        "tipo",
        "accesso",
        "ufficio",
        "operatore",
    )

    list_filter = (
        "tipo",
        "ufficio",
        "timestamp",
    )

    search_fields = (
        "descrizione",
        "accesso__visitatore__nome",
        "accesso__visitatore__cognome",
        "operatore__username",
    )

    readonly_fields = (
        "accesso",
        "tipo",
        "timestamp",
        "ufficio",
        "operatore",
        "descrizione",
        "dati",
    )

    ordering = (
        "-timestamp",
    )

    def has_add_permission(self, request):
        return False