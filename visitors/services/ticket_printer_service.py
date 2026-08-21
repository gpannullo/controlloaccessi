import logging
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from escpos.printer import Network

from common.exceptions import TicketPrinterException


logger = logging.getLogger(__name__)


class TicketPrinterService:
    """
    Stampa il ticket del visitatore su una stampante
    termica ESC/POS collegata alla rete.
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
        port = config.get("PORT", 9100)
        timeout = config.get("TIMEOUT", 5)

        if not host:
            raise TicketPrinterException(
                "Indirizzo della stampante non configurato."
            )

        printer = None

        try:
            printer = Network(
                host=host,
                port=port,
                timeout=timeout,
            )

            data_ingresso = timezone.localtime(
                accesso.ingresso
            )

            # Intestazione
            printer.set(
                align="center",
                bold=True,
                width=1,
                height=1,
            )
            printer.textln("COMUNE DI AVERSA")
            printer.textln("CONTROLLO ACCESSI")
            printer.textln("--------------------------------")

            # Numero di coda molto evidente
            printer.set(
                align="center",
                bold=True,
                width=3,
                height=3,
            )
            printer.textln(
                accesso.numero_coda_formattato
            )

            printer.set(
                align="center",
                bold=False,
                width=1,
                height=1,
            )
            printer.textln("NUMERO DI ATTESA")
            printer.textln("")

            # Informazioni operative
            printer.set(
                align="left",
                bold=False,
                width=1,
                height=1,
            )

            printer.textln(
                f"Ufficio: {accesso.ufficio_destinazione.nome}"
            )

            if accesso.badge:
                printer.textln(
                    f"Badge:   {accesso.badge.codice}"
                )

            printer.textln(
                f"Data:    {data_ingresso:%d/%m/%Y}"
            )

            printer.textln(
                f"Ora:     {data_ingresso:%H:%M}"
            )

            printer.textln("--------------------------------")
            printer.textln(
                "Attendere la chiamata dell'ufficio"
            )

            # QR facoltativo con solo identificativo interno.
            if config.get("PRINT_QR", False):
                printer.textln("")
                token = accesso.genera_token_pubblico()
                base_url = config.get("PUBLIC_TICKET_BASE_URL", "").rstrip("/")
                if not base_url:
                    raise TicketPrinterException(
                        "Indirizzo pubblico dei ticket non configurato."
                    )
                printer.qr(
                    f"{base_url}/attesa/{quote(token)}/",
                    size=5,
                    center=True,
                )

            printer.textln("")
            printer.textln("")
            printer.cut()

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

        finally:
            if printer is not None:
                try:
                    printer.close()
                except Exception:
                    logger.warning(
                        "Errore durante la chiusura "
                        "della connessione alla stampante.",
                        exc_info=True,
                    )
