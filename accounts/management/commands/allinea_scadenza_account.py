from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser
from accounts.services.factory import DirectoryFactory


class Command(BaseCommand):
    help = "Allinea nel DB la scadenza account letta da Active Directory."

    def add_arguments(self, parser):
        parser.add_argument("--applica", action="store_true", help="Scrive le date nel DB; senza opzione esegue solo una simulazione.")

    def handle(self, *args, **options):
        applica = options["applica"]
        utenti_ad = DirectoryFactory.get_service().get_users()
        mappa = {str(u.get("username", "")).casefold(): u for u in utenti_ad}
        aggiornati = 0
        invariati = 0
        mancanti = 0

        for user in CustomUser.objects.all().order_by("username"):
            dato = mappa.get(user.username.casefold())
            if dato is None:
                mancanti += 1
                continue
            nuova = dato.get("account_expiry")
            if user.scadenza_account == nuova:
                invariati += 1
                continue
            self.stdout.write(f"{user.username}: {user.scadenza_account or 'Mai'} -> {nuova or 'Mai'}")
            if applica:
                with transaction.atomic():
                    user.scadenza_account = nuova
                    user.save(update_fields=["scadenza_account"])
            aggiornati += 1

        modalita = "APPLICATA" if applica else "SIMULAZIONE"
        self.stdout.write(self.style.SUCCESS(
            f"{modalita}: {aggiornati} da aggiornare, {invariati} invariati, {mancanti} non presenti in AD."
        ))
