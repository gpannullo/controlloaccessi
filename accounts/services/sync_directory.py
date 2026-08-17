from django.core.management.base import BaseCommand

from accounts.services.factory import DirectoryFactory
from accounts.services.group_sync_service import GroupSyncService
from accounts.services.user_sync_service import UserSyncService
from audit.services import AuditService


class Command(BaseCommand):

    help = "Sincronizza la Directory Aziendale"

    def handle(self, *args, **kwargs):

        directory = DirectoryFactory.get_service()

        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("=== SINCRONIZZAZIONE DIRECTORY ==="))
        self.stdout.write("")

        group_result = GroupSyncService().sync(directory)

        self.stdout.write(
            self.style.SUCCESS(
                f"Gruppi - Creati: {group_result.created} | Aggiornati: {group_result.updated}"
            )
        )

        user_result = UserSyncService().sync(directory)

        self.stdout.write(
            self.style.SUCCESS(
                f"Utenti - Creati: {user_result.created} | Aggiornati: {user_result.updated}"
            )
        )

        AuditService.log(
            user=None,
            tipo="SYSTEM",
            oggetto="SYNC_DIRECTORY",
            descrizione="Sincronizzazione Active Directory completata"
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Sincronizzazione completata."))