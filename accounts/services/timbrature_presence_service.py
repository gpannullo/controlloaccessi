import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone


logger = logging.getLogger(__name__)
User = get_user_model()

_TRACCIATO = re.compile(
    r"^(?P<badge>\d{10})(?P<verso>[IU])(?P<causale>\d{4})(?P<data>\d{6})(?P<ora>\d{4})$"
)


class TimbratureError(Exception):
    """Errore di configurazione, connessione o formato del file presenze."""


@dataclass(frozen=True)
class Timbratura:
    badge: str
    verso: str
    causale: str
    rilevata_il: datetime


@dataclass(frozen=True)
class RisultatoImportazioneTimbrature:
    righe_lette: int
    timbrature_valide: int
    badge_senza_utente: int
    utenti_aggiornati: int
    presenti: int
    assenti: int


class TimbratureSftpClient:
    """Scarica il file da SFTP verificando obbligatoriamente la chiave host."""

    @staticmethod
    def _configurazione():
        valori = {
            "host": settings.PRESENCE_SSH_HOST,
            "username": settings.PRESENCE_SSH_USERNAME,
            "private_key": settings.PRESENCE_SSH_PRIVATE_KEY,
            "known_hosts": settings.PRESENCE_SSH_KNOWN_HOSTS,
            "remote_path": settings.PRESENCE_SSH_REMOTE_PATH,
        }
        mancanti = [nome for nome, valore in valori.items() if not valore]
        if mancanti:
            raise TimbratureError("Configurazione timbrature incompleta: %s." % ", ".join(mancanti))
        if not Path(valori["private_key"]).is_file():
            raise TimbratureError("Chiave privata SSH delle timbrature non trovata.")
        if not Path(valori["known_hosts"]).is_file():
            raise TimbratureError("File known_hosts delle timbrature non trovato.")
        return valori

    def scarica(self):
        try:
            import paramiko
        except ImportError as exc:
            raise TimbratureError("Dipendenza paramiko non installata.") from exc

        config = self._configurazione()
        client = paramiko.SSHClient()
        client.load_host_keys(config["known_hosts"])
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=config["host"],
                port=settings.PRESENCE_SSH_PORT,
                username=config["username"],
                key_filename=config["private_key"],
                look_for_keys=False,
                allow_agent=False,
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
            )
            sftp = client.open_sftp()
            try:
                with sftp.open(config["remote_path"], "rb") as file_remoto:
                    return file_remoto.read().decode("utf-8-sig")
            finally:
                sftp.close()
        except Exception as exc:
            raise TimbratureError("Lettura SFTP del file timbrature non riuscita: %s" % exc) from exc
        finally:
            client.close()


class TimbraturePresenceService:
    fonte = "SSH_TIMBRATURE"

    @staticmethod
    def analizza(contenuto):
        timbrature = []
        righe_non_valide = []
        for numero_riga, riga in enumerate(contenuto.splitlines(), start=1):
            valore = riga.strip()
            if not valore:
                continue
            corrispondenza = _TRACCIATO.fullmatch(valore)
            if not corrispondenza:
                righe_non_valide.append(numero_riga)
                continue
            try:
                rilevata_il = datetime.strptime(
                    corrispondenza["data"] + corrispondenza["ora"], "%d%m%y%H%M"
                )
            except ValueError:
                righe_non_valide.append(numero_riga)
                continue
            timbrature.append(
                Timbratura(
                    badge=corrispondenza["badge"],
                    verso=corrispondenza["verso"],
                    causale=corrispondenza["causale"],
                    rilevata_il=rilevata_il,
                )
            )
        if righe_non_valide:
            raise TimbratureError(
                "Formato non valido nelle righe: %s." % ", ".join(map(str, righe_non_valide[:10]))
            )
        return timbrature

    @transaction.atomic
    def importa(self, contenuto):
        timbrature = self.analizza(contenuto)
        oggi = timezone.localdate()
        ultima_per_badge = {}
        for timbratura in timbrature:
            if timbratura.rilevata_il.date() != oggi:
                continue
            precedente = ultima_per_badge.get(timbratura.badge)
            if precedente is None or timbratura.rilevata_il > precedente.rilevata_il:
                ultima_per_badge[timbratura.badge] = timbratura

        utenti = list(
            User.objects.select_for_update().filter(is_active=True, badge__isnull=False).exclude(badge="")
        )
        badge_conosciuti = {utente.badge for utente in utenti}
        adesso = timezone.now()
        aggiornati = presenti = assenti = 0
        for utente in utenti:
            timbratura = ultima_per_badge.get(utente.badge)
            stato = User.StatoPresenza.PRESENTE if timbratura and timbratura.verso == "I" else User.StatoPresenza.ASSENTE
            if stato == User.StatoPresenza.PRESENTE:
                presenti += 1
            else:
                assenti += 1
            utente.stato_presenza = stato
            utente.presenza_verificata_il = adesso
            utente.presenza_fonte = self.fonte
            aggiornati += 1

        if utenti:
            User.objects.bulk_update(
                utenti,
                ["stato_presenza", "presenza_verificata_il", "presenza_fonte"],
            )

        return RisultatoImportazioneTimbrature(
            righe_lette=len(contenuto.splitlines()),
            timbrature_valide=len(timbrature),
            badge_senza_utente=len(set(ultima_per_badge) - badge_conosciuti),
            utenti_aggiornati=aggiornati,
            presenti=presenti,
            assenti=assenti,
        )

    def sincronizza(self):
        return self.importa(TimbratureSftpClient().scarica())
