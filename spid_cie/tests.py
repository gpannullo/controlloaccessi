import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CodiceAccessoGateway, IdentitaDigitale


@override_settings(SPID_GATEWAY={"ENABLED": True, "BASE_URL": "https://gateway.example/identita/spid", "SHARED_SECRET": "test-secret", "MAX_AGE_SECONDS": 60})
class GatewayIdentityTests(TestCase):
    def _signed_post(self, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(timezone.now().timestamp()))
        signature = hmac.new(b"test-secret", f"{timestamp}.".encode("ascii") + body, hashlib.sha256).hexdigest()
        return self.client.post(reverse("spid_cie:gateway_identity"), data=body, content_type="application/json", headers={"X-Spid-Gateway-Timestamp": timestamp, "X-Spid-Gateway-Signature": signature})

    def test_signed_identity_can_be_exchanged_once(self):
        code = "a" * 48
        response = self._signed_post({"code": code, "codice_fiscale": "RSSMRA80A01F205X", "nome": "Mario", "cognome": "Rossi", "email": "mario@example.it", "destinazione": "/prenotazioni/?step=4"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CodiceAccessoGateway.objects.count(), 1)

        complete = reverse("spid_cie:gateway_complete") + f"?code={code}"
        response = self.client.get(complete)
        self.assertRedirects(response, "/prenotazioni/?step=4", fetch_redirect_response=False)
        identity = IdentitaDigitale.objects.get(codice_fiscale="RSSMRA80A01F205X")
        self.assertEqual(self.client.session.get("spid_cie_identity_id"), identity.pk)
        self.assertIsNotNone(CodiceAccessoGateway.objects.get().usato_il)

        self.assertEqual(self.client.get(complete).status_code, 400)
