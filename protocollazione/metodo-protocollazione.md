# Metodo comune per protocollare PDF

L'app chiamante non dipende da Cityware: usa
`protocollazione.services.protocolla_documenti`. Il backend è selezionato da
`PROTOCOLLAZIONE_BACKEND`. Il provider predefinito è
`protocollazione.providers.cityware.backend.CitywareBackend`; nessuna pianificazione
è necessaria per questo metodo.

```python
from protocollazione.contracts import Documento, Firmatario, Soggetto, TipoProtocollo
from protocollazione.services import protocolla_documenti

esito = protocolla_documenti(
    ufficio="CODICE_UFFICIO",
    firmatario=Firmatario(codice="CODICE_FIRMATARIO", ufficio="CODICE_UFFICIO_FIRMATARIO"),
    destinatario=Soggetto(denominazione="Ufficio destinatario", codice="CODICE_DESTINATARIO"),
    pdf=[Documento("report.pdf", pdf_bytes), Documento("dettaglio.pdf", dettaglio_bytes)],
    oggetto="Registro accessi del 21 ottobre 2026",
    classificazione="CODICE_TITOLARIO",
    tipo=TipoProtocollo.INTERNO,  # default PARTENZA
    chiave="registro-accessi:2026-10-21:v1",  # stabile per questa richiesta
    operatore=request.user,
)
numero = esito.numero
anno = esito.anno
segnatura = esito.segnatura
```

`pdf` accetta anche un solo Documento; `destinatario` anche una sequenza di
Soggetto. I codici sono quelli del gestionale protocollo, non le PK Django.
Il primo PDF è il principale, gli altri sono allegati allo STESSO protocollo.
Nomi distinti, bytes PDF, limite Cityware per documento applicato a tutti i file.
La verifica dell'intestazione PDF non equivale a validazione PDF/A o antivirus.
I file definitivi devono essere conservati dall'app chiamante.

Sono obbligatori oggetto e classificazione oltre ai dati richiesti. `riservato`
è True per default. Per un destinatario interno da mettere in carico con
trasmissione/gestione, il contratto di basso livello supporta anche `Trasmissione`:
non confondere il codice di un soggetto destinatario con il codice dell'ufficio.

## Risultato e audit

Il risultato EsitoProtocollo contiene numero (stringa, conserva gli zeri), anno,
data, segnatura, identificativo remoto, tipo ed eventuale avviso. Prima del ritorno
viene salvato nel registro protocolli e in AuditEvent con tipo SYSTEM,
oggetto `protocollazione:<id registro>` e azione PROTOCOLLAZIONE_COMPLETATA.
L'audit contiene operatore, chiave, backend ed estremi, non PDF o credenziali.

Riutilizzando la stessa chiave e gli stessi dati si ottiene lo stesso esito senza
nuovo invio né duplicazione audit. Se cambia anche un solo allegato la richiesta
è bloccata. Un errore nella scrittura audit dopo il successo remoto è recuperabile
richiamando con la stessa chiave e gli stessi dati, senza ripetere la protocollazione.

L'operatore deve essere attivo e possedere il permesso
`protocollazione.add_registrazioneprotocollo`. Occorrono
`PROTOCOLLAZIONE_ENABLED=true` e configurazione Cityware valida. Eseguire fuori
da transazioni DB/ATOMIC_REQUESTS; non chiamare questo metodo dal save di un
modello dentro una transazione. In caso di esito incerto non cambiare chiave né
reinviare: verificare il registro e il gestionale.

Cityware: con più PDF esegue InsertDocumento per tutti, controlla gli hash SHA256,
poi un solo PutProtocollo con allegatiPrecaricati. Se il precaricamento fallisce
non esegue PutProtocollo; possono rimanere file temporanei sul gestionale da
verificare manualmente. Non sono attivati invii reali nei test automatici.
