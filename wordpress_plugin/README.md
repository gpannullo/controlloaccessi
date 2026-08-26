# Connettore appuntamenti WordPress

Installare `aversa-appointments-connector.php` come *must-use plugin* nel
WordPress storico, copiandolo in `wp-content/mu-plugins/`. Se la cartella non
esiste, crearla: WordPress lo caricherà automaticamente, senza attivazione e
senza scrivere alcuna configurazione nel database.

Nella stessa cartella, copiare
`aversa-appointments-connector-config.example.php` come
`aversa-appointments-connector-config.php` e inserire una chiave casuale
lunga:

```php
<?php
defined('ABSPATH') || exit;
return array('shared_secret' => 'inserire-una-chiave-casuale-lunga');
```

Il file di configurazione reale è escluso dal repository. Essendo un file PHP,
una richiesta diretta termina senza restituire la chiave; verificare comunque
che il web server esegua PHP e non ne esponga mai il sorgente.

Il WS esposto è:

```text
GET /wp-json/aversa/v1/appuntamenti?page=1&per_page=100&updated_after=2026-08-26T00:00:00Z
```

Richiede gli header `X-Aversa-Timestamp` (Unix timestamp) e
`X-Aversa-Signature` (HMAC SHA-256 del solo timestamp con la chiave condivisa).
Il WS non modifica WordPress né il suo database: esegue esclusivamente query
`SELECT` e restituisce al massimo 100 appuntamenti per pagina.

Nel file `/etc/controlloaccessi.env` aggiungere, con gli stessi valori di
endpoint e chiave:

```dotenv
WORDPRESS_APPOINTMENTS_ENABLED=True
WORDPRESS_APPOINTMENTS_ENDPOINT=https://<hostname-wordpress>/wp-json/aversa/v1/appuntamenti
WORDPRESS_APPOINTMENTS_SHARED_SECRET=inserire-la-stessa-chiave-casuale-lunga
WORDPRESS_APPOINTMENTS_TIMEOUT=30
WORDPRESS_APPOINTMENTS_PAGE_SIZE=100
```

Per una prima prova eseguire:

```bash
cd /var/www/controlloaccessi/app
/var/www/controlloaccessi/venv/bin/python manage.py sync_wordpress_appointments
```

Il comando crea o aggiorna gli appuntamenti nell'archivio `Appuntamenti
WordPress`; non crea prenotazioni operative né occupa slot. Dal Django admin
associare prima le `Mappature uffici WordPress` agli uffici locali.

Per l'esecuzione giornaliera installare i due file in `deploy/systemd/` in
`/etc/systemd/system/`, quindi eseguire `systemctl daemon-reload` e abilitare
il timer `controlloaccessi-wordpress-sync.timer`.
