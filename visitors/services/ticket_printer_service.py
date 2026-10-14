import logging
import ssl
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone

from common.exceptions import TicketPrinterException


logger = logging.getLogger(__name__)


class TicketPrinterService:
    """
    Stampa il ticket del visitatore con Epson ePOS su HTTPS.

    La TM-T20IV riceve il documento tramite il proprio servizio ePOS,
    non tramite il socket ESC/POS RAW sulla porta 9100.
    """

    @staticmethod
    def _get_config():
        return getattr(
            settings,
            "TICKET_PRINTER",
            {},
        )

    @classmethod
    def is_enabled(cls):
        return bool(
            cls._get_config().get("ENABLED", False)
        )

    @staticmethod
    def _xml_text(value):
        return escape("" if value is None else str(value))

    @classmethod
    def _invia_epos(cls, config, comandi):
        """Invia un documento ePOS-Print e verifica l'esito Epson."""
        endpoint = config.get("EPOS_URL")
        if not endpoint:
            endpoint = (
                f"https://{config['HOST']}"
                "/cgi-bin/epos/service.cgi"
            )

        timeout_ms = int(config.get("EPOS_TIMEOUT", 10000))
        device_id = quote(str(config.get("EPOS_DEVICE_ID", "local_printer")))
        separatore = "&" if "?" in endpoint else "?"
        endpoint = (
            f"{endpoint}{separatore}devid={device_id}"
            f"&timeout={timeout_ms}"
        )
        payload = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soapenv:Body>"
            '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'
            f"{comandi}"
            "</epos-print></soapenv:Body></soapenv:Envelope>"
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '\"\"',
            },
            method="POST",
        )
        verifica_ssl = bool(config.get("EPOS_VERIFY_SSL", False))
        context = None if verifica_ssl else ssl._create_unverified_context()
        with urlopen(
            request,
            timeout=max(timeout_ms / 1000, 1),
            context=context,
        ) as risposta:
            corpo = risposta.read()

        root = ET.fromstring(corpo)
        esito = next(
            (elemento for elemento in root.iter() if elemento.tag.endswith("response")),
            root,
        )
        if esito.attrib.get("success", "false").lower() != "true":
            codice = esito.attrib.get("code", "UNKNOWN")
            raise RuntimeError(f"Epson ePOS ha rifiutato il ticket ({codice}).")

    @classmethod
    def stampa_accesso(cls, accesso):
        """
        Stampa numero di coda, ufficio, badge e orario.

        Per motivi di riservatezza il nome del visitatore
        non viene stampato sul ticket.
        """

        config = cls._get_config()

        if not config.get("ENABLED", False):
            logger.info(
                "Stampa ticket disabilitata. Accesso: %s",
                accesso.pk,
            )
            return False

        host = config.get("HOST")
        if not host:
            raise TicketPrinterException(
                "Indirizzo della stampante non configurato."
            )

        try:
            data_ingresso = timezone.localtime(
                accesso.ingresso
            )
            ufficio = accesso.ufficio_destinazione
            def testo(valore, align="left"):
                return (
                    f'<text align="{align}">{cls._xml_text(valore)}</text>'
                    '<feed line="1"/>'
                )

            def riga_dato(etichetta, valore):
                """Crea una riga monospace con valore allineato a destra."""
                etichetta = f"{etichetta}:"
                valore = str(valore)
                spazi = max(1, 42 - len(etichetta) - len(valore))
                return testo(f"{etichetta}{' ' * spazi}{valore}")

            comandi = (
                '<text align="center" em="true" width="2" height="2">COMUNE DI AVERSA</text><feed line="1"/>'
                '<text align="center" em="false" width="1" height="1"/>'
                '<text align="center" em="true">CONTROLLO ACCESSI</text><feed line="1"/>'
                '<hline x1="0" x2="576" style="thin"/><feed line="1"/>'
                '<text align="center" em="false" width="1" height="1"/>'
                f'<text align="center" em="true" width="3" height="3">{cls._xml_text(accesso.numero_coda_formattato)}</text>'
                '<feed line="2"/>'
                '<text align="center" em="false" width="1" height="1"/>'
                '<text align="center">Numero di attesa</text><feed line="2"/>'
                + riga_dato("Ufficio", ufficio.nome)
                + (riga_dato("Piano", ufficio.piano) if ufficio.piano else "")
                + (riga_dato("Porta", ufficio.stanza) if ufficio.stanza else "")
                + (riga_dato("Badge", accesso.badge.codice) if accesso.badge else "")
                + riga_dato("Data", f"{data_ingresso:%d/%m/%Y}")
                + riga_dato("Ora", f"{data_ingresso:%H:%M}")
                + riga_dato(
                    "Coda",
                    "Prioritaria" if accesso.appuntamento_id else "Ordinaria",
                )
                + '<hline x1="0" x2="576" style="thin"/><feed line="1"/>'
                + testo("Attendi la chiamata all'ufficio.", align="center")
            )

            # Il QR contiene esclusivamente un token casuale, mai dati
            # anagrafici, numero badge o identificativi interni.
            if config.get("PRINT_QR", False):
                comandi += (
                    '<feed line="1"/>'
                )
                token = accesso.genera_token_pubblico()
                base_url = config.get("PUBLIC_TICKET_BASE_URL", "").rstrip("/")
                if not base_url:
                    raise TicketPrinterException(
                        "Indirizzo pubblico dei ticket non configurato."
                    )
                url_attesa = f"{base_url}/attesa/{quote(token)}/"
                comandi += (
                    '<symbol type="qrcode_model_2" level="level_h" width="5" height="5" '
                    f'align="center">{cls._xml_text(url_attesa)}</symbol>'
                    '<feed line="1"/>'
                    '<text align="center">Scansiona il codice per monitorare</text>'
                    '<feed line="1"/>'
                    '<text align="center">i tempi di attesa</text>'
                    '<feed line="1"/>'
                )

            comandi += '<feed line="2"/><cut type="feed"/>'
            cls._invia_epos(config, comandi)

            logger.info(
                "Ticket stampato per accesso %s",
                accesso.pk,
            )

            return True

        except Exception as exc:
            logger.exception(
                "Errore nella stampa del ticket "
                "per l'accesso %s",
                accesso.pk,
            )

            raise TicketPrinterException(
                "Registrazione completata, ma non è stato "
                "possibile stampare il ticket."
            ) from exc

