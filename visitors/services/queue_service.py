from django.db import transaction
from django.utils import timezone

from django.contrib.auth import get_user_model

from visitors.services.capacity_service import CapacityService

User = get_user_model()
from audit.services.audit_service import AuditService
from common.exceptions import BusinessException
from visitors.models import (
    AccessoVisitatore,
    SessioneRicevimento,
)
from django.db.models import Max


class QueueService:
    @staticmethod
    def _audit(
            *,
            user,
            accesso=None,
            descrizione,
            ip_address=None,
    ):
        AuditService.log(
            user=user,
            tipo="ACCESSO",
            oggetto=(
                f"AccessoVisitatore:{accesso.pk}"
                if accesso
                else "GestioneCoda"
            ),
            descrizione=descrizione,
            ip_address=ip_address,
        )

    @staticmethod
    def operatori_attivi(ufficio):
        """
        Restituisce solo gli operatori:
        - con sessione di ricevimento attiva;
        - presenti secondo il sistema esterno;
        - ancora attivi in Django.
        """

        return (
            SessioneRicevimento.objects
            .filter(
                ufficio=ufficio,
                attiva=True,
                terminata_il__isnull=True,
                operatore__is_active=True,
                operatore__stato_presenza=(
                    User.StatoPresenza.PRESENTE
                ),
            )
            .select_related("operatore")
            .order_by("iniziata_il")
        )

    @classmethod
    def capacita_ufficio(cls, ufficio):
        """
        Numero di visitatori che possono essere ricevuti
        contemporaneamente nell'ufficio.
        """

        return cls.operatori_attivi(ufficio).count()

    @classmethod
    def capacita_fuori_ufficio(cls, ufficio):
        """
        La capacità della coda fuori dalla porta coincide
        con il numero degli operatori attivi.
        """

        return cls.capacita_ufficio(ufficio)

    @staticmethod
    def coda_hall(ufficio):
        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                appuntamento__isnull=True,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .order_by(
                "ingresso",
                "numero_coda",
            )
        )

    @staticmethod
    def coda_prioritaria(ufficio):
        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                appuntamento__isnull=False,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .select_related("appuntamento")
            .order_by(
                "appuntamento__data_ora",
                "ingresso",
                "numero_coda",
            )
        )

    @staticmethod
    def coda_fuori_ufficio(ufficio):
        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                stato_coda=(
                    AccessoVisitatore
                    .StatoCoda
                    .FUORI_UFFICIO
                ),
            )
            .order_by(
                "spostato_fuori_ufficio_il",
                "ingresso",
                "numero_coda",
            )
        )

    @staticmethod
    def visitatori_in_ufficio(ufficio):
        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                stato_coda=(
                    AccessoVisitatore.StatoCoda.IN_UFFICIO
                ),
            )
            .select_related("operatore_assegnato")
            .order_by("ingresso_ufficio_il")
        )

    @classmethod
    @transaction.atomic
    def accoda_nuovo_accesso(
            cls,
            accesso,
            operatore=None,
            ip_address=None,
    ):
        """
        Posiziona automaticamente il nuovo visitatore.

        Se esiste un posto disponibile nella coda fuori
        dall'ufficio, il visitatore viene immediatamente
        autorizzato a salire al piano.

        Altrimenti resta nella hall.
        """

        accesso = (
            AccessoVisitatore.objects
            .select_for_update()
            .select_related(
                "ufficio_destinazione",
                "badge",
            )
            .get(pk=accesso.pk)
        )

        ufficio = accesso.ufficio_destinazione

        # La capacità della coda fuori porta coincide
        # con il numero degli sportellisti disponibili.
        capacita_fuori = (
            CapacityService
            .numero_operatori_attivi(
                ufficio
            )
        )

        numero_fuori = (
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                spostato_fuori_ufficio_il__isnull=False,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
                tipo_accesso=(
                    AccessoVisitatore.TipoAccesso.RICEVIMENTO
                ),
            )
            .count()
        )

        posti_fuori = max(
            capacita_fuori - numero_fuori,
            0,
        )

        if posti_fuori > 0:

            accesso.spostato_fuori_ufficio_il = (
                timezone.now()
            )

            accesso.save(
                update_fields=[
                    "spostato_fuori_ufficio_il",
                ]
            )

            cls._audit(
                user=operatore,
                accesso=accesso,
                descrizione=(
                    f"Accesso {accesso.pk}: visitatore "
                    f"autorizzato a recarsi fuori "
                    f"dall'ufficio {ufficio.nome}."
                ),
                ip_address=ip_address,
            )

        else:

            # Rimane nella hall.
            accesso.spostato_fuori_ufficio_il = None

            accesso.save(
                update_fields=[
                    "spostato_fuori_ufficio_il",
                ]
            )

            cls._audit(
                user=operatore,
                accesso=accesso,
                descrizione=(
                    f"Accesso {accesso.pk}: visitatore "
                    f"inserito nella hall per "
                    f"l'ufficio {ufficio.nome}."
                ),
                ip_address=ip_address,
            )

        return accesso

    @classmethod
    @transaction.atomic
    def promuovi_dalla_hall(
            cls,
            ufficio,
            operatore=None,
            ip_address=None,
    ):
        """
        Riempie la coda fuori dall'ufficio fino alla capacità
        consentita.

        Restituisce gli accessi spostati dalla hall.
        """

        capacita = cls.capacita_fuori_ufficio(
            ufficio
        )

        if capacita <= 0:
            return []

        numero_fuori = (
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                stato_coda=(
                    AccessoVisitatore
                    .StatoCoda
                    .FUORI_UFFICIO
                ),
                tipo_accesso=(
                    AccessoVisitatore.TipoAccesso.RICEVIMENTO
                ),
            )
            .count()
        )

        posti_disponibili = max(
            capacita - numero_fuori,
            0,
        )

        if posti_disponibili == 0:
            return []

        # Per ora la selezione è FIFO.
        # Qui inseriremo successivamente la priorità
        # per i visitatori prenotati.
        accessi_da_promuovere = (
            cls._prossimi_dalla_hall(
                ufficio=ufficio,
                limite=posti_disponibili,
            )
        )

        momento = timezone.now()

        for accesso in accessi_da_promuovere:
            accesso.stato_coda = (
                AccessoVisitatore
                .StatoCoda
                .FUORI_UFFICIO
            )

            accesso.spostato_fuori_ufficio_il = momento

            accesso.save(
                update_fields=[
                    "stato_coda",
                    "spostato_fuori_ufficio_il",
                ]
            )

            cls._audit(
                user=operatore,
                accesso=accesso,
                descrizione=(
                    f"Accesso {accesso.pk} spostato dalla hall "
                    f"alla coda fuori dall'ufficio "
                    f"{ufficio.nome}."
                ),
                ip_address=ip_address,
            )

        return accessi_da_promuovere

    @staticmethod
    def _prossimi_dalla_hall(
            ufficio,
            limite,
    ):
        """
        Seleziona prima i prenotati arrivati,
        poi i visitatori ordinari.
        """

        prioritari = list(
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                appuntamento__isnull=False,
                tipo_accesso=(
                    AccessoVisitatore.TipoAccesso.RICEVIMENTO
                ),
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .order_by(
                "appuntamento__data_ora",
                "ingresso",
                "numero_coda",
            )[:limite]
        )

        posti_residui = limite - len(prioritari)

        if posti_residui <= 0:
            return prioritari

        ordinari = list(
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                appuntamento__isnull=True,
                tipo_accesso=(
                    AccessoVisitatore.TipoAccesso.RICEVIMENTO
                ),
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .order_by(
                "ingresso",
                "numero_coda",
            )[:posti_residui]
        )

        return prioritari + ordinari

    @classmethod
    @transaction.atomic
    def avvia_ricevimento(
            cls,
            *,
            ufficio,
            operatore,
            ip_address=None,
    ):
        """
        Avvia o recupera la sessione attiva dell'operatore.
        Dopo l'avvio riempie automaticamente la coda
        fuori dalla porta.
        """

        sessione, created = (
            SessioneRicevimento.objects
            .get_or_create(
                ufficio=ufficio,
                operatore=operatore,
                attiva=True,
                defaults={
                    "iniziata_il": timezone.now(),
                },
            )
        )

        if created:
            cls._audit(
                user=operatore,
                descrizione=(
                    f"Avvio ricevimento presso "
                    f"l'ufficio {ufficio.nome}."
                ),
                ip_address=ip_address,
            )

        cls.promuovi_dalla_hall(
            ufficio=ufficio,
            operatore=operatore,
            ip_address=ip_address,
        )

        return sessione

    @classmethod
    @transaction.atomic
    def termina_ricevimento(
            cls,
            *,
            ufficio,
            operatore,
            ip_address=None,
    ):
        """
        Termina la sessione dell'operatore.

        Non è possibile terminarla mentre l'operatore
        ha ancora un visitatore dentro l'ufficio.
        """

        visita_in_corso = (
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                operatore_assegnato=operatore,
                uscita__isnull=True,
                stato_coda=(
                    AccessoVisitatore.StatoCoda.IN_UFFICIO
                ),
            )
            .exists()
        )

        if visita_in_corso:
            raise BusinessException(
                "Non è possibile terminare il ricevimento: "
                "l'operatore ha ancora una visita in corso."
            )

        sessione = (
            SessioneRicevimento.objects
            .select_for_update()
            .filter(
                ufficio=ufficio,
                operatore=operatore,
                attiva=True,
                terminata_il__isnull=True,
            )
            .first()
        )

        if sessione is None:
            raise BusinessException(
                "Non risulta una sessione di ricevimento attiva."
            )

        sessione.attiva = False
        sessione.terminata_il = timezone.now()

        sessione.save(
            update_fields=[
                "attiva",
                "terminata_il",
            ]
        )

        cls._audit(
            user=operatore,
            descrizione=(
                f"Termine ricevimento presso "
                f"l'ufficio {ufficio.nome}."
            ),
            ip_address=ip_address,
        )

        return sessione

    @classmethod
    @transaction.atomic
    def prendi_prossimo(
            cls,
            *,
            ufficio,
            operatore,
            ip_address=None,
    ):
        """
        Fa entrare il primo visitatore presente fuori
        dall'ufficio e lo assegna al dipendente.

        Dopo l'ingresso, promuove automaticamente il primo
        visitatore dalla hall alla porta.
        """

        sessione_attiva = (
            SessioneRicevimento.objects
            .filter(
                ufficio=ufficio,
                operatore=operatore,
                attiva=True,
                terminata_il__isnull=True,
            )
            .exists()
        )

        if not sessione_attiva:
            raise BusinessException(
                "Avviare il ricevimento prima di chiamare "
                "un visitatore."
            )

        visita_corrente = (
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                operatore_assegnato=operatore,
                uscita__isnull=True,
                stato_coda=(
                    AccessoVisitatore.StatoCoda.IN_UFFICIO
                ),
            )
            .exists()
        )

        if visita_corrente:
            raise BusinessException(
                "L'operatore sta già ricevendo un visitatore."
            )

        # Per ora FIFO.
        # In seguito questo ordinamento verrà modificato
        # per privilegiare i prenotati presenti nella fascia.
        accesso = (
            AccessoVisitatore.objects
            .select_for_update()
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                stato_coda=(
                    AccessoVisitatore
                    .StatoCoda
                    .FUORI_UFFICIO
                ),
            )
            .order_by(
                "spostato_fuori_ufficio_il",
                "ingresso",
                "numero_coda",
            )
            .first()
        )

        if accesso is None:
            raise BusinessException(
                "Non ci sono visitatori in attesa "
                "fuori dall'ufficio."
            )

        accesso.stato_coda = (
            AccessoVisitatore.StatoCoda.IN_UFFICIO
        )

        accesso.operatore_assegnato = operatore
        accesso.ingresso_ufficio_il = timezone.now()

        accesso.save(
            update_fields=[
                "stato_coda",
                "operatore_assegnato",
                "ingresso_ufficio_il",
            ]
        )

        cls._audit(
            user=operatore,
            accesso=accesso,
            descrizione=(
                f"Accesso {accesso.pk} entrato "
                f"nell'ufficio {ufficio.nome}; "
                f"operatore assegnato: {operatore}."
            ),
            ip_address=ip_address,
        )

        # Il passaggio PORTA -> UFFICIO libera un posto
        # davanti alla porta.
        cls.promuovi_dalla_hall(
            ufficio=ufficio,
            operatore=operatore,
            ip_address=ip_address,
        )

        return accesso

    @classmethod
    @transaction.atomic
    def concludi_visita(
            cls,
            *,
            accesso,
            operatore,
            ip_address=None,
    ):
        """
        Conclude la visita presso l'ufficio.

        Non chiude l'accesso all'edificio: la portineria
        dovrà successivamente registrare l'uscita.
        """

        accesso = (
            AccessoVisitatore.objects
            .select_for_update()
            .select_related("ufficio_destinazione")
            .get(pk=accesso.pk)
        )

        if (
                accesso.stato_coda
                != AccessoVisitatore.StatoCoda.IN_UFFICIO
        ):
            raise BusinessException(
                "La visita non risulta attualmente in corso."
            )

        if accesso.operatore_assegnato_id != operatore.pk:
            raise BusinessException(
                "La visita è assegnata a un altro operatore."
            )

        accesso.stato_coda = (
            AccessoVisitatore.StatoCoda.VISITA_CONCLUSA
        )

        accesso.visita_conclusa_il = timezone.now()

        accesso.save(
            update_fields=[
                "stato_coda",
                "visita_conclusa_il",
            ]
        )

        cls._audit(
            user=operatore,
            accesso=accesso,
            descrizione=(
                f"Visita conclusa presso l'ufficio "
                f"{accesso.ufficio_destinazione.nome}; "
                f"operatore: {operatore}."
            ),
            ip_address=ip_address,
        )

        return accesso

    @staticmethod
    def prossimo_numero(ufficio):
        """
        Restituisce il successivo numero di coda per
        l'ufficio nella giornata corrente.

        Il progressivo riparte da 1 ogni giorno
        e per ciascun ufficio.
        """

        oggi = timezone.localdate()

        ultimo_numero = (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso__date=oggi,
            )
            .aggregate(
                massimo=Max("numero_coda"),
            )
            .get("massimo")
        )

        return (ultimo_numero or 0) + 1
