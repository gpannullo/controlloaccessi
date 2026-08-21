from datetime import datetime
from datetime import timezone as datetime_timezone

import ssl
from pathlib import Path

from ldap3 import ALL, Connection, MODIFY_ADD, MODIFY_DELETE, Server, SUBTREE, Tls
from ldap3.core.exceptions import LDAPBindError
from django.conf import settings
from ldap3.utils.conv import escape_filter_chars

from .directory_service import DirectoryService
from .directory_snapshot import DirectorySnapshot


class ActiveDirectoryService(DirectoryService):
    USER_ATTRIBUTES = [
        "sAMAccountName",
        "givenName",
        "sn",
        "mail",
        "otherMailbox",
        "mobile",
        "memberOf",
        "userAccountControl",
        "msDS-UserPasswordExpiryTimeComputed",
    ]

    GROUP_ATTRIBUTES = [
        "cn",
        "description",
        "objectSid",
    ]

    def __init__(self):
        server_name = settings.DIRECTORY["SERVER"].removeprefix("ldap://").removeprefix("ldaps://").rstrip("/")
        ca_cert_file = settings.DIRECTORY.get("TLS_CA_CERT_FILE")
        ca_cert_data = None
        if ca_cert_file:
            cert_bytes = Path(ca_cert_file).read_bytes()
            ca_cert_data = (
                cert_bytes.decode("ascii")
                if cert_bytes.lstrip().startswith(b"-----BEGIN CERTIFICATE-----")
                else ssl.DER_cert_to_PEM_cert(cert_bytes)
            )
        tls = Tls(
            validate=ssl.CERT_REQUIRED if settings.DIRECTORY.get("TLS_VALIDATE", True) else ssl.CERT_NONE,
            ca_certs_data=ca_cert_data,
        )
        self.server = Server(
            server_name,
            port=settings.DIRECTORY["PORT"],
            use_ssl=settings.DIRECTORY["USE_SSL"],
            tls=tls,
            get_info=ALL,
        )

        self.base_dn = settings.DIRECTORY["BASE_DN"]
        self.bind_user = settings.DIRECTORY["BIND_USER"]
        self.bind_password = settings.DIRECTORY["BIND_PASSWORD"]
        self.domain = settings.DIRECTORY["DOMAIN"]

    def get_snapshot(self):
        snapshot = DirectorySnapshot()
        snapshot.groups = self.get_groups()
        snapshot.users = self.get_users()
        snapshot.generated_at = datetime.now().isoformat()
        return snapshot

    def _connection(self):

        conn = Connection(
            self.server,
            user=self.bind_user,
            password=self.bind_password,
            auto_bind=True,
        )

        return conn

    def authenticate(self, username: str, password: str) -> bool:

        return self.authentication_status(username, password) == "authenticated"

    def cambia_password_personale(self, username: str, password_attuale: str, nuova_password: str):
        """Cambio password eseguito con le credenziali dell'utente.

        La richiesta LDAP contiene delete/add di unicodePwd, anziché un reset
        amministrativo. In questo modo AD applica le policy effettive
        dell'utente, incluso lo storico delle password.
        """
        try:
            conn = Connection(
                self.server,
                user=f"{username.strip()}@{self.domain}",
                password=password_attuale,
                auto_bind=True,
            )
        except LDAPBindError as exc:
            raise ValueError("La password attuale non è corretta.") from exc

        safe_username = escape_filter_chars(username.strip())
        try:
            found = conn.search(
                search_base=self.base_dn,
                search_filter=(
                    "(&(objectCategory=person)(objectClass=user)"
                    f"(sAMAccountName={safe_username}))"
                ),
                search_scope=SUBTREE,
                attributes=[],
                size_limit=1,
            )
            if not found or not conn.entries:
                raise ValueError("Utente Active Directory non trovato.")

            old_value = ('"%s"' % password_attuale).encode("utf-16-le")
            new_value = ('"%s"' % nuova_password).encode("utf-16-le")
            conn.modify(
                conn.entries[0].entry_dn,
                {
                    "unicodePwd": [
                        (MODIFY_DELETE, [old_value]),
                        (MODIFY_ADD, [new_value]),
                    ]
                },
            )
            if conn.result.get("description") != "success":
                description = conn.result.get("description", "")
                message = conn.result.get("message", "")
                if description == "constraintViolation":
                    raise ValueError(
                        "La nuova password non rispetta la policy Active Directory "
                        "(complessità, lunghezza, storico o età minima)."
                    )
                raise ValueError(
                    "Cambio password non riuscito: %s" % (message or description)
                )
        finally:
            conn.unbind()

    def authentication_status(self, username: str, password: str) -> str:
        """Restituisce anche il caso AD ``data 773``: password da cambiare."""

        try:
            conn = Connection(
                self.server,
                user=f"{username}@{self.domain}",
                password=password,
                auto_bind=True,
            )

            stato = "authenticated" if conn.bound else "invalid"
            conn.unbind()
            return stato
        except LDAPBindError as exc:
            # Active Directory restituisce 773 quando le credenziali sono
            # corrette ma la password provvisoria deve essere cambiata.
            return "password_change_required" if "773" in str(exc) else "invalid"
        except Exception:
            return "invalid"

    def get_groups(self):

        conn = self._connection()

        conn.search(
            search_base=self.base_dn,
            search_filter="(objectClass=group)",
            attributes=self.GROUP_ATTRIBUTES,
        )

        groups = []

        for entry in conn.entries:
            groups.append({
                "name": str(entry.cn),
                "description": str(entry.description) if entry.description else "",
                "sid": str(entry.objectSid) if entry.objectSid else "",
            })

        conn.unbind()

        return groups

    def get_users(self):

        conn = self._connection()

        conn.search(
            search_base=self.base_dn,
            search_filter="(&(objectCategory=person)(objectClass=user))",
            attributes=self.USER_ATTRIBUTES,
        )

        users = []

        for entry in conn.entries:

            member_of = []

            if hasattr(entry, "memberOf"):

                for group in entry.memberOf.values:
                    cn = group.split(",")[0].replace("CN=", "")

                    member_of.append(cn)

            disabled = False
            password_expiry = None
            password_never_expires = False

            if hasattr(entry, "userAccountControl"):
                uac = int(entry.userAccountControl.value)

                disabled = bool(uac & 2)
                password_never_expires = bool(uac & 0x10000)
            expiry = getattr(entry, "msDS-UserPasswordExpiryTimeComputed", None)
            if expiry and expiry.value and int(expiry.value) not in {0, 9223372036854775807}:
                password_expiry = datetime.fromtimestamp((int(expiry.value) - 116444736000000000) / 10000000, tz=datetime_timezone.utc)

            users.append({

                "username": str(entry.sAMAccountName),

                "first_name": str(entry.givenName)
                if entry.givenName else "",

                "last_name": str(entry.sn)
                if entry.sn else "",

                "email": str(entry.mail)
                if entry.mail else "",

                "personal_email": entry.otherMailbox.values[0] if hasattr(entry, "otherMailbox") and entry.otherMailbox.values else "",
                "mobile": str(entry.mobile) if entry.mobile else "",

                "groups": member_of,

                "active": not disabled,
                "password_expiry": password_expiry,
                "password_never_expires": password_never_expires,

            })

        conn.unbind()

        return users

    def get_user_groups(self, username: str) -> list[str]:
        """
        Restituisce i gruppi AD direttamente associati all'utente.
        """

        safe_username = escape_filter_chars(username.strip())

        conn = self._connection()

        try:
            found = conn.search(
                search_base=self.base_dn,
                search_filter=(
                    "(&(objectCategory=person)"
                    "(objectClass=user)"
                    f"(sAMAccountName={safe_username}))"
                ),
                search_scope=SUBTREE,
                attributes=["memberOf"],
                size_limit=1,
            )

            if not found or not conn.entries:
                return []

            entry = conn.entries[0]
            groups = []

            for group_dn in entry.memberOf.values:
                first_component = group_dn.split(",", 1)[0]

                if first_component.upper().startswith("CN="):
                    groups.append(first_component[3:])

            return groups

        finally:
            conn.unbind()
