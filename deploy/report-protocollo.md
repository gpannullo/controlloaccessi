# Protocollazione giornaliera

Due protocolli INTERNI riservati separati: visitatori e passaggi QR del giorno
precedente, alle 01:00 Europe/Rome. Anche le giornate senza movimenti producono un
report. Sono riutilizzati i PDF delle pagine di generazione, con secondi inclusi.
Il report visitatori include accessi a cavallo della mezzanotte e la cronologia
completa degli accessi selezionati; quello QR esclude le timbrature automatiche.

## Configurazione

Configurare le variabili CITYWARE_* esistenti (endpoint HTTPS, credenziali,
dominio e CA) e nell'env del solo server di produzione aggiungere:

```dotenv
PROTOCOLLAZIONE_ENABLED=true
REPORT_PROTOCOLLO_OPERATORE=utente_servizio_locale
REPORT_PROTOCOLLO_CLASSIFICAZIONE_VISITATORI=CODICE_TITOLARIO
REPORT_PROTOCOLLO_CLASSIFICAZIONE_QR=CODICE_TITOLARIO
REPORT_PROTOCOLLO_UFFICIO=CODICE_UFFICIO
REPORT_PROTOCOLLO_FIRMATARIO=CODICE_SOGGETTO_CITYWARE
REPORT_PROTOCOLLO_UFFICIO_FIRMATARIO=CODICE_UFFICIO
```

I codici devono essere confermati dal responsabile del protocollo. L'operatore
è un utente Django attivo con il permesso `protocollazione.add_registrazioneprotocollo`;
non serve che sia superuser. Le credenziali Cityware restano distinte.

Dopo deploy e `manage.py migrate`, con env caricato eseguire:

```sh
/var/www/controlloaccessi/venv/bin/python manage.py protocolla_report_giornalieri
```

Senza `--invia` genera e valida in memoria: nessuna scrittura DB né chiamata remota.
Non verifica quindi l'autenticazione effettiva presso Cityware. Per un invio reale
autorizzato aggiungere `--invia`. Opzioni: `--data YYYY-MM-DD`,
`--tipo visitatori` oppure `--tipo qr`. Ammesse solo giornate concluse.

## Attivazione (solo produzione, dopo approvazione dei codici)

```sh
sudo install -m 644 deploy/systemd/controlloaccessi-report-protocollo.service /etc/systemd/system/
sudo install -m 644 deploy/systemd/controlloaccessi-report-protocollo.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now controlloaccessi-report-protocollo.timer
sudo systemctl list-timers controlloaccessi-report-protocollo.timer
```

Non installare/abilitare il timer sul server di test: database distinti non
condividono la protezione contro duplicati. Persistent recupera un'attivazione
persa, ma NON ricostruisce tutti i giorni di un fermo prolungato. Recuperare le
singole date mancanti esplicitamente con `--data`, tenendo presente che i PDF
sono fotografie dei dati disponibili al momento della generazione.

## Registro e sicurezza

Admin → Protocollazione documenti → Report giornalieri: copia PDF immutabile
scaricabile con permesso di visualizzazione. Registrazioni protocollo: esito,
numero, anno, segnatura. I PDF contengono dati personali: proteggere DB e backup,
non pubblicarli in static/media. Concordare tempi di conservazione con l'Ente.

Una chiave univoca per tipo/data e un PDF conservato impediscono rigenerazioni e
duplicati. Cambi di configurazione non alterano una richiesta già conservata.
Un report fallito non impedisce il tentativo dell'altro; il comando termina con
errore se uno fallisce. IN_CORSO, INCERTO o ERRORE nel registro impediscono nuovi
invii: verificare prima in Cityware, non cancellare registri e non cambiare chiavi
per forzare il reinvio. Nessun retry automatico di scritture SOAP.

Controllare gli errori con:
`journalctl -u controlloaccessi-report-protocollo.service --no-pager`.
Il timer non invia email di allarme: integrare il controllo degli errori nella
supervisione del server. Disattivazione: `systemctl disable --now controlloaccessi-report-protocollo.timer`.
