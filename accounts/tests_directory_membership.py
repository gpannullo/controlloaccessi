from unittest.mock import Mock
from django.test import SimpleTestCase
from accounts.services.directory_admin_service import DirectoryAdminService, DirectoryAdminException

class MembershipTests(SimpleTestCase):
    def setUp(self):
        self.service = DirectoryAdminService.__new__(DirectoryAdminService)
        self.conn = Mock()

    def check(self):
        self.service._ensure_group_member(self.conn, 'CN=Group,DC=test', 'CN=User,DC=test')

    def test_existing_membership_no_write(self):
        self.conn.result = {'result': 6}
        self.check()
        self.conn.modify.assert_not_called()

    def test_missing_membership_added(self):
        self.conn.result = {'result': 5}
        self.conn.modify.side_effect = lambda *args: setattr(self.conn, 'result', {'result': 0, 'description': 'success'})
        self.check()
        self.conn.modify.assert_called_once()

    def test_race_duplicate_verified(self):
        for code in (20, 68):
            self.conn = Mock()
            results = iter([5, 6])
            self.conn.compare.side_effect = lambda *args: setattr(self.conn, 'result', {'result': next(results)})
            self.conn.modify.side_effect = lambda *args: setattr(self.conn, 'result', {'result': code})
            self.check()
            self.assertEqual(self.conn.compare.call_count, 2)

    def test_compare_failure_not_ignored(self):
        self.conn.result = {'result': 50, 'description': 'insufficientAccessRights'}
        with self.assertRaises(DirectoryAdminException): self.check()
        self.conn.modify.assert_not_called()

    def test_write_failure_not_ignored(self):
        self.conn.result = {'result': 5}
        self.conn.modify.side_effect = lambda *args: setattr(self.conn, 'result', {'result': 50, 'description': 'insufficientAccessRights'})
        with self.assertRaises(DirectoryAdminException): self.check()

    def test_unconfirmed_duplicate_not_ignored(self):
        self.conn.compare.side_effect = lambda *args: setattr(self.conn, 'result', {'result': 5})
        self.conn.modify.side_effect = lambda *args: setattr(self.conn, 'result', {'result': 68})
        with self.assertRaises(DirectoryAdminException): self.check()
