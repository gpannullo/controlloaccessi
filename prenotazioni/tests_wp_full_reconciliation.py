from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings
from prenotazioni import wordpress_connector as connector


@override_settings(WORDPRESS_APPOINTMENTS={'ENABLED': True, 'ENDPOINT': 'https://example.invalid/bookings', 'SHARED_SECRET': 'test', 'TIMEOUT': 10, 'PAGE_SIZE': 100})
class FullReconciliationTests(SimpleTestCase):
    def test_existing_cursor_does_not_hide_undated_bookings(self):
        state = MagicMock(cursore=datetime(2026, 10, 12, tzinfo=timezone.utc))
        item = {'id': 16935, 'aggiornato_il': '1970-01-01T00:00:00Z'}
        with patch.object(connector.StatoSincronizzazioneWordPress.objects, 'get_or_create', return_value=(state, False)), patch.object(connector, '_request', side_effect=[{'items': [], 'has_more': True}, {'items': [item], 'has_more': False}]) as request, patch.object(connector.transaction, 'atomic'), patch.object(connector, '_salva', return_value=(None, False)) as save, patch.object(connector, 'allinea_uffici_appuntamenti_wordpress'), patch.object(connector, 'allinea_appuntamenti_locali_wordpress'):
            result = connector.sincronizza_appuntamenti_wordpress()
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertNotIn('updated_after', call.args[0])
        self.assertIn('page=2', request.call_args.args[0])
        save.assert_called_once_with(item)
        self.assertEqual(result['aggiornati'], 1)
        self.assertEqual(result['creati'], 0)
