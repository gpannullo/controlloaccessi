from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from access_control.models import Ufficio
from accounts.models import SnapshotPresenzaUfficio


User = get_user_model()


class SnapshotPresenzaService:
    """
    Crea una fotografia della presenza per ciascun ufficio.

    Gli utenti vengono ricavati dai gruppi organizzativi collegati
    all'ufficio, eliminando eventuali duplicati.
    """

    @staticmethod
    def _utenti_ufficio(ufficio):
        utenti_ids = set()

        gruppi = (
            ufficio.gruppi
            .filter(attivo=True)
            .select_related("django_group")
        )

        for gruppo in gruppi:
            utenti_ids.update(
                gruppo.django_group
                .user_set
                .filter(is_active=True)
                .values_list("pk", flat=True)
            )

        return User.objects.filter(
            pk__in=utenti_ids,
            is_active=True,
        )

    @classmethod
    def crea_snapshot_ufficio(cls, ufficio, rilevato_il=None):
        if rilevato_il is None:
            rilevato_il = timezone.now()

        utenti = cls._utenti_ufficio(ufficio)

        dipendenti_totali = utenti.count()

        sportellisti = utenti.filter(
            tipo_attivita=User.TipoAttivita.SPORTELLISTA,
        )
        sportellisti_totali = sportellisti.count()

        controllo_presenze = getattr(
            settings,
            "PRESENCE_CHECK_ENABLED",
            False,
        )

        if controllo_presenze:
            dipendenti_presenti = utenti.filter(
                stato_presenza=User.StatoPresenza.PRESENTE,
            ).count()

            sportellisti_presenti = sportellisti.filter(
                stato_presenza=User.StatoPresenza.PRESENTE,
            ).count()
        else:
            # Coerente con CapacityService: se il controllo presenze
            # è disabilitato, gli utenti attivi assegnati vengono
            # considerati disponibili.
            dipendenti_presenti = dipendenti_totali
            sportellisti_presenti = sportellisti_totali

        return SnapshotPresenzaUfficio.objects.create(
            ufficio=ufficio,
            rilevato_il=rilevato_il,
            dipendenti_presenti=dipendenti_presenti,
            sportellisti_presenti=sportellisti_presenti,
            dipendenti_totali=dipendenti_totali,
            sportellisti_totali=sportellisti_totali,
        )

    @classmethod
    def crea_snapshot_tutti_uffici(cls):
        momento = timezone.now()
        risultati = []

        uffici = (
            Ufficio.objects
            .filter(attivo=True)
            .order_by("nome")
        )

        for ufficio in uffici:
            risultati.append(
                cls.crea_snapshot_ufficio(
                    ufficio,
                    rilevato_il=momento,
                )
            )

        return risultati
