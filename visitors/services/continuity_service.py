from django.db import transaction
from django.utils import timezone

from audit.services.audit_service import AuditService
from common.exceptions import BusinessException
from visitors.models import AccessoVisitatore, Badge, EventoAccesso
from visitors.services.queue_service import QueueService


class ContinuitaAccessoService:
    @staticmethod
    def _audit(user, accesso, descrizione, ip_address=None):
        AuditService.log(
            user=user,
            tipo="ACCESSO",
            oggetto=f"AccessoVisitatore:{accesso.pk}",
            descrizione=descrizione,
            ip_address=ip_address,
        )

    @classmethod
    @transaction.atomic
    def trasferisci_ufficio(
        cls,
        *,
        accesso,
        nuovo_ufficio,
        operatore,
        motivo,
        note="",
        ip_address=None,
    ):
        accesso = (
            AccessoVisitatore.objects
            .select_for_update()
            .select_related("visitatore", "badge", "ufficio_destinazione")
            .get(pk=accesso.pk)
        )

        if accesso.uscita is not None:
            raise BusinessException("L'accesso risulta già chiuso.")

        if accesso.ingresso_ufficio_il is None:
            raise BusinessException(
                "Il visitatore non risulta dentro l'ufficio."
            )

        if accesso.operatore_assegnato_id != operatore.pk:
            raise BusinessException(
                "La visita è assegnata a un altro dipendente."
            )

        if nuovo_ufficio.pk == accesso.ufficio_destinazione_id:
            raise BusinessException(
                "Selezionare un ufficio diverso da quello corrente."
            )

        momento = timezone.now()
        vecchio_ufficio = accesso.ufficio_destinazione
        badge = accesso.badge
        dipendente = operatore.get_full_name() or operatore.username
        nota_trasferimento = "Trasferito a %s da %s alle ore: %s." % (
            nuovo_ufficio.nome,
            dipendente,
            timezone.localtime(momento).strftime("%d/%m/%Y %H:%M"),
        )
        if note:
            nota_trasferimento += " Nota: %s" % note

        accesso.visita_conclusa_il = momento
        accesso.uscita = momento
        accesso.stato = AccessoVisitatore.Stato.CHIUSO
        accesso.stato_coda = AccessoVisitatore.StatoCoda.VISITA_CONCLUSA
        accesso.note = (
            f"{accesso.note}\n" if accesso.note else ""
        ) + nota_trasferimento
        accesso.save(
            update_fields=[
                "visita_conclusa_il",
                "uscita",
                "stato",
                "stato_coda",
                "note",
            ]
        )

        if badge:
            Badge.objects.select_for_update().get(pk=badge.pk)
            badge.riservato_rientro = False
            badge.save(update_fields=["riservato_rientro"])

        nuovo_accesso = AccessoVisitatore.objects.create(
            visitatore=accesso.visitatore,
            ufficio_destinazione=nuovo_ufficio,
            badge=badge,
            numero_coda=QueueService.prossimo_numero(nuovo_ufficio),
            prefisso_coda=nuovo_ufficio.prefisso_coda_effettivo,
            documento_presentato=accesso.documento_presentato,
            accompagnato=accesso.accompagnato,
            ingresso=momento,
            motivo=motivo,
            accesso_precedente=accesso,
            note=nota_trasferimento,
            stato_coda=AccessoVisitatore.StatoCoda.HALL,
            tipo_accesso=AccessoVisitatore.TipoAccesso.RICEVIMENTO,
        )

        EventoAccesso.objects.create(
            accesso=nuovo_accesso,
            tipo=EventoAccesso.Tipo.REGISTRAZIONE,
            timestamp=momento,
            ufficio=nuovo_ufficio,
            operatore=operatore,
            descrizione=(
                f"Nuovo accesso generato per trasferimento da "
                f"{vecchio_ufficio.nome} a {nuovo_ufficio.nome}."
            ),
            dati={"accesso_precedente": accesso.pk},
        )

        cls._audit(
            operatore, accesso,
            f"Accesso concluso e trasferito a {nuovo_ufficio.nome}; "
            f"nuovo accesso {nuovo_accesso.pk}.",
            ip_address,
        )
        cls._audit(
            operatore, nuovo_accesso,
            f"Accesso creato da trasferimento; provenienza "
            f"{vecchio_ufficio.nome}; accesso precedente {accesso.pk}.",
            ip_address,
        )

        QueueService.accoda_nuovo_accesso(
            accesso=nuovo_accesso,
            operatore=operatore,
            ip_address=ip_address,
        )

        return nuovo_accesso

    @classmethod
    @transaction.atomic
    def rientro_da_badge(
        cls,
        *,
        codice_badge,
        operatore,
        ip_address=None,
    ):
        badge = (
            Badge.objects.select_for_update()
            .filter(
                codice__iexact=codice_badge,
                attivo=True,
                riservato_rientro=True,
            )
            .first()
        )
        if badge is None:
            raise BusinessException(
                "Il badge non risulta riservato per un rientro."
            )

        precedente = (
            AccessoVisitatore.objects
            .filter(
                badge=badge,
                uscita__isnull=False,
            )
            .select_related("visitatore", "ufficio_destinazione")
            .order_by("-uscita", "-pk")
            .first()
        )
        if precedente is None:
            raise BusinessException(
                "Non è stato trovato l'accesso precedente del badge."
            )

        if AccessoVisitatore.objects.filter(
            badge=badge, uscita__isnull=True
        ).exists():
            raise BusinessException(
                "Il badge risulta già associato a un accesso aperto."
            )

        momento = timezone.now()
        nuovo_accesso = AccessoVisitatore.objects.create(
            visitatore=precedente.visitatore,
            ufficio_destinazione=precedente.ufficio_destinazione,
            badge=badge,
            numero_coda=QueueService.prossimo_numero(
                precedente.ufficio_destinazione
            ),
            prefisso_coda=(
                precedente.ufficio_destinazione.prefisso_coda_effettivo
            ),
            documento_presentato=precedente.documento_presentato,
            accompagnato=precedente.accompagnato,
            rientro_prioritario=True,
            ingresso=momento,
            motivo=precedente.motivo,
            note=(
                f"Rientro prioritario dal precedente accesso "
                f"{precedente.pk}."
            ),
            stato_coda=AccessoVisitatore.StatoCoda.HALL,
            tipo_accesso=precedente.tipo_accesso,
        )

        badge.riservato_rientro = False
        badge.save(update_fields=["riservato_rientro"])

        EventoAccesso.objects.create(
            accesso=nuovo_accesso,
            tipo=EventoAccesso.Tipo.REGISTRAZIONE,
            timestamp=momento,
            ufficio=precedente.ufficio_destinazione,
            operatore=operatore,
            descrizione=(
                f"Rientro con badge {badge.codice}; nuovo accesso "
                f"prioritario collegato al precedente {precedente.pk}."
            ),
            dati={"accesso_precedente": precedente.pk, "rientro": True},
        )

        cls._audit(
            operatore, nuovo_accesso,
            f"Rientro prioritario con badge {badge.codice}; "
            f"accesso precedente {precedente.pk}.",
            ip_address,
        )

        # Riparte dalla hall; se la capacità lo consente può essere
        # promosso immediatamente secondo la normale logica di coda.
        QueueService.accoda_nuovo_accesso(
            accesso=nuovo_accesso,
            operatore=operatore,
            ip_address=ip_address,
        )

        return nuovo_accesso

    @classmethod
    @transaction.atomic
    def libera_badge_rientro(cls, *, badge, operatore, ip_address=None):
        badge = Badge.objects.select_for_update().get(pk=badge.pk)
        if not badge.riservato_rientro:
            raise BusinessException(
                "Il badge non risulta riservato per un rientro."
            )
        badge.riservato_rientro = False
        badge.save(update_fields=["riservato_rientro"])
        AuditService.log(
            user=operatore,
            tipo="ACCESSO",
            oggetto=f"Badge:{badge.pk}",
            descrizione=(
                f"Badge {badge.codice} liberato manualmente dalla "
                "riserva per rientro."
            ),
            ip_address=ip_address,
        )
        return badge
