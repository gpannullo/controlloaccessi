from datetime import date
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TransactionTestCase, override_settings
from protocollazione.contracts import EsitoProtocollo, EsitoIncertoError, InvioBloccatoError
from visitors.services.report_protocol_service import protocolla_report_giornaliero as process_report
from protocollazione.models import ReportGiornaliero, RegistrazioneProtocollo

CONFIG = {'OPERATORE': 'protocol-test', 'CLASSIFICAZIONE_VISITATORI': '1', 'CLASSIFICAZIONE_QR': '2',
          'UFFICIO': '1', 'FIRMATARIO': '2', 'UFFICIO_FIRMATARIO': '1'}


@override_settings(REPORT_PROTOCOLLO=CONFIG, PROTOCOLLAZIONE_ENABLED=True)
class DailyProtocolTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='protocol-test', is_active=True, is_superuser=True)
        self.day = date(2026, 1, 2)
        self.result = EsitoProtocollo('1', '2026', '123', 'C', '2026-01-03', 'segnatura')
        self.builder = patch('visitors.services.report_protocol_service._pdf', return_value=b'%PDF-test').start()
        self.backend = patch('visitors.services.report_protocol_service.get_backend').start().return_value
        self.sender = patch('protocollazione.services.get_backend').start().return_value
        self.sender.protocolla.return_value = self.result
        self.addCleanup(patch.stopall)

    def test_validation_does_not_write_or_send(self):
        process_report('qr', self.day, self.user)
        self.assertFalse(ReportGiornaliero.objects.exists())
        self.assertFalse(RegistrazioneProtocollo.objects.exists())
        self.sender.protocolla.assert_not_called()

    def test_retry_preserves_snapshot_and_sends_once(self):
        first = process_report('qr', self.day, self.user, send=True)
        with override_settings(REPORT_PROTOCOLLO={}):
            second = process_report('qr', self.day, self.user, send=True)
        self.assertEqual(first, second)
        self.builder.assert_called_once()
        self.sender.protocolla.assert_called_once()
        self.assertEqual(ReportGiornaliero.objects.count(), 1)

    def test_uncertain_never_resends(self):
        self.sender.protocolla.side_effect = EsitoIncertoError('timeout')
        with self.assertRaises(EsitoIncertoError):
            process_report('visitatori', self.day, self.user, send=True)
        with self.assertRaises(InvioBloccatoError):
            process_report('visitatori', self.day, self.user, send=True)
        self.sender.protocolla.assert_called_once()

    def test_command_continues_other_report_and_fails(self):
        with patch('visitors.management.commands.protocolla_report_giornalieri.protocolla_report_giornaliero',
                   side_effect=[ValueError('private'), self.result]) as process:
            err = StringIO()
            with self.assertRaises(CommandError):
                call_command('protocolla_report_giornalieri', data=self.day, invia=True, stdout=StringIO(), stderr=err)
            self.assertEqual(process.call_count, 2)
            self.assertNotIn('private', err.getvalue())

    def test_current_day_rejected(self):
        from django.utils import timezone
        from visitors.services.report_protocol_service import ROME
        with self.assertRaises(CommandError):
            call_command('protocolla_report_giornalieri', data=timezone.localdate(timezone=ROME))

    def test_disabled_send_creates_nothing(self):
        with override_settings(PROTOCOLLAZIONE_ENABLED=False), self.assertRaises(CommandError):
            call_command('protocolla_report_giornalieri', data=self.day, invia=True)
        self.assertFalse(ReportGiornaliero.objects.exists())

    def test_pdf_download_requires_view_permission(self):
        from django.test import RequestFactory
        from django.contrib.admin.sites import AdminSite
        from django.core.exceptions import PermissionDenied
        from protocollazione.admin import ReportGiornalieroAdmin
        process_report('qr', self.day, self.user, send=True)
        row = ReportGiornaliero.objects.get()
        admin = ReportGiornalieroAdmin(ReportGiornaliero, AdminSite())
        request = RequestFactory().get('/')
        request.user = get_user_model().objects.create(username='no-permission', is_active=True, is_staff=True)
        with self.assertRaises(PermissionDenied):
            admin.pdf(request, row.pk)
        request.user = self.user
        self.assertEqual(admin.pdf(request, row.pk).content, b'%PDF-test')
