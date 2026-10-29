from django.core.management.base import BaseCommand, CommandError

from prenotazioni.wordpress_connector import (
    WordPressConnectorError,
    simula_allineamento_persone_pubbliche_wordpress,
)


class Command(BaseCommand):
    help = "Simula il riallineamento reciproco fra Persone pubbliche e Unità organizzative WordPress."

    def handle(self, *args, **options):
        try:
            risultato = simula_allineamento_persone_pubbliche_wordpress()
        except WordPressConnectorError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.NOTICE(
                "Persone da ripubblicare: {persone}; aggiunte nelle unità: {aggiunte}; rimozioni dalle unità: {rimozioni}.".format(
                    persone=len(risultato["persone_da_ripubblicare"]),
                    aggiunte=sum(len(voce["persone"]) for voce in risultato["aggiunte_in_unita"]),
                    rimozioni=sum(len(voce["persone"]) for voce in risultato["rimozioni_in_unita"]),
                )
            )
        )
        for voce in risultato["persone_da_ripubblicare"]:
            self.stdout.write("* {nome} (WordPress {persona_id})".format(**voce))
        for voce in risultato["aggiunte_in_unita"]:
            self.stdout.write("+ unità {unita_id}: persone {persone}".format(**voce))
        for voce in risultato["rimozioni_in_unita"]:
            self.stdout.write("- unità {unita_id}: persone {persone}".format(**voce))
