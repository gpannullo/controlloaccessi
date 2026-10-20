from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from contextlib import nullcontext

from django.test import SimpleTestCase
from django.utils import timezone

from .password_reminders import eligible, queue_reminders


class PasswordReminderTests(SimpleTestCase):
    def test_expiry_boundaries(self):
        now = timezone.now()
        user = SimpleNamespace(is_active=True, password_senza_scadenza=False)
        for delta, expected in [(-1, False), (0, False), (1, True), (15*86400, True), (15*86400+1, False)]:
            user.scadenza_password = now + timedelta(seconds=delta)
            self.assertEqual(eligible(user, now), expected)
        user.scadenza_password = None
        self.assertFalse(eligible(user, now))
        user.scadenza_password = now + timedelta(days=1)
        user.is_active = False
        self.assertFalse(eligible(user, now))
        user.is_active = True
        user.password_senza_scadenza = True
        self.assertFalse(eligible(user, now))

    def run_queue(self, *, dry=False, duplicate=False, email='user@example.org'):
        user = SimpleNamespace(is_active=True, password_senza_scadenza=False,
            scadenza_password=timezone.now()+timedelta(days=3), email=email,
            username='test', get_full_name=lambda: '<Test>')
        with patch('comunicazioni.password_reminders.get_user_model') as model, \
             patch('comunicazioni.password_reminders.transaction.atomic', side_effect=nullcontext), \
             patch('comunicazioni.password_reminders.PromemoriaPassword') as log, \
             patch('comunicazioni.password_reminders.mail.send') as send:
            model.return_value.objects.filter.return_value.values_list.return_value.iterator.return_value = [1]
            model.return_value.objects.select_for_update.return_value.get.return_value = user
            log.objects.filter.return_value.exists.return_value = duplicate
            stats = queue_reminders(dry_run=dry)
            if dry or duplicate or not email:
                send.assert_not_called()
                log.objects.create.assert_not_called()
            else:
                send.assert_called_once()
                self.assertEqual(send.call_args.kwargs['priority'], 'medium')
                self.assertEqual(send.call_args.kwargs['expires_at'], user.scadenza_password)
                self.assertEqual(send.call_args.kwargs['template'], 'password_in_scadenza')
                self.assertEqual(send.call_args.kwargs['context']['nome'], '<Test>')
                log.objects.create.assert_called_once()
            return stats

    def test_enqueue(self):
        self.assertEqual(self.run_queue()['accodati'], 1)

    def test_dry_run(self):
        self.assertEqual(self.run_queue(dry=True)['candidati'], 1)

    def test_duplicate(self):
        self.assertEqual(self.run_queue(duplicate=True)['duplicati'], 1)

    def test_missing_email(self):
        self.assertEqual(self.run_queue(email='')['senza_email_valida'], 1)
