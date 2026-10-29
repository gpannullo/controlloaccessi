from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from access_control.services.wordpress_sync_service import allinea_e_verifica_ufficio_wordpress
from prenotazioni.wordpress_connector import WordPressConnectorError


class AlignmentTests(SimpleTestCase):
    def setUp(self):
        self.office = MagicMock(responsabile_id=None)
        self.unit = MagicMock(origine_id='12', nome='Ufficio', stato='publish', responsabile_id=None)
        self.unit.personale_wordpress.values_list.return_value = ['21']
        self.office.unita_organizzative_wordpress.all.return_value = [self.unit]
        self.office.assegnazioni_personale.filter.return_value.values_list.return_value = []
        self.people = patch('prenotazioni.models.PersonaleWordPress.objects.filter').start()
        self.people.return_value.exclude.return_value.values_list.return_value = []
        self.read = patch('prenotazioni.wordpress_connector.leggi_anagrafiche_wordpress').start()
        self.read.return_value = {'uffici':[{'id':12,'nome':'Ufficio','stato':'publish','persone':['21'],'responsabile':None}]}
        self.write = patch('access_control.services.wordpress_sync_service.sincronizza_ufficio_wordpress', return_value={'unita':1}).start()
        self.addCleanup(patch.stopall)

    def test_verified_read_after_write(self):
        self.assertEqual(allinea_e_verifica_ufficio_wordpress(self.office)['differenze'], [])
        self.write.assert_called_once_with(self.office)
        self.assertEqual(self.read.call_count, 2)

    def test_mismatch_not_success(self):
        self.read.return_value['uffici'][0]['persone'] = ['22']
        self.assertTrue(allinea_e_verifica_ufficio_wordpress(self.office)['differenze'])

    def test_unsupported_connector_no_writes(self):
        del self.read.return_value['uffici'][0]['responsabile']
        with self.assertRaises(WordPressConnectorError): allinea_e_verifica_ufficio_wordpress(self.office)
        self.write.assert_not_called()

    def test_missing_mapping_no_writes(self):
        self.office.unita_organizzative_wordpress.all.return_value = []
        with self.assertRaises(WordPressConnectorError): allinea_e_verifica_ufficio_wordpress(self.office)
        self.write.assert_not_called()

    def test_missing_public_person_no_writes(self):
        self.office.assegnazioni_personale.filter.return_value.values_list.return_value = [7]
        with self.assertRaises(WordPressConnectorError): allinea_e_verifica_ufficio_wordpress(self.office)
        self.write.assert_not_called()
