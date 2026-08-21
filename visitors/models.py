import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from access_control.models import Ufficio


class Visitatore(models.Model):
    nome = models.CharField(
        max_length=100,
        verbose_name="Nome",
    )

    cognome = models.CharField(
        max_length=100,
        verbose_name="Cognome",
    )

    codice_fiscale = models.CharField(
        max_length=16,
        blank=True,
        db_index=True,
        verbose_name="Codice fiscale",
    )

    documento_tipo = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Tipo documento",
    )

    documento_numero = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        verbose_name="Numero documento",
    )

    documento_scadenza = models.DateField(
        null=True,
        blank=True,
        verbose_name="Scadenza documento",
    )

    telefono = models.CharField(
        max_length=50,
        verbose_name="Telefono",
    )

    note = models.TextField(
        blank=True,
        verbose_name="Note",
    )

    creato_il = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creato il",
    )

    class Meta:
        ordering = [
            "cognome",
            "nome",
        ]

        verbose_name = "Visitatore"
        verbose_name_plural = "Visitatori"

    def __str__(self):
        return f"{self.nome} {self.cognome}"


class Badge(models.Model):
    codice = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Codice badge",
    )

    attivo = models.BooleanField(
        default=True,
        verbose_name="Attivo",
    )

    note = models.TextField(
        blank=True,
        verbose_name="Note",
    )

    riservato_rientro = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Riservato per rientro",
    )

    class Meta:
        ordering = ["codice"]

        verbose_name = "Badge"
        verbose_name_plural = "Badge"

    def __str__(self):
        return self.codice

    @property
    def disponibile(self):
        if self.riservato_rientro:
            return False

        return not self.accessi.filter(
            uscita__isnull=True,
        ).exists()


class AccessoVisitatore(models.Model):
    class Stato(models.TextChoices):
        IN_CORSO = "IN", "In corso"
        CHIUSO = "CH", "Chiuso"

    class StatoCoda(models.TextChoices):
        HALL = "HALL", "In attesa nella hall"
        FUORI_UFFICIO = "PORTA", "In attesa fuori dall'ufficio"
        IN_UFFICIO = "UFF", "Dentro l'ufficio"
        VISITA_CONCLUSA = "FINE", "Visita conclusa"
        ANNULLATO = "ANN", "Annullato"

    class TipoAccesso(models.TextChoices):
        RICEVIMENTO = "RIC", "Ricevimento"
        VISITA = "VIS", "Visita"

    tipo_accesso = models.CharField(
        max_length=3,
        choices=TipoAccesso.choices,
        default=TipoAccesso.RICEVIMENTO,
        db_index=True,
        verbose_name="Tipo accesso",
    )

    visitatore = models.ForeignKey(
        Visitatore,
        on_delete=models.PROTECT,
        related_name="accessi",
    )

    ufficio_destinazione = models.ForeignKey(
        Ufficio,
        on_delete=models.PROTECT,
        related_name="visite",
    )

    badge = models.ForeignKey(
        Badge,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="accessi",
        verbose_name="Badge",
    )

    numero_coda = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Numero di coda",
    )

    prefisso_coda = models.CharField(
        max_length=1,
        blank=True,
        editable=False,
        verbose_name="Prefisso della coda",
    )

    token_pubblico = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        verbose_name="Token pubblico ticket",
    )

    token_pubblico_creato_il = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Creazione token pubblico",
    )

    documento_presentato = models.BooleanField(
        default=True,
        verbose_name="Documento presentato",
    )

    accompagnato = models.BooleanField(
        default=False,
        verbose_name="Visitatore accompagnato",
    )

    rientro_prioritario = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Rientro prioritario",
    )

    ingresso = models.DateTimeField(
        default=timezone.now,
        verbose_name="Ingresso nella sede",
    )

    uscita = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Uscita dalla sede",
    )

    stato = models.CharField(
        max_length=2,
        choices=Stato.choices,
        default=Stato.IN_CORSO,
    )

    motivo = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Motivo della visita",
    )

    note = models.TextField(
        blank=True,
        verbose_name="Note della portineria",
    )

    accesso_precedente = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accessi_successivi",
        verbose_name="Accesso precedente",
    )

    stato_coda = models.CharField(
        max_length=5,
        choices=StatoCoda.choices,
        default=StatoCoda.HALL,
        db_index=True,
        verbose_name="Posizione nella coda",
    )

    operatore_assegnato = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accessi_visitatori_gestiti",
        verbose_name="Dipendente assegnato",
    )

    spostato_fuori_ufficio_il = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Arrivo fuori dall'ufficio",
    )

    ingresso_ufficio_il = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Ingresso nell'ufficio",
    )

    visita_conclusa_il = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Conclusione della visita",
    )

    appuntamento = models.OneToOneField(
        "Appuntamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accesso",
        verbose_name="Appuntamento collegato",
    )

    class Meta:
        ordering = ["-ingresso"]
        verbose_name = "Accesso visitatore"
        verbose_name_plural = "Accessi visitatori"

    @property
    def numero_coda_formattato(self):
        if self.numero_coda is None:
            return ""

        prefisso = self.prefisso_coda or (
            self.ufficio_destinazione.prefisso_coda_effettivo
        )
        return f"{prefisso}{self.numero_coda:03d}"

    def genera_token_pubblico(self):
        """Genera il token casuale da inserire nel QR, mai l'id interno."""
        if self.token_pubblico:
            return self.token_pubblico

        self.token_pubblico = secrets.token_urlsafe(32)
        self.token_pubblico_creato_il = timezone.now()
        self.save(update_fields=["token_pubblico", "token_pubblico_creato_il"])
        return self.token_pubblico

    @property
    def prioritario(self):
        return (
            self.rientro_prioritario
            or self.appuntamento_id is not None
        )

    def checkout(self):
        self.uscita = timezone.now()
        self.stato = self.Stato.CHIUSO

        self.save(
            update_fields=[
                "uscita",
                "stato",
            ]
        )

    def __str__(self):
        numero = self.numero_coda_formattato or "-"

        return (
            f"{numero} - "
            f"{self.visitatore} → "
            f"{self.ufficio_destinazione}"
        )

    @property
    def tempo_attesa_hall(self):
        if self.ingresso and self.spostato_fuori_ufficio_il:
            return self.spostato_fuori_ufficio_il - self.ingresso
        return None

    @property
    def tempo_attesa_fuori_ufficio(self):
        if (
                self.spostato_fuori_ufficio_il
                and self.ingresso_ufficio_il
        ):
            return (
                    self.ingresso_ufficio_il
                    - self.spostato_fuori_ufficio_il
            )
        return None

    @property
    def tempo_ricevimento(self):
        if (
                self.ingresso_ufficio_il
                and self.visita_conclusa_il
        ):
            return (
                    self.visita_conclusa_il
                    - self.ingresso_ufficio_il
            )
        return None


class SessioneRicevimento(models.Model):
    ufficio = models.ForeignKey(
        Ufficio,
        on_delete=models.CASCADE,
        related_name="sessioni_ricevimento",
        verbose_name="Ufficio",
    )

    operatore = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessioni_ricevimento",
        verbose_name="Operatore",
    )

    iniziata_il = models.DateTimeField(
        default=timezone.now,
        verbose_name="Inizio ricevimento",
    )

    terminata_il = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fine ricevimento",
    )

    attiva = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Sessione attiva",
    )

    class Meta:
        ordering = [
            "-iniziata_il",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "ufficio",
                    "operatore",
                ],
                condition=models.Q(attiva=True),
                name="unique_active_reception_session",
            )
        ]

        verbose_name = "Sessione di ricevimento"
        verbose_name_plural = "Sessioni di ricevimento"

    def __str__(self):
        return (
            f"{self.operatore} - "
            f"{self.ufficio} - "
            f"{self.iniziata_il:%d/%m/%Y %H:%M}"
        )


class Appuntamento(models.Model):
    class Stato(models.TextChoices):
        PRENOTATO = "PR", "Prenotato"
        CONFERMATO = "CO", "Confermato"
        ESEGUITO = "ES", "Eseguito"
        ANNULLATO = "AN", "Annullato"
        NO_SHOW = "NS", "No show"

    nome_cittadino = models.CharField(
        max_length=100,
    )

    cognome_cittadino = models.CharField(
        max_length=100,
    )

    telefono = models.CharField(
        max_length=50,
        blank=True,
    )

    ufficio = models.ForeignKey(
        Ufficio,
        on_delete=models.CASCADE,
        related_name="appuntamenti",
    )

    data_ora = models.DateTimeField()

    motivo = models.CharField(
        max_length=255,
        blank=True,
    )

    stato = models.CharField(
        max_length=2,
        choices=Stato.choices,
        default=Stato.PRENOTATO,
    )

    creato_il = models.DateTimeField(
        auto_now_add=True,
    )

    def conferma(self):
        self.stato = self.Stato.CONFERMATO
        self.save(
            update_fields=["stato"]
        )

    def annulla(self):
        self.stato = self.Stato.ANNULLATO
        self.save(
            update_fields=["stato"]
        )

    def esegui(self):
        self.stato = self.Stato.ESEGUITO
        self.save(
            update_fields=["stato"]
        )

    def __str__(self):
        return (
            f"{self.nome_cittadino} "
            f"{self.cognome_cittadino} → "
            f"{self.ufficio}"
        )


class EventoAccesso(models.Model):
    class Tipo(models.TextChoices):
        REGISTRAZIONE = "REG", "Registrazione"
        HALL = "HAL", "Ingresso in hall"
        FUORI_PORTA = "POR", "Invio fuori ufficio"
        CHIAMATA = "CHI", "Chiamata"
        INGRESSO_UFFICIO = "ING", "Ingresso ufficio"
        VISITA_CONCLUSA = "FIN", "Visita conclusa"
        USCITA = "USC", "Uscita dalla sede"
        NOTA = "NOT", "Nota"

    accesso = models.ForeignKey(
        AccessoVisitatore,
        on_delete=models.CASCADE,
        related_name="eventi",
        verbose_name="Accesso",
    )

    tipo = models.CharField(
        max_length=3,
        choices=Tipo.choices,
        db_index=True,
        verbose_name="Tipo evento",
    )

    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="Data e ora",
    )

    ufficio = models.ForeignKey(
        Ufficio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventi_accesso",
        verbose_name="Ufficio",
    )

    operatore = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventi_accesso",
        verbose_name="Operatore",
    )

    descrizione = models.TextField(
        blank=True,
        verbose_name="Descrizione",
    )

    dati = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dati aggiuntivi",
    )

    class Meta:
        ordering = [
            "-timestamp",
            "-pk",
        ]

        indexes = [
            models.Index(
                fields=[
                    "tipo",
                    "timestamp",
                ],
                name="idx_evento_tipo_data",
            ),
            models.Index(
                fields=[
                    "ufficio",
                    "tipo",
                    "timestamp",
                ],
                name="idx_evento_uff_tipo",
            ),
        ]

        verbose_name = "Evento accesso"
        verbose_name_plural = "Eventi accesso"

    def __str__(self):
        return (
            f"{self.get_tipo_display()} - "
            f"{self.accesso} - "
            f"{self.timestamp:%d/%m/%Y %H:%M:%S}"
        )


class AmministratoreEnte(models.Model):
    """
    Persona con carica istituzionale dell'Ente.

    L'anagrafica non viene duplicata: nome, cognome e username
    provengono sempre dall'utente Django sincronizzato da
    Active Directory.
    """

    utente = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="profilo_amministratore_ente",
        limit_choices_to={"is_active": True},
        null=True,  # consente l'applicazione della migration su DB esistenti
        blank=False,
        verbose_name="Utente Active Directory",
    )
    carica = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Carica",
    )
    attivo = models.BooleanField(default=True, verbose_name="Attivo")
    ordine = models.PositiveIntegerField(default=0, verbose_name="Ordine")

    class Meta:
        ordering = [
            "ordine",
            "utente__last_name",
            "utente__first_name",
            "utente__username",
        ]
        verbose_name = "Amministratore dell'Ente"
        verbose_name_plural = "Amministratori dell'Ente"

    @property
    def nome_completo(self):
        if not self.utente:
            return "Utente non associato"
        return self.utente.get_full_name() or self.utente.username

    def __str__(self):
        if self.carica:
            return f"{self.nome_completo} - {self.carica}"
        return self.nome_completo

    @property
    def ultimo_transito(self):
        return self.transiti.order_by("-timestamp", "-pk").first()

    @property
    def presente(self):
        ultimo = self.ultimo_transito
        return bool(
            ultimo
            and ultimo.tipo == TransitoAmministratore.Tipo.INGRESSO
        )


class TransitoAmministratore(models.Model):
    class Tipo(models.TextChoices):
        INGRESSO = "IN", "Ingresso"
        USCITA = "OUT", "Uscita"

    amministratore = models.ForeignKey(
        AmministratoreEnte,
        on_delete=models.PROTECT,
        related_name="transiti",
        verbose_name="Amministratore",
    )
    tipo = models.CharField(
        max_length=3,
        choices=Tipo.choices,
        db_index=True,
        verbose_name="Tipo transito",
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="Data e ora",
    )
    operatore = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transiti_amministratori_registrati",
        verbose_name="Registrato da",
    )

    class Meta:
        ordering = ["-timestamp", "-pk"]
        verbose_name = "Transito amministratore"
        verbose_name_plural = "Transiti amministratori"
        indexes = [
            models.Index(
                fields=["amministratore", "timestamp"],
                name="idx_amm_transito_data",
            ),
        ]

    def __str__(self):
        return (
            f"{self.amministratore} - "
            f"{self.get_tipo_display()} - "
            f"{self.timestamp:%d/%m/%Y %H:%M}"
        )
