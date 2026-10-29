from datetime import date
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from accounts.services.statino_servizio_civile import costruisci_statino


class Command(BaseCommand):
    help = 'Genera lo statino mensile delle presenze di un gruppo AD/Django.'

    def add_arguments(self, parser):
        parser.add_argument('--mese', required=True, help='Mese nel formato YYYY-MM')
        parser.add_argument('--gruppo', default='Servizio Civile')
        parser.add_argument('--output', help='Percorso del PDF da creare')

    def handle(self, *args, **options):
        try:
            mese = date.fromisoformat(options['mese'] + '-01')
        except ValueError as exc:
            raise CommandError('--mese deve avere formato YYYY-MM') from exc
        pdf = costruisci_statino(mese, options['gruppo'], 'Sistema')
        output = Path(options['output'] or f'statino-{options["gruppo"].lower().replace(" ", "-")}-{mese:%Y-%m}.pdf')
        output.write_bytes(pdf)
        self.stdout.write(self.style.SUCCESS(f'Statino creato: {output}'))
