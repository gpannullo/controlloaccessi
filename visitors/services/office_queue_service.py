from django.db import transaction
from django.db.models import Q, Max
from django.db.models.functions import Coalesce
from datetime import timedelta
from django.utils import timezone

from audit.services.audit_service import AuditService
from common.exceptions import BusinessException
from visitors.models import AccessoVisitatore, EventoAccesso


class OfficeQueueService:
    """Gestisce le operazioni dei dipendenti sulle code dei visitatori."""

    @staticmethod
    def _ordine_hall(prenotati=False):
        fields = ['reinserito_hall_il']
        if prenotati:
            fields.append('appuntamento__data_ora')
        return Coalesce(*fields, 'ingresso')

    @classmethod
    @transaction.atomic
    def salta_non_presente(cls, *, accesso_id, ufficio, operatore, ip_address=None):
        accesso = AccessoVisitatore.objects.select_for_update(of=('self',)).get(pk=accesso_id, ufficio_destinazione=ufficio)
        if (accesso.uscita or accesso.visita_conclusa_il or not accesso.ingresso_ufficio_il
                or accesso.operatore_assegnato_id != operatore.pk):
            raise BusinessException('Puoi saltare soltanto il visitatore attualmente chiamato da te.')
        now = timezone.now()
        peers = AccessoVisitatore.objects.filter(ufficio_destinazione=ufficio, uscita__isnull=True,
            visita_conclusa_il__isnull=True, ingresso_ufficio_il__isnull=True,
            rientro_prioritario=accesso.rientro_prioritario,
            appuntamento__isnull=accesso.appuntamento_id is None)
        last = peers.aggregate(last=Max(cls._ordine_hall(bool(accesso.appuntamento_id))))['last']
        order = max(now, last + timedelta(microseconds=1)) if last else now
        previous = {'chiamata_il': accesso.ingresso_ufficio_il.isoformat(),
                    'fuori_ufficio_il': accesso.spostato_fuori_ufficio_il.isoformat() if accesso.spostato_fuori_ufficio_il else None}
        accesso.reinserito_hall_il = order
        accesso.ingresso_ufficio_il = None
        accesso.spostato_fuori_ufficio_il = None
        accesso.operatore_assegnato = None
        accesso.stato_coda = AccessoVisitatore.StatoCoda.HALL
        accesso.save(update_fields=['reinserito_hall_il', 'ingresso_ufficio_il', 'spostato_fuori_ufficio_il', 'operatore_assegnato', 'stato_coda'])
        description = 'Visitatore non presente alla chiamata: reinserito in fondo alla hall della propria categoria.'
        EventoAccesso.objects.create(accesso=accesso, tipo=EventoAccesso.Tipo.HALL, timestamp=now,
            ufficio=ufficio, operatore=operatore, descrizione=description, dati={'azione':'salto_non_presente', **previous})
        cls._audit(user=operatore, accesso=accesso, descrizione=description, ip_address=ip_address)
        # Nessun ingresso diretto dalla hall: il successivo deve essere già fuori porta.
        if cls.coda_fuori_ufficio(ufficio).filter(Q(rientro_prioritario=True) | Q(appuntamento__isnull=False) | Q(tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO)).exists():
            cls.fai_entrare_prossimo(ufficio=ufficio, operatore=operatore, ip_address=ip_address, escludi_promozione=accesso.pk)
        else:
            cls.promuovi_dalla_hall(ufficio=ufficio, operatore=operatore, ip_address=ip_address, escludi_accesso=accesso.pk)
        return accesso

    @staticmethod
    def _audit(
        *,
        user,
        accesso,
        descrizione,
        ip_address=None,
    ):
        AuditService.log(
            user=user,
            tipo="ACCESSO",
            oggetto=f"AccessoVisitatore:{accesso.pk}",
            descrizione=descrizione,
            ip_address=ip_address,
        )

    @staticmethod
    def visita_corrente(ufficio, operatore):
        """
        Restituisce l'eventuale visitatore attualmente
        ricevuto dall'operatore.
        """

        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                operatore_assegnato=operatore,
                ingresso_ufficio_il__isnull=False,
                visita_conclusa_il__isnull=True,
                uscita__isnull=True,
            )
            .select_related(
                "visitatore",
                "badge",
                "appuntamento",
            )
            .first()
        )

    @staticmethod
    def coda_fuori_ufficio(ufficio):
        """
        Visitatori già inviati al piano ma non ancora
        entrati nell'ufficio.
        """

        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                spostato_fuori_ufficio_il__isnull=False,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .select_related(
                "visitatore",
                "badge",
                "appuntamento",
            )
            .order_by(
                "spostato_fuori_ufficio_il",
                "ingresso",
                "numero_coda",
            )
        )

    @staticmethod
    def coda_prioritaria(ufficio):
        """Rientri prioritari e appuntamenti ancora nella hall."""
        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .filter(
                Q(rientro_prioritario=True)
                | Q(appuntamento__isnull=False)
            )
            .select_related("visitatore", "badge", "appuntamento")
            .order_by(
                "-rientro_prioritario",
                Coalesce('reinserito_hall_il', 'appuntamento__data_ora', 'ingresso'),
                "numero_coda",
            )
        )

    @staticmethod
    def coda_hall(ufficio):
        """
        Visitatori non prenotati ancora in attesa
        nella hall.
        """

        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                appuntamento__isnull=True,
                rientro_prioritario=False,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .select_related(
                "visitatore",
                "badge",
            )
            .order_by(
                Coalesce('reinserito_hall_il', 'ingresso'),
                "numero_coda",
            )
        )

    @staticmethod
    def visite_in_corso_ufficio(ufficio):
        """
        Visitatori già dentro l'ufficio e assegnati
        agli altri dipendenti.
        """

        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                ingresso_ufficio_il__isnull=False,
                visita_conclusa_il__isnull=True,
            )
            .select_related(
                "visitatore",
                "badge",
                "operatore_assegnato",
            )
            .order_by("ingresso_ufficio_il")
        )

    @classmethod
    @transaction.atomic
    def promuovi_dalla_hall(
        cls,
        *,
        ufficio,
        numero_posti=1,
        operatore=None,
        ip_address=None,
        escludi_accesso=None,
    ):
        """
        Sposta automaticamente dalla hall alla porta soltanto
        RICEVIMENTI e APPUNTAMENTI.

        Le VISITE non vengono mai promosse automaticamente:
        richiedono l'autorizzazione esplicita di un dipendente.
        """

        if numero_posti <= 0:
            return []

        rientri = list(
            AccessoVisitatore.objects
            .select_for_update(of=('self',))
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                rientro_prioritario=True,
                spostato_fuori_ufficio_il__isnull=True,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .exclude(pk=escludi_accesso)
            .order_by(cls._ordine_hall(), "numero_coda", "pk")[:numero_posti]
        )

        posti_residui = numero_posti - len(rientri)
        prioritari = []
        if posti_residui > 0:
            prioritari = list(
                AccessoVisitatore.objects
                .select_for_update(of=('self',))
                .filter(
                    ufficio_destinazione=ufficio,
                    uscita__isnull=True,
                    rientro_prioritario=False,
                    appuntamento__isnull=False,
                    tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO,
                    spostato_fuori_ufficio_il__isnull=True,
                    ingresso_ufficio_il__isnull=True,
                    visita_conclusa_il__isnull=True,
                )
                .exclude(pk=escludi_accesso)
                .order_by(
                    cls._ordine_hall(True), "ingresso", "numero_coda", "pk"
                )[:posti_residui]
            )

        posti_residui -= len(prioritari)
        ordinari = []
        if posti_residui > 0:
            ordinari = list(
                AccessoVisitatore.objects
                .select_for_update(of=('self',))
                .filter(
                    ufficio_destinazione=ufficio,
                    uscita__isnull=True,
                    rientro_prioritario=False,
                    appuntamento__isnull=True,
                    tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO,
                    spostato_fuori_ufficio_il__isnull=True,
                    ingresso_ufficio_il__isnull=True,
                    visita_conclusa_il__isnull=True,
                )
                .exclude(pk=escludi_accesso)
                .order_by(cls._ordine_hall(), "numero_coda", "pk")[:posti_residui]
            )

        accessi = rientri + prioritari + ordinari
        momento = timezone.now()

        for accesso in accessi:
            accesso.spostato_fuori_ufficio_il = momento
            accesso.stato_coda = (
                AccessoVisitatore.StatoCoda.FUORI_UFFICIO
            )

            accesso.save(
                update_fields=[
                    "spostato_fuori_ufficio_il",
                    "stato_coda",
                ]
            )

            cls._audit(
                user=operatore,
                accesso=accesso,
                descrizione=(
                    f"Visitatore spostato dalla hall alla coda "
                    f"fuori dall'ufficio {ufficio.nome}."
                ),
                ip_address=ip_address,
            )

        return accessi

    @classmethod
    @transaction.atomic
    def autorizza_salita_visita(
        cls,
        *,
        accesso,
        ufficio,
        operatore,
        ip_address=None,
    ):
        """
        Autorizza esplicitamente una VISITA a lasciare la hall
        e recarsi fuori dalla porta dell'ufficio.

        La visita non consuma la capacità automatica riservata
        a ricevimento/appuntamenti.
        """

        accesso = (
            AccessoVisitatore.objects
            .select_for_update(of=('self',))
            .get(
                pk=accesso.pk,
                ufficio_destinazione=ufficio,
            )
        )

        if (
            accesso.tipo_accesso
            != AccessoVisitatore.TipoAccesso.VISITA
        ):
            raise BusinessException(
                "L'accesso selezionato non è una visita."
            )

        if accesso.uscita is not None:
            raise BusinessException(
                "L'accesso risulta già chiuso."
            )

        if accesso.visita_conclusa_il is not None:
            raise BusinessException(
                "La visita risulta già conclusa."
            )

        if accesso.ingresso_ufficio_il is not None:
            raise BusinessException(
                "Il visitatore risulta già entrato nell'ufficio."
            )

        if accesso.spostato_fuori_ufficio_il is not None:
            raise BusinessException(
                "Il visitatore è già stato autorizzato a salire."
            )

        momento = timezone.now()
        accesso.spostato_fuori_ufficio_il = momento
        accesso.stato_coda = (
            AccessoVisitatore.StatoCoda.FUORI_UFFICIO
        )
        accesso.save(
            update_fields=[
                "spostato_fuori_ufficio_il",
                "stato_coda",
            ]
        )

        cls._audit(
            user=operatore,
            accesso=accesso,
            descrizione=(
                f"Visita autorizzata a lasciare la hall e "
                f"recarsi fuori dall'ufficio {ufficio.nome}."
            ),
            ip_address=ip_address,
        )

        return accesso

    @classmethod
    def _verifica_operatore_libero(
        cls,
        *,
        ufficio,
        operatore,
    ):
        visita_corrente = (
            AccessoVisitatore.objects
            .select_for_update(of=('self',))
            .filter(
                ufficio_destinazione=ufficio,
                operatore_assegnato=operatore,
                ingresso_ufficio_il__isnull=False,
                visita_conclusa_il__isnull=True,
                uscita__isnull=True,
            )
            .exists()
        )

        if visita_corrente:
            raise BusinessException(
                "Hai già un visitatore in ricevimento."
            )

    @classmethod
    def _fai_entrare_accesso(
        cls,
        *,
        accesso,
        ufficio,
        operatore,
        ip_address=None,
        promuovi_ricevimento=False,
        escludi_promozione=None,
    ):
        momento = timezone.now()

        accesso.operatore_assegnato = operatore
        accesso.ingresso_ufficio_il = momento
        accesso.stato_coda = (
            AccessoVisitatore.StatoCoda.IN_UFFICIO
        )

        accesso.save(
            update_fields=[
                "operatore_assegnato",
                "ingresso_ufficio_il",
                "stato_coda",
            ]
        )

        EventoAccesso.objects.create(
            accesso=accesso,
            tipo=EventoAccesso.Tipo.CHIAMATA,
            timestamp=momento,
            ufficio=ufficio,
            operatore=operatore,
            descrizione=(
                f"Chiamato il numero "
                f"{accesso.numero_coda_formattato} "
                f"per l'ufficio {ufficio.nome}."
            ),
            dati={
                "numero_coda": accesso.numero_coda_formattato,
                "badge": (
                    accesso.badge.codice
                    if accesso.badge
                    else None
                ),
                "tipo_accesso": accesso.tipo_accesso,
            },
        )

        cls._audit(
            user=operatore,
            accesso=accesso,
            descrizione=(
                f"Visitatore entrato nell'ufficio {ufficio.nome}; "
                f"operatore assegnato: {operatore}."
            ),
            ip_address=ip_address,
        )

        if promuovi_ricevimento:
            cls.promuovi_dalla_hall(
                ufficio=ufficio,
                numero_posti=1,
                operatore=operatore,
                ip_address=ip_address,
                escludi_accesso=escludi_promozione,
            )

        return accesso

    @classmethod
    @transaction.atomic
    def fai_entrare_prossimo(
        cls,
        *,
        ufficio,
        operatore,
        ip_address=None,
        escludi_promozione=None,
    ):
        """
        Fa entrare il prossimo RICEVIMENTO, dando precedenza
        agli appuntamenti. Le VISITE restano fuori finché il
        dipendente non usa l'azione esplicita dedicata.
        """

        cls._verifica_operatore_libero(
            ufficio=ufficio,
            operatore=operatore,
        )

        base = (
            AccessoVisitatore.objects
            .select_for_update(of=('self',))
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                spostato_fuori_ufficio_il__isnull=False,
                ingresso_ufficio_il__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .filter(
                Q(rientro_prioritario=True)
                | Q(appuntamento__isnull=False)
                | Q(tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO)
            )
        )

        accesso = (
            base
            .filter(rientro_prioritario=True)
            .order_by(
                "spostato_fuori_ufficio_il",
                "ingresso",
                "numero_coda",
            )
            .first()
        )

        if accesso is None:
            accesso = (
                base
                .filter(
                    rientro_prioritario=False,
                    appuntamento__isnull=False,
                )
                .order_by(
                    cls._ordine_hall(True),
                    "spostato_fuori_ufficio_il",
                    "ingresso",
                    "numero_coda",
                )
                .first()
            )

        if accesso is None:
            accesso = (
                base
                .filter(rientro_prioritario=False, appuntamento__isnull=True)
                .order_by(
                    "spostato_fuori_ufficio_il",
                    "ingresso",
                    "numero_coda",
                )
                .first()
            )

        if accesso is None:
            raise BusinessException(
                "Non ci sono ricevimenti in attesa fuori dall'ufficio."
            )

        return cls._fai_entrare_accesso(
            accesso=accesso,
            ufficio=ufficio,
            operatore=operatore,
            ip_address=ip_address,
            promuovi_ricevimento=True,
            escludi_promozione=escludi_promozione,
        )

    @classmethod
    @transaction.atomic
    def fai_entrare_visitatore(
        cls,
        *,
        accesso,
        ufficio,
        operatore,
        ip_address=None,
    ):
        """Fa entrare una specifica VISITA già fuori porta."""

        cls._verifica_operatore_libero(
            ufficio=ufficio,
            operatore=operatore,
        )

        accesso = (
            AccessoVisitatore.objects
            .select_for_update(of=('self',))
            .get(
                pk=accesso.pk,
                ufficio_destinazione=ufficio,
            )
        )

        if (
            accesso.tipo_accesso
            != AccessoVisitatore.TipoAccesso.VISITA
        ):
            raise BusinessException(
                "L'accesso selezionato non è una visita."
            )

        if (
            accesso.uscita is not None
            or accesso.visita_conclusa_il is not None
        ):
            raise BusinessException(
                "La visita non è più attiva."
            )

        if accesso.spostato_fuori_ufficio_il is None:
            raise BusinessException(
                "La visita non è ancora stata autorizzata a salire."
            )

        if accesso.ingresso_ufficio_il is not None:
            raise BusinessException(
                "Il visitatore risulta già entrato nell'ufficio."
            )

        return cls._fai_entrare_accesso(
            accesso=accesso,
            ufficio=ufficio,
            operatore=operatore,
            ip_address=ip_address,
            promuovi_ricevimento=False,
        )

    @classmethod
    @transaction.atomic
    def concludi_visita(
        cls,
        *,
        accesso,
        operatore,
        note="",
        ip_address=None,
    ):
        """
        Conclude la visita presso l'ufficio.

        L'accesso all'edificio resta aperto fino alla
        restituzione del badge in portineria.
        """

        accesso = (
            AccessoVisitatore.objects
            .select_for_update(of=("self",))
            .select_related(
                "ufficio_destinazione",
                "visitatore",
                "badge",
            )
            .get(pk=accesso.pk)
        )

        if accesso.uscita is not None:
            raise BusinessException(
                "L'accesso risulta già chiuso."
            )

        if accesso.ingresso_ufficio_il is None:
            raise BusinessException(
                "Il visitatore non risulta entrato nell'ufficio."
            )

        if accesso.visita_conclusa_il is not None:
            raise BusinessException(
                "La visita risulta già conclusa."
            )

        if accesso.operatore_assegnato_id != operatore.pk:
            raise BusinessException(
                "La visita è assegnata a un altro dipendente."
            )

        accesso.visita_conclusa_il = timezone.now()

        if note:
            nota = f"Conclusione visita: {note}"

            if accesso.note:
                accesso.note = f"{accesso.note}\n{nota}"
            else:
                accesso.note = nota

            update_fields = [
                "visita_conclusa_il",
                "note",
            ]
        else:
            update_fields = [
                "visita_conclusa_il",
            ]

        accesso.save(
            update_fields=update_fields,
        )

        descrizione = (
            f"Visita conclusa presso l'ufficio "
            f"{accesso.ufficio_destinazione.nome}; "
            f"operatore: {operatore}."
        )

        if note:
            descrizione += f" Note: {note}"

        cls._audit(
            user=operatore,
            accesso=accesso,
            descrizione=descrizione,
            ip_address=ip_address,
        )

        return accesso
