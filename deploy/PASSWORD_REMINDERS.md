# Promemoria password

Ogni giorno alle 08:00 Europe/Rome, account attivi con password ancora valida
e scadenza entro 15 giorni. La fonte è `scadenza_password`, aggiornata dalla
sincronizzazione AD: mantenere attivo il relativo timer. Nessuna interrogazione
LDAP viene eseguita dal promemoria. Dopo il cambio password il dato locale deve
essere aggiornato prima della successiva esecuzione.

Destinatario: `CustomUser.email` (istituzionale), nessun ripiego sulla personale.
Esclusi indirizzi vuoti/non validi, account disattivati, password senza scadenza
o già scadute. Un accodamento per utente e giorno; registro e messaggio nella
stessa transazione. Post Office invia tramite il timer mail-queue già esistente.
I messaggi scadono alla data di scadenza password. Il registro attesta
l'accodamento, non la consegna: verificare errori SMTP in Post Office.

## Installazione SOLO in produzione

Con l'ambiente Django caricato, dalla directory app:

```sh
/var/www/controlloaccessi/venv/bin/python manage.py migrate
/var/www/controlloaccessi/venv/bin/python manage.py send_password_reminders --dry-run
```

Come amministratore:

```sh
sudo install -m 644 deploy/systemd/controlloaccessi-password-reminder.service /etc/systemd/system/
sudo install -m 644 deploy/systemd/controlloaccessi-password-reminder.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now controlloaccessi-password-reminder.timer
sudo systemctl list-timers controlloaccessi-password-reminder.timer
```

Non avviare manualmente il service salvo voler accodare subito messaggi reali.
Non abilitare il timer sul server di test per evitare doppi invii.
Persistent=false evita invii di recupero all'installazione/riavvio.
Controllare che controlloaccessi-mail-queue.timer sia attivo.

```sh
sudo journalctl -u controlloaccessi-password-reminder.service --since today
```
