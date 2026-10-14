from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from django.core.management import call_command
from comunicazioni.management.commands.password_campaign_2026 import changed, END

class CampaignTests(SimpleTestCase):
    def test_password_change(self):
        row = SimpleNamespace(pwd_last_set='123', ad_guid='abc')
        self.assertFalse(changed(row, {'pwd':'123', 'guid':'abc'}))
        self.assertTrue(changed(row, {'pwd':'124', 'guid':'abc'}))
        self.assertTrue(changed(row, {'pwd':'123', 'guid':'def'}))

    def test_end_no_ldap_or_email(self):
        with patch('comunicazioni.management.commands.password_campaign_2026.timezone.now', return_value=END), patch('comunicazioni.management.commands.password_campaign_2026.directory_state') as ldap:
            call_command('password_campaign_2026')
            ldap.assert_not_called()
