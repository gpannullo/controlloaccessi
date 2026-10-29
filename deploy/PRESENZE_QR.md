# Presenze QR

Modulo per personale autenticato, attivo, non DIS e senza badge (anche
`0000000000` viene considerato un segnaposto). Non usa PDND o WordPress.
Usa il login personale esistente, incluso il cambio password obbligatorio.

## Attivazione

1. Distribuire il codice e applicare `python manage.py migrate presenze_qr`.
2. Impostare nell'ambiente del servizio:

```ini
PRESENZE_QR_ENABLED=true
PRESENZE_QR_SOLO_RETE_COMUNALE=false
PRESENZE_QR_RETI_CONSENTITE=10.0.0.0/22,192.168.15.0/24
PRESENZE_QR_PROXY_ATTENDIBILI=127.0.0.1/32,::1/128
```

Le reti sono esempi basati sull'attuale configurazione: verificare gli IP
effettivamente osservati, NAT e proxy prima di attivare la restrizione.
Non inserire tutta la LAN tra i proxy attendibili. Gunicorn deve essere
raggiungibile solo dal reverse proxy. Nginx deve SOVRASCRIVERE
`X-Real-IP` con `$remote_addr`, non accettare quello inviato dal client.
Se il peer è un proxy attendibile e l'header manca/non è valido, le funzioni
riservate alla rete vengono negate. Non viene usato X-Forwarded-For.

Il vhost account deve inoltrare `/account/presenze/` a Django, senza un
allow/deny interno applicato a questo percorso se si desidera usare la rete mobile.
Il monitor `/qr/` (alias `/monitor-presenze/<id>/`) deve essere esposto solo sul vhost interno,
con le stesse restrizioni Nginx/firewall di ControlloAccessi.
Il controllo applicativo verifica sempre host e rete, anche sul POST che
genera/legge il QR. Il monitor non richiede login; il telefono deve invece
autenticare il dipendente per timbrare. Il POST del monitor mantiene il CSRF.

3. Riavviare il servizio. In admin creare una **Postazione presenze QR**.
4. Utilizzare il PC del monitor senza sessioni amministrative aperte.
5. Aprire il link **Apri monitor** della postazione in admin oppure
   `https://controlloaccessi.comune.aversa.ce.it/qr/` (prima postazione attiva).
   Per una postazione specifica resta valido `/monitor-presenze/<id>/`.
6. Sul cellulare utilizzare il QR o la voce **Presenze QR** del portale Account.

Il QR PNG usa qrcode/Pillow gia presenti tra le dipendenze della stampa.
La pagina monitor e autonoma, senza jQuery, Bootstrap o CDN; usa XMLHttpRequest
e JavaScript classico. Richiede JSON.parse e supporto PNG data URI (IE8 o superiore).
Su Windows XP la compatibilita TLS/certificati dipende dal browser: non ridurre
la sicurezza HTTPS del server. La compatibilita sul dispositivo va collaudata.
Il modulo è DISABILITATO per default: distribuirlo non abilita le timbrature.

## Regole

- QR unico per postazione, valido 30 secondi, consumato dal primo POST riuscito.
- Monitor aggiorna ogni secondo: dopo il consumo mostra un nuovo QR al polling
  successivo; nessuna seconda persona può usare il precedente nel frattempo.
- Alla scadenza il vecchio QR viene nascosto anche se manca la connessione.
- Generazione e consumo bloccano la riga della postazione in PostgreSQL;
  la generazione del timbro è inoltre unica a DB. Ripetere lo stesso POST
  dallo stesso utente restituisce il timbro già creato senza duplicarlo.
- Il link contiene il token nel frammento `#token=`, non nella richiesta GET.
  Il browser lo conserva temporaneamente in sessionStorage durante il login e
  lo cancella dopo il successo. Non inserire il token nei log applicativi.
- La GET non timbra: dopo il login la pagina usa un POST con CSRF.
- Dalle 08:00:00 alle 09:30:00 incluse: Entrata automatica.
- Dalle 12:30:00 alle 14:00:00 incluse: Uscita automatica.
- Fuori fascia: scelta manuale. L'orario autorevole è il server, Europe/Rome.
- Se il QR scade durante il login/cambio password/completamento profilo,
  inquadrare il nuovo QR. Non si prolunga la validità per il singolo utente.
- Ultime 10 timbrature QR personali (non storico del lettore fisico).
- Correzione del proprio verso entro 60 secondi ORIGINALI, verificati dal server.
  L'orario del timbro non cambia; ogni inversione è registrata nello storico.
- Aggiornamento stato presenza tramite update diretto, senza scritture LDAP/WP.
  Correggere un timbro precedente non sovrascrive la presenza di uno successivo.
- Il lettore badge ignora il segnaposto zero e non ripristina timbrature più vecchie
  di un timbro QR se successivamente viene associato un badge.
- Lo stub API di presenza non sovrascrive uno stato QR con NON_VERIFICATA.
- Nessun azzeramento giornaliero automatico nuovo: valgono i movimenti registrati.

## Audit e limiti

Registro in admin: aperture, generazione QR, timbrature, correzioni e rifiuti.
Sono registrati utente, orario, IP e postazione dove disponibile, mai password
o token completi. Timbrature e audit sono in sola lettura nell'admin.
Definire con l'Ente tempi di conservazione, informativa e accessi autorizzati;
non viene introdotta automaticamente una cancellazione dei registri.

Un QR dinamico non certifica la presenza fisica: può essere inoltrato in tempo
reale. Il flag di rete riduce questa possibilità, dipendendo dalla configurazione
del proxy e dell'eventuale VPN. Non è previsto un blocco basato sulla posizione GPS.

Prima del deploy definitivo collaudare: due telefoni sullo stesso QR (un solo
successo), scadenza QR, login da rete mobile, attivazione del flag LAN e tentativo
di correzione oltre un minuto. I test locali usano un DB isolato, non account AD.
