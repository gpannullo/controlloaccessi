"""Notifiche personali App IO per le variazioni della coda."""

from spid_cie.services import AppIOService
from visitors.models import AccessoVisitatore


class QueueIONotificationService:
    """Invia un aggiornamento IO solo per uno stato di coda consolidato."""

    SUBJECT = "Aggiornamento attesa"

    @classmethod
    def invia_se_coerente(cls, accesso_id, stato_coda, ufficio_id, conclusa):
        accesso = (
            AccessoVisitatore.objects.select_related(
                "visitatore", "ufficio_destinazione"
            )
            .filter(pk=accesso_id)
            .first()
        )
        if accesso is None:
            return None
        if (
            accesso.stato_coda != stato_coda
            or accesso.ufficio_destinazione_id != ufficio_id
            or bool(accesso.visita_conclusa_il) != bool(conclusa)
        ):
            return None

        codice_fiscale = (accesso.visitatore.codice_fiscale or "").strip().upper()
        if len(codice_fiscale) != 16:
            return None

        contenuto = cls._contenuto(accesso)
        riferimento = "coda:%s:%s:%s" % (
            accesso.pk,
            accesso.stato_coda,
            int(bool(accesso.visita_conclusa_il)),
        )
        return AppIOService.invia_messaggio(
            codice_fiscale,
            cls.SUBJECT,
            contenuto,
            riferimento_esterno=riferimento,
        )

    @staticmethod
    def _contenuto(accesso):
        ufficio = accesso.ufficio_destinazione.nome
        numero = accesso.numero_coda_formattato or "-"
        stato = accesso.stato_coda

        if stato == AccessoVisitatore.StatoCoda.HALL:
            testo = "La registrazione e stata acquisita. Attendi nella hall."
        elif stato == AccessoVisitatore.StatoCoda.FUORI_UFFICIO:
            testo = "Puoi recarti presso l'ufficio indicato e attendere fuori dalla porta."
        elif stato == AccessoVisitatore.StatoCoda.IN_UFFICIO:
            testo = "E' il tuo turno: sei stato chiamato dall'ufficio."
        elif stato == AccessoVisitatore.StatoCoda.VISITA_CONCLUSA:
            testo = "La visita presso l'ufficio e conclusa."
        elif stato == AccessoVisitatore.StatoCoda.ANNULLATO:
            testo = "L'attesa e stata annullata."
        else:
            testo = "Lo stato della tua attesa e stato aggiornato."

        return (
            "# Stato della tua attesa\n\n"
            "%s\n\n"
            "Numero di attesa: **%s**.\n"
            "Ufficio: **%s**."
        ) % (testo, numero, ufficio)
