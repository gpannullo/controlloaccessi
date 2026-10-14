# Deploy Windows verso test e produzione

Chiudere la lavorazione locale con commit e push su `develop/v0.4`.
Avviare `deploy\deploy-server.bat`: controlla entrambi i server, poi distribuisce
prima sul test `192.168.15.26` e quindi in produzione `192.168.15.24`.
Account SSH: `controlloaccessi`. Non crea commit, tag o push.

Prerequisiti: Git e OpenSSH Windows nel PATH, accesso SSH ai due server e
chiavi host verificate presenti in known_hosts. Usa la configurazione SSH
dell'utente Windows. Non contiene password o chiavi private.
Per una chiave specifica:

```bat
deploy\deploy-server.bat -IdentityFile "C:\percorso\chiave_privata"
deploy\deploy-server.bat -CheckOnly
```

Il controllo richiede copie Git pulite (anche file non tracciati), branch corretto,
HEAD locale uguale a origin, avanzamento fast-forward e permesso sudo senza
password per `/usr/bin/systemctl restart controlloaccessi`.
I server devono poter leggere `/etc/controlloaccessi.env` e accedere a GitHub.
Le attuali copie modificate direttamente sui server vanno prima riconciliate
con Git: lo script NON esegue reset, clean, stash o sovrascritture forzate.

Esegue pull fast-forward, installazione requirements nel venv esistente,
check Django, migrations, collectstatic e restart del servizio Django/Gunicorn.
Verifica che il servizio sia attivo. Non e un collaudo funzionale completo.
Non riavvia PostgreSQL, Nginx, Docker SPID, timer o demoni indipendenti.
Questi richiedono una procedura specifica se modificati.

Ogni errore interrompe il deploy, impedendo di proseguire sull'altro server.
Non esiste transazione tra i due server: il test potrebbe essere aggiornato
mentre la produzione no. Le migrazioni gia applicate non vengono annullate.
Prima di migrazioni distruttive effettuare e verificare un backup del database.
Le migrazioni devono essere compatibili col codice ancora in esecuzione fino
al restart; per cambiamenti incompatibili pianificare manutenzione dedicata.
