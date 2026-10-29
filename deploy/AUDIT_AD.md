# Audit Active Directory — prima implementazione

App Python `audit_ad`, endpoint `/audit-ad/events/`, menu admin **Audit Active Directory**.
Non modifica AD, non blocca utenti, non applica contromisure automatiche.
Le segnalazioni sono indicatori da investigare, non certificazioni di compromissione.

## Installazione (non ancora eseguita sui server)

1. Distribuire codice e applicare `python manage.py migrate` (nuove tabelle isolate).
2. Impostare nell'env di produzione chiavi casuali distinte di almeno 32 caratteri:

```ini
AUDIT_AD_ENABLED=true
AUDIT_AD_SECRET_DC100=<segreto-casuale-distinto>
AUDIT_AD_SECRET_DC101=<altro-segreto-casuale>
AUDIT_AD_FAILURE_THRESHOLD=10
```

Generare ciascuna chiave con `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Non inserire segreti nel repository, nei parametri del processo o nei log.
Sul test lasciare `AUDIT_AD_ENABLED=false`; non inviare i log a due archivi senza necessità.
Riavviare Django dopo la configurazione. L'endpoint fallisce chiuso se manca la chiave.

3. Nel solo vhost interno HTTPS nginx aggiungere:

```nginx
location = /audit-ad/events/ {
    allow 192.168.15.100;
    allow 192.168.15.101;
    deny all;
    client_max_body_size 1m;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_pass http://127.0.0.1:8000;
}
```

Non esporre questo path sui vhost pubblici, chiudere Gunicorn al traffico esterno.
Django deve riconoscere HTTPS tramite il proxy fidato (SECURE_PROXY_SSL_HEADER).
Non fidarsi di X-Forwarded-For ricevuti dal client. Solo loopback è proxy fidato nel receiver.
Non disabilitare la validazione TLS; installare sul DC la corretta catena attendibile.
Eseguire `nginx -t` prima del reload. Applicare un limite richieste nginx proporzionato
al volume (senza scartare gli invii normali); monitorare 403/413/429/500.

## Inoltro Windows (.100 e .101)

Il collector `deploy/forward-ad-events.ps1` richiede Windows PowerShell 5.1.
Legge il registro **Security** locale. Configurare le Advanced Audit Policies necessarie
per successo/fallimento autenticazione, Kerberos, account/group management e policy change.
Verificare con `auditpol /get /category:*`; non modificare alla cieca policy di dominio.
Gli eventi non generati dalle policy non possono essere recuperati dall'app.

Su ogni DC creare cartella protetta, ad esempio `C:\ProgramData\IrisAudit`, script e `config.json`:

```json
{
  "endpoint": "https://controlloaccessi.comune.aversa.ce.it/audit-ad/events/",
  "source": "192.168.15.100",
  "secret": "INSERIRE_LA_CHIAVE_DISTINTA_DEL_DC"
}
```

Sul secondo DC usare `.101` e la sua chiave. ACL: lettura del config e dello script
solo amministratori e identità del task; scrittura del checkpoint solo identità del task.
Usare un'identità dedicata con i soli diritti necessari alla lettura Security e all'esecuzione
del task; non richiede credenziali Domain Admin nella configurazione.

Eseguire prima manualmente:

```powershell
powershell.exe -NoProfile -File C:\ProgramData\IrisAudit\forward-ad-events.ps1 -ConfigPath C:\ProgramData\IrisAudit\config.json
```

Poi Utilità di pianificazione: ogni minuto, eseguire anche senza sessione aperta,
non avviare istanze parallele, conservare esiti e avvisare in caso di errore.
Non viene creata automaticamente alcuna attività sui DC.

Prima esecuzione: ultimi 15 minuti, non tutto lo storico. Successive: checkpoint temporale,
sovrapposizione di 2 minuti per eventi tardivi, recupero a finestre di 15 minuti.
Batch 50 eventi, avanzamento checkpoint solo dopo conferma di tutti i batch.
Retry dopo guasti può reinviare eventi ma non duplica righe (impronta con DC, computer,
record ID, data e event ID, resistente al reset del contatore dopo cancellazione log).
HMAC SHA256 firma timestamp + punto + byte JSON; tolleranza orologi 5 minuti.
Un replay valido entro la finestra è idempotente. Sincronizzare gli orologi con NTP.
La chiave autorizza quella sorgente, non garantisce che un DC compromesso dica la verità.

## Analisi e consultazione

Solo superuser attivi possono consultare eventi e segnalazioni nell'admin.
Eventi in sola lettura; sulle segnalazioni si possono salvare note e stato verificato.
Disponibili data, DC, ID evento, utente, IP, workstation, protocollo e tipo logon,
oltre ai dati strutturati EventData/UserData raccolti. Nessuna password è richiesta.
I log possono comunque contenere dati personali o sensibili: proteggere DB e backup.

Regole iniziali:
- 1102/4719: cancellazione registro Security / modifica audit.
- 4728/4732/4756: aggiunta a gruppi privilegiati identificati per SID (non nomi localizzati).
- almeno 10 eventi 4625/4771 dallo stesso IP in 5 minuti: possibili tentativi ripetuti.
  Le righe sono eventi, non necessariamente 10 persone o 10 tentativi distinti.
  IP NAT/condivisi e password obsolete possono generare falsi positivi.

Analisi all'acquisizione; per riordinamenti fra batch/DC rianalizzare periodicamente:

```bash
python manage.py analyze_ad --hours 24
```

Il comando è idempotente e stampa anche le sorgenti senza eventi recenti (non equivale
a una prova di guasto: un server potrebbe non avere eventi). Predisporre uno scheduler
operativo per tale comando e alert esterni per errori collector/disco/DB/assenza feed.
La prima versione non invia email/IO e non implementa un SIEM completo.

## Limiti e verifiche prima della messa in servizio

- I DC non vedono ogni sessione su ogni piattaforma: 4624 è generato sulla macchina
  di destinazione, 4768/4769/4776 descrivono autenticazioni/ticket. Browser, OS client,
  applicazione e IP non sono sempre disponibili. Non vengono inventati dai log.
- Per copertura completa integrare successivamente server membri, workstation e app.
- Eventi persi per rotazione del registro, disabilitazione audit, lunga indisponibilità
  o eventi scritti oltre la sovrapposizione non sono recuperabili dal collector.
  Dimensionare Security log e monitorare il ritardo del checkpoint e spazio disco.
- Conservazione da concordare con responsabili sicurezza/privacy; nessuna cancellazione
  automatica introdotta. Non è un archivio WORM né una catena di custodia forense.
- Testare su DC controllato: invio, reinvio idempotente, 403 per firma errata,
  consultazione negata a staff non superuser; simulare log nei test, non cancellare log reali.
- Eseguire prova di carico prima di inoltrare tutto Security: volume potenzialmente elevato.

Riferimenti Microsoft:
https://learn.microsoft.com/windows/security/threat-protection/auditing/event-4624
https://learn.microsoft.com/en-us/azure/sentinel/windows-security-event-id-reference
