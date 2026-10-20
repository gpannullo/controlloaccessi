# Template email nel database

Eseguire il normale deploy con `migrate`. La migration comunicazioni 0004 crea:

| Nome (non rinominare) | Variabili |
| --- | --- |
| account_creato | nome, username, password_provvisoria, url |
| password_reimpostata | nome, username, password_provvisoria, url |
| password_in_scadenza | nome, username, scadenza, url |
| comunicazione_generica | oggetto, messaggio, nome, username |
| campagna_cambio_password | nome, username, scadenza, url |

Modifica in Admin → Post Office → Email templates (Modelli e-mail): oggetto,
contenuto testuale e contenuto HTML. Lingua predefinita vuota; mantenere i nomi.
Le descrizioni riportano le variabili disponibili. Usare `{{ nome }}` ecc.
Non inserire password reali o dati dei destinatari nei template.

Testo semplice e oggetto usano autoescape off per non alterare caratteri come & e <;
l'HTML mantiene escaping attivo, anche per password e testo libero.
Non usare `safe` sui dati dei destinatari. Modifiche riservate a personale autorizzato.
Creazione/reset continuano a inviare password provvisorie come in precedenza:
proteggere l'accesso alle email accodate e definire una conservazione limitata.

La migration non sovrascrive template esistenti e non li elimina in rollback.
La cancellazione/rinomina di un template richiesto causa errore di accodamento.
I messaggi sono renderizzati all'accodamento: quelli già in coda non cambiano.
Nessun invio avviene eseguendo la migration. Non viene riattivata la campagna
straordinaria conclusa il 10 ottobre 2026, né cambiano destinatari e schedulazioni.
