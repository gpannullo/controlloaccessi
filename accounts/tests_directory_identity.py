from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from accounts.authentication.backend import ActiveDirectoryBackend
from accounts.services.directory_identity import get_or_create_directory_user
from accounts.services.user_sync_service import UserSyncService


class DirectoryIdentityTests(TestCase):
    def login(self, username, valid=True):
        with patch('accounts.authentication.backend.DirectoryFactory.get_service') as factory, patch('accounts.authentication.backend.AuditService.log'):
            factory.return_value.authenticate.return_value = valid
            factory.return_value.get_user_groups.return_value = []
            return ActiveDirectoryBackend().authenticate(None, username=username, password='test-only')

    def test_existing_lowercase_reused(self):
        original = get_user_model().objects.create(username='g.pannullo')
        for name in ('G.pannullo', 'G.PANNULLO', ' g.Pannullo '):
            self.assertEqual(self.login(name).pk, original.pk)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_existing_mixed_case_reused_without_renaming(self):
        original = get_user_model().objects.create(username='G.Pannullo')
        self.assertEqual(self.login('g.pannullo').pk, original.pk)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_legacy_duplicates_choose_same_identity(self):
        get_user_model().objects.create(username='G.pannullo')
        original = get_user_model().objects.create(username='g.pannullo')
        for name in ('G.pannullo', 'g.pannullo', 'G.PANNULLO'):
            self.assertEqual(self.login(name).pk, original.pk)
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_new_user_canonical_and_invalid_login_creates_nothing(self):
        self.assertIsNone(self.login('New.User', valid=False))
        self.assertEqual(get_user_model().objects.count(), 0)
        first = self.login('New.User')
        self.assertEqual(first.username, 'new.user')
        self.assertEqual(self.login('NEW.USER').pk, first.pk)

    def test_sync_does_not_recreate_mixed_case(self):
        original = get_user_model().objects.create(username='g.pannullo')
        UserSyncService().sync(SimpleNamespace(users=[{'username':'G.PANNULLO','active':True,'first_name':'Giuseppe'}]))
        original.refresh_from_db()
        self.assertEqual(original.first_name, 'Giuseppe')
        self.assertEqual(get_user_model().objects.count(), 1)
