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
