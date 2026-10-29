import requests
from protocollazione.providers.cityware.soap import envelope
from protocollazione.providers.cityware import settings as s

s.USERNAME = 'wsuser_iris'
s.PASSWORD = 'Ye6B^#U#UiVHk-t'

body = envelope(
    "GetItaEngineContextToken",
    {
        "userName": s.USERNAME,
        "userPassword": s.PASSWORD,
        "domainCode": s.DOMAIN_CODE,
    },
)

headers = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": (
        f'"{s.SOAP_ACTION_BASE.rstrip("/")}/'
        'GetItaEngineContextToken"'
    ),
}

response = requests.post(
    s.ENDPOINT,
    data=body,
    headers=headers,
    timeout=(10, 60),
    verify=True,
)

print("HTTP:", response.status_code)
print(response.text[:5000])
