from django.core.management.base import BaseCommand, CommandError

from accounts.services.timbrature_presence_service import TimbratureError, TimbraturePresenceService


class Command(BaseCommand):
    help = "Scarica via SFTP il file timbrature e aggiorna le presenze locali."

    def handle(self, *args, **options):
        try:
            risultato = TimbraturePresenceService().sincronizza()
        except TimbratureError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Timbrature importate: righe=%s, valide=%s, utenti aggiornati=%s, presenti=%s, assenti=%s, badge senza utente=%s."
                % (
                    risultato.righe_lette,
                    risultato.timbrature_valide,
                    risultato.utenti_aggiornati,
                    risultato.presenti,
                    risultato.assenti,
                    risultato.badge_senza_utente,
                )
            )
        )
