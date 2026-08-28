import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.services.timbrature_presence_service import TimbraturePresenceService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Demone di sincronizzazione SFTP delle timbrature del personale."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=settings.PRESENCE_SSH_INTERVAL_SECONDS)

    def handle(self, *args, **options):
        intervallo = max(10, options["interval"])
        if not settings.PRESENCE_SSH_ENABLED:
            self.stderr.write("PRESENCE_SSH_ENABLED non abilitato: demone non avviato.")
            return
        self.stdout.write(f"Demone timbrature avviato: intervallo {intervallo} secondi.")
        while True:
            try:
                risultato = TimbraturePresenceService().sincronizza()
                self.stdout.write(
                    "Presenze aggiornate: presenti=%s, assenti=%s, badge sconosciuti=%s."
                    % (risultato.presenti, risultato.assenti, risultato.badge_senza_utente)
                )
            except Exception:
                logger.exception("Importazione timbrature non riuscita")
            time.sleep(intervallo)
