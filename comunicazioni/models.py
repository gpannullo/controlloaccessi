from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

from access_control.models import Ufficio


class ComunicazioneEmail(models.Model):
    class Destinazione(models.TextChoices):
        ISTITUZIONALE = "IST", "E-mail istituzionale"
        PERSONALE = "PER", "E-mail personale"
        AGGIUNTIVA = "AGG", "E-mail aggiuntiva"

    class Stato(models.TextChoices):
        BOZZA = "BOZ", "Bozza"
        ACCODATA = "QUE", "Accodata per l'invio"

    oggetto = models.CharField(max_length=255)
    messaggio = models.TextField(help_text="Testo in formato semplice dell'e-mail.")
    destinazione = models.CharField(max_length=3, choices=Destinazione.choices, default=Destinazione.ISTITUZIONALE)
    tutti_gli_utenti_attivi = models.BooleanField(default=False, verbose_name="Tutti gli utenti attivi")
    destinatari = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="comunicazioni_ricevute")
    gruppi = models.ManyToManyField(Group, blank=True, related_name="comunicazioni_email")
    uffici = models.ManyToManyField(Ufficio, blank=True, related_name="comunicazioni_email")
    stato = models.CharField(max_length=3, choices=Stato.choices, default=Stato.BOZZA, editable=False)
    creata_da = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="comunicazioni_create")
    creato_il = models.DateTimeField(auto_now_add=True)
    accodata_il = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-creato_il"]
        verbose_name = "Comunicazione e-mail"
        verbose_name_plural = "Comunicazioni e-mail"

    def __str__(self):
        return self.oggetto


class DestinatarioComunicazioneEmail(models.Model):
    comunicazione = models.ForeignKey(ComunicazioneEmail, on_delete=models.CASCADE, related_name="invii")
    utente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    indirizzo_email = models.EmailField()
    accodato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["indirizzo_email"]
        verbose_name = "Destinatario comunicazione"
        verbose_name_plural = "Destinatari comunicazione"
        constraints = [models.UniqueConstraint(fields=["comunicazione", "indirizzo_email"], name="destinatario_comunicazione_email_unico")]
