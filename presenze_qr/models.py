import uuid
from django.conf import settings
from django.db import models
from django.contrib.auth.models import Group


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


class GruppoPresenze(models.Model):
    """Gruppo interno per la gestione delle presenze di un gruppo AD."""

    nome = models.CharField(max_length=150, unique=True)
    gruppo_ad = models.OneToOneField(
        Group, on_delete=models.PROTECT, related_name="gruppo_presenze",
        verbose_name="Gruppo AD/Django",
    )
    referente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="gruppi_presenze_referente",
        verbose_name="Referente presenze",
    )
    utenti = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="gruppi_presenze",
        verbose_name="Utenti proposti",
    )
    attivo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Gruppo presenze"
        verbose_name_plural = "Gruppi presenze"

    def __str__(self):
        return self.nome

    def sincronizza_utenti(self):
        """Propone gli utenti appartenenti al gruppo AD/Django collegato."""
        utenti = self.gruppo_ad.user_set.all()
        self.utenti.set(utenti)
        return utenti.count()


class GiustificativoPresenza(models.Model):
    class Stato(models.TextChoices):
        IN_ATTESA = "ATTESA", "In attesa"
        APPROVATO = "APPROVATO", "Approvato"
        RIFIUTATO = "RIFIUTATO", "Rifiutato"

    gruppo = models.ForeignKey(GruppoPresenze, on_delete=models.PROTECT, related_name="giustificativi")
    utente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="giustificativi_presenza")
    dal = models.DateField()
    al = models.DateField()
    causale = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    allegato = models.FileField(upload_to="presenze/giustificativi/", blank=True)
    stato = models.CharField(max_length=10, choices=Stato.choices, default=Stato.IN_ATTESA)
    creato_il = models.DateTimeField(auto_now_add=True)
    approvato_il = models.DateTimeField(null=True, blank=True)
    approvato_da = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="giustificativi_approvati")
    class Meta:
        ordering = ["-creato_il"]
    def __str__(self):
        return f"{self.utente} {self.dal} - {self.al}"


class AutodichiarazioneTimbratura(models.Model):
    class Stato(models.TextChoices):
        IN_ATTESA = "ATTESA", "In attesa"
        APPROVATA = "APPROVATA", "Approvata"
        RIFIUTATA = "RIFIUTATA", "Rifiutata"
    gruppo = models.ForeignKey(GruppoPresenze, on_delete=models.PROTECT, related_name="autodichiarazioni")
    utente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="autodichiarazioni_presenza")
    registrata_il = models.DateTimeField()
    verso = models.CharField(max_length=1, choices=[("I", "Entrata"), ("U", "Uscita")])
    motivazione = models.TextField()
    token_approvazione = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    stato = models.CharField(max_length=10, choices=Stato.choices, default=Stato.IN_ATTESA)
    creata_il = models.DateTimeField(auto_now_add=True)
    approvata_il = models.DateTimeField(null=True, blank=True)
    approvata_da = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="autodichiarazioni_approvate")
    timbratura = models.OneToOneField("Timbratura", null=True, blank=True, on_delete=models.SET_NULL, related_name="autodichiarazione")


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
