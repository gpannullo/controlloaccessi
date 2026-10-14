# Cityware e protocollazione intercambiabile

Le app applicative chiamano **solo** `protocollazione.services.protocolla`.
`ProtocolloBackend` e' il contratto astratto; `cityware.backend.CitywareBackend`
implementa login, PutProtocollo con documento principale Base64 e logout SOAP 1.1.
Per sostituire il gestionale implementare un nuovo backend conforme e cambiare
`PROTOCOLLAZIONE_BACKEND`, installando/configurando la relativa app. Non modificare
visitors, prenotazioni o le altre app chiamanti. Gli esiti storici mantengono il
backend originale. I codici di uffici, firmatari e classificazione vanno rimappati
nella configurazione/dati del nuovo fornitore: non sono identificativi universali.

## Stato e limiti della prima integrazione

- Codice installato, invii disabilitati per default. Nessuna chiamata di scrittura
  effettuata, nemmeno sul sistema demo. Nessun pulsante di protocollazione del
  report collegato automaticamente: i parametri vanno concordati prima.
- Un documento principale per registrazione, protocollo Arrivo/Partenza/Interno,
  mittenti/destinatari, firmatari, classificazione, riservatezza e trasmissioni.
- La protocollazione non equivale a firma digitale, invio PEC, pubblicazione o
  conservazione. `mettiAllaFirma=0`; marcatura segnatura solo su richiesta.
- Fascicolazione studiata (manuale wsProFascicolo 1.4), NON eseguita implicitamente.
  CreaFascicolo/FascicolaProtocollo e ulteriori allegati sono estensioni successive:
  non si presume alcun fascicolo o sottofascicolo dell'ente.
- Non viene archiviato il documento nel registro: l'app chiamante deve conservarne
  i byte definitivi in storage privato con adeguata retention prima dell'invio.
  Se si marca il PDF lato Cityware, l'hash locale identifica l'originale inviato,
  non il documento marcato: il recupero di quest'ultimo e' un passo successivo.

## Configurazione

Variabili in `deploy/cityware.env.example`; credenziali solo nell'env protetto.
Richiedere endpoint HTTPS, SOAPAction del WSDL, utente abilitato, codice ente,
ufficio operatore, firmatario/ufficio e classificazione concordata. Non sono state
copiate le credenziali demo dei manuali nel codice o nell'env.
Il WSDL demo ha soapAction con schema HTTP mentre il trasporto e' HTTPS:
`CITYWARE_SOAP_ACTION_BASE` conserva quell'identificatore, senza trasmettere via HTTP.
Nessun `verify=False`, redirect o retry automatico. Timeout separati, risposta
limitata a 2 MB, XML senza DTD/entita' esterne. Il documento e' limitato a 20 MB
prima della codifica Base64 (configurabile).

## API comune

```python
from protocollazione.contracts import Documento, RichiestaProtocollo, TipoProtocollo
from protocollazione.services import protocolla

richiesta = RichiestaProtocollo(
    oggetto="Registro visitatori del ...",
    tipo=TipoProtocollo.INTERNO,
    documento=Documento("registro-visitatori.pdf", pdf_definitivo),
    classificazione=classificazione_concordata,
    riservato=True,
)
esito = protocolla(richiesta, chiave="report-visitatori:<id-versione-stabile>", operatore=request.user)
# esito.anno, numero, data, segnatura, identificativo, tipo, avviso
```

La chiave e' unica per la versione del documento: NON generarne una nuova ad ogni
click e NON rigenerare il PDF ad ogni retry (data/ID estrazione cambiano i byte).
Servono utente attivo e permesso `protocollazione.add_registrazioneprotocollo`.
Una futura view deve essere POST, protetta CSRF e dai permessi del modulo; mai GET.
Non chiamare dentro `transaction.atomic`/ATOMIC_REQUESTS: il registro deve essere
committato prima della chiamata esterna. Con ATOMIC_REQUESTS usare non_atomic_requests.

## Registro e prevenzione doppioni

`RegistrazioneProtocollo` conserva chiave, backend, hash SHA256 della richiesta e
del documento, operatore, stato ed estremi restituiti. L'admin e' di sola lettura
(servono i permessi di consultazione oltre all'accesso admin previsto dal progetto).
Non registra password, token, XML SOAP o contenuto documenti.

- Completato + stessa chiave/dati: restituisce l'esito salvato senza reinviare.
- Stessa chiave con dati diversi: rifiuto.
- In corso, errore o incerto: blocco, nessun reinvio automatico.
- Crash/errore DB dopo l'invio: la riga rimane in corso; verifica manuale necessaria.
- Timeout, SOAP Fault o risposta incompleta dopo PutProtocollo: esito incerto.
- Errore login: nessuna registrazione inviata; stato errore.
- Warning con estremi completi: conserva protocollo con `avviso=True`.

Cityware non documenta una chiave idempotente server-side. Non e' quindi possibile
garantire exactly-once tra rete e database; il blocco persistente richiede verifica
umana degli esiti dubbi. Non cancellare righe e non usare nuove chiavi per aggirarlo.
Un fallimento del logout non annulla una protocollazione gia' confermata.

## Verifica e attivazione

Test offline, SQLite in memoria, nessun DB produttivo e nessuna chiamata SOAP:
`python manage.py test protocollazione --settings=protocollazione.test_settings`

Riferimenti: manuale_wsProtocollo_v8_4.4.pdf pp. 2-4, 16-20; guida Demo e Guida
uitlizzo Web Service Protocollo pp. 1-2; manuale_wsProFascicolo 1.4 pp. 6-7.
Controllato anche il WSDL demo in sola lettura. Il manuale usa `retProtocollo`,
il WSDL `datiProtocollo`: sono gestite entrambe le risposte. Gli elenchi non
applicabili vengono omessi secondo il manuale, non vengono inventati firmatari
o destinatari fittizi per soddisfare minOccurs incoerenti del WSDL demo.

Prima dell'uso reale: verificare WSDL/versione dell'ente, configurazione e permessi;
autorizzare una registrazione di collaudo su ambiente test, verificare documento,
segnatura e riservatezza nel gestionale, poi abilitare esplicitamente gli invii.
