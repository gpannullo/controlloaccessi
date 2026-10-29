from datetime import datetime, timezone as utc
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase, RequestFactory
from django.urls import reverse
from presenze_qr.models import Timbratura
from dashboard.staff_report import monthly_staff, MonthlyStaffForm, staff_monthly_report, ROME


class MonthlyStaffTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name='Servizio Civile')
        self.user = get_user_model().objects.create(username='report.test', first_name='Mario', last_name='Rossi')
        self.user.groups.add(self.group)

    def punch(self, when, verso='I', origine='QR', user=None):
        return Timbratura.objects.create(utente=user or self.user, registrata_il=when,
                                        verso=verso, verso_originale=verso, origine=origine)

    def test_leap_year_all_days_and_multiple_movements(self):
        for hour, verso in [(8,'I'), (12,'U'), (14,'I'), (17,'U')]:
            self.punch(datetime(2024,2,1,hour,tzinfo=ROME), verso)
        report = monthly_staff(self.group, 2024, 2)[0]
        self.assertEqual(len(report['giorni']), 29)
        self.assertEqual(report['giorni'][0]['giorno'], 'Giovedì')
        self.assertEqual([p['ora'] for p in report['giorni'][0]['passaggi']], ['08:00','12:00','14:00','17:00'])
        self.assertEqual(report['giorni'][1]['passaggi'], [])

    def test_local_month_bounds_and_mixed_sources(self):
        self.punch(datetime(2026,9,30,22,30,tzinfo=utc.utc))  # October 1 in Rome
        self.punch(datetime(2026,10,31,22,59,tzinfo=utc.utc), origine='AUTOMATICO')
        self.punch(datetime(2026,10,31,23,0,tzinfo=utc.utc))  # November 1
        rows = monthly_staff(self.group, 2026, 10)[0]['giorni']
        self.assertEqual(rows[0]['passaggi'][0]['ora'], '00:30')
        self.assertEqual(rows[-1]['passaggi'][0]['origine'], 'Sistema automatico')
        self.assertEqual(sum(len(r['passaggi']) for r in rows), 2)

    def test_group_scope_and_inactive_members(self):
        outsider = get_user_model().objects.create(username='outside')
        self.punch(datetime(2026,10,1,8,tzinfo=ROME), user=outsider)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        result = monthly_staff(self.group, 2026, 10)
        self.assertEqual([r['utente'].pk for r in result], [self.user.pk])
        self.assertEqual(sum(len(r['passaggi']) for r in result[0]['giorni']), 0)

    def test_december_rollover_and_empty_group(self):
        self.assertEqual(len(monthly_staff(self.group,2026,12)[0]['giorni']),31)
        self.assertEqual(monthly_staff(Group.objects.create(name='Vuoto'),2026,12),[])

    def test_invalid_input(self):
        for fields in ({'gruppo':self.group.pk,'mese':13,'anno':2026},
                       {'gruppo':self.group.pk,'mese':1,'anno':99999},
                       {'gruppo':99999,'mese':1,'anno':2026}):
            self.assertFalse(MonthlyStaffForm(fields).is_valid())

    def test_access_and_render(self):
        path = reverse('dashboard:staff_monthly_report')
        request = RequestFactory().get(path, {'gruppo':self.group.pk,'mese':2,'anno':2024})
        request.session = {}
        request._messages = FallbackStorage(request)
        request.user = AnonymousUser()
        self.assertNotEqual(staff_monthly_report(request).status_code,200)
        request.user = self.user
        self.assertNotEqual(staff_monthly_report(request).status_code,200)
        self.user.is_superuser = True
        response = staff_monthly_report(request)
        self.assertEqual(response.status_code,200)
        self.assertIn('Rossi',response.content.decode())
        self.assertIn('29/02/2024',response.content.decode())
        self.assertIn('no-store',response['Cache-Control'])
