"""Adapter ANPR E002, basato sulle specifiche C020 e C029 fornite dall'Ente."""
import json
import re
import uuid
from datetime import date
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string

from .services import PDNDService, PDNDConfigurationError


class ANPRError(Exception):
    """Errore privo di token, CF e contenuto della risposta."""


class ANPRService(PDNDService):
    @classmethod
    def accerta_residenza(cls, codice_fiscale, *, operatore, riferimento_pratica,
                         data_riferimento=None, postazione, loa):
        return cls._consulta('C020', codice_fiscale, operatore, riferimento_pratica,
                             data_riferimento, postazione, loa)

    @classmethod
    def accerta_dati_anagrafici(cls, codice_fiscale, *, operatore, riferimento_pratica,
                              data_riferimento=None, postazione, loa):
        return cls._consulta('C029', codice_fiscale, operatore, riferimento_pratica,
                             data_riferimento, postazione, loa)

    @staticmethod
    def payload(caso, cf, pratica, data=None):
        cf = cf.strip().upper()
        if caso not in {'C020', 'C029'} or not re.fullmatch(r'[A-Z0-9]{16}|[0-9]{11}', cf):
            raise ValueError('Codice fiscale o caso d’uso non valido.')
        if not pratica or not pratica.strip():
            raise ValueError('Specificare il riferimento della pratica.')
        day = data or timezone.localdate()
        if type(day) is not date:
            raise ValueError('La data di riferimento deve essere datetime.date.')
        return {'idOperazioneClient': uuid.uuid4().hex,
                'criteriRicerca': {'codiceFiscale': cf},
                'datiRichiesta': {'casoUso': caso, 'motivoRichiesta': pratica.strip(),
                                  'dataRiferimentoRichiesta': day.isoformat()}}

    @staticmethod
    def normalizza(result, caso):
        if not isinstance(result, dict) or result.get('listaErrori'):
            raise ANPRError('ANPR ha restituito errori applicativi.')
        listing = result.get('listaSoggetti') or {}
        if not isinstance(listing, dict):
            raise ANPRError('Formato risposta ANPR inatteso.')
        subjects = listing.get('datiSoggetto', [])
        if not isinstance(subjects, list):
            raise ANPRError('Formato risposta ANPR inatteso.')
        people = []
        try:
            for subject in subjects:
                g = subject.get('generalita') or {}
                cf = g.get('codiceFiscale') or {}
                person = {'nome': g.get('nome'), 'cognome': g.get('cognome'),
                          'data_nascita': g.get('dataNascita'),
                          'senza_giorno': g.get('senzaGiorno'), 'senza_giorno_mese': g.get('senzaGiornoMese'),
                          'codice_fiscale': cf.get('codFiscale'), 'validita_cf': cf.get('validitaCF'),
                          'id_anpr': (subject.get('identificativi') or {}).get('idANPR')}
                if caso == 'C020':
                    person['residenze'] = subject.get('residenza') or []
                people.append(person)
        except (AttributeError, TypeError) as exc:
            raise ANPRError('Formato risposta ANPR inatteso.') from exc
        return {'soggetti': people, 'anomalie': result.get('listaAnomalie') or [],
                'id_operazione_anpr': result.get('idOperazioneANPR')}

    @classmethod
    def _consulta(cls, caso, cf, operator, pratica, day, location, loa):
        if not (getattr(operator, 'is_authenticated', False) and getattr(operator, 'is_active', False)
                and (operator.is_superuser or operator.has_perm('pdnd.consulta_anpr'))):
            raise PermissionError('Operatore non autorizzato alla consultazione ANPR.')
        payload = cls.payload(caso, cf, pratica, day)
        config = getattr(settings, 'ANPR', {})
        service = config.get(caso, {})
        endpoint = service.get('ENDPOINT', '')
        if (not cls.configuration().get('ENABLED') or not service.get('PURPOSE_ID')
                or urlsplit(endpoint).scheme != 'https' or not config.get('SECURITY_HEADERS_PROVIDER')):
            raise PDNDConfigurationError('Configurare endpoint HTTPS, finalità e provider firma/tracciamento ANPR.')
        if not location or not loa:
            raise ValueError('Postazione e livello di autenticazione sono obbligatori.')
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        audit = cls._audit(caso, payload['criteriRicerca']['codiceFiscale'], operator)
        audit.request_id = payload['idOperazioneClient']
        try:
            provider = import_string(config['SECURITY_HEADERS_PROVIDER'])
            # Il provider deve applicare i profili ModI concordati, usando gli stessi byte inviati.
            security = provider(body=body, purpose_id=service['PURPOSE_ID'],
                                audience=service.get('AUDIENCE', ''), user_id=str(operator.pk),
                                user_location=location, loa=loa,
                                correlation_id=payload['idOperazioneClient'])
            required = ('Agid-JWT-Signature', 'Agid-JWT-TrackingEvidence')
            if not isinstance(security, dict) or any(not security.get(h) for h in required):
                raise PDNDConfigurationError('Firma/tracciamento ANPR incompleti.')
            headers = {h: security[h] for h in required}
            headers.update({'Authorization': 'Bearer ' + cls._access_token(service['PURPOSE_ID']),
                            'Content-Type': 'application/json', 'Accept': 'application/json'})
            response = requests.post(endpoint, data=body, headers=headers,
                                     timeout=cls.configuration().get('TIMEOUT', 20), allow_redirects=False)
            if response.status_code != 200:
                raise ANPRError('ANPR: risposta HTTP %s.' % response.status_code)
            result = cls.normalizza(response.json(), caso)
            audit.esito = audit.Esito.ESEGUITA
            audit.save(update_fields=['esito', 'request_id'])
            return result
        except Exception as exc:
            audit.esito = audit.Esito.ERRORE
            audit.dettaglio_errore = 'Consultazione ANPR non completata (%s).' % type(exc).__name__
            audit.save(update_fields=['esito', 'request_id', 'dettaglio_errore'])
            raise ANPRError(audit.dettaglio_errore) from None
