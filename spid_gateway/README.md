# Gateway SPID SAML

Componente isolato per il protocollo SAML2 SPID. È raggiungibile solo tramite
Nginx sul percorso `/identita/spid/` del dominio prenotazioni.

## Configurazione

1. Copiare `.env.example` in `.env`, compilando tutti i segreti e i contatti.
2. Generare e proteggere `private.key` e `public.cert` in
   `/etc/controlloaccessi/spid` (permessi `640`, proprietario root).
3. Nel file `/etc/controlloaccessi.env` dell'app principale impostare:

   ```dotenv
   SPID_GATEWAY_ENABLED=True
   SPID_GATEWAY_BASE_URL=https://prenotazioni.comune.aversa.ce.it/identita/spid
   SPID_GATEWAY_SHARED_SECRET=lo-stesso-segreto-lungo-del-gateway
   ```

4. Avviare il gateway con `docker compose up -d --build` dalla cartella
   `spid_gateway`.
5. Aggiungere la location Nginx riportata sotto e ricaricare Nginx.

## Nginx

Nel virtual host HTTPS di `prenotazioni.comune.aversa.ce.it`, prima della
location generale che inoltra a ControlloAccessi:

```nginx
location ^~ /identita/spid/ {
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_pass http://127.0.0.1:8010;
}
```

Il metadata da fornire al Validator è:

```text
https://prenotazioni.comune.aversa.ce.it/identita/spid/metadata/
```

Il gateway invia l'identità verificata all'app principale tramite POST HMAC;
il browser riceve solo un codice casuale monouso con durata massima di 5 minuti.
