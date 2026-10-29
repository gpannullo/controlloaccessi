from django.core.management.base import BaseCommand, CommandError

from prenotazioni.wordpress_connector import WordPressConnectorError, sincronizza_appuntamenti_wordpress


class Command(BaseCommand):
    help = "Scarica e archivia gli appuntamenti dal Web Service WordPress."

    def handle(self, *args, **options):
        try:
            risultato = sincronizza_appuntamenti_wordpress()
        except WordPressConnectorError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Sincronizzazione WordPress completata: "
                f'{risultato["totale"]} ricevuti, {risultato["creati"]} creati, {risultato["aggiornati"]} aggiornati.'
            )
        )
