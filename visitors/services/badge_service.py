from django.db import transaction

from common.exceptions import BusinessException
from visitors.models import AccessoVisitatore, Badge


class BadgeNonDisponibileError(BusinessException):
    """
    Nessun badge attivo risulta disponibile.
    """


class BadgeService:

    @staticmethod
    def assegna_primo_disponibile():
        """
        Restituisce il primo badge attivo non associato
        a un accesso ancora aperto.

        Il metodo deve essere eseguito dentro una transazione.
        """

        badge_occupati = (
            AccessoVisitatore.objects
            .filter(
                uscita__isnull=True,
                badge__isnull=False,
            )
            .values_list(
                "badge_id",
                flat=True,
            )
        )

        badge = (
            Badge.objects
            .select_for_update()
            .filter(
                attivo=True,
                riservato_rientro=False,
            )
            .exclude(
                pk__in=badge_occupati,
            )
            .order_by("codice")
            .first()
        )

        if badge is None:
            raise BadgeNonDisponibileError(
                "Non risultano badge disponibili."
            )

        return badge

    @staticmethod
    def disponibili():
        """
        Restituisce tutti i badge attualmente disponibili.
        """

        badge_occupati = (
            AccessoVisitatore.objects
            .filter(
                uscita__isnull=True,
                badge__isnull=False,
            )
            .values_list(
                "badge_id",
                flat=True,
            )
        )

        return (
            Badge.objects
            .filter(
                attivo=True,
                riservato_rientro=False,
            )
            .exclude(
                pk__in=badge_occupati,
            )
            .order_by("codice")
        )

    @staticmethod
    def numero_disponibili():
        return BadgeService.disponibili().count()