"""Configurazione non segreta del provider Cityware.

Le credenziali sono lette esclusivamente dall'ambiente del processo.
"""
import os

ENDPOINT = 'https://boaversa.nuvolapalitalsoft.it/ws/Protocollo/proWsProtocollo.php'
SOAP_ACTION_BASE = ENDPOINT
DOMAIN_CODE = 'A512'
UFFICIO_OPERATORE = '0010'
FIRMATARIO = '0081'
UFFICIO_FIRMATARIO = '0010'
CA_BUNDLE = ''
CONNECT_TIMEOUT = 10
TIMEOUT = 60
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024

USERNAME = os.getenv('CITYWARE_USERNAME', '')
PASSWORD = os.getenv('CITYWARE_PASSWORD', '')

