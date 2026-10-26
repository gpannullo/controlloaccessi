from datetime import datetime
from types import SimpleNamespace
from django.test import SimpleTestCase
from accounts.services.statino_servizio_civile import _normalizza, _coppie


class StatinoServizioCivileTests(SimpleTestCase):
    def test_tolleranza_orari(self):
        self.assertEqual(_normalizza(datetime.strptime('08:33', '%H:%M').time(), 'I').strftime('%H:%M'), '08:30')
        self.assertEqual(_normalizza(datetime.strptime('13:33', '%H:%M').time(), 'U').strftime('%H:%M'), '13:30')

    def test_coppia_e_durata(self):
        base = datetime(2026, 10, 1)
        rows = [SimpleNamespace(verso='I', registrata_il=base.replace(hour=8, minute=32)), SimpleNamespace(verso='U', registrata_il=base.replace(hour=13, minute=33))]
        result = _coppie(rows)
        self.assertEqual(result[0][2].total_seconds(), 5 * 3600)
