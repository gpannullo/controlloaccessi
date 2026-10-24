"""Test manuale del ciclo login/logout Cityware.

Eseguire dalla root del progetto con l'ambiente Django caricato. Non crea
protocolli e non stampa password o il token completo.
"""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ControlloAccessi.settings')

import django

django.setup()

from protocollazione.providers.cityware import settings as cityware_settings
from protocollazione.providers.cityware.soap import CitywareSoapClient


def mask(value):
    value = str(value or '')
    return value[:4] + ('...' if len(value) > 8 else '') + value[-4:] if value else '<vuoto>'


def main():
    config = {
        'ENDPOINT': cityware_settings.ENDPOINT,
        'SOAP_ACTION_BASE': cityware_settings.SOAP_ACTION_BASE,
        'USERNAME': cityware_settings.USERNAME,
        'PASSWORD': cityware_settings.PASSWORD,
        'DOMAIN_CODE': cityware_settings.DOMAIN_CODE,
        'CA_BUNDLE': cityware_settings.CA_BUNDLE,
        'CONNECT_TIMEOUT': cityware_settings.CONNECT_TIMEOUT,
        'TIMEOUT': cityware_settings.TIMEOUT,
    }
    print(f'Endpoint: {config["ENDPOINT"]}')
    print(f'Utente: {config["USERNAME"] or "<mancante>"}')
    print(f'Dominio: {config["DOMAIN_CODE"]}')
    if not config['USERNAME'] or not config['PASSWORD']:
        print('ERRORE: CITYWARE_USERNAME o CITYWARE_PASSWORD mancanti.', file=sys.stderr)
        return 2

    client = CitywareSoapClient(config)
    token = None
    try:
        print('LOGIN: chiamata GetItaEngineContextToken...')
        result = client.call('GetItaEngineContextToken', {
            'userName': config['USERNAME'],
            'userPassword': config['PASSWORD'],
            'domainCode': config['DOMAIN_CODE'],
        })
        token = result.get('return')
        if not isinstance(token, str) or not token.strip():
            print(f'LOGIN FALLITO: risposta senza ticket (campi: {sorted(result)})', file=sys.stderr)
            return 1
        print(f'LOGIN OK: ticket={mask(token)}')
        print('LOGOUT: chiamata DestroyItaEngineContextToken...')
        logout = client.call('DestroyItaEngineContextToken', {
            'token': token,
            'domainCode': config['DOMAIN_CODE'],
        })
        print(f'LOGOUT OK: risposta ricevuta (campi: {sorted(logout)})')
        return 0
    except Exception as exc:
        print(f'ERRORE Cityware: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
