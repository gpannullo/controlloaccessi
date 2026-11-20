import os
import urllib
from pprint import pprint

import requests
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.exceptions import Fault

WSDL_URL = ("https://boaversa.nuvolapalitalsoft.it/ws/Protocollo/proWsProtocollo.php?wsdl")

wsdl =  urllib.request.urlopen(WSDL_URL).read().decode('utf-8')

# client = Client(wsdl)
client = Client(wsdl=WSDL_URL)

print("PRIMO CLIENT")

USERNAME = 'wsuser_iris'
PASSWORD = 'stH$!kt^BtBh38'
DOMAIN_CODE = "01"

session = requests.Session()
session.verify = True

transport = Transport(
    session=session,
    timeout=60,
    operation_timeout=60,
)

settings = Settings(strict=False, xml_huge_tree=True)

client = Client(
    wsdl=WSDL_URL,
    transport=transport,
    settings=settings,
)

try:
    print("Login Cityware...")

    ticket = client.service.GetItaEngineContextToken(
        userName=USERNAME,
        userPassword=PASSWORD,
        domainCode=DOMAIN_CODE,
    )

    if not ticket:
        raise RuntimeError("Cityware non ha restituito il ticket.")

    print("Login effettuato.")
    print("Ticket ricevuto:", str(ticket)[:4] + "...")

    # Qui si possono effettuare le chiamate successive,
    # ad esempio PutProtocollo usando ticket.

except Fault as exc:
    print("Errore SOAP Cityware:", exc)

except Exception as exc:
    print("Errore di comunicazione:", type(exc).__name__, exc)

finally:
    if "ticket" in locals() and ticket:
        try:
            print("Logout Cityware...")

            client.service.DestroyItaEngineContextToken(
                token=ticket,
                domainCode=DOMAIN_CODE,
            )

            print("Logout completato.")

        except Exception as exc:
            print("Logout non confermato:", type(exc).__name__, exc)