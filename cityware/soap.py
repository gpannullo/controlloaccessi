"""SOAP 1.1 RPC encoded come da manuale wsProtocollo 8.4.4.

Nessun retry, redirect, logging del payload o disabilitazione TLS.
"""
from contextlib import contextmanager
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import requests
from defusedxml.ElementTree import fromstring

from protocollazione.contracts import ConfigurazioneProtocolloError, ErroreProtocollo, EsitoIncertoError

SOAP='http://schemas.xmlsoap.org/soap/envelope/'
XSI='http://www.w3.org/2001/XMLSchema-instance'
NS='urn:proWsProtocollo'
ET.register_namespace('soapenv',SOAP)
ET.register_namespace('xsi',XSI)


def envelope(method, data):
    root=ET.Element(f'{{{SOAP}}}Envelope',{'xmlns:xsd':'http://www.w3.org/2001/XMLSchema','xmlns:tns':NS})
    body=ET.SubElement(root,f'{{{SOAP}}}Body')
    call=ET.SubElement(body,method,{f'{{{SOAP}}}encodingStyle':'http://schemas.xmlsoap.org/soap/encoding/'})
    types={'datiProtocollo':'datiProtocollo','firmatari':'firmatari','firmatario':'firmatario','mittenti':'mittenti','destinatari':'destinatari','mittenteDestinatario':'mittenteDestinatario','trasmissioniInterne':'trasmissioniInterne','trasmissione':'trasmissione','allegato':'allegato'}
    def add(parent,key,value):
        if isinstance(value,list):
            for item in value: add(parent,key,item)
            return
        node=ET.SubElement(parent,key)
        if isinstance(value,dict):
            node.set(f'{{{XSI}}}type','tns:'+types[key])
            for k,v in value.items():add(node,k,v)
        else:
            node.set(f'{{{XSI}}}type','xsd:boolean' if isinstance(value,bool) else 'xsd:string')
            node.text=('true' if value else 'false') if isinstance(value,bool) else str(value)
    for key,value in data.items():add(call,key,value)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def parse_response(content, method):
    root=fromstring(content,forbid_dtd=True,forbid_entities=True,forbid_external=True)
    body=root.find(f'{{{SOAP}}}Body')
    if body is None:raise ValueError('SOAP Body assente')
    def local(node):return node.tag.rsplit('}',1)[-1]
    if any(local(n)=='Fault' for n in body):raise ValueError('SOAP Fault')
    result=next((n for n in body if local(n)==method+'Response'),None)
    if result is None:raise ValueError('Operazione di risposta inattesa')
    refs={node.attrib['id']:node for node in root.iter() if 'id' in node.attrib}
    def unpack(node,seen=()):
        href=node.attrib.get('href','')
        if href:
            if not href.startswith('#') or href in seen or href[1:] not in refs:raise ValueError('Riferimento SOAP invalido')
            return unpack(refs[href[1:]],seen+(href,))
        if node.attrib.get(f'{{{XSI}}}nil') in ('true','1'):return None
        if not len(node):return node.text or ''
        return {local(child):unpack(child,seen) for child in node}
    return {local(n):unpack(n) for n in result}


class CitywareSoapClient:
    def __init__(self,config):
        self.config=config
        self.endpoint=config.get('ENDPOINT','')
        url=urlsplit(self.endpoint)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ConfigurazioneProtocolloError('CITYWARE_ENDPOINT deve essere un endpoint HTTPS senza query o credenziali.')
        self.action_base=config.get('SOAP_ACTION_BASE') or self.endpoint
        if any(c in self.action_base for c in ('\r','\n','"')):
            raise ConfigurazioneProtocolloError('SOAP action non valida.')

    def call(self,method,data,*,writing=False):
        try:
            payload=envelope(method,data)
        except Exception:
            raise ErroreProtocollo('Impossibile serializzare la richiesta SOAP.') from None
        try:
            with requests.Session() as session:
                session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
                with session.post(self.endpoint,data=payload,headers={'Content-Type':'text/xml; charset=utf-8','SOAPAction':f'"{self.action_base.rstrip("/")}/{method}"'},timeout=(self.config.get('CONNECT_TIMEOUT',10),self.config.get('TIMEOUT',60)),verify=self.config.get('CA_BUNDLE') or True,allow_redirects=False,stream=True) as response:
                    response.raise_for_status()
                    if response.status_code!=200:raise ValueError('HTTP inatteso')
                    parts=[]; size=0
                    for part in response.iter_content(65536):
                        size+=len(part)
                        if size>2*1024*1024:raise ValueError('Risposta eccessiva')
                        parts.append(part)
            return parse_response(b''.join(parts),method)
        except Exception:
            if writing:
                raise EsitoIncertoError('Esito remoto non verificabile: controllare Cityware prima di ripetere.') from None
            raise ErroreProtocollo('Comunicazione Cityware non riuscita prima della registrazione.') from None

    @contextmanager
    def session(self):
        result=self.call('GetItaEngineContextToken',{'userName':self.config['USERNAME'],'userPassword':self.config['PASSWORD'],'domainCode':self.config['DOMAIN_CODE']})
        token=result.get('return')
        if not isinstance(token,str) or not token.strip():
            raise ErroreProtocollo('Cityware non ha restituito un token valido.')
        try:
            yield token
        finally:
            try:
                self.call('DestroyItaEngineContextToken',{'token':token,'domainCode':self.config['DOMAIN_CODE']})
            except ErroreProtocollo:
                # Logout failure must never turn a successful write into a retry.
                import logging
                logging.getLogger(__name__).warning('Chiusura sessione Cityware non confermata.')
