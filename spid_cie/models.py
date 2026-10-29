from django.db import models


class IdentitaDigitale(models.Model):
    class Provider(models.TextChoices):
        SPID = "SPID", "SPID"
        CIE = "CIE", "CIE"

    provider = models.CharField(max_length=4, choices=Provider.choices)
    subject = models.CharField(max_length=255)
    codice_fiscale = models.CharField(max_length=16, blank=True, db_index=True)
    nome = models.CharField(max_length=100, blank=True)
    cognome = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    autenticato_il = models.DateTimeField(auto_now=True)
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "subject"],
                name="spid_cie_identita_provider_subject_unico",
            )
        ]
        ordering = ["cognome", "nome", "provider"]
        verbose_name = "Identità digitale"
        verbose_name_plural = "Identità digitali"

    def __str__(self):
        return f"{self.get_provider_display()} — {self.nome} {self.cognome}".strip()


class MessaggioIO(models.Model):
    """Storico tecnico delle comunicazioni personali inviate tramite App IO."""

    class Stato(models.TextChoices):
        INVIATO = "INVIATO", "Inviato a IO"
        NON_CONFIGURATO = "NON_CONFIGURATO", "Integrazione non configurata"
        NON_ABILITATO = "NON_ABILITATO", "Cittadino non abilitato al servizio"
        ERRORE = "ERRORE", "Errore di invio"

    codice_fiscale = models.CharField(max_length=16, db_index=True)
    oggetto = models.CharField(max_length=120)
    contenuto = models.TextField()
    riferimento_esterno = models.CharField(max_length=64, blank=True, db_index=True)
    messaggio_io_id = models.CharField(max_length=100, blank=True, db_index=True)
    stato = models.CharField(max_length=20, choices=Stato.choices)
    risposta = models.TextField(blank=True)
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creato_il"]
        verbose_name = "Messaggio App IO"
        verbose_name_plural = "Messaggi App IO"

    def __str__(self):
        return f"{self.codice_fiscale} — {self.oggetto}"


class CodiceAccessoGateway(models.Model):
    """Codice monouso ricevuto dal gateway SPID, mai salvato in chiaro."""

    codice_hash = models.CharField(max_length=64, unique=True)
    codice_fiscale = models.CharField(max_length=16)
    nome = models.CharField(max_length=100, blank=True)
    cognome = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    destinazione = models.CharField(max_length=500)
    scade_il = models.DateTimeField(db_index=True)
    usato_il = models.DateTimeField(null=True, blank=True)
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creato_il"]
        verbose_name = "Codice accesso gateway SPID"
        verbose_name_plural = "Codici accesso gateway SPID"
