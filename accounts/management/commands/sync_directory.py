from django.core.management.base import BaseCommand

from accounts.services.synchronization_service import SynchronizationService


class Command(BaseCommand):
    help = "Sincronizza Active Directory"

    def handle(self, *args, **options):

        SynchronizationService().run()