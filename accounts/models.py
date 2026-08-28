from django.contrib.auth.models import AbstractUser
from django.db import models

from access_control.models import Ufficio


class CustomUser(AbstractUser):
    """
    Estensione del modello utente Django.

    Tutte le informazioni organizzative (ufficio, gruppi, ecc.)
    provengono dalla Directory Aziendale e NON vengono salvate qui.
    """

    class StatoPresenza(models.TextChoices):
        NON_VERIFICATA = "UNK", "Non verificata"
        PRESENTE = "PRE", "Presente"
        ASSENTE = "ASS", "Assente"

    class TipoAttivita(models.TextChoices):
        SPORTELLISTA = "SPO", "Sportellista"
        AMMINISTRATIVISTA = "AMM", "Amministrativista"
        TECNICO = "TEC", "Tecnico"
        DISUSO = "DIS", "Disuso"

    tipo_attivita = models.CharField(
        max_length=3,
        choices=TipoAttivita.choices,
        default=TipoAttivita.AMMINISTRATIVISTA,
        db_index=True,
        verbose_name="Tipo di attività",
    )

    email_aggiuntiva = models.EmailField(blank=True, verbose_name="E-mail aggiuntiva")
    telefono_aggiuntivo = models.CharField(max_length=50, blank=True, verbose_name="Telefono aggiuntivo")
    scadenza_password = models.DateTimeField(null=True, blank=True, editable=False)
    password_senza_scadenza = models.BooleanField(default=False, editable=False)
    email_personale = models.EmailField(blank=True, editable=False)
    cellulare_personale = models.CharField(max_length=50, blank=True, editable=False)
    badge = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Badge presenze",
        help_text="Codice riportato nel file delle timbrature.",
    )

    livello_sicurezza = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Livello di sicurezza"
    )

    stato_presenza = models.CharField(
        max_length=3,
        choices=StatoPresenza.choices,
        default=StatoPresenza.NON_VERIFICATA,
        db_index=True,
        verbose_name="Stato presenza",
    )

    presenza_verificata_il = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Ultima verifica presenza",
    )

    presenza_fonte = models.CharField(
        max_length=100,
        blank=True,
        editable=False,
        verbose_name="Fonte della presenza",
    )

    class Meta:
        verbose_name = "Utente"
        verbose_name_plural = "Utenti"

    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"

    @property
    def presente_in_servizio(self):
        return (
                self.stato_presenza
                == self.StatoPresenza.PRESENTE
        )

    @property
    def puo_ricevere_pubblico(self):
        return (
            self.tipo_attivita
            == self.TipoAttivita.SPORTELLISTA
        )

    @property
    def password_info(self):
        """Compatibilità per la tabella utenti: dati sincronizzati localmente."""
        return {
            "password_never_expires": self.password_senza_scadenza,
            "password_expiry": self.scadenza_password,
        }


class SnapshotPresenzaUfficio(models.Model):
    """
    Fotografia della presenza dei dipendenti di un ufficio
    in un determinato momento.

    Serve per costruire statistiche storiche:
    - dipendenti medi presenti;
    - sportellisti medi presenti;
    - capacità media dell'ufficio.
    """

    ufficio = models.ForeignKey(
        Ufficio,
        on_delete=models.CASCADE,
        related_name="snapshot_presenze",
        verbose_name="Ufficio",
    )

    rilevato_il = models.DateTimeField(
        db_index=True,
        verbose_name="Rilevato il",
    )

    dipendenti_presenti = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Dipendenti presenti",
    )

    sportellisti_presenti = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Sportellisti presenti",
    )

    dipendenti_totali = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Dipendenti assegnati",
    )

    sportellisti_totali = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Sportellisti assegnati",
    )

    class Meta:
        ordering = [
            "-rilevato_il",
        ]

        indexes = [
            models.Index(
                fields=[
                    "ufficio",
                    "rilevato_il",
                ],
                name="idx_presenza_ufficio_data",
            ),
        ]

        verbose_name = "Snapshot presenza ufficio"
        verbose_name_plural = "Snapshot presenze uffici"

    def __str__(self):
        return (
            f"{self.ufficio} - "
            f"{self.rilevato_il:%d/%m/%Y %H:%M} - "
            f"{self.dipendenti_presenti} presenti"
        )
