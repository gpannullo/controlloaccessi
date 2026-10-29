from datetime import timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from prenotazioni import wordpress_connector as connector


class BookingTimezoneTests(SimpleTestCase):
    def test_summer_and_winter(self):
        for date, offset in [('2026-10-15T15:25', 2), ('2026-12-15T15:25', 1)]:
            parsed = connector._parse_datetime(date, naive_tz=ZoneInfo('Europe/Rome'))
            self.assertEqual(parsed.hour, 15)
            self.assertEqual(parsed.utcoffset(), timedelta(hours=offset))

    def test_explicit_offset_preserved(self):
        for date, offset in [('2026-10-15T15:25Z', 0), ('2026-10-15T15:25+02:00', 2)]:
            parsed = connector._parse_datetime(date, naive_tz=ZoneInfo('Europe/Rome'))
            self.assertEqual(parsed.utcoffset(), timedelta(hours=offset))

    def test_technical_timestamp_remains_utc(self):
        self.assertEqual(connector._parse_datetime('2026-10-15T15:25').utcoffset(), timedelta(0))

    def test_save_uses_local_timezone_for_slots_only(self):
        item = {'id': 17035, 'aggiornato_il': '2026-10-15T12:00',
                'data_ora_inizio': '2026-10-15T15:25', 'data_ora_fine': '2026-10-15T15:40'}
        with patch.object(connector, '_mappatura', return_value=None), patch.object(
            connector.AppuntamentoWordPress.objects, 'update_or_create',
            return_value=(MagicMock(), False),
        ) as save, patch.object(connector, '_allinea_appuntamento_locale') as align:
            connector._salva(item)
        values = save.call_args.kwargs['defaults']
        for field in ('data_ora_inizio', 'data_ora_fine'):
            self.assertEqual(values[field].utcoffset(), timedelta(hours=2))
            self.assertEqual(values[field].hour, 15)
        self.assertEqual(values['origine_aggiornato_il'].utcoffset(), timedelta(0))
        align.assert_called_once()
