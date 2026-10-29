from datetime import datetime, date, timezone as tz
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Timbratura
from .qr_report import report_rows, build_qr_report

class QRReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='qr.report', is_active=False)

    def test_date_rome_and_only_qr_without_ten_row_limit(self):
        for minute in range(12):
            Timbratura.objects.create(utente=self.user, origine='QR', verso='I', verso_originale='I',
                registrata_il=datetime(2026,10,20,22,minute,tzinfo=tz.utc))
        Timbratura.objects.create(utente=self.user, origine='AUTOMATICO', verso='I', verso_originale='I',
            registrata_il=datetime(2026,10,21,8,tzinfo=tz.utc))
        Timbratura.objects.create(utente=self.user, origine='QR', verso='I', verso_originale='I',
            registrata_il=datetime(2026,10,21,22,tzinfo=tz.utc))
        rows = report_rows(date(2026,10,21),date(2026,10,21),datetime(2026,10,22,tzinfo=tz.utc))
        self.assertEqual(rows.count(),12)
        pdf=build_qr_report(rows,date(2026,10,21),date(2026,10,21),datetime(2026,10,22,tzinfo=tz.utc),'Test')
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_empty_pdf(self):
        pdf=build_qr_report([],date(2026,10,21),date(2026,10,21),datetime(2026,10,22,tzinfo=tz.utc),'Test')
        self.assertTrue(pdf.startswith(b'%PDF'))
