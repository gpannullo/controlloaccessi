from datetime import date
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings
from .anpr import ANPRService, ANPRError


class ANPRTests(SimpleTestCase):
    def test_payload(self):
        for code in ['C020', 'C029']:
            p = ANPRService.payload(code, ' rssmra80a01h501u ', 'PRATICA123', date(2026, 9, 29))
            self.assertEqual(p['criteriRicerca'], {'codiceFiscale': 'RSSMRA80A01H501U'})
            self.assertEqual(p['datiRichiesta']['casoUso'], code)
            self.assertTrue(p['idOperazioneClient'].isalnum())

    def test_practice_required(self):
        with self.assertRaises(ValueError):
            ANPRService.payload('C029', 'RSSMRA80A01H501U', '')

    def test_normalization(self):
        data = {'listaSoggetti': {'datiSoggetto': [{'generalita': {'nome':'Mario', 'codiceFiscale': {'validitaCF':'9'}}, 'residenza':[{'tipoIndirizzo':'1'}]}, {}]}}
        result = ANPRService.normalizza(data, 'C020')
        self.assertEqual(len(result['soggetti']), 2)
        self.assertEqual(result['soggetti'][0]['validita_cf'], '9')
        self.assertIsNone(result['soggetti'][1]['data_nascita'])
        self.assertNotIn('residenze', ANPRService.normalizza(data, 'C029')['soggetti'][0])

    def test_errors(self):
        for data in [[], {'listaErrori':[{}]}, {'listaSoggetti': [] , 'listaErrori':[{}]}]:
            with self.assertRaises(ANPRError):
                ANPRService.normalizza(data, 'C029')

    def test_denied(self):
        with self.assertRaises(PermissionError):
            ANPRService.accerta_residenza('RSSMRA80A01H501U', operatore=None, riferimento_pratica='123', postazione='desk', loa='2')

    @override_settings(PDND={'ENABLED':True, 'TIMEOUT':20}, ANPR={
        'SECURITY_HEADERS_PROVIDER':'fake.provider',
        'C020': {'ENDPOINT':'https://example.invalid/c020', 'PURPOSE_ID':'purpose20'},
        'C029': {'ENDPOINT':'https://example.invalid/c029', 'PURPOSE_ID':'purpose29'}})
    def test_calls_and_no_redirects(self):
        user = SimpleNamespace(pk=1, is_authenticated=True, is_active=True, is_superuser=True)
        with patch.object(ANPRService, '_audit', return_value=MagicMock()), patch.object(ANPRService, '_access_token', return_value='fake') as token, patch('pdnd.anpr.import_string') as provider, patch('pdnd.anpr.requests.post') as post:
            provider.return_value.return_value = {'Agid-JWT-Signature':'signed', 'Agid-JWT-TrackingEvidence':'tracked'}
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'listaSoggetti': {'datiSoggetto':[]}}
            for code, method in [('C020', ANPRService.accerta_residenza), ('C029', ANPRService.accerta_dati_anagrafici)]:
                self.assertEqual(method('RSSMRA80A01H501U', operatore=user, riferimento_pratica='123', postazione='desk', loa='2')['soggetti'], [])
                self.assertFalse(post.call_args.kwargs['allow_redirects'])
                self.assertEqual(provider.return_value.call_args.kwargs['body'], post.call_args.kwargs['data'])
                token.assert_called_with('purpose'+code[-2:])
