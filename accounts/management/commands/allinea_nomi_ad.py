from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.services.active_directory_service import ActiveDirectoryService
from accounts.services.directory_admin_service import DirectoryAdminException, DirectoryAdminService


class Command(BaseCommand):
    help = "Allinea in Active Directory il campo name al formato 'Cognome Nome'."

    def add_arguments(self, parser):
        parser.add_argument(
            "--applica",
            action="store_true",
            help="Scrive le modifiche in AD; senza questo flag esegue solo una simulazione.",
        )

    def handle(self, *args, **options):
        users = ActiveDirectoryService().get_users()
        da_aggiornare = []
        for user in users:
            cognome = str(user.get("last_name") or "").strip()
            nome = str(user.get("first_name") or "").strip()
            atteso = " ".join(part for part in (cognome, nome) if part)
            attuale = str(user.get("directory_name") or "").strip()
            if atteso and attuale != atteso:
                da_aggiornare.append((user["username"], attuale, atteso))

        self.stdout.write("Account AD analizzati: %d" % len(users))
        self.stdout.write("Nomi da correggere: %d" % len(da_aggiornare))
        if not da_aggiornare:
            self.stdout.write(self.style.SUCCESS("Nessun disallineamento rilevato."))
            return

        for username, attuale, atteso in da_aggiornare:
            self.stdout.write("- %s: '%s' -> '%s'" % (username, attuale or "(vuoto)", atteso))

        if not options["applica"]:
            self.stdout.write("Simulazione: nessuna modifica scritta. Usare --applica per confermare.")
            return
        if not settings.DIRECTORY.get("WRITE_ENABLED", False):
            raise CommandError("Scritture AD disabilitate: impostare AD_WRITE_ENABLED=True.")

        service = DirectoryAdminService()
        aggiornati = 0
        errori = 0
        for username, _attuale, atteso in da_aggiornare:
            try:
                service.aggiorna_nome_directory(username, atteso)
                aggiornati += 1
            except DirectoryAdminException as exc:
                errori += 1
                self.stderr.write(self.style.ERROR("%s: %s" % (username, exc)))
        self.stdout.write("Aggiornati: %d; errori: %d" % (aggiornati, errori))
        if errori:
            raise CommandError("Allineamento completato con errori.")
