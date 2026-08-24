from django.conf import settings
from django.db import models


class PDNDAuditLog(models.Model):
    class Servizio(models.TextChoices):
        ANPR_SOGGETTO = "ANPR_SOGGETTO", "ANPR — dati del soggetto"
        ANPR_FAMIGLIA = "ANPR_FAMIGLIA", "ANPR — composizione famiglia"
        INPS_ISEE = "INPS_ISEE", "INPS — attestazione ISEE"
        DURC = "DURC", "DURC — regolarità contributiva"

    class Esito(models.TextChoices):
        ESEGUITA = "ESEGUITA", "Eseguita"
        NON_CONFIGURATA = "NON_CONFIGURATA", "Servizio non configurato"
        NEGATA = "NEGATA", "Negata dal servizio"
        ERRORE = "ERRORE", "Errore tecnico"

    operatore = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="interrogazioni_pdnd")
    servizio = models.CharField(max_length=20, choices=Servizio.choices)
    identificativo_hash = models.CharField(max_length=64, db_index=True)
    esito = models.CharField(max_length=20, choices=Esito.choices)
    request_id = models.CharField(max_length=100, blank=True)
    dettaglio_errore = models.CharField(max_length=500, blank=True)
    eseguita_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-eseguita_il"]
        verbose_name = "Audit interrogazione PDND"
        verbose_name_plural = "Audit interrogazioni PDND"

    def __str__(self):
        return f"{self.get_servizio_display()} — {self.eseguita_il:%d/%m/%Y %H:%M}"
