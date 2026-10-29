from datetime import datetime, timezone
from django.test import SimpleTestCase
from .admin import rome_time

class RomeDisplayTests(SimpleTestCase):
    def test_summer(self):
        self.assertEqual(rome_time(datetime(2026, 10, 20, 10, tzinfo=timezone.utc)),
                         '20/10/2026 12:00:00 CEST (UTC+0200)')

    def test_winter(self):
        self.assertEqual(rome_time(datetime(2026, 12, 20, 10, tzinfo=timezone.utc)),
                         '20/12/2026 11:00:00 CET (UTC+0100)')

    def test_midnight(self):
        self.assertTrue(rome_time(datetime(2026, 10, 20, 23, tzinfo=timezone.utc)).startswith('21/10/2026 01:00:00'))
