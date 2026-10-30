from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

class Sottocommissione(models.Model):
    nome = models.CharField(max_length=150); codice = models.CharField(max_length=30, unique=True); attiva = models.BooleanField(default=True)
    class Meta: ordering = ["nome"]; verbose_name = "Sottocommissione"; verbose_name_plural = "Sottocommissioni"
    def __str__(self): return f"{self.codice} - {self.nome}"

class Comune(models.Model):
    sottocommissione = models.ForeignKey(Sottocommissione, on_delete=models.CASCADE, related_name="comuni")
    nome = models.CharField(max_length=150); codice_istat = models.CharField(max_length=20, blank=True); attivo = models.BooleanField(default=True)
    class Meta:
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(fields=["sottocommissione", "nome"], name="sec_comune_sottocommissione_nome")]
    def __str__(self): return self.nome

class AccountSEC(models.Model):
    comune = models.ForeignKey(Comune, on_delete=models.CASCADE, related_name="account")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account_sec")
    solo_locale = models.BooleanField(default=True, editable=False); attivo = models.BooleanField(default=True)
    class Meta: verbose_name = "Account SEC"; verbose_name_plural = "Account SEC"
    def save(self, *args, **kwargs): self.solo_locale = True; super().save(*args, **kwargs)
    def __str__(self): return f"{self.user.get_full_name() or self.user.username} - {self.comune}"

class Verbale(models.Model):
    class Tipologia(models.TextChoices): DINAMICA = "DINAMICA", "Dinamica"; SEMESTRALE = "SEMESTRALE", "Semestrale"
    class Tornata(models.TextChoices): PRIMA = "PRIMA", "Prima tornata"; SECONDA = "SECONDA", "Seconda tornata"; TERZA = "TERZA", "Terza tornata"; ALTRA = "ALTRA", "Altra tornata"
    comune = models.ForeignKey(Comune, on_delete=models.CASCADE, related_name="verbali")
    tipologia = models.CharField(max_length=12, choices=Tipologia.choices); tornata = models.CharField(max_length=12, choices=Tornata.choices, blank=True)
    numero = models.PositiveIntegerField(validators=[MinValueValidator(1)]); data_verbale = models.DateField()
    iscritti_precedenti = models.PositiveIntegerField(default=0); aggiunti = models.PositiveIntegerField(default=0); cancellati = models.PositiveIntegerField(default=0); elettori = models.PositiveIntegerField(default=0, editable=False)
    pdf = models.FileField(upload_to="sec/verbali/%Y/%m/", validators=[FileExtensionValidator(["pdf"])])
    caricato_da = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="verbali_sec"); creato_il = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-data_verbale", "-numero"]; verbose_name = "Verbale elettorale"; verbose_name_plural = "Verbali elettorali"
    def save(self, *args, **kwargs):
        self.elettori = max(0, self.iscritti_precedenti + self.aggiunti - self.cancellati)
        if self.tipologia == self.Tipologia.SEMESTRALE: self.tornata = ""
        super().save(*args, **kwargs)
    def __str__(self): return f"Verbale {self.numero}/{self.data_verbale:%d-%m-%Y} - {self.comune}"
