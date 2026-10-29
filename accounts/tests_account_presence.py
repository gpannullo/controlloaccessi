from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, RequestFactory
from django.template.loader import render_to_string
from accounts.views import my_account


class AccountPresenceTests(SimpleTestCase):
    def request(self):
        request = RequestFactory().get('/account/?tab=presenza&user_id=999')
        request.user = SimpleNamespace(is_authenticated=True, username='self', badge='0000001234',
            stato_presenza='PRE', presenza_verificata_il=None, ultima_timbratura_il=None,
            uffici_responsabili=MagicMock())
        return request

    def test_readonly_template(self):
        request = self.request()
        output = render_to_string('accounts/my_account.html', {'request':request, 'tab':'presenza', 'dettaglio':{}, 'is_public_account':True})
        self.assertIn('0000001234', output)
        self.assertIn('Nessuna timbratura disponibile', output)
        self.assertNotIn('name="badge"', output)
        self.assertNotIn('name="stato_presenza"', output)

    def test_missing_badge(self):
        request = self.request(); request.user.badge = None
        output = render_to_string('accounts/my_account.html', {'request':request, 'tab':'presenza', 'dettaglio':{}, 'is_public_account':True})
        self.assertIn('Nessun badge associato', output)
        self.assertIn('?tab=presenza', output)

    def test_view_only_authenticated_user(self):
        request = self.request()
        with patch('presenze_qr.services.storico_personale', return_value=[]) as storico, patch('presenze_qr.services.abilitato', return_value=False), patch('accounts.views.DirectoryAdminService') as ldap, patch('accounts.views.AssegnazioneUfficio') as assignments, patch('accounts.views.render') as render:
            ldap.return_value.dettaglio.return_value = {}
            my_account(request)
            ldap.return_value.dettaglio.assert_called_once_with('self')
            assignments.objects.filter.assert_called_once_with(utente=request.user, attiva=True)
            self.assertEqual(render.call_args.args[2]['tab'], 'presenza')
            storico.assert_called_once_with(request.user)
