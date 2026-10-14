from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .sync_result import SyncResult
from .directory_identity import find_directory_user

User = get_user_model()


class MembershipSyncService:

    def sync(self, snapshot):

        result = SyncResult()

        users = snapshot.users

        for u in users:

            user = find_directory_user(u['username'])
            if user is None:
                continue

            user.groups.clear()

            for group_name in u.get("groups", []):

                try:
                    group = Group.objects.get(name=group_name)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    continue

            result.add_updated()

        return result
