from .factory import DirectoryFactory
from .group_sync_service import GroupSyncService
from .user_sync_service import UserSyncService
from .membership_sync_service import MembershipSyncService


class SynchronizationService:

    def __init__(self):

        self.directory = DirectoryFactory.create()

    def run(self):

        print()
        print("=" * 70)
        print("SINCRONIZZAZIONE ACTIVE DIRECTORY")
        print("=" * 70)

        snapshot = self.directory.get_snapshot()

        group_result = GroupSyncService().sync(snapshot)

        user_result = UserSyncService().sync(snapshot)

        membership_result = MembershipSyncService().sync(snapshot)

        print()
        print("=" * 70)
        print("RIEPILOGO")
        print("=" * 70)

        print()

        print("GRUPPI")

        print(f"Creati      : {group_result.created}")
        print(f"Aggiornati  : {group_result.updated}")

        print()

        print("UTENTI")

        print(f"Creati      : {user_result.created}")
        print(f"Aggiornati  : {user_result.updated}")

        print()

        print("MEMBERSHIP")

        print(f"Aggiornate  : {membership_result.updated}")

        print()

        print("=" * 70)