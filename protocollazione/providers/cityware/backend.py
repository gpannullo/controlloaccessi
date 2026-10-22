import base64
import hashlib
from pathlib import PurePosixPath

from django.conf import settings
from protocollazione.contracts import (ProtocolloBackend,TipoProtocollo,EsitoProtocollo,
    ValidazioneProtocolloError,ConfigurazioneProtocolloError,EsitoIncertoError,Firmatario)
from .soap import CitywareSoapClient
from . import settings as cityware_settings


class CitywareBackend(ProtocolloBackend):
    TYPES={TipoProtocollo.ARRIVO:'A',TipoProtocollo.PARTENZA:'P',TipoProtocollo.INTERNO:'C'}

    def __init__(self):
        self.config = {
            'ENDPOINT': cityware_settings.ENDPOINT,
            'SOAP_ACTION_BASE': cityware_settings.SOAP_ACTION_BASE,
            'USERNAME': cityware_settings.USERNAME,
            'PASSWORD': cityware_settings.PASSWORD,
            'DOMAIN_CODE': cityware_settings.DOMAIN_CODE,
            'UFFICIO_OPERATORE': cityware_settings.UFFICIO_OPERATORE,
            'FIRMATARIO': cityware_settings.FIRMATARIO,
            'UFFICIO_FIRMATARIO': cityware_settings.UFFICIO_FIRMATARIO,
            'CA_BUNDLE': cityware_settings.CA_BUNDLE,
            'CONNECT_TIMEOUT': cityware_settings.CONNECT_TIMEOUT,
            'TIMEOUT': cityware_settings.TIMEOUT,
            'MAX_DOCUMENT_BYTES': cityware_settings.MAX_DOCUMENT_BYTES,
        }
        # Backward-compatible test/embedding override; production uses settings.py.
        override = getattr(settings, 'CITYWARE', None)
        if override:
            self.config.update(dict(override))

    def firmatari(self,r):
        if r.firmatari:return r.firmatari
        if self.config.get('FIRMATARIO') and self.config.get('UFFICIO_FIRMATARIO'):
            return (Firmatario(self.config['FIRMATARIO'],self.config['UFFICIO_FIRMATARIO']),)
        return ()

    def valida(self,r):
        if not all(self.config.get(k) for k in ('ENDPOINT','USERNAME','PASSWORD','DOMAIN_CODE')):
            raise ConfigurazioneProtocolloError('Configurare endpoint, credenziali e codice ente Cityware.')
        CitywareSoapClient(self.config)
        if r.tipo not in self.TYPES or not r.oggetto.strip() or not r.classificazione.strip():
            raise ValidazioneProtocolloError('Tipo, oggetto e classificazione sono obbligatori.')
        if not (r.ufficio or self.config.get('UFFICIO_OPERATORE')):
            raise ValidazioneProtocolloError('Ufficio operatore obbligatorio.')
        if r.tipo in (TipoProtocollo.PARTENZA,TipoProtocollo.INTERNO) and not self.firmatari(r):
            raise ValidazioneProtocolloError('Almeno un firmatario è obbligatorio per partenza o interno.')
        if r.tipo==TipoProtocollo.PARTENZA and not r.destinatari:
            raise ValidazioneProtocolloError('Indicare almeno un destinatario per la partenza.')
        if r.tipo==TipoProtocollo.ARRIVO and not r.mittenti:
            raise ValidazioneProtocolloError('Indicare almeno un mittente per l’arrivo.')
        if any(not p.denominazione.strip() for p in (*r.mittenti,*r.destinatari)):
            raise ValidazioneProtocolloError('Denominazione soggetto obbligatoria.')
        if any(not f.codice.strip() or not f.ufficio.strip() for f in self.firmatari(r)):
            raise ValidazioneProtocolloError('Firmatario e relativo ufficio obbligatori.')
        if any(not t.ufficio.strip() for t in r.trasmissioni):
            raise ValidazioneProtocolloError('Ufficio della trasmissione obbligatorio.')
        names = set()
        for doc in (r.documento, *r.allegati):
            if not doc.nome or len(doc.nome)>255 or '/' in doc.nome or '\\' in doc.nome or any(ord(c)<32 for c in doc.nome):
                raise ValidazioneProtocolloError('Nome documento non valido.')
            if doc.nome.casefold() in names:
                raise ValidazioneProtocolloError('I documenti devono avere nomi distinti.')
            names.add(doc.nome.casefold())
            if not isinstance(doc.contenuto,bytes) or not doc.contenuto or len(doc.contenuto)>self.config.get('MAX_DOCUMENT_BYTES',20*1024*1024):
                raise ValidazioneProtocolloError('Documento vuoto o oltre il limite configurato.')

    def payload(self,r):
        def party(p):
            return {k:v for k,v in {'denominazione':p.denominazione,'codice':p.codice,'codiceFiscale':p.codice_fiscale,'email':p.email,'indirizzo':p.indirizzo,'cap':p.cap,'citta':p.citta,'prov':p.provincia}.items() if v}
        data={'tipoProtocollo':self.TYPES[r.tipo],'ufficioOperatore':r.ufficio or self.config['UFFICIO_OPERATORE'],'oggetto':r.oggetto,'classificazione':r.classificazione,'riservato':r.riservato}
        # Manuale: firmatari solo obbligatori per P/C, mittenti/destinatari in base al tipo.
        # Il WSDL demo dichiara minOccurs=1 anche per elenchi non applicabili.
        if self.firmatari(r):data['firmatari']={'firmatario':[{'codice':f.codice,'ufficio':f.ufficio} for f in self.firmatari(r)]}
        if r.mittenti:data['mittenti']={'mittenteDestinatario':[party(p) for p in r.mittenti]}
        if r.destinatari:data['destinatari']={'mittenteDestinatario':[party(p) for p in r.destinatari]}
        if r.trasmissioni:data['trasmissioniInterne']={'trasmissione':[{'codiceDestinatario':t.soggetto,'codiceUfficio':t.ufficio,'gestione':t.gestione,'responsabile':t.responsabile} for t in r.trasmissioni]}
        doc=r.documento
        data['allegato']={'id':'','tipoFile':'PRINCIPALE','nomeFile':doc.nome,'estensione':PurePosixPath(doc.nome).suffix.lstrip('.'),'stream':base64.b64encode(doc.contenuto).decode('ascii'),'note':'','marcaDocumento':'1' if doc.marca_segnatura else '0','mettiAllaFirma':'0','sha':hashlib.sha256(doc.contenuto).hexdigest()}
        return data

    def protocolla(self,richiesta):
        self.valida(richiesta)
        payload=self.payload(richiesta)
        client=CitywareSoapClient(self.config)
        with client.session() as token:
            if richiesta.allegati:
                # Manuale 8.4.4: preload all PDFs, then register once, not N protocols.
                payload.pop('allegato')
                uploaded = []
                for index, doc in enumerate((richiesta.documento, *richiesta.allegati)):
                    response = client.call('InsertDocumento', {
                        'token': token, 'nomeFile': doc.nome,
                        'stream': base64.b64encode(doc.contenuto).decode('ascii')}, writing=True)
                    info = response.get('allegatoPrecaricato') or {}
                    status = (response.get('messageResult') or {}).get('tipoRisultato', '')
                    digest = hashlib.sha256(doc.contenuto).hexdigest()
                    if (str(status).lower() not in ('info', 'warning') or not isinstance(info, dict)
                            or not isinstance(info.get('idunivoco'), str) or not info['idunivoco'].strip()
                            or str(info.get('hashfile', '')).lower() != digest):
                        raise EsitoIncertoError('Precaricamento non confermato: verificare Cityware prima di ripetere.')
                    uploaded.append({
                        'idunivoco': info['idunivoco'], 'hashfile': digest, 'nomeFile': doc.nome,
                        'tipoFile': 'PRINCIPALE' if index == 0 else 'ALLEGATO',
                        'estensione': PurePosixPath(doc.nome).suffix.lstrip('.'), 'note': '',
                        'marcaDocumento': '1' if doc.marca_segnatura else '0', 'mettiAllaFirma': '0'})
                payload['allegatiPrecaricati'] = {'allegatoPrecaricato': uploaded}
            result=client.call('PutProtocollo',{'token':token,'datiProtocollo':payload},writing=True)
            return self.esito(result,richiesta.tipo)

    def esito(self,result,tipo):
        # WSDL e manuale differiscono nel nome del contenitore della risposta.
        info=result.get('datiProtocollo') or result.get('retProtocollo') or result.get('items') or {}
        message=result.get('messageResult') or {}
        status=str(message.get('tipoRisultato','')).lower()
        if status not in ('info','warning') or not isinstance(info,dict):
            raise EsitoIncertoError('Registrazione non confermata: verificare il gestionale.')
        fields=['rowidProtocollo','annoProtocollo','numeroProtocollo','tipoProtocollo','dataProtocollo','segnatura']
        if not all(isinstance(info.get(k),str) and info[k].strip() for k in fields) or info['tipoProtocollo']!=self.TYPES[tipo]:
            raise EsitoIncertoError('Risposta priva degli estremi completi del protocollo.')
        return EsitoProtocollo(info['rowidProtocollo'],info['annoProtocollo'],info['numeroProtocollo'],str(tipo),info['dataProtocollo'],info['segnatura'],status=='warning')
