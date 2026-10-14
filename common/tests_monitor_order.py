from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from access_control.models import Ufficio
from visitors.models import AccessoVisitatore, Visitatore, EventoAccesso
from common.views.monitor import _ordina_uffici_per_coda


class MonitorOrderTests(TestCase):
    def setUp(self):
        self.a = Ufficio.objects.create(codice='A', nome='Anagrafe')
        self.b = Ufficio.objects.create(codice='B', nome='Tributi')
        self.v = Visitatore.objects.create(nome='Test', cognome='Monitor')
        self.access = AccessoVisitatore.objects.create(visitatore=self.v, ufficio_destinazione=self.b, numero_coda=1)
        self.now = timezone.now()
        AccessoVisitatore.objects.filter(pk=self.access.pk).update(ingresso=self.now - timedelta(days=1))

    def order(self):
        return list(_ordina_uffici_per_coda(Ufficio.objects.all(), timezone.localdate()).values_list('pk', flat=True))

    def event(self, office, kind, time):
        EventoAccesso.objects.create(accesso=self.access, ufficio=office, tipo=kind, timestamp=time)

    def test_latest_queue_event_moves_office_first_and_stays(self):
        self.assertEqual(self.order(), [self.a.pk, self.b.pk])
        self.event(self.b, 'POR', self.now)
        self.assertEqual(self.order(), [self.b.pk, self.a.pk])
        self.assertEqual(self.order(), [self.b.pk, self.a.pk])
        self.event(self.a, 'CHI', self.now + timedelta(seconds=1))
        self.assertEqual(self.order(), [self.a.pk, self.b.pk])

    def test_notes_and_previous_days_do_not_reorder(self):
        self.event(self.b, 'POR', self.now - timedelta(days=1))
        self.event(self.b, 'NOT', self.now)
        self.assertEqual(self.order(), [self.a.pk, self.b.pk])

    def test_queue_movement_without_event_moves_office_first(self):
        self.event(self.a, 'CHI', self.now)
        AccessoVisitatore.objects.filter(pk=self.access.pk).update(
            ingresso=self.now, spostato_fuori_ufficio_il=self.now + timedelta(seconds=1),
        )
        self.assertEqual(self.order(), [self.b.pk, self.a.pk])

    def test_empty_office_follows_waiting_office_despite_newer_event(self):
        AccessoVisitatore.objects.filter(pk=self.access.pk).update(ingresso=self.now)
        self.event(self.a, 'FIN', self.now + timedelta(seconds=5))
        self.assertEqual(self.order(), [self.b.pk, self.a.pk])

    def test_last_waiting_visitor_enters_office_moves_behind_other_queue(self):
        AccessoVisitatore.objects.filter(pk=self.access.pk).update(ingresso=self.now)
        AccessoVisitatore.objects.create(visitatore=self.v, ufficio_destinazione=self.a, numero_coda=2)
        self.event(self.b, 'POR', self.now + timedelta(seconds=5))
        self.assertEqual(self.order(), [self.b.pk, self.a.pk])
        AccessoVisitatore.objects.filter(pk=self.access.pk).update(ingresso_ufficio_il=self.now + timedelta(seconds=6))
        self.assertEqual(self.order(), [self.a.pk, self.b.pk])
