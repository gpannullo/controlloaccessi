from django.core.management.base import BaseCommand
from django.conf import settings
from ldap3 import Connection

from accounts.services.active_directory_service import ActiveDirectoryService


class Command(BaseCommand):
    help = "Test connessione Active Directory"

    def handle(self, *args, **options):

        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("TEST ACTIVE DIRECTORY")
        self.stdout.write("=" * 70)

        try:

            self.stdout.write(
                self.style.SUCCESS(
                    f"Server : {settings.DIRECTORY['SERVER']}"
                )
            )

            server = ActiveDirectoryService().server

            conn = Connection(
                server,
                user=settings.DIRECTORY["BIND_USER"],
                password=settings.DIRECTORY["BIND_PASSWORD"],
                auto_bind=True,
            )

            self.stdout.write(self.style.SUCCESS("Connessione LDAPS riuscita"))

        except Exception as ex:

            self.stdout.write(
                self.style.ERROR(f"Errore connessione:\n{ex}")
            )

            return

        self.stdout.write("")
        self.stdout.write(f"Base DN : {settings.DIRECTORY['BASE_DN']}")
        self.stdout.write("")

        #
        # UTENTI
        #

        self.stdout.write("Ricerca utenti...")

        conn.search(
            search_base=settings.DIRECTORY["BASE_DN"],
            search_filter="(&(objectCategory=person)(objectClass=user))",
            attributes=[
                "sAMAccountName",
                "givenName",
                "sn",
                "mail",
            ],
        )

        utenti = conn.entries

        self.stdout.write(
            self.style.SUCCESS(f"Trovati {len(utenti)} utenti")
        )

        self.stdout.write("")

        self.stdout.write("Primi utenti")

        for u in utenti[:10]:

            username = getattr(u, "sAMAccountName", "")

            nome = getattr(u, "givenName", "")

            cognome = getattr(u, "sn", "")

            self.stdout.write(
                f"  {username} - {nome} {cognome}"
            )

        self.stdout.write("")

        #
        # GRUPPI
        #

        self.stdout.write("Ricerca gruppi...")

        conn.search(
            search_base=settings.DIRECTORY["BASE_DN"],
            search_filter="(objectClass=group)",
            attributes=[
                "cn",
                "description",
            ],
        )

        gruppi = conn.entries

        self.stdout.write(
            self.style.SUCCESS(f"Trovati {len(gruppi)} gruppi")
        )

        self.stdout.write("")

        self.stdout.write("Primi gruppi")

        for g in gruppi[:20]:

            self.stdout.write(f"  {g.cn}")

        conn.unbind()

        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write(
            self.style.SUCCESS("TEST TERMINATO CON SUCCESSO")
        )
        self.stdout.write("=" * 70)
