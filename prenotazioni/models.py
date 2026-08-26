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


class SedeWordPress(models.Model):
    """Anagrafica delle sedi (post type ``luogo``) del WordPress storico."""

    origine_id = models.CharField(max_length=64, unique=True)
    nome = models.CharField(max_length=255)
    stato = models.CharField(max_length=32, blank=True)
    aggiornato_il = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Sede WordPress"
        verbose_name_plural = "Sedi WordPress"

    def __str__(self):
        return self.nome


class MappaturaUfficioWordPress(models.Model):
    """Corrispondenza fra le anagrafiche WordPress e gli uffici locali."""

    unita_organizzativa_id = models.CharField(max_length=64)
    luogo_id = models.CharField(max_length=64)
    unita_organizzativa = models.CharField(max_length=255, blank=True)
    sede = models.ForeignKey(
        SedeWordPress,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mappature_ufficio",
    )
    calendario_wordpress_id = models.CharField(max_length=64, blank=True)
    ufficio = models.ForeignKey(
        "access_control.Ufficio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mappature_wordpress",
    )
    aggiornato_il = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["unita_organizzativa_id", "luogo_id"],
                name="mappatura_ufficio_wordpress_unica",
            )
        ]
        ordering = ["unita_organizzativa", "luogo_id"]
        verbose_name = "Mappatura ufficio WordPress"
        verbose_name_plural = "Mappature uffici WordPress"

    def __str__(self):
        destinazione = self.ufficio or "da associare"
        return f"{self.unita_organizzativa or self.unita_organizzativa_id} → {destinazione}"


class AppuntamentoWordPress(models.Model):
    """Archivio idempotente degli appuntamenti ricevuti dal WordPress storico."""

    origine_id = models.BigIntegerField(unique=True, db_index=True)
    origine_stato = models.CharField(max_length=32, blank=True)
    origine_aggiornato_il = models.DateTimeField(db_index=True)
    prenotato_il = models.DateTimeField(null=True, blank=True)
    data_ora_inizio = models.DateTimeField(null=True, blank=True, db_index=True)
    data_ora_fine = models.DateTimeField(null=True, blank=True)
    unita_organizzativa_id = models.CharField(max_length=64, blank=True)
    unita_organizzativa = models.CharField(max_length=255, blank=True)
    luogo_id = models.CharField(max_length=64, blank=True)
    servizio = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    codice_fiscale = models.CharField(max_length=16, blank=True)
    dettaglio_richiesta = models.TextField(blank=True)
    ufficio = models.ForeignKey(
        "access_control.Ufficio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appuntamenti_wordpress",
    )
    dati_origine = models.JSONField(default=dict, blank=True)
    acquisito_il = models.DateTimeField(auto_now_add=True)
    sincronizzato_il = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_ora_inizio", "-origine_id"]
        verbose_name = "Appuntamento WordPress"
        verbose_name_plural = "Appuntamenti WordPress"

    def __str__(self):
        return f"WP {self.origine_id} — {self.data_ora_inizio or 'senza data'}"


class StatoSincronizzazioneWordPress(models.Model):
    chiave = models.CharField(max_length=64, unique=True, default="appuntamenti")
    cursore = models.DateTimeField(null=True, blank=True)
    ultima_esecuzione_il = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Stato sincronizzazione WordPress"
        verbose_name_plural = "Stati sincronizzazione WordPress"
