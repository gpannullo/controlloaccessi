import hashlib
from dataclasses import replace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, SimpleTestCase
from audit.models import AuditEvent
from protocollazione.contracts import Documento, Firmatario, Soggetto, TipoProtocollo, EsitoIncertoError, InvioBloccatoError, ValidazioneProtocolloError
from protocollazione.services import protocolla_documenti
from protocollazione.tests import RESULT, request_data
from cityware.backend import CitywareBackend
from cityware.soap import envelope


class MethodTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='protocol-api', is_active=True, is_superuser=True)
        self.kw = dict(ufficio='U1', firmatario=Firmatario('F1', 'U1'), destinatario=Soggetto('Destinatario'),
                       pdf=[Documento('uno.pdf', b'%PDF-1.4 uno'), Documento('due.pdf', b'%PDF-1.4 due')],
                       oggetto='Test', classificazione='1.2', chiave='test-api:1', operatore=self.user)

    def test_multiple_documents_audit_once(self):
        with patch.object(CitywareBackend, 'protocolla', return_value=RESULT) as call:
            self.assertEqual(protocolla_documenti(**self.kw).numero, RESULT.numero)
            self.assertEqual(protocolla_documenti(**self.kw).anno, RESULT.anno)
            call.assert_called_once()
            req = call.call_args.args[0]
            self.assertEqual(req.ufficio, 'U1')
            self.assertEqual(req.firmatari[0].codice, 'F1')
            self.assertEqual(len(req.allegati), 1)
            self.assertEqual(req.tipo, TipoProtocollo.PARTENZA)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertIn(RESULT.numero, AuditEvent.objects.get().descrizione)

    def test_changed_attachment_blocks_duplicate(self):
        with patch.object(CitywareBackend, 'protocolla', return_value=RESULT):
            protocolla_documenti(**self.kw)
        self.kw['pdf'][1] = Documento('due.pdf', b'%PDF-1.4 changed')
        with self.assertRaises(InvioBloccatoError):
            protocolla_documenti(**self.kw)

    def test_missing_pdf_rejected(self):
        self.kw['pdf'] = []
        with self.assertRaises(ValidazioneProtocolloError):
            protocolla_documenti(**self.kw)

    def test_audit_failure_repaired_without_resend(self):
        with patch.object(CitywareBackend, 'protocolla', return_value=RESULT) as call:
            with patch('protocollazione.services._audit_esito', side_effect=RuntimeError('audit unavailable')):
                with self.assertRaises(RuntimeError):
                    protocolla_documenti(**self.kw)
            protocolla_documenti(**self.kw)
            call.assert_called_once()
        self.assertEqual(AuditEvent.objects.count(), 1)


class MultipleSoapTests(SimpleTestCase):
    def test_preload_then_one_protocol(self):
        req = replace(request_data(), allegati=(Documento('secondo.pdf', b'%PDF-1.4 second'),))
        fields = {'rowidProtocollo': '42', 'annoProtocollo': '2026', 'numeroProtocollo': '000012',
                  'tipoProtocollo': 'C', 'dataProtocollo': '20260917', 'segnatura': '12/2026/ENTE'}
        with patch('cityware.backend.CitywareSoapClient') as cls:
            client = cls.return_value
            client.session.return_value.__enter__.return_value = 'token'
            client.call.side_effect = [
                {'messageResult': {'tipoRisultato': 'Info'}, 'allegatoPrecaricato': {
                    'idunivoco': str(i), 'hashfile': hashlib.sha256(doc.contenuto).hexdigest()}}
                for i, doc in enumerate((req.documento, *req.allegati))
            ] + [{'retProtocollo': fields, 'messageResult': {'tipoRisultato': 'Info'}}]
            self.assertEqual(CitywareBackend().protocolla(req), RESULT)
            self.assertEqual([c.args[0] for c in client.call.call_args_list], ['InsertDocumento', 'InsertDocumento', 'PutProtocollo'])
            payload = client.call.call_args.args[1]
            self.assertNotIn('allegato', payload['datiProtocollo'])
            items = payload['datiProtocollo']['allegatiPrecaricati']['allegatoPrecaricato']
            self.assertEqual([d['tipoFile'] for d in items], ['PRINCIPALE', 'ALLEGATO'])
            xml = envelope('PutProtocollo', payload)
            self.assertEqual(xml.count(b'<allegatoPrecaricato '), 2)

    def test_bad_preload_hash_never_registers(self):
        req = replace(request_data(), allegati=(Documento('secondo.pdf', b'%PDF-1.4 second'),))
        with patch('cityware.backend.CitywareSoapClient') as cls:
            client = cls.return_value
            client.call.return_value = {'messageResult': {'tipoRisultato': 'Info'},
                                       'allegatoPrecaricato': {'idunivoco': 'id', 'hashfile': 'wrong'}}
            with self.assertRaises(EsitoIncertoError):
                CitywareBackend().protocolla(req)
            client.call.assert_called_once()
