from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.services.factory import DirectoryFactory
from audit.services.audit_service import AuditService

User = get_user_model()


class ActiveDirectoryBackend(BaseBackend):
    """
    Backend di autenticazione su Active Directory.
    """

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs,
    ):
        if not username or not password:
            return None

        username = username.strip()
        directory = DirectoryFactory.get_service()

        if not directory.authenticate(username, password):
            return None

        ad_groups = {
            group_name.casefold()
            for group_name in directory.get_user_groups(username)
        }

        staff_groups = {
            group_name.casefold()
            for group_name in settings.DIRECTORY.get(
                "DJANGO_STAFF_GROUPS",
                [],
            )
        }

        superuser_groups = {
            group_name.casefold()
            for group_name in settings.DIRECTORY.get(
                "DJANGO_SUPERUSER_GROUPS",
                [],
            )
        }

        is_superuser = bool(ad_groups & superuser_groups)
        is_staff = is_superuser or bool(ad_groups & staff_groups)

        user, _ = User.objects.get_or_create(
            username=username,
        )

        fields_to_update = []

        if not user.is_active:
            user.is_active = True
            fields_to_update.append("is_active")

        if user.is_staff != is_staff:
            user.is_staff = is_staff
            fields_to_update.append("is_staff")

        if user.is_superuser != is_superuser:
            user.is_superuser = is_superuser
            fields_to_update.append("is_superuser")

        if fields_to_update:
            user.save(update_fields=fields_to_update)

        AuditService.log(
            user=user,
            tipo="LOGIN",
            descrizione=(
                "Accesso tramite Active Directory. "
                f"Staff: {is_staff}; superuser: {is_superuser}."
            ),
        )

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None