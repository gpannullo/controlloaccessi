from dataclasses import replace
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from protocollazione.contracts import *
from protocollazione.services import protocolla, get_backend
from protocollazione.models import RegistrazioneProtocollo
from protocollazione.providers.cityware.backend import CitywareBackend
from protocollazione.providers.cityware.soap import CitywareSoapClient, envelope, parse_response


def request_data():
    return RichiestaProtocollo('Report di prova',TipoProtocollo.INTERNO,Documento('report.pdf',b'%PDF-1.4\nTEST'),'1.2')


RESULT=EsitoProtocollo('42','2026','000012','interno','20260917','12/2026/ENTE')

TEST_CITYWARE = {
    'ENDPOINT': 'https://example.invalid/soap', 'USERNAME': 'test',
    'PASSWORD': 'not-a-real-password', 'DOMAIN_CODE': 'test',
    'UFFICIO_OPERATORE': '0001', 'FIRMATARIO': '0002',
    'UFFICIO_FIRMATARIO': '0001',
}


class AlternateBackend(ProtocolloBackend):
    def valida(self,richiesta):pass
    def protocolla(self,richiesta):return RESULT


@override_settings(CITYWARE=TEST_CITYWARE, PROTOCOLLAZIONE_ENABLED=True)
class ContractTests(SimpleTestCase):
    def test_abstract(self):
        with self.assertRaises(TypeError):ProtocolloBackend()

    def test_provider(self):
        self.assertIsInstance(get_backend(),CitywareBackend)

    def test_mapping(self):
        b=CitywareBackend(); r=request_data(); b.valida(r)
        p=b.payload(r)
        self.assertEqual(p['tipoProtocollo'],'C')
        self.assertEqual(p['allegato']['stream'],'JVBERi0xLjQKVEVTVA==')
        self.assertTrue(p['riservato'])
        self.assertEqual(p['firmatari']['firmatario'][0]['codice'],'0002')
        self.assertEqual(p['allegato']['mettiAllaFirma'],'0')

    def test_validation(self):
        b=CitywareBackend(); r=request_data()
        for invalid in [replace(r,oggetto=''),replace(r,classificazione=''),replace(r,tipo=TipoProtocollo.PARTENZA),replace(r,tipo=TipoProtocollo.ARRIVO),replace(r,documento=Documento('../file.pdf',b'abc')),replace(r,documento=Documento('file.pdf',b''))]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidazioneProtocolloError):b.valida(invalid)

    def test_http_refused(self):
        with self.assertRaises(ConfigurazioneProtocolloError):CitywareSoapClient({'ENDPOINT':'http://example.invalid/'})

    def test_xml_escaping_and_multiplicity(self):
        data=CitywareBackend().payload(replace(request_data(),oggetto='Nome & <altro>',destinatari=(Soggetto('Uno'),Soggetto('Due'))))
        xml=envelope('PutProtocollo',{'token':'secret','datiProtocollo':data})
        self.assertIn(b'Nome &amp; &lt;altro&gt;',xml)
        self.assertEqual(xml.count(b'<mittenteDestinatario '),2)
        self.assertIn(b'tns:datiProtocollo',xml)

    def test_no_entities(self):
        with self.assertRaises(Exception):parse_response(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>','PutProtocollo')

    def test_result_aliases(self):
        fields={'rowidProtocollo':'42','annoProtocollo':'2026','numeroProtocollo':'000012','tipoProtocollo':'C','dataProtocollo':'20260917','segnatura':'12/2026/ENTE'}
        for alias in ['datiProtocollo','retProtocollo','items']:
            result=CitywareBackend().esito({alias:fields,'messageResult':{'tipoRisultato':'Info'}},TipoProtocollo.INTERNO)
            self.assertEqual(result,RESULT)

    def test_uncertain_partial_response(self):
        with self.assertRaises(EsitoIncertoError):CitywareBackend().esito({'messageResult':{'tipoRisultato':'Info'}},TipoProtocollo.INTERNO)

    def test_session_closed_on_failure(self):
        client=CitywareSoapClient({'ENDPOINT':'https://example.invalid','USERNAME':'x','PASSWORD':'x','DOMAIN_CODE':'x'})
        with patch.object(client,'call',side_effect=[{'return':'token'},{}]) as call:
            with self.assertRaises(ValueError):
                with client.session():raise ValueError('test')
            self.assertEqual(call.call_args.args[0],'DestroyItaEngineContextToken')

    def test_logout_does_not_mask_success(self):
        client=CitywareSoapClient({'ENDPOINT':'https://example.invalid','USERNAME':'x','PASSWORD':'x','DOMAIN_CODE':'x'})
        with patch.object(client,'call',side_effect=[{'return':'token'},ErroreProtocollo('logout')]):
            with client.session() as token:self.assertEqual(token,'token')

    def test_transport_no_retry_and_no_redirect(self):
        with patch('protocollazione.providers.cityware.soap.requests.Session') as session:
            session.return_value.__enter__.return_value.post.side_effect=TimeoutError()
            with self.assertRaises(EsitoIncertoError):
                CitywareSoapClient({'ENDPOINT':'https://example.invalid'}).call('PutProtocollo',{},writing=True)
            post=session.return_value.__enter__.return_value.post
            self.assertEqual(post.call_count,1)
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertTrue(post.call_args.kwargs['verify'])

    def test_complete_soap_flow_offline(self):
        def soap(method,inner):
            return f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><{method}Response>{inner}</{method}Response></s:Body></s:Envelope>'.encode()
        fields={'rowidProtocollo':'42','annoProtocollo':'2026','numeroProtocollo':'000012','tipoProtocollo':'C','dataProtocollo':'20260917','segnatura':'12/2026/ENTE'}
        responses=[soap('GetItaEngineContextToken','<return>fake-token</return>'),soap('PutProtocollo','<retProtocollo>'+''.join(f'<{k}>{v}</{k}>' for k,v in fields.items())+'</retProtocollo><messageResult><tipoRisultato>Info</tipoRisultato></messageResult>'),soap('DestroyItaEngineContextToken','<return>Success</return>')]
        with patch('protocollazione.providers.cityware.soap.requests.Session') as session:
            post=session.return_value.__enter__.return_value.post
            def response(*args,**kwargs):
                result=MagicMock(); result.__enter__.return_value=result
                result.status_code=200; result.iter_content.return_value=[responses.pop(0)]
                return result
            post.side_effect=response
            self.assertEqual(CitywareBackend().protocolla(request_data()),RESULT)
            self.assertEqual(post.call_count,3)


@override_settings(CITYWARE=TEST_CITYWARE, PROTOCOLLAZIONE_ENABLED=True)
class LedgerTests(TransactionTestCase):
    def setUp(self):
        self.user=get_user_model().objects.create(username='tester',is_active=True,is_staff=True,is_superuser=True)

    def test_success_and_idempotency(self):
        with patch.object(CitywareBackend,'protocolla',return_value=RESULT) as send:
            self.assertEqual(protocolla(request_data(),chiave='report:1',operatore=self.user),RESULT)
            self.assertEqual(protocolla(request_data(),chiave='report:1',operatore=self.user),RESULT)
            self.assertEqual(send.call_count,1)
        self.assertEqual(RegistrazioneProtocollo.objects.get().stato,'completato')

    @override_settings(PROTOCOLLAZIONE_BACKEND='protocollazione.tests.AlternateBackend')
    def test_replace_provider_without_caller_changes(self):
        self.assertEqual(protocolla(request_data(),chiave='report:alt',operatore=self.user),RESULT)

    def test_stored_result_survives_provider_change(self):
        with patch.object(CitywareBackend,'protocolla',return_value=RESULT):protocolla(request_data(),chiave='report:1',operatore=self.user)
        with override_settings(PROTOCOLLAZIONE_ENABLED=False,PROTOCOLLAZIONE_BACKEND='missing.Backend'):
            self.assertEqual(protocolla(request_data(),chiave='report:1',operatore=self.user),RESULT)

    def test_changed_content(self):
        with patch.object(CitywareBackend,'protocolla',return_value=RESULT):protocolla(request_data(),chiave='report:1',operatore=self.user)
        with self.assertRaises(InvioBloccatoError):protocolla(replace(request_data(),oggetto='Diverso'),chiave='report:1',operatore=self.user)

    def test_uncertain_not_resent(self):
        with patch.object(CitywareBackend,'protocolla',side_effect=EsitoIncertoError('test')) as send:
            with self.assertRaises(EsitoIncertoError):protocolla(request_data(),chiave='report:1',operatore=self.user)
            with self.assertRaises(InvioBloccatoError):protocolla(request_data(),chiave='report:1',operatore=self.user)
            self.assertEqual(send.call_count,1)
        self.assertEqual(RegistrazioneProtocollo.objects.get().stato,'incerto')

    def test_failure_before_write(self):
        with patch.object(CitywareBackend,'protocolla',side_effect=ErroreProtocollo('login')):
            with self.assertRaises(ErroreProtocollo):protocolla(request_data(),chiave='report:1',operatore=self.user)
        self.assertEqual(RegistrazioneProtocollo.objects.get().stato,'errore')

    def test_pending_blocks_send(self):
        with patch.object(CitywareBackend,'protocolla',return_value=RESULT):protocolla(request_data(),chiave='report:1',operatore=self.user)
        RegistrazioneProtocollo.objects.update(stato='in_corso')
        with self.assertRaises(InvioBloccatoError):protocolla(request_data(),chiave='report:1',operatore=self.user)

    def test_transaction_rejected(self):
        with transaction.atomic():
            with self.assertRaises(InvioBloccatoError):protocolla(request_data(),chiave='report:1',operatore=self.user)

    def test_unauthorized(self):
        self.user.is_superuser=False
        with self.assertRaises(PermissionDenied):protocolla(request_data(),chiave='report:1',operatore=self.user)

    @override_settings(PROTOCOLLAZIONE_ENABLED=False)
    def test_disabled(self):
        with self.assertRaises(ConfigurazioneProtocolloError):protocolla(request_data(),chiave='report:1',operatore=self.user)
        self.assertFalse(RegistrazioneProtocollo.objects.exists())
