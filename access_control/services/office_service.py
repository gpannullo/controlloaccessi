from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from access_control.models import (
    CalendarioApertura,
    GruppoOrganizzativo,
    Ufficio,
)


class OfficeService:

    @transaction.atomic
    def generate_from_groups(self, gruppi):
        creati = 0
        aggiornati = 0

        for gruppo in gruppi:
            if (
                gruppo.tipo
                != GruppoOrganizzativo.Tipo.ORGANIZZATIVO
            ):
                continue

            if gruppo.uffici.exists():
                continue

            codice = self.generate_code(
                gruppo.nome
            )

            ufficio, created = Ufficio.objects.get_or_create(
                codice=codice,
                defaults={
                    "nome": gruppo.nome,
                    "attivo": True,
                    "riceve_pubblico": True,
                    "gruppo_operativo": gruppo,
                },
            )
            if not created and ufficio.gruppo_operativo_id is None:
                ufficio.gruppo_operativo = gruppo
                ufficio.save(update_fields=["gruppo_operativo"])

            if created:
                creati += 1
            else:
                aggiornati += 1

        return {
            "created": creati,
            "updated": aggiornati,
        }

    @staticmethod
    def generate_code(nome):
        codice = nome.upper()
        codice = codice.replace(" ", "_")
        codice = codice.replace("-", "_")

        return codice[:20]

    @staticmethod
    def _local_datetime(data_ora=None):
        if data_ora is None:
            return timezone.localtime()

        if timezone.is_aware(data_ora):
            return timezone.localtime(
                data_ora
            )

        return data_ora

    @classmethod
    def is_open(cls, ufficio, data_ora=None):
        """
        Verifica se l'ufficio è effettivamente aperto
        al pubblico nel momento indicato.
        """

        if (
            not ufficio.attivo
            or not ufficio.riceve_pubblico
        ):
            return False

        data_ora = cls._local_datetime(
            data_ora
        )

        return CalendarioApertura.objects.filter(
            ufficio=ufficio,
            giorno=data_ora.weekday(),
            ora_inizio__lte=data_ora.time(),
            ora_fine__gte=data_ora.time(),
        ).exists()

    @classmethod
    def get_open_offices(cls, data_ora=None):
        """
        Restituisce gli uffici aperti esattamente
        nel momento indicato.
        """

        data_ora = cls._local_datetime(
            data_ora
        )

        return (
            Ufficio.objects
            .filter(
                attivo=True,
                riceve_pubblico=True,
                aperture__giorno=(
                    data_ora.weekday()
                ),
                aperture__ora_inizio__lte=(
                    data_ora.time()
                ),
                aperture__ora_fine__gte=(
                    data_ora.time()
                ),
            )
            .distinct()
            .order_by("nome")
        )

    @classmethod
    def get_offices_receiving_today(
        cls,
        data_ora=None,
        richiede_personale_presente=False,
    ):
        """
        Restituisce gli uffici che possono accettare
        registrazioni nella giornata corrente.

        L'ufficio può non essere ancora aperto:
        è sufficiente che abbia almeno una fascia
        di ricevimento prevista oggi.
        """

        data_ora = cls._local_datetime(
            data_ora
        )

        uffici = (
            Ufficio.objects
            .filter(
                attivo=True,
                riceve_pubblico=True,
                aperture__giorno=(
                    data_ora.weekday()
                ),
                # Prima dell'apertura e durante le pause
                # il cittadino può comunque registrarsi.
                # Dopo l'ultima chiusura della giornata no.
                aperture__ora_fine__gt=(
                    data_ora.time()
                ),
            )
            .distinct()
            .order_by("nome")
        )

        if richiede_personale_presente:
            User = get_user_model()
            uffici = uffici.filter(
                assegnazioni_personale__attiva=True,
                assegnazioni_personale__utente__is_active=True,
                assegnazioni_personale__utente__stato_presenza=(
                    User.StatoPresenza.PRESENTE
                ),
            ).distinct()

        return uffici

    @classmethod
    def get_offices_with_present_staff(cls):
        """
        Restituisce gli uffici attivi nei quali risulta
        presente almeno un dipendente, indipendentemente
        dal ruolo di sportellista/amministrativista e dal
        calendario di ricevimento al pubblico.
        """

        User = get_user_model()

        return (
            Ufficio.objects
            .filter(
                attivo=True,
                assegnazioni_personale__attiva=True,
                assegnazioni_personale__utente__is_active=True,
                assegnazioni_personale__utente__stato_presenza=(
                    User.StatoPresenza.PRESENTE
                ),
            )
            .distinct()
            .order_by("nome")
        )

    @staticmethod
    def get_active_offices_for_day(giorno):
        """
        Restituisce gli uffici attivi che hanno almeno
        una fascia di apertura nel giorno indicato.
        """

        return (
            Ufficio.objects
            .filter(
                attivo=True,
                riceve_pubblico=True,
                aperture__giorno=giorno,
            )
            .distinct()
            .order_by("nome")
        )
