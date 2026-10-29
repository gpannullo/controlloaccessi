from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from audit_ad.models import Event
from audit_ad.services import analyze

class Command(BaseCommand):
    help = 'Rianalizza gli eventi recenti e segnala sorgenti senza eventi da 15 minuti (anche se inattive).'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24)

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(hours=max(1, min(options['hours'], 720)))
        count = 0
        for event in Event.objects.filter(occurred_at__gte=since).order_by('occurred_at').iterator():
            analyze(event)
            count += 1
        self.stdout.write(f'Analizzati {count} eventi.')
        for source in settings.AUDIT_AD_SOURCES:
            latest = Event.objects.filter(source=source).order_by('-received_at').first()
            if not latest or latest.received_at < timezone.now() - timedelta(minutes=15):
                self.stdout.write(self.style.WARNING(f'{source}: nessun evento recente, verificare inoltro e policy audit.'))
