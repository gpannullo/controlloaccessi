from datetime import datetime, timezone as tz
from unittest.mock import patch
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from visitors.report_views import VisitorReportForm, report_period_context


class ReportPageTests(SimpleTestCase):
    def test_period_uses_rome_at_midnight(self):
        with patch('django.utils.timezone.now', return_value=datetime(2026,10,20,23,30,tzinfo=tz.utc)):
            context = report_period_context()
        self.assertEqual(context['report_today'].isoformat(), '2026-10-21')
        self.assertEqual(context['report_yesterday'].isoformat(), '2026-10-20')

    def test_both_forms_render_navigation_and_dates(self):
        context = report_period_context()
        context['form'] = VisitorReportForm(initial={'dal':context['report_yesterday'],'al':context['report_yesterday']})
        for template in ('visitors/report_visitatori.html','presenze_qr/report.html'):
            html = render_to_string(template, context)
            self.assertIn('report-qr/',html)
            self.assertIn('HH:mm:ss',html)
            self.assertIn('?dal='+context['report_yesterday'].isoformat(),html)
            self.assertIn('name="formato" value="pdf"',html)

    def test_invalid_period_rejected(self):
        self.assertFalse(VisitorReportForm({'dal':'2026-10-21','al':'2026-10-20'}).is_valid())
