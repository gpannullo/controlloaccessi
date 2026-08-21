from django.db import transaction
from django.utils import timezone

from audit.services.audit_service import AuditService
from common.exceptions import (
    BusinessException,
    VisitorAlreadyInsideException,
)
from visitors.models import AccessoVisitatore
from visitors.services.badge_service import BadgeService
from visitors.services.capacity_service import CapacityService
from visitors.services.queue_service import QueueService


class AccessoGiaChiusoException(BusinessException):
    """L'accesso risulta già chiuso."""


class ReceptionService:

    @staticmethod
    @transaction.atomic
    def check_in(
            visitatore,
            ufficio,
            motivo="",
            note="",
            documento_presentato=True,
            operatore=None,
            ip_address=None,
            appuntamento=None,
            tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO,
            accompagnato=False,
    ):
        accesso_esistente = (
            AccessoVisitatore.objects
            .filter(
                visitatore=visitatore,
                uscita__isnull=True,
            )
            .exists()
        )

        if (
            tipo_accesso
            == AccessoVisitatore.TipoAccesso.RICEVIMENTO
        ):
            capacita = CapacityService.capacita_residua(
                ufficio
            )

            if (
                appuntamento is None
                and not capacita["accetta_non_prenotati"]
            ):
                raise BusinessException(
                    "L'ufficio non può accettare altri visitatori "
                    "non prenotati nella giornata corrente. "
                    f"Operatori disponibili: "
                    f"{capacita['operatori']}; "
                    f"persone ancora da servire: "
                    f"{capacita['persone_da_servire']}; "
                    f"prenotazioni riservate: "
                    f"{capacita['prenotazioni_riservate']}."
                )

        if accesso_esistente:
            raise VisitorAlreadyInsideException(
                "Il visitatore risulta già presente nella sede."
            )

        badge = BadgeService.assegna_primo_disponibile()

        numero_coda = QueueService.prossimo_numero(
            ufficio=ufficio,
        )

        accesso = AccessoVisitatore.objects.create(
            visitatore=visitatore,
            ufficio_destinazione=ufficio,
            ingresso=timezone.now(),
            motivo=motivo,
            badge=badge,
            numero_coda=numero_coda,
            prefisso_coda=ufficio.prefisso_coda_effettivo,
            note=note,
            documento_presentato=documento_presentato,
            accompagnato=accompagnato,
            stato_coda=AccessoVisitatore.StatoCoda.HALL,
            tipo_accesso=tipo_accesso,
            appuntamento=appuntamento,
        )

        AuditService.log(
            user=operatore,
            tipo="ACCESSO",
            oggetto=f"AccessoVisitatore:{accesso.pk}",
            descrizione=(
                f"Registrazione accesso {accesso.pk}; "
                f"ufficio {ufficio.nome}; "
                f"badge {badge.codice}; "
                f"numero coda "
                f"{accesso.numero_coda_formattato}."
            ),
            ip_address=ip_address,
        )

        # Il ricevimento segue la normale gestione automatica
        # della coda. La VISITA resta invece sempre nella hall
        # finché un dipendente dell'ufficio non ne autorizza
        # esplicitamente la salita.
        if (
            tipo_accesso
            == AccessoVisitatore.TipoAccesso.RICEVIMENTO
        ):
            QueueService.accoda_nuovo_accesso(
                accesso=accesso,
                operatore=operatore,
                ip_address=ip_address,
            )

        return accesso

    @staticmethod
    @transaction.atomic
    def check_out(
            accesso,
            uscita,
            operatore,
            note_chiusura="",
            ip_address=None,
            riserva_badge_rientro=False,
    ):
        accesso = (
            AccessoVisitatore.objects
            .select_for_update()
            .select_related(
                "ufficio_destinazione",
                "badge",
            )
            .get(pk=accesso.pk)
        )

        if accesso.uscita is not None:
            raise AccessoGiaChiusoException(
                "L'accesso risulta già chiuso."
            )

        if uscita < accesso.ingresso:
            raise BusinessException(
                "L'orario di uscita non può essere "
                "precedente all'ingresso."
            )

        accesso.uscita = uscita
        accesso.stato = AccessoVisitatore.Stato.CHIUSO

        accesso.save(
            update_fields=[
                "uscita",
                "stato",
            ]
        )

        if accesso.badge_id:
            accesso.badge.riservato_rientro = bool(
                riserva_badge_rientro
            )
            accesso.badge.save(
                update_fields=["riservato_rientro"]
            )

        descrizione = (
            f"Chiusura accesso {accesso.pk}; "
            f"badge "
            f"{accesso.badge.codice if accesso.badge else '-'}; "
            f"uscita dichiarata "
            f"{timezone.localtime(uscita):%d/%m/%Y %H:%M}."
        )

        if riserva_badge_rientro:
            descrizione += " Badge riservato per rientro."

        if note_chiusura:
            descrizione += (
                f" Note: {note_chiusura}"
            )

        AuditService.log(
            user=operatore,
            tipo="ACCESSO",
            oggetto=f"AccessoVisitatore:{accesso.pk}",
            descrizione=descrizione,
            ip_address=ip_address,
        )

        return accesso
