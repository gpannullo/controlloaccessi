from django.contrib.auth import get_user_model

from .sync_result import SyncResult

User = get_user_model()


class UserSyncService:

    def sync(self, snapshot):

        result = SyncResult()

        users = snapshot.users

        for u in users:

            user, created = User.objects.update_or_create(
                username=u["username"],
                defaults={
                    "first_name": u.get("first_name", ""),
                    "last_name": u.get("last_name", ""),
                    "email": u.get("email", ""),
                    "is_active": u["active"],
                    "scadenza_password": u.get("password_expiry"),
                    "password_senza_scadenza": u.get("password_never_expires", False),
                    "email_personale": u.get("personal_email", ""),
                    "cellulare_personale": u.get("mobile", ""),
                    "badge": u.get("badge") or None,
                }
            )

            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])

            if created:
                result.add_created()
            else:
                result.add_updated()

        return result
