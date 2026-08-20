from datetime import datetime

import ssl
from pathlib import Path

from ldap3 import Server, Connection, ALL, SUBTREE, Tls
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

        try:

            conn = Connection(
                self.server,
                user=f"{username}@{self.domain}",
                password=password,
                auto_bind=True,
            )

            return conn.bound

        except Exception:

            return False

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

            if hasattr(entry, "userAccountControl"):
                uac = int(entry.userAccountControl.value)

                disabled = bool(uac & 2)

            users.append({

                "username": str(entry.sAMAccountName),

                "first_name": str(entry.givenName)
                if entry.givenName else "",

                "last_name": str(entry.sn)
                if entry.sn else "",

                "email": str(entry.mail)
                if entry.mail else "",

                "groups": member_of,

                "active": not disabled,

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
