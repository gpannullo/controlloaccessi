from django.conf import settings
from django.db import models


class ReportGiornaliero(models.Model):
    chiave = models.CharField(max_length=200, unique=True)
    giorno = models.DateField()
    tipo = models.CharField(max_length=20, choices=[('visitatori', 'Visitatori'), ('qr', 'Passaggi QR')])
    documento = models.BinaryField(editable=False)
    parametri = models.JSONField(default=dict)
    generato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Report giornaliero da protocollare'
        verbose_name_plural = 'Report giornalieri da protocollare'
        ordering = ['-giorno', 'tipo']

    def __str__(self):
        return self.chiave


class RegistrazioneProtocollo(models.Model):
    class Stato(models.TextChoices):
        IN_CORSO = 'in_corso', 'In corso / da verificare se interrotto'
        COMPLETATO = 'completato', 'Protocollato'
        ERRORE = 'errore', 'Errore prima della registrazione'
        INCERTO = 'incerto', 'Esito incerto: verificare sul gestionale'

    chiave = models.CharField(max_length=200, unique=True)
    backend = models.CharField(max_length=255)
    impronta_richiesta = models.CharField(max_length=64)
    impronta_documento = models.CharField(max_length=64)
    nome_documento = models.CharField(max_length=255)
    oggetto = models.TextField()
    stato = models.CharField(max_length=20, choices=Stato.choices, default=Stato.IN_CORSO)
    esito = models.JSONField(default=dict, blank=True)
    errore = models.CharField(max_length=255, blank=True)
    reinvio_autorizzato = models.BooleanField(default=False, editable=False)
    reinvio_autorizzato_il = models.DateTimeField(null=True, blank=True, editable=False)
    operatore = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    creato_il = models.DateTimeField(auto_now_add=True)
    aggiornato_il = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Registrazione protocollo'
        verbose_name_plural = 'Registrazioni protocollo'
        ordering = ['-creato_il']

    def __str__(self):
        return f'{self.chiave} - {self.get_stato_display()}'
