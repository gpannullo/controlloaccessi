import logging
from dataclasses import dataclass
from enum import Enum

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone


logger = logging.getLogger(__name__)

User = get_user_model()


class ExternalPresenceStatus(Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


@dataclass
class PresenceResult:
    username: str
    status: ExternalPresenceStatus
    source: str = ""
    detail: str = ""


class PresenceApiClient:
    """
    Client predisposto per il futuro sistema esterno.

    Per ora non effettua chiamate HTTP e restituisce UNKNOWN.
    Quando sarà disponibile l'API, sarà sufficiente
    implementare check_user().
    """

    def check_user(self, user) -> PresenceResult:
        return PresenceResult(
            username=user.username,
            status=ExternalPresenceStatus.UNKNOWN,
            source="API_NON_CONFIGURATA",
            detail="Verifica presenza non ancora implementata.",
        )


class PresenceService:

    def __init__(self, client=None):
        self.client = client or PresenceApiClient()

    @staticmethod
    def _django_status(external_status):
        mapping = {
            ExternalPresenceStatus.PRESENT: (
                User.StatoPresenza.PRESENTE
            ),
            ExternalPresenceStatus.ABSENT: (
                User.StatoPresenza.ASSENTE
            ),
            ExternalPresenceStatus.UNKNOWN: (
                User.StatoPresenza.NON_VERIFICATA
            ),
        }

        return mapping[external_status]

    @transaction.atomic
    def update_user_presence(self, user):
        result = self.client.check_user(user)

        user = (
            User.objects
            .select_for_update()
            .get(pk=user.pk)
        )

        user.stato_presenza = self._django_status(
            result.status
        )

        user.presenza_verificata_il = timezone.now()
        user.presenza_fonte = result.source

        user.save(
            update_fields=[
                "stato_presenza",
                "presenza_verificata_il",
                "presenza_fonte",
            ]
        )

        return result

    def update_all_active_users(self):
        results = []

        for user in User.objects.filter(
            is_active=True,
        ).iterator():
            try:
                results.append(
                    self.update_user_presence(user)
                )
            except Exception:
                logger.exception(
                    "Errore aggiornando la presenza di %s",
                    user.username,
                )

        return results