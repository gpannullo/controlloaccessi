from datetime import datetime
from math import floor

from django.utils import timezone

from ControlloAccessi import settings
from access_control.models import CalendarioApertura
from visitors.models import (
    AccessoVisitatore,
    Appuntamento,
    SessioneRicevimento,
)
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


class CapacityService:

    @staticmethod
    def numero_dipendenti_presenti(ufficio):
        """Conta i dipendenti assegnati, attivi e presenti.

        Questa verifica è sempre rigorosa: serve a stabilire se il
        visitatore può essere inviato fisicamente fuori dall'ufficio,
        indipendentemente dall'eventuale configurazione generale dei
        controlli presenze.
        """
        return User.objects.filter(
            assegnazioni_ufficio__ufficio=ufficio,
            assegnazioni_ufficio__attiva=True,
            is_active=True,
            stato_presenza=User.StatoPresenza.PRESENTE,
        ).distinct().count()

    @staticmethod
    def numero_operatori_attivi(ufficio):
        """
        Conta gli utenti attivi assegnati all'ufficio,
        configurati come sportellisti e, quando previsto,
        presenti secondo il sistema esterno.
        """

        controllo_presenze = getattr(
            settings,
            "PRESENCE_CHECK_ENABLED",
            False,
        )

        utenti = User.objects.filter(
            assegnazioni_ufficio__ufficio=ufficio,
            assegnazioni_ufficio__attiva=True,
            is_active=True,
            tipo_attivita=User.TipoAttivita.SPORTELLISTA,
        ).distinct()
        if controllo_presenze:
            utenti = utenti.filter(stato_presenza=User.StatoPresenza.PRESENTE)
        return utenti.count()

    @staticmethod
    def tempo_medio_servizio(ufficio):
        """
        Calcola la durata media delle ultime visite concluse.

        Se non esiste uno storico sufficiente, usa il valore
        predefinito configurato nell'ufficio.
        """

        accessi = (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                ingresso_ufficio_il__isnull=False,
                visita_conclusa_il__isnull=False,
            )
            .order_by("-visita_conclusa_il")
            .values_list(
                "ingresso_ufficio_il",
                "visita_conclusa_il",
            )[:ufficio.numero_visite_media]
        )

        durate = []

        for ingresso, conclusione in accessi:
            minuti = (
                             conclusione - ingresso
                     ).total_seconds() / 60

            # Esclude durate anomale.
            if 1 <= minuti <= 240:
                durate.append(minuti)

        if not durate:
            return max(
                ufficio.tempo_medio_servizio_default,
                1,
            )

        return max(
            round(
                sum(durate) / len(durate)
            ),
            1,
        )

    @staticmethod
    def prossima_chiusura(
            ufficio,
            data_ora=None,
    ):
        """
        Restituisce la fine della fascia corrente oppure
        della prossima fascia prevista nella giornata.
        """

        if data_ora is None:
            data_ora = timezone.localtime()

        elif timezone.is_aware(data_ora):
            data_ora = timezone.localtime(
                data_ora
            )

        apertura = (
            CalendarioApertura.objects
            .filter(
                ufficio=ufficio,
                giorno=data_ora.weekday(),
                ora_fine__gt=data_ora.time(),
            )
            .order_by(
                "ora_inizio",
                "ora_fine",
            )
            .first()
        )

        if apertura is None:
            return None

        chiusura = datetime.combine(
            data_ora.date(),
            apertura.ora_fine,
        )

        return timezone.make_aware(
            chiusura,
            timezone.get_current_timezone(),
        )

    @staticmethod
    def prenotazioni_da_riservare(
            ufficio,
            data_ora=None,
    ):
        """
        Conta le prenotazioni future ancora da utilizzare.

        Non considera:
        - prenotazioni annullate;
        - prenotazioni già eseguite;
        - prenotazioni già collegate a un accesso.
        """

        if data_ora is None:
            data_ora = timezone.now()

        oggi = timezone.localdate(
            data_ora
        )

        return (
            Appuntamento.objects
            .filter(
                ufficio=ufficio,
                data_ora__date=oggi,
                data_ora__gte=data_ora,
                stato__in=[
                    Appuntamento.Stato.PRENOTATO,
                    Appuntamento.Stato.CONFERMATO,
                ],
                accesso__isnull=True,
            )
            .count()
        )

    @staticmethod
    def persone_da_servire(ufficio):
        """
        Conta tutte le persone ancora da servire:

        - coda prioritaria;
        - hall ordinaria;
        - fuori dall'ufficio;
        - dentro l'ufficio.

        Esclude visite concluse e persone già uscite.
        """

        return (
            AccessoVisitatore.objects
            .filter(
                ufficio_destinazione=ufficio,
                uscita__isnull=True,
                visita_conclusa_il__isnull=True,
            )
            .count()
        )

    @classmethod
    def capacita_residua(
            cls,
            ufficio,
            data_ora=None,
    ):
        """
        Calcola quanti visitatori non prenotati possono
        ancora essere accettati.

        Restituisce sempre lo stesso insieme di chiavi.
        """

        if data_ora is None:
            data_ora = timezone.now()

        operatori = (
            cls.numero_operatori_attivi(
                ufficio
            )
        )

        tempo_medio = (
            cls.tempo_medio_servizio(
                ufficio
            )
        )

        chiusura = cls.prossima_chiusura(
            ufficio,
            data_ora,
        )

        persone = cls.persone_da_servire(
            ufficio
        )

        prenotazioni_riservate = (
            cls.prenotazioni_da_riservare(
                ufficio,
                data_ora,
            )
        )

        risultato_base = {
            "operatori": operatori,
            "tempo_medio": tempo_medio,
            "minuti_residui": 0,
            "capacita_teorica": 0,
            "overbooking": ufficio.overbooking,
            "persone_da_servire": persone,
            "prenotazioni_riservate": (
                prenotazioni_riservate
            ),
            "posti_disponibili_ordinari": 0,
            "accetta_non_prenotati": False,
        }

        if operatori <= 0:
            return risultato_base

        if chiusura is None:
            return risultato_base

        if timezone.is_aware(data_ora):
            adesso = timezone.localtime(
                data_ora
            )
        else:
            adesso = data_ora

        chiusura_locale = (
            timezone.localtime(
                chiusura
            )
        )

        minuti_residui = max(
            floor(
                (
                        chiusura_locale - adesso
                ).total_seconds() / 60
            ),
            0,
        )

        capacita_per_operatore = floor(
            minuti_residui / tempo_medio
        )

        capacita_teorica = (
                operatori
                * capacita_per_operatore
        )

        posti_disponibili_ordinari = max(
            capacita_teorica
            + ufficio.overbooking
            - persone
            - prenotazioni_riservate,
            0,
        )

        return {
            "operatori": operatori,
            "tempo_medio": tempo_medio,
            "minuti_residui": minuti_residui,
            "capacita_teorica": capacita_teorica,
            "overbooking": ufficio.overbooking,
            "persone_da_servire": persone,
            "prenotazioni_riservate": (
                prenotazioni_riservate
            ),
            "posti_disponibili_ordinari": (
                posti_disponibili_ordinari
            ),
            "accetta_non_prenotati": (
                    posti_disponibili_ordinari > 0
            ),
        }
