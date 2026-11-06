from django.contrib.auth import get_user_model

from .sync_result import SyncResult
from .directory_identity import get_or_create_directory_user
from django.db import transaction
from accounts.services.directory_admin_service import DirectoryAdminService
from django.conf import settings

User = get_user_model()


class UserSyncService:

    def sync(self, snapshot):

        result = SyncResult()

        users = snapshot.users

        for u in users:

            with transaction.atomic():
                user, created = get_or_create_directory_user(u['username'])
                defaults = {
                    "first_name": u.get("first_name", ""),
                    "last_name": u.get("last_name", ""),
                    "email": u.get("email", ""),
                    "is_active": u["active"],
                    "scadenza_password": u.get("password_expiry"),
                    "scadenza_account": u.get("account_expiry"),
                    "password_senza_scadenza": u.get("password_never_expires", False),
                    "email_personale": u.get("personal_email", ""),
                    "cellulare_personale": u.get("mobile", ""),
                    "badge": u.get("badge") or None,
                }
                for field, value in defaults.items():
                    setattr(user, field, value)
                user.save(update_fields=list(defaults))

                desired_name = " ".join(part for part in [u.get("last_name", "").strip(), u.get("first_name", "").strip()] if part)
                if desired_name and settings.DIRECTORY.get("WRITE_ENABLED", False) and u.get("directory_name", "") != desired_name:
                    try:
                        DirectoryAdminService().aggiorna_nome_directory(u["username"], desired_name)
                    except Exception:
                        # Il sync locale non deve fallire se la scrittura AD è temporaneamente indisponibile.
                        pass

            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])

            if created:
                result.add_created()
            else:
                result.add_updated()

        return result
