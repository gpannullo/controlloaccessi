from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from accounts.services.factory import DirectoryFactory
from accounts.services.directory_admin_service import DirectoryAdminService
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class Command(BaseCommand):
    help = "Allinea nel DB la scadenza account letta da Active Directory."

    def add_arguments(self, parser):
        parser.add_argument("--applica", action="store_true", help="Scrive le date nel DB; senza opzione esegue solo una simulazione.")

    @staticmethod
    def _data(value):
        if not value:
            return "Mai"
        if value.year >= 9999:
            return "Mai"
        return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")

    def _tabella(self, righe):
        headers = ("Login", "Attivo", "Scadenza password", "Scadenza account", "Nuova scadenza account")
        values = [headers] + [
            (r["username"], "SI" if r["active"] else "NO", self._data(r["password"]), self._data(r["account"]), self._data(r["nuova"]))
            for r in righe
        ]
        widths = [max(len(str(row[i])) for row in values) for i in range(5)]
        line = "  ".join("-" * width for width in widths)
        self.stdout.write("  ".join(headers[i].ljust(widths[i]) for i in range(5)))
        self.stdout.write(line)
        for r, row in zip(righe, values[1:]):
            text = "  ".join(str(row[i]).ljust(widths[i]) for i in range(5))
            # Blu: l'account scade prima della password.
            if r["account"] and r["password"] and r["account"] < r["password"]:
                text = f"\033[94m{text}\033[0m"
            self.stdout.write(text)

    def handle(self, *args, **options):
        applica = options["applica"]
        utenti_ad = DirectoryFactory.get_service().get_users()
        mappa = {str(u.get("username", "")).casefold(): u for u in utenti_ad}
        da_modificare = []
        politici = []
        gia_allineati = []
        non_attivi = []
        non_presenti = []
        scadenza_non_attivo = datetime(2026, 11, 1, tzinfo=ZoneInfo("Europe/Rome"))
        adesso = timezone.now()

        for user in CustomUser.objects.all().order_by("username"):
            dato = mappa.get(user.username.casefold())
            if dato is None:
                non_presenti.append(user.username)
                continue
            account_attivo = bool(dato.get("active"))
            account_attuale = user.scadenza_account
            if not account_attivo:
                riga = {"username": user.username, "active": False, "password": dato.get("password_expiry"), "account": account_attuale, "nuova": scadenza_non_attivo}
                (gia_allineati if account_attuale == scadenza_non_attivo else non_attivi).append(riga)
                if applica and account_attuale != scadenza_non_attivo:
                    with transaction.atomic():
                        DirectoryAdminService().imposta_scadenza_account(user.username, scadenza_non_attivo)
                        user.scadenza_account = scadenza_non_attivo
                        user.save(update_fields=["scadenza_account"])
                continue
            gruppi = {str(g).casefold() for g in dato.get("groups", [])}
            if gruppi.intersection({"consigliere", "assessore"}):
                nuova_password = adesso + timedelta(days=30)
                nuova = adesso + timedelta(days=60)
                riga = {"username": user.username, "active": True, "password": nuova_password, "account": account_attuale, "nuova": nuova}
                politici.append(riga)
                if applica and account_attuale != nuova:
                    with transaction.atomic():
                        DirectoryAdminService().imposta_scadenza_account(user.username, nuova)
                        user.scadenza_account = nuova
                        user.save(update_fields=["scadenza_account"])
                continue
            password_expiry = dato.get("password_expiry")
            if not password_expiry:
                gia_allineati.append({"username": user.username, "active": True, "password": None, "account": user.scadenza_account, "nuova": user.scadenza_account})
                continue
            nuova = password_expiry + timedelta(days=30)
            riga = {"username": user.username, "active": True, "password": password_expiry, "account": user.scadenza_account, "nuova": nuova}
            destinazione = gia_allineati if user.scadenza_account == nuova else da_modificare
            destinazione.append(riga)
            if applica:
                with transaction.atomic():
                    if destinazione is da_modificare:
                        DirectoryAdminService().imposta_scadenza_account(user.username, nuova)
                        user.scadenza_account = nuova
                        user.save(update_fields=["scadenza_account"])

        modalita = "APPLICATA" if applica else "SIMULAZIONE"
        self.stdout.write(self.style.SUCCESS(f"\n{modalita} - DA MODIFICARE ({len(da_modificare)})"))
        self._tabella(da_modificare) if da_modificare else self.stdout.write("Nessun account da modificare.")
        self.stdout.write(self.style.SUCCESS(f"\nCLASSE POLITICA - CONSIGLIERE/ASSESSORE ({len(politici)})"))
        self.stdout.write("Obiettivo: password tra 30 giorni, account tra 60 giorni.")
        self._tabella(politici) if politici else self.stdout.write("Nessun account della classe politica da aggiornare.")
        self.stdout.write(self.style.SUCCESS(f"\nNON MODIFICATI ({len(gia_allineati)})"))
        self._tabella(gia_allineati) if gia_allineati else self.stdout.write("Nessun account già allineato.")
        self.stdout.write(self.style.WARNING(f"\nNON ATTIVI - SCADENZA IMPOSTATA AL 01/11/2026 ({len(non_attivi)})"))
        self._tabella(non_attivi) if non_attivi else self.stdout.write("Nessun account non attivo da aggiornare.")
        self.stdout.write(self.style.WARNING(f"\nNON PRESENTI IN AD ({len(non_presenti)})"))
        for username in non_presenti:
            self.stdout.write(username)
