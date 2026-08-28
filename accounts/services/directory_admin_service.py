from datetime import timezone as datetime_timezone
from django.conf import settings
from django.utils import timezone
from ldap3 import MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE
from ldap3.utils.conv import escape_filter_chars

from .active_directory_service import ActiveDirectoryService


class DirectoryAdminException(Exception):
    pass


class DirectoryAdminService(ActiveDirectoryService):
    """Scritture AD per utenti esistenti, sempre disabilitate di default."""

    def _require_writes(self):
        if not settings.DIRECTORY.get("WRITE_ENABLED", False):
            raise DirectoryAdminException(
                "Le scritture AD sono disabilitate: impostare AD_WRITE_ENABLED=True."
            )

    def _user(self, username):
        conn = self._connection()
        safe = escape_filter_chars(username.strip())
        if not conn.search(self.base_dn, "(&(objectCategory=person)(objectClass=user)(sAMAccountName=%s))" % safe, attributes=self.USER_ATTRIBUTES, size_limit=1) or not conn.entries:
            conn.unbind()
            raise DirectoryAdminException("Utente AD non trovato.")
        return conn, conn.entries[0]

    @staticmethod
    def _ok(conn, operation):
        if conn.result.get("description") != "success":
            raise DirectoryAdminException("%s non riuscita: %s" % (operation, conn.result.get("message") or conn.result.get("description")))

    def dettaglio(self, username):
        conn, entry = self._user(username)
        try:
            other_mailbox = getattr(entry, "otherMailbox", None)
            scadenza_password = None
            expiry = getattr(entry, "msDS-UserPasswordExpiryTimeComputed", None)
            if expiry and expiry.value and int(expiry.value) not in {0, 9223372036854775807}:
                scadenza_password = timezone.datetime.fromtimestamp(
                    (int(expiry.value) - 116444736000000000) / 10000000,
                    tz=datetime_timezone.utc,
                )
            uac = int(entry.userAccountControl.value or 0)
            return {
                "first_name": str(entry.givenName or ""),
                "last_name": str(entry.sn or ""),
                "email": str(entry.mail or ""),
                "personal_email": other_mailbox.values[0] if other_mailbox and other_mailbox.values else "",
                "mobile": str(entry.mobile or ""),
                "badge": str(entry.employeeID.value or "") if getattr(entry, "employeeID", None) else "",
                "active": not bool(uac & 2),
                "password_expiry": scadenza_password,
                "password_never_expires": bool(uac & 0x10000),
                "groups": sorted([dn.split(",", 1)[0][3:] for dn in entry.memberOf.values], key=str.casefold) if hasattr(entry, "memberOf") else [],
            }
        finally:
            conn.unbind()

    def aggiorna_anagrafica(self, username, first_name, last_name, personal_email, mobile):
        self._require_writes(); conn, entry = self._user(username)
        try:
            changes = {}
            for attribute, value in {
                "givenName": first_name.strip(),
                "sn": last_name.strip(),
                "otherMailbox": personal_email.strip(),
                "mobile": mobile.strip(),
            }.items():
                if value:
                    changes[attribute] = [
                        (MODIFY_REPLACE, [value])
                    ]
                elif getattr(entry, attribute).value:
                    changes[attribute] = [
                        (MODIFY_DELETE, [])
                    ]
            conn.modify(entry.entry_dn, changes)
            self._ok(conn, "Aggiornamento anagrafica")
        finally:
            conn.unbind()

    def imposta_badge(self, username, badge):
        """Allinea il badge locale con l'attributo standard AD employeeID."""
        self._require_writes()
        conn, entry = self._user(username)
        try:
            valore = (badge or "").strip()
            modifica = (
                [(MODIFY_REPLACE, [valore])]
                if valore
                else [(MODIFY_DELETE, [])]
            )
            conn.modify(entry.entry_dn, {"employeeID": modifica})
            self._ok(conn, "Aggiornamento badge")
        finally:
            conn.unbind()

    def imposta_attivo(self, username, attivo):
        self._require_writes(); conn, entry = self._user(username)
        try:
            uac = int(entry.userAccountControl.value or 0); uac = uac & ~2 if attivo else uac | 2
            conn.modify(entry.entry_dn, {"userAccountControl": [(MODIFY_REPLACE, [str(uac)])]}); self._ok(conn, "Aggiornamento stato account")
        finally:
            conn.unbind()

    def reset_password(self, username, password, force_change):
        self._require_writes()
        if not settings.DIRECTORY.get("USE_SSL", False):
            raise DirectoryAdminException("Il reset password richiede LDAPS (AD_USE_SSL=True).")
        conn, entry = self._user(username)
        try:
            changes = {"unicodePwd": [(MODIFY_REPLACE, [f'"{password}"'.encode("utf-16-le")])]}
            if force_change: changes["pwdLastSet"] = [(MODIFY_REPLACE, ["0"])]
            conn.modify(entry.entry_dn, changes); self._ok(conn, "Reset password")
        finally:
            conn.unbind()

    def cambia_password_iniziale(self, username, password):
        """Imposta la password e abilita la sua normale scadenza AD.

        È usato sia dal primo cambio obbligatorio sia dal cambio volontario.
        Se presente, rimuove esclusivamente il bit DONT_EXPIRE_PASSWD,
        preservando tutti gli altri flag dell'account.
        """
        self._require_writes()
        if not settings.DIRECTORY.get("USE_SSL", False):
            raise DirectoryAdminException("Il cambio password richiede LDAPS (AD_USE_SSL=True).")
        conn, entry = self._user(username)
        try:
            user_account_control = int(entry.userAccountControl.value or 0)
            changes = {
                "unicodePwd": [(MODIFY_REPLACE, [('"%s"' % password).encode("utf-16-le")])],
                # -1 fa impostare ad AD l'istante corrente, rimuovendo pwdLastSet=0.
                "pwdLastSet": [(MODIFY_REPLACE, ["-1"])],
            }
            if user_account_control & 0x10000:
                changes["userAccountControl"] = [
                    (MODIFY_REPLACE, [str(user_account_control & ~0x10000)])
                ]

            conn.modify(entry.entry_dn, changes)
            self._ok(conn, "Cambio password e attivazione scadenza")
        finally:
            conn.unbind()

    def rimuovi_password_senza_scadenza(self, username):
        """Rimuove il solo flag DONT_EXPIRE_PASSWD dopo un cambio riuscito."""
        self._require_writes()
        conn, entry = self._user(username)
        try:
            user_account_control = int(entry.userAccountControl.value or 0)
            if not user_account_control & 0x10000:
                return
            conn.modify(
                entry.entry_dn,
                {
                    "userAccountControl": [
                        (MODIFY_REPLACE, [str(user_account_control & ~0x10000)])
                    ]
                },
            )
            self._ok(conn, "Attivazione scadenza password")
        finally:
            conn.unbind()

    def aggiorna_gruppi(self, username, nomi):
        self._require_writes(); conn, entry = self._user(username)
        try:
            current = set(entry.memberOf.values if hasattr(entry, "memberOf") else []); target = set()
            for nome in nomi:
                safe = escape_filter_chars(nome)
                if not conn.search(self.base_dn, "(&(objectClass=group)(cn=%s))" % safe, attributes=[], size_limit=1) or not conn.entries: raise DirectoryAdminException("Gruppo AD non trovato: %s." % nome)
                target.add(conn.entries[0].entry_dn)
            for dn in current - target: conn.modify(dn, {"member": [(MODIFY_DELETE, [entry.entry_dn])]}); self._ok(conn, "Rimozione gruppo")
            for dn in target - current: conn.modify(dn, {"member": [(MODIFY_ADD, [entry.entry_dn])]}); self._ok(conn, "Aggiunta gruppo")
        finally:
            conn.unbind()

    def rimuovi_da_gruppo(self, username, nome_gruppo):
        """Rimuove una sola appartenenza diretta, senza alterare gli altri gruppi AD."""
        self._require_writes()
        conn, entry = self._user(username)
        try:
            safe = escape_filter_chars(nome_gruppo.strip())
            if not conn.search(
                self.base_dn,
                "(&(objectClass=group)(cn=%s))" % safe,
                attributes=[],
                size_limit=1,
            ) or not conn.entries:
                raise DirectoryAdminException("Gruppo AD non trovato: %s." % nome_gruppo)
            conn.modify(conn.entries[0].entry_dn, {"member": [(MODIFY_DELETE, [entry.entry_dn])]})
            self._ok(conn, "Rimozione assegnazione ufficio")
        finally:
            conn.unbind()

    def aggiungi_utente_al_gruppo(self, username, nome_gruppo):
        """Aggiunge l'utente a un singolo gruppo AD, senza toccare le altre appartenenze."""
        self._require_writes()
        conn, entry = self._user(username)
        try:
            safe = escape_filter_chars(nome_gruppo.strip())
            if not conn.search(
                self.base_dn,
                "(&(objectClass=group)(cn=%s))" % safe,
                attributes=[],
                size_limit=1,
            ) or not conn.entries:
                raise DirectoryAdminException("Gruppo AD non trovato: %s." % nome_gruppo)
            conn.modify(conn.entries[0].entry_dn, {"member": [(MODIFY_ADD, [entry.entry_dn])]})
            self._ok(conn, "Aggiunta gruppo AD")
        finally:
            conn.unbind()

    def imposta_mail_istituzionale(self, username, dominio=None):
        """Aggiorna mail/UPN e l'appartenenza al gruppo MDAEMON."""
        self._require_writes()
        conn, entry = self._user(username)
        try:
            if dominio:
                indirizzo = "%s@%s" % (username.strip(), dominio.strip().lower())
                conn.modify(entry.entry_dn, {
                    "mail": [(MODIFY_REPLACE, [indirizzo])],
                    "userPrincipalName": [(MODIFY_REPLACE, [indirizzo])],
                })
                self._ok(conn, "Aggiornamento mail istituzionale")
                nome_gruppo, modifica = "MDAEMON", MODIFY_ADD
            else:
                changes = {
                    "userPrincipalName": [(MODIFY_REPLACE, ["%s@%s" % (username.strip(), settings.DIRECTORY["DOMAIN"])])],
                }
                if getattr(entry, "mail", None) and entry.mail.value:
                    changes["mail"] = [(MODIFY_DELETE, [])]
                conn.modify(entry.entry_dn, changes)
                self._ok(conn, "Rimozione mail istituzionale")
                nome_gruppo, modifica = "MDAEMON", MODIFY_DELETE
            safe = escape_filter_chars(nome_gruppo)
            if not conn.search(self.base_dn, "(&(objectClass=group)(cn=%s))" % safe, attributes=[], size_limit=1) or not conn.entries:
                raise DirectoryAdminException("Gruppo AD non trovato: MDAEMON.")
            gruppo_dn = conn.entries[0].entry_dn
            appartiene = gruppo_dn in set(entry.memberOf.values if hasattr(entry, "memberOf") else [])
            if (dominio and not appartiene) or (not dominio and appartiene):
                conn.modify(gruppo_dn, {"member": [(modifica, [entry.entry_dn])]})
                self._ok(conn, "Aggiornamento gruppo MDAEMON")
            return indirizzo if dominio else ""
        finally:
            conn.unbind()

    def allinea_mail_da_upn(self):
        """Valorizza ``mail`` solo quando è assente, copiando il relativo UPN."""
        self._require_writes()
        conn = self._connection()
        aggiornati, saltati, errori = [], 0, []
        try:
            conn.search(
                self.base_dn,
                "(&(objectCategory=person)(objectClass=user))",
                attributes=["sAMAccountName", "mail", "userPrincipalName"],
            )
            for entry in conn.entries:
                username = str(entry.sAMAccountName or "").strip()
                mail = str(entry.mail or "").strip()
                upn = str(entry.userPrincipalName or "").strip()
                if mail:
                    saltati += 1
                    continue
                if not username or "@" not in upn:
                    errori.append(username or entry.entry_dn)
                    continue
                if conn.modify(entry.entry_dn, {"mail": [(MODIFY_REPLACE, [upn])]}):
                    aggiornati.append({"username": username, "email": upn})
                else:
                    errori.append(username)
            return aggiornati, saltati, errori
        finally:
            conn.unbind()

    def crea_utente(self, username, first_name, last_name, email, personal_email, mobile, password=None, upn_domain=None):
        self._require_writes()
        if not settings.DIRECTORY.get("USE_SSL", False):
            raise DirectoryAdminException("La creazione con password richiede LDAPS.")
        display_name = " ".join(item for item in [first_name.strip(), last_name.strip()] if item) or username.strip()
        # Il CN deve essere univoco anche per utenti omonimi: lo username è già
        # normalizzato e verificato in AD prima della creazione.
        dn = "CN=%s,%s" % (username.strip(), settings.DIRECTORY["USER_SEARCH_BASE"])
        conn = self._connection()
        try:
            if self.username_esiste(username, conn=conn):
                raise DirectoryAdminException("Lo username %s esiste già in Active Directory." % username)
            attributes = {
                "sAMAccountName": username.strip(),
                "userPrincipalName": "%s@%s" % (username.strip(), upn_domain or settings.DIRECTORY["DOMAIN"]),
                "givenName": first_name.strip(),
                "sn": last_name.strip(),
                "displayName": display_name,
                # L'utente resta disabilitato finché password e cambio obbligatorio
                # non sono stati impostati correttamente sulla connessione LDAPS.
                "userAccountControl": 514,
            }
            if email.strip(): attributes["mail"] = email.strip()
            if personal_email.strip(): attributes["otherMailbox"] = personal_email.strip()
            if mobile.strip(): attributes["mobile"] = mobile.strip()
            if not conn.add(dn, ["top", "person", "organizationalPerson", "user"], attributes):
                self._ok(conn, "Creazione utente")
            if password:
                # unicodePwd non si può valorizzare con LDAP Add: AD richiede una
                # modifica separata su canale LDAPS/TLS.
                conn.modify(dn, {
                    "unicodePwd": [(MODIFY_REPLACE, [('"%s"' % password).encode("utf-16-le")])],
                    "pwdLastSet": [(MODIFY_REPLACE, ["0"])],
                    "userAccountControl": [(MODIFY_REPLACE, ["512"])],
                })
                self._ok(conn, "Impostazione password e attivazione account")
            return dn
        finally:
            conn.unbind()

    def username_esiste(self, username, conn=None):
        """Verifica lo username in AD; ``conn`` evita un secondo bind durante la creazione."""
        owns_connection = conn is None
        conn = conn or self._connection()
        try:
            safe = escape_filter_chars(username.strip())
            return bool(
                conn.search(
                    self.base_dn,
                    "(&(objectCategory=person)(objectClass=user)(sAMAccountName=%s))" % safe,
                    attributes=[],
                    size_limit=1,
                )
                and conn.entries
            )
        finally:
            if owns_connection:
                conn.unbind()

    def aggiungi_al_gruppo(self, user_dn, nome_gruppo):
        """Aggiunge un nuovo account al solo gruppo operativo assegnato dall'ufficio."""
        self._require_writes()
        conn = self._connection()
        try:
            safe = escape_filter_chars(nome_gruppo.strip())
            if not conn.search(
                self.base_dn,
                "(&(objectClass=group)(cn=%s))" % safe,
                attributes=[],
                size_limit=1,
            ) or not conn.entries:
                raise DirectoryAdminException("Gruppo AD non trovato: %s." % nome_gruppo)
            conn.modify(conn.entries[0].entry_dn, {"member": [(MODIFY_ADD, [user_dn])]})
            self._ok(conn, "Assegnazione gruppo operativo")
        finally:
            conn.unbind()

    def lista_gruppi(self):
        conn = self._connection()
        try:
            conn.search(self.base_dn, "(objectClass=group)", attributes=["cn", "description", "member"])
            return sorted([{"name": str(entry.cn), "description": str(entry.description or ""), "members": [dn.split(",", 1)[0][3:] for dn in entry.member.values] if hasattr(entry, "member") else []} for entry in conn.entries], key=lambda item: item["name"].casefold())
        finally:
            conn.unbind()

    def rinomina_gruppo(self, nome, nuovo_nome):
        self._require_writes(); conn = self._connection()
        try:
            safe = escape_filter_chars(nome)
            if not conn.search(self.base_dn, "(&(objectClass=group)(cn=%s))" % safe, attributes=[], size_limit=1) or not conn.entries: raise DirectoryAdminException("Gruppo AD non trovato.")
            conn.modify_dn(conn.entries[0].entry_dn, "CN=%s" % nuovo_nome.strip()); self._ok(conn, "Rinomina gruppo")
        finally:
            conn.unbind()
