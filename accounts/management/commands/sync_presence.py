from django.core.management.base import BaseCommand

from accounts.services.presence_service import (
    ExternalPresenceStatus,
    PresenceService,
)


class Command(BaseCommand):
    help = "Aggiorna la presenza dei dipendenti"

    def handle(self, *args, **options):
        results = (
            PresenceService()
            .update_all_active_users()
        )

        presenti = sum(
            result.status
            == ExternalPresenceStatus.PRESENT
            for result in results
        )

        assenti = sum(
            result.status
            == ExternalPresenceStatus.ABSENT
            for result in results
        )

        sconosciuti = sum(
            result.status
            == ExternalPresenceStatus.UNKNOWN
            for result in results
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Aggiornamento presenze completato: "
                f"presenti={presenti}, "
                f"assenti={assenti}, "
                f"non verificati={sconosciuti}."
            )
        )