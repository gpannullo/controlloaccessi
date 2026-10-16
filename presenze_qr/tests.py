from datetime import datetime, timedelta, timezone as tz
from unittest.mock import patch
from django.test import TestCase, RequestFactory, override_settings, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from .models import Postazione, Timbratura, Attivita
from .services import emetti, timbra, correggi, automatico, TimbraturaError
from .security import client_ip, controlla_rete


@override_settings(PRESENZE_QR_ENABLED=True)
class PresenzeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='qr.test', email_personale='test@example.org', cellulare_personale='123')
        self.other = get_user_model().objects.create(username='qr.other')
        self.station = Postazione.objects.create(nome='Ingresso')
        self.now = datetime(2026, 10, 13, 6, 30, tzinfo=tz.utc)
        self.clock = patch('presenze_qr.services.timezone.now', return_value=self.now)
        self.clock.start(); self.addCleanup(self.clock.stop)

    def token(self):
        return emetti(self.station.pk, self.user, '10.0.3.6')[1]

    def test_scan_has_full_page_result_without_immediate_redirect(self):
        from django.template.loader import render_to_string
        request = RequestFactory().get('/presenze/scan/')
        request.user = self.user
        html = render_to_string('presenze_qr/scan.html', {
            'abilitato_qr': True, 'automatico': 'I',
        }, request=request)
        self.assertIn('role="alertdialog"', html)
        self.assertIn('Ingresso registrato', html)
        self.assertIn('Uscita registrata', html)
        self.assertIn('QR scaduto, già utilizzato o non valido', html)
        self.assertIn('Timbratura già registrata', html)
        self.assertIn('entro 60 secondi', html)
        self.assertNotIn('location.replace(result.url)', html)

    def test_one_use_and_idempotent_retry(self):
        token = self.token()
        a, created = timbra(self.user, token, 'auto', '1.2.3.4')
        self.assertTrue(created); self.assertEqual(a.verso, 'I')
        b, created = timbra(self.user, token, 'U', '1.2.3.4')
        self.assertFalse(created); self.assertEqual(a.pk, b.pk)
        with self.assertRaises(TimbraturaError): timbra(self.other, token, 'I', None)
        self.assertEqual(Timbratura.objects.count(), 1)
        self.user.refresh_from_db(); self.assertEqual(self.user.stato_presenza, 'PRE')
        self.assertEqual(self.user.presenza_fonte, 'QR')
        self.assertNotEqual(token, self.token())

    def test_expires_exactly_thirty_seconds(self):
        token = self.token()
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(seconds=30)):
            with self.assertRaises(TimbraturaError): timbra(self.user, token, 'I', None)
            self.assertNotEqual(token, self.token())

    def test_invalid_token_badge_and_disabled_do_not_consume(self):
        token = self.token()
        with self.assertRaises(TimbraturaError): timbra(self.user, token+'x', 'I', None)
        get_user_model().objects.filter(pk=self.user.pk).update(badge='0000000001')
        with self.assertRaises(TimbraturaError): timbra(self.user, token, 'I', None)
        get_user_model().objects.filter(pk=self.user.pk).update(badge=None, is_active=False)
        with self.assertRaises(TimbraturaError): timbra(self.user, token, 'I', None)
        self.station.refresh_from_db(); self.assertIsNone(self.station.consumato_il)

    def test_correction_window_ownership_audit(self):
        record, _ = timbra(self.user, self.token(), 'I', None)
        with self.assertRaises(TimbraturaError): correggi(self.other, record.pk, 'I', None)
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(seconds=59)):
            corrected = correggi(self.user, record.pk, 'I', None)
            self.assertEqual(corrected.verso, 'U'); self.assertEqual(corrected.verso_originale, 'I')
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(seconds=60)):
            with self.assertRaises(TimbraturaError): correggi(self.user, record.pk, 'U', None)
        self.assertEqual(Attivita.objects.filter(azione='CORREZIONE', verso_prima='I', verso_dopo='U').count(), 1)

    def test_old_correction_does_not_override_new_presence(self):
        first, _ = timbra(self.user, self.token(), 'I', None)
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(seconds=60)):
            timbra(self.user, self.token(), 'I', None)
            with self.assertRaises(TimbraturaError): correggi(self.user, first.pk, 'I', None)
        self.user.refresh_from_db(); self.assertEqual(self.user.stato_presenza, 'PRE')

    def test_time_windows_rome(self):
        from zoneinfo import ZoneInfo
        for hour, minute, expected in [(8,0,'I'),(9,30,'I'),(9,31,None),(12,30,'U'),(14,0,'U'),(14,1,None)]:
            self.assertEqual(automatico(datetime(2026,10,13,hour,minute,tzinfo=ZoneInfo('Europe/Rome'))),expected)

    def test_manual_choice_required_outside_windows(self):
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(hours=2)):
            token = self.token()
            with self.assertRaises(TimbraturaError): timbra(self.user, token, 'auto', None)
            self.assertEqual(timbra(self.user, token, 'U', None)[0].verso, 'U')

    @override_settings(PRESENZE_QR_SOLO_RETE_COMUNALE=True, PRESENZE_QR_RETI_CONSENTITE=['10.0.0.0/22'], PRESENZE_QR_PROXY_ATTENDIBILI=['127.0.0.1/32'])
    def test_proxy_cannot_be_spoofed(self):
        factory = RequestFactory()
        req = factory.get('/', REMOTE_ADDR='8.8.8.8', HTTP_X_REAL_IP='10.0.3.6')
        self.assertEqual(client_ip(req),'8.8.8.8')
        with self.assertRaises(PermissionDenied): controlla_rete(req)
        req = factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_REAL_IP='10.0.3.6')
        self.assertEqual(controlla_rete(req),'10.0.3.6')
        with self.assertRaises(PermissionDenied): controlla_rete(factory.get('/',REMOTE_ADDR='127.0.0.1'))

    def test_get_never_punches_and_post_needs_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.get(reverse('presenze_qr:scan')).status_code,200)
        self.assertEqual(client.get(reverse('presenze_qr:registra')).status_code,405)
        self.assertEqual(client.post(reverse('presenze_qr:registra'), {'token':self.token(),'verso':'I'}).status_code,403)
        self.assertFalse(Timbratura.objects.exists())

    def test_only_last_ten_owned_records(self):
        from .services import storico_personale
        for n in range(11):
            with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(minutes=n)):
                timbra(self.user,self.token(),'I',None)
        timbra(self.other,self.token(),'U',None)
        self.client.force_login(self.user)
        response = self.client.get(reverse('presenze_qr:personale'))
        self.assertEqual(response.status_code,302)
        rows = storico_personale(self.user)
        self.assertEqual(len(rows),10)
        self.assertTrue(all(r.utente_id==self.user.pk for r in rows))

    def test_same_minute_blocked_next_minute_allowed(self):
        timbra(self.user,self.token(),'I',None)
        token = self.token()
        with self.assertRaises(TimbraturaError): timbra(self.user,token,'U',None)
        self.assertEqual(Timbratura.objects.count(),1)
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(minutes=1)):
            timbra(self.user,self.token(),'U',None)
        self.assertEqual(Timbratura.objects.count(),2)

    def test_only_latest_even_when_both_under_sixty_seconds(self):
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(seconds=59)):
            first,_ = timbra(self.user,self.token(),'I',None)
        with patch('presenze_qr.services.timezone.now', return_value=self.now+timedelta(seconds=61)):
            last,_ = timbra(self.user,self.token(),'U',None)
            with self.assertRaises(TimbraturaError): correggi(self.user,first.pk,'I',None)
            correggi(self.user,last.pk,'U',None)

    def test_anonymous_monitor_requires_network_and_host(self):
        self.assertEqual(self.client.get('/qr/', HTTP_HOST='controlloaccessi.comune.aversa.ce.it', REMOTE_ADDR='10.0.3.6').status_code,200)
        self.assertEqual(self.client.get('/qr/', HTTP_HOST='controlloaccessi.comune.aversa.ce.it', REMOTE_ADDR='8.8.8.8').status_code,403)
        self.assertNotEqual(self.client.get('/qr/', HTTP_HOST='account.comune.aversa.ce.it', REMOTE_ADDR='10.0.3.6').status_code,200)
        self.assertEqual(self.client.post(reverse('monitor_presenze_codice',args=[self.station.pk]), HTTP_HOST='controlloaccessi.comune.aversa.ce.it', REMOTE_ADDR='10.0.3.6').status_code,200)
        self.assertEqual(self.client.post(reverse('monitor_presenze_codice',args=[self.station.pk]), HTTP_HOST='controlloaccessi.comune.aversa.ce.it', REMOTE_ADDR='8.8.8.8').status_code,403)

    def test_anonymous_monitor_csrf_and_standalone_page(self):
        client = Client(enforce_csrf_checks=True)
        args = dict(HTTP_HOST='controlloaccessi.comune.aversa.ce.it', REMOTE_ADDR='10.0.3.6')
        response = client.get('/qr/', **args)
        html = response.content.decode()
        for unwanted in ('jquery', 'bootstrap', 'fetch(', '=>', 'cdn.'):
            self.assertNotIn(unwanted, html.lower())
        url = reverse('monitor_presenze_codice', args=[self.station.pk])
        self.assertEqual(client.post(url, **args).status_code, 403)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(url, {'csrfmiddlewaretoken': token}, **args).status_code, 200)

    def test_monitor_generates_svg_without_consuming(self):
        self.user.is_superuser=True; self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        response=self.client.post(reverse('monitor_presenze_codice',args=[self.station.pk]),HTTP_HOST='controlloaccessi.comune.aversa.ce.it',REMOTE_ADDR='10.0.3.6')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['qr'].startswith('data:image/png;base64,'))
        self.assertFalse(Timbratura.objects.exists())

    def test_public_account_login_keeps_scan_destination(self):
        from accounts.views import DirectoryLoginView
        req = RequestFactory().post('/accounts/login/', {'next': reverse('presenze_qr:scan')}, HTTP_HOST='account.comune.aversa.ce.it')
        view = DirectoryLoginView(); view.setup(req)
        self.assertEqual(view.get_success_url(), reverse('presenze_qr:scan'))

    @override_settings(PRESENZE_QR_SOLO_RETE_COMUNALE=True)
    def test_network_restriction_applies_to_writes_too(self):
        self.client.force_login(self.user)
        response=self.client.post(reverse('presenze_qr:registra'),{'token':self.token(),'verso':'I'},REMOTE_ADDR='8.8.8.8')
        self.assertEqual(response.status_code,403)
        self.assertFalse(Timbratura.objects.exists())

    def test_unconfigured_presence_api_preserves_qr_state(self):
        from accounts.services.presence_service import PresenceService
        timbra(self.user,self.token(),'I',None)
        PresenceService().update_user_presence(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.stato_presenza,'PRE')
        self.assertEqual(self.user.presenza_fonte,'QR')
