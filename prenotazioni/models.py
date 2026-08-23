import secrets

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class Prenotazione(models.Model):
    class Stato(models.TextChoices):
        PRENOTATA = "PR", "Prenotata"
        CONFERMATA = "CO", "Confermata"
        ANNULLATA = "AN", "Annullata"
        ESEGUITA = "ES", "Eseguita"
        ASSENTE = "NS", "Assente"

    codice = models.CharField(max_length=32, unique=True, editable=False)
    ufficio = models.ForeignKey("access_control.Ufficio", on_delete=models.PROTECT, related_name="prenotazioni_pubbliche")
    data_ora = models.DateTimeField()
    motivo = models.CharField(max_length=255)
    dettagli = models.CharField(max_length=200, blank=True)
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    codice_fiscale = models.CharField(max_length=16, validators=[RegexValidator(r"^[A-Za-z0-9]{16}$", "Indicare un codice fiscale di 16 caratteri.")])
    email = models.EmailField()
    telefono = models.CharField(max_length=50, blank=True)
    identita_digitale = models.ForeignKey("spid_cie.IdentitaDigitale", on_delete=models.SET_NULL, null=True, blank=True, related_name="prenotazioni")
    stato = models.CharField(max_length=2, choices=Stato.choices, default=Stato.PRENOTATA)
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ufficio", "data_ora"], condition=Q(stato__in=["PR", "CO"]), name="prenotazione_pubblica_slot_unico")
        ]
        ordering = ["-data_ora"]
        verbose_name = "Prenotazione pubblica"
        verbose_name_plural = "Prenotazioni pubbliche"

    def save(self, *args, **kwargs):
        if not self.codice:
            self.codice = secrets.token_urlsafe(12)
        self.codice_fiscale = self.codice_fiscale.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codice} — {self.cognome} {self.nome}"
