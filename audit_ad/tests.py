import hashlib
import hmac
import json
import time
from datetime import timedelta
from types import SimpleNamespace
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from django.contrib.admin.sites import AdminSite
from .models import Event, Alert
from .services import ingest
from .views import receive
from .admin import EventAdmin

SECRET = 'test-secret-with-at-least-32-characters'

@override_settings(AUDIT_AD_ENABLED=True, AUDIT_AD_SOURCES={'192.168.15.100': SECRET},
                   AUDIT_AD_TRUSTED_PROXIES=['127.0.0.1'], AUDIT_AD_FAILURE_THRESHOLD=3)
class AuditTests(TestCase):
    def row(self, record=1, event=4625, **data):
        return {'event_id': event, 'record_id': record, 'computer': 'dc.test',
                'time': (timezone.now() - timedelta(seconds=10)).isoformat(),
                'data': {'TargetUserName': 'test', 'IpAddress': '::ffff:10.0.3.6', **data}}

    def request(self, rows, peer='192.168.15.100', timestamp=None, signature=None, **extra):
        body = json.dumps({'events': rows}).encode()
        stamp = str(timestamp if timestamp is not None else int(time.time()))
        signed = hmac.new(SECRET.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        return RequestFactory().post('/audit-ad/events/', body, content_type='application/json', secure=True,
            REMOTE_ADDR=peer, HTTP_X_AD_SOURCE='192.168.15.100', HTTP_X_AD_TIMESTAMP=stamp,
            HTTP_X_AD_SIGNATURE=signature or signed, **extra)

    def test_receive_and_deduplicate(self):
        row = self.row()
        self.assertEqual(receive(self.request([row])).status_code, 200)
        self.assertEqual(receive(self.request([row])).status_code, 200)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().client_ip, '10.0.3.6')

    def test_authentication_and_proxy(self):
        for request in [self.request([self.row()], signature='bad'),
                        self.request([self.row()], timestamp=int(time.time())-301),
                        self.request([self.row()], peer='10.0.0.1', HTTP_X_REAL_IP='192.168.15.100')]:
            self.assertEqual(receive(request).status_code, 403)
        self.assertEqual(receive(self.request([self.row()], peer='127.0.0.1', HTTP_X_REAL_IP='192.168.15.100')).status_code, 200)

    def test_invalid_batch_atomic(self):
        self.assertEqual(receive(self.request([self.row(), {'broken': True}])).status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_failure_rule(self):
        rows = [self.row(i) for i in range(3)]
        ingest('192.168.15.100', rows)
        ingest('192.168.15.100', rows)
        self.assertEqual(Alert.objects.filter(rule='repeated_failures').count(), 1)

    def test_audit_and_privileged_changes(self):
        ingest('192.168.15.100', [self.row(1, 1102), self.row(2, 4728, TargetSid='S-1-5-21-1-2-3-512'), self.row(3, 4728, TargetSid='S-1-5-21-1-2-3-513')])
        self.assertEqual(Alert.objects.count(), 2)

    def test_success_not_failure(self):
        ingest('192.168.15.100', [self.row(i, 4624) for i in range(10)])
        self.assertFalse(Alert.objects.exists())

    def test_late_batch_is_analyzed(self):
        rows = [self.row(i) for i in range(3)]
        ingest('192.168.15.100', [rows[-1]])
        ingest('192.168.15.100', rows[:2])
        self.assertEqual(Alert.objects.filter(rule='repeated_failures').count(), 1)

    def test_clear_record_counter_does_not_drop_new_event(self):
        row = self.row()
        ingest('192.168.15.100', [row])
        row['time'] = (timezone.now() - timedelta(seconds=1)).isoformat()
        ingest('192.168.15.100', [row])
        self.assertEqual(Event.objects.count(), 2)

    def test_admin_restricted(self):
        model_admin = EventAdmin(Event, AdminSite())
        request = SimpleNamespace(user=SimpleNamespace(is_active=True, is_superuser=False))
        self.assertFalse(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        request.user.is_superuser = True
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_tampered_body(self):
        request = self.request([self.row()])
        request._body = request.body.replace(b'test', b'evil')
        self.assertEqual(receive(request).status_code, 403)

    def test_naive_dates_rejected(self):
        row = self.row()
        row['time'] = '2026-01-01T12:00:00'
        self.assertEqual(receive(self.request([row])).status_code, 400)

    @override_settings(AUDIT_AD_ENABLED=False)
    def test_disabled(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            receive(self.request([self.row()]))
