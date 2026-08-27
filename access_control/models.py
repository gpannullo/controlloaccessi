from string import ascii_uppercase

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import Group


class Ufficio(models.Model):
    """
    Rappresenta un ufficio dell'Ente.
    """

    codice = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Codice"
    )

    prefisso_coda = models.CharField(
        max_length=2,
        blank=True,
        verbose_name="Prefisso coda",
        help_text=(
            "Generato automaticamente se non indicato (A, B, …, poi AB, AC, …). "
            "Impostare un prefisso diverso per ogni ufficio."
        ),
    )

    nome = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nome"
    )

    riceve_pubblico = models.BooleanField(
        default=True,
        verbose_name="Riceve il pubblico"
    )

    attivo = models.BooleanField(
        default=True
    )

    piano = models.CharField(
        max_length=20,
        blank=True
    )

    stanza = models.CharField(
        max_length=20,
        blank=True
    )

    telefono = models.CharField(
        max_length=50,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    responsabile = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uffici_responsabili"
    )

    tempo_medio_servizio_default = models.PositiveSmallIntegerField(
        default=20,
        verbose_name="Tempo medio predefinito della visita (minuti)",
        help_text=(
            "Utilizzato quando non esistono ancora dati storici "
            "sufficienti per calcolare la durata media."
        ),
    )

    overbooking = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Tolleranza overbooking",
        help_text=(
            "Numero di visitatori che il sistema può accettare "
            "oltre la capacità stimata."
        ),
    )

    numero_visite_media = models.PositiveSmallIntegerField(
        default=50,
        verbose_name="Visite considerate per la media",
        help_text=(
            "Numero massimo di visite concluse utilizzate "
            "per calcolare il tempo medio di servizio."
        ),
    )

    note = models.TextField(
        blank=True
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Ufficio"
        verbose_name_plural = "Uffici"

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        self.prefisso_coda = (self.prefisso_coda or "").strip().upper()
        if self.prefisso_coda and (
            not self.prefisso_coda.isalpha()
            or len(self.prefisso_coda) not in {1, 2}
            or (
                len(self.prefisso_coda) == 2
                and self.prefisso_coda[0] == self.prefisso_coda[1]
            )
        ):
            raise ValidationError(
                {"prefisso_coda": "Indicare una o due lettere diverse (es. A oppure AB)."}
            )
        if self.prefisso_coda and Ufficio.objects.exclude(pk=self.pk).filter(
            prefisso_coda__iexact=self.prefisso_coda
        ).exists():
            raise ValidationError(
                {"prefisso_coda": "Questo prefisso è già assegnato a un altro ufficio."}
            )

    def _genera_prefisso_coda(self):
        usati = {
            valore.upper()
            for valore in Ufficio.objects.exclude(pk=self.pk)
            .exclude(prefisso_coda="")
            .values_list("prefisso_coda", flat=True)
        }
        for lettera in ascii_uppercase:
            if lettera not in usati:
                return lettera
        for prima in ascii_uppercase:
            for seconda in ascii_uppercase:
                prefisso = f"{prima}{seconda}"
                if prima != seconda and prefisso not in usati:
                    return prefisso
        raise ValidationError(
            {"prefisso_coda": "Non sono disponibili altri prefissi per gli uffici."}
        )

    def save(self, *args, **kwargs):
        self.prefisso_coda = (self.prefisso_coda or "").strip().upper()
        if not self.prefisso_coda:
            self.prefisso_coda = self._genera_prefisso_coda()
        return super().save(*args, **kwargs)

    @property
    def prefisso_coda_effettivo(self):
        """Prefisso usato dai nuovi ticket.

        Il ripiego sul codice mantiene operative le configurazioni
        precedenti, ma ogni ufficio deve essere configurato esplicitamente.
        """
        return (self.prefisso_coda or self.codice[:1] or "A").upper()

    @property
    def numero_dipendenti(self):
        totale = 0

        for gruppo in self.gruppi.select_related("django_group"):
            totale += gruppo.django_group.user_set.count()

        return totale


class GruppoOrganizzativo(models.Model):
    class Tipo(models.TextChoices):
        ORGANIZZATIVO = "ORG", "Organizzativo"
        TECNICO = "TEC", "Tecnico"
        SICUREZZA = "SEC", "Sicurezza"

    nome = models.CharField(
        max_length=150,
        unique=True
    )

    directory_name = models.CharField(
        max_length=150,
        unique=True
    )

    django_group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="gruppi_organizzativi"
    )

    tipo = models.CharField(
        max_length=3,
        choices=Tipo.choices,
        default=Tipo.TECNICO
    )

    ufficio = models.ForeignKey(
        Ufficio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gruppi"
    )

    directory_sid = models.CharField(
        max_length=255,
        unique=True,
        editable=False,
        null=True,
        blank=True,
        verbose_name="SID gruppo Active Directory"
    )

    sincronizzato = models.BooleanField(default=True)

    attivo = models.BooleanField(default=True)

    note = models.TextField(blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Gruppo Organizzativo"
        verbose_name_plural = "Gruppi Organizzativi"

    def __str__(self):
        return self.nome


class CalendarioApertura(models.Model):
    class Giorno(models.IntegerChoices):
        LUNEDI = 0, "Lunedì"
        MARTEDI = 1, "Martedì"
        MERCOLEDI = 2, "Mercoledì"
        GIOVEDI = 3, "Giovedì"
        VENERDI = 4, "Venerdì"
        SABATO = 5, "Sabato"
        DOMENICA = 6, "Domenica"

    ufficio = models.ForeignKey(
        Ufficio,
        on_delete=models.CASCADE,
        related_name="aperture"
    )

    giorno = models.IntegerField(
        choices=Giorno.choices
    )

    ora_inizio = models.TimeField()

    ora_fine = models.TimeField()

    su_appuntamento = models.BooleanField(
        default=False
    )

    class Meta:
        ordering = [
            "giorno",
            "ora_inizio",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "ufficio",
                    "giorno",
                    "ora_inizio",
                    "ora_fine",
                ],
                name="uk_calendario_apertura",
            )
        ]

    def __str__(self):
        return (
            f"{self.ufficio} - "
            f"{self.get_giorno_display()}"
        )
