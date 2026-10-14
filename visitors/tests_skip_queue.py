from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from access_control.models import Ufficio
from visitors.models import AccessoVisitatore, Visitatore, Appuntamento
from visitors.services.office_queue_service import OfficeQueueService as Queue
from common.exceptions import BusinessException

class SkipQueueTests(TestCase):
    def setUp(self):
        self.office = Ufficio.objects.create(nome='Test salto')
        self.user = get_user_model().objects.create(username='test_salto')
        self.visitor = Visitatore.objects.create(nome='Test', cognome='Visitatore')
        self.audit = patch.object(Queue, '_audit').start()
        self.addCleanup(patch.stopall)

    def access(self, number, booked=False, **kwargs):
        appointment = Appuntamento.objects.create(ufficio=self.office, data_ora=timezone.now()+timedelta(hours=number)) if booked else None
        return AccessoVisitatore.objects.create(visitatore=self.visitor, ufficio_destinazione=self.office,
            numero_coda=number, appuntamento=appointment, **kwargs)

    def called(self, booked=False):
        return self.access(1, booked, stato_coda='UFF', operatore_assegnato=self.user,
            ingresso_ufficio_il=timezone.now(), spostato_fuori_ufficio_il=timezone.now())

    def skip(self, a):
        return Queue.salta_non_presente(accesso_id=a.pk, ufficio=self.office, operatore=self.user)

    def test_ordinary_goes_to_tail_and_no_direct_entry(self):
        a=self.called(); b=self.access(2); c=self.access(3)
        arrival=a.ingresso
        self.skip(a); a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(a.stato_coda, 'HALL'); self.assertIsNone(a.operatore_assegnato_id)
        self.assertEqual(a.ingresso, arrival); self.assertEqual(a.numero_coda,1)
        self.assertEqual(b.stato_coda,'PORTA'); self.assertIsNone(b.ingresso_ufficio_il)
        self.assertEqual(list(Queue.coda_hall(self.office).values_list('pk',flat=True)),[c.pk,a.pk])
        self.assertTrue(a.eventi.filter(dati__azione='salto_non_presente').exists())
        with self.assertRaises(BusinessException):self.skip(a)

    def test_booked_tail_preserves_priority(self):
        a=self.called(True); b=self.access(2,True); c=self.access(3,True); self.access(4)
        self.skip(a); a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(b.stato_coda,'PORTA')
        self.assertEqual(list(Queue.coda_prioritaria(self.office).values_list('pk',flat=True)),[c.pk,a.pk])
        self.assertIsNotNone(a.appuntamento_id)

    def test_next_already_outside_enters(self):
        a=self.called(); b=self.access(2,stato_coda='PORTA',spostato_fuori_ufficio_il=timezone.now())
        self.skip(a); b.refresh_from_db(); a.refresh_from_db()
        self.assertEqual(b.stato_coda,'UFF'); self.assertEqual(a.stato_coda,'HALL')

    def test_other_operator_denied(self):
        a=self.called(); a.operatore_assegnato=None; a.save()
        with self.assertRaises(BusinessException):self.skip(a)
