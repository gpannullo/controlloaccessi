from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .sync_result import SyncResult

User = get_user_model()


class MembershipSyncService:

    def sync(self, snapshot):

        result = SyncResult()

        users = snapshot.users

        for u in users:

            try:
                user = User.objects.get(username=u["username"])
            except User.DoesNotExist:
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