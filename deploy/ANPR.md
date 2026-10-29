# ANPR C020 e C029

Adapter predisposti, non attivati. Nessuna chiamata reale effettuata.
Le altre funzioni PDND e la UI generica esistente restano invariate.

```python
from pdnd.anpr import ANPRService
esito = ANPRService.accerta_dati_anagrafici(
    codice_fiscale, operatore=request.user, riferimento_pratica=numero_pratica,
    postazione=identificativo_postazione, loa=livello_autenticazione,
)
# Stessi argomenti per ANPRService.accerta_residenza(...).
```

La risposta contiene `soggetti` (lista, mai scelta arbitrariamente la prima
persona), `anomalie`, `id_operazione_anpr`. Le residenze sono incluse solo
per C020. Campi mancanti e date incomplete non vengono inventati.
`validita_cf` è l'indicatore ANPR, non una validazione locale del checksum.

L'operatore deve essere attivo e superuser oppure avere `pdnd.consulta_anpr`.
Eseguire la migration PDND prima dell'uso. L'audit registra il CF hashato,
il servizio e l'identificativo client, non il corpo della risposta.

## Configurazione

Restano necessarie le variabili PDND generali esistenti (client, chiave,
KID, token URL, audience client assertion). Aggiungere:

* PDND_ANPR_C020_ENDPOINT
* PDND_ANPR_C020_PURPOSE_ID
* PDND_ANPR_C020_AUDIENCE
* PDND_ANPR_C029_ENDPOINT
* PDND_ANPR_C029_PURPOSE_ID
* PDND_ANPR_C029_AUDIENCE
* PDND_ANPR_SECURITY_HEADERS_PROVIDER

Gli endpoint sono URL completi terminanti con `/anpr-service-e002`:
collaudo `https://modipa-val.anpr.interno.it/govway/rest/in/MinInternoPortaANPR-PDND/C029-servizioAccertamentoDatiAnagrafici/v1/anpr-service-e002`;
per C020 il segmento servizio è `C020-servizioAccertamentoResidenza`.
In produzione l'host è `modipa.anpr.interno.it`.

## Blocco di sicurezza da completare prima dell'attivazione

Gli YAML forniti dichiarano i pattern AUDIT_REST_02/INTEGRITY_REST_02 ma
l'operazione POST ridefinisce la security con solo Bearer. Non dedurre da
questo che firma e tracciamento siano facoltativi.
Il provider (percorso Python importabile) dovrà essere implementato dopo
conferma dei profili dell'erogatore. Riceve body bytes, purpose_id, audience,
user_id, user_location, loa e correlation_id; deve restituire gli header
Agid-JWT-Signature e Agid-JWT-TrackingEvidence correttamente firmati.
Non inserire JWT statici nell'env. Verificare anche l'eventuale correlazione
richiesta con il voucher/client assertion prima del collaudo.
Senza provider la chiamata viene bloccata: non è ancora un'integrazione live.

Non sono stati aggiunti pulsanti o endpoint pubblici e non è stato fatto deploy.
