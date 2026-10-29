import uuid
from django.conf import settings
from django.db import models


class Postazione(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    attiva = models.BooleanField(default=True)
    generazione = models.UUIDField(default=uuid.uuid4, editable=False)
    scade_il = models.DateTimeField(null=True, editable=False)
    consumato_il = models.DateTimeField(null=True, editable=False)

    class Meta:
        verbose_name_plural = 'Postazioni presenze QR'
        permissions = [('gestisci_monitor', 'Può utilizzare il monitor presenze QR')]

    def __str__(self):
        return self.nome


class Timbratura(models.Model):
    utente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    postazione = models.ForeignKey(Postazione, on_delete=models.PROTECT, null=True, blank=True)
    generazione = models.UUIDField(unique=True, editable=False, null=True)
    origine = models.CharField(max_length=12, choices=[('QR', 'QR'), ('AUTOMATICO', 'Sistema automatico')], default='QR', editable=False)
    chiave_importazione = models.CharField(max_length=64, unique=True, null=True, editable=False)
    badge = models.CharField(max_length=10, blank=True, editable=False)
    causale = models.CharField(max_length=4, blank=True, editable=False)
    registrata_il = models.DateTimeField(db_index=True)
    verso = models.CharField(max_length=1, choices=[('I', 'Entrata'), ('U', 'Uscita')])
    verso_originale = models.CharField(max_length=1, editable=False)
    ip = models.GenericIPAddressField(null=True, editable=False)

    class Meta:
        ordering = ['-registrata_il', '-pk']
        verbose_name_plural = 'Timbrature'
        indexes = [models.Index(fields=['utente', '-registrata_il'], name='qr_utente_data_idx')]


class Attivita(models.Model):
    utente = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    postazione = models.ForeignKey(Postazione, null=True, on_delete=models.SET_NULL)
    timbratura = models.ForeignKey(Timbratura, null=True, on_delete=models.PROTECT)
    registrata_il = models.DateTimeField(auto_now_add=True)
    azione = models.CharField(max_length=40)
    ip = models.GenericIPAddressField(null=True)
    verso_prima = models.CharField(max_length=1, blank=True)
    verso_dopo = models.CharField(max_length=1, blank=True)

    class Meta:
        ordering = ['-registrata_il', '-pk']
        verbose_name_plural = 'Registro attività presenze QR'
