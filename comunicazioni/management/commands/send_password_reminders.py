from django.core.management.base import BaseCommand
from comunicazioni.password_reminders import queue_reminders


class Command(BaseCommand):
    help = 'Accoda il promemoria giornaliero per password valide in scadenza entro 15 giorni.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Verifica senza accodare né registrare messaggi.')

    def handle(self, *args, **options):
        self.stdout.write(str(queue_reminders(dry_run=options['dry_run'])))
