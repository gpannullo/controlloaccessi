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
        headers = ("Login", "Attivo", "Scadenza password", "Nuova scadenza password", "Scadenza account", "Nuova scadenza account")
        values = [headers] + [
            (r["username"], "SI" if r["active"] else "NO", self._data(r["password"]), self._data(r.get("nuova_password")), self._data(r["account"]), self._data(r["nuova"]))
            for r in righe
        ]
        widths = [max(len(str(row[i])) for row in values) for i in range(6)]
        line = "  ".join("-" * width for width in widths)
        self.stdout.write("  ".join(headers[i].ljust(widths[i]) for i in range(6)))
        self.stdout.write(line)
        for r, row in zip(righe, values[1:]):
            text = "  ".join(str(row[i]).ljust(widths[i]) for i in range(6))
            # Blu: l'account scade prima della password.
            if r["account"] and r["password"] and r["account"] < r["password"]:
                text = f"\033[94m{text}\033[0m"
            self.stdout.write(text)

    def handle(self, *args, **options):
        applica = options["applica"]
        utenti_ad = DirectoryFactory.get_service().get_users()
        mappa = {str(u.get("username", "")).casefold(): u for u in utenti_ad}
        da_modificare = []
        ordinari = []
        servizi = []
        politici = []
        gia_allineati = []
        non_attivi = []
        non_presenti = []
        scadenza_non_attivo = datetime(2026, 11, 1, tzinfo=ZoneInfo("Europe/Rome"))
        adesso = timezone.now()
        account_servizio = {"user.protocollo", "user.sportello", "utenza.m2m"}

        for user in CustomUser.objects.all().order_by("username"):
            dato = mappa.get(user.username.casefold())
            if dato is None:
                non_presenti.append(user.username)
                continue
            if (("." not in user.username and "_" not in user.username)
                    or user.username.casefold() == "g.pannullo"
                    or user.username.casefold() in account_servizio):
                servizi.append(user.username)
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
            password_expiry = dato.get("password_expiry")
            password_mai = password_expiry is None
            nuova_password = adesso if password_mai else password_expiry
            nuova_account = adesso + timedelta(days=30) if password_mai else password_expiry + timedelta(days=30)
            # Dopo pwdLastSet=0 AD può non restituire una data di scadenza
            # password. Se accountExpires è già stato impostato dal comando
            # alla finestra di 30 giorni, non va spostato ad ogni esecuzione.
            if password_mai and account_attuale:
                differenza = abs((account_attuale - nuova_account).total_seconds())
                if differenza <= 86400:
                    nuova_account = account_attuale
            riga = {"username": user.username, "active": account_attivo, "password": password_expiry, "nuova_password": nuova_password, "account": account_attuale, "nuova": nuova_account}
            destinazione = politici if gruppi.intersection({"consigliere", "assessore"}) else ordinari
            destinazione.append(riga)
            if account_attuale == nuova_account:
                gia_allineati.append(riga)
            else:
                da_modificare.append(riga)
            if applica:
                with transaction.atomic():
                    if password_mai:
                        DirectoryAdminService().imposta_password_scaduta(user.username)
                    DirectoryAdminService().imposta_scadenza_account(user.username, nuova_account)
                    user.scadenza_account = nuova_account
                    user.save(update_fields=["scadenza_account"])
            continue

        modalita = "APPLICATA" if applica else "SIMULAZIONE"
        self.stdout.write(self.style.SUCCESS(f"\n{modalita} - DA MODIFICARE ({len(da_modificare)})"))
        self._tabella(da_modificare) if da_modificare else self.stdout.write("Nessun account da modificare.")
        self.stdout.write(self.style.SUCCESS(f"\nCLASSE POLITICA - CONSIGLIERE/ASSESSORE ({len(politici)})"))
        self.stdout.write("Gruppi invariati. Password con data già presente non modificata; password Mai impostata come scaduta oggi; account +30 giorni.")
        self._tabella(politici) if politici else self.stdout.write("Nessun account della classe politica da aggiornare.")
        self.stdout.write(self.style.SUCCESS(f"\nNON MODIFICATI ({len(gia_allineati)})"))
        self._tabella(gia_allineati) if gia_allineati else self.stdout.write("Nessun account già allineato.")
        self.stdout.write(self.style.WARNING(f"\nNON ATTIVI - SCADENZA IMPOSTATA AL 01/11/2026 ({len(non_attivi)})"))
        self._tabella(non_attivi) if non_attivi else self.stdout.write("Nessun account non attivo da aggiornare.")
        self.stdout.write(self.style.WARNING(f"\nACCOUNT ORDINARI - POLICY PASSWORD/ACCOUNT ({len(ordinari)})"))
        self._tabella(ordinari) if ordinari else self.stdout.write("Nessun account ordinario.")
        self.stdout.write(self.style.SUCCESS(f"\nACCOUNT DI SERVIZIO - NON MODIFICATI ({len(servizi)})"))
        for username in servizi:
            self.stdout.write(username)
        self.stdout.write(self.style.WARNING(f"\nNON PRESENTI IN AD ({len(non_presenti)})"))
        for username in non_presenti:
            self.stdout.write(username)
