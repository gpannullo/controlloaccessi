from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.services.timbrature_presence_service import TimbraturePresenceService, TimbratureError as ImportError
from .models import Timbratura
from .services import correggi, TimbraturaError


class StoricoAutomaticoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='badge.test', badge='0000900036')
        self.service = TimbraturePresenceService()
        day = timezone.localdate().strftime('%d%m%y')
        self.lines = ['0000900036I0000'+day+'0830', '0000900036U0000'+day+'1330']

    def test_all_movements_and_repeated_import(self):
        text = '\n'.join(self.lines + self.lines)
        self.service.importa(text)
        self.service.importa(text)
        self.assertEqual(Timbratura.objects.count(), 2)
        self.assertEqual(set(Timbratura.objects.values_list('origine', flat=True)), {'AUTOMATICO'})
        self.assertEqual(Timbratura.objects.filter(utente=self.user).count(), 2)
        self.assertFalse(Timbratura.objects.exclude(causale='0000').exists())

    def test_inactive_and_unknown_badges(self):
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.service.importa('\n'.join(self.lines + [self.lines[0].replace('0000900036', '0000000999')]))
        self.assertEqual(Timbratura.objects.count(), 2)

    def test_invalid_file_no_partial_archive(self):
        with self.assertRaises(ImportError):
            self.service.importa(self.lines[0]+'\ninvalid')
        self.assertEqual(Timbratura.objects.count(), 0)

    def test_automatic_cannot_be_corrected_even_after_badge_removed(self):
        self.service.importa(self.lines[0])
        row = Timbratura.objects.get()
        Timbratura.objects.filter(pk=row.pk).update(registrata_il=timezone.now())
        get_user_model().objects.filter(pk=self.user.pk).update(badge=None)
        with self.assertRaises(TimbraturaError):
            correggi(self.user, row.pk, 'I', None)

    def test_reassignment_does_not_move_history(self):
        self.service.importa(self.lines[0])
        get_user_model().objects.filter(pk=self.user.pk).update(badge=None)
        other = get_user_model().objects.create(username='new.owner', badge='0000900036')
        self.service.importa(self.lines[0])
        self.assertEqual(Timbratura.objects.get().utente_id, self.user.pk)
