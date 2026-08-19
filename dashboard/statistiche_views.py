from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import user_passes_test
from django.db.models import Avg
from django.shortcuts import render
from django.utils import timezone

from access_control.models import CalendarioApertura, Ufficio
from accounts.models import SnapshotPresenzaUfficio
from visitors.models import AccessoVisitatore
from visitors.services.capacity_service import CapacityService


GRUPPI_STATISTICHE = {
    "Dirigenti",
    "Funzionari_EQ",
}

GIORNI = [
    (0, "Lunedì"),
    (1, "Martedì"),
    (2, "Mercoledì"),
    (3, "Giovedì"),
    (4, "Venerdì"),
    (5, "Sabato"),
    (6, "Domenica"),
]


def _puo_vedere_statistiche(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.groups.filter(
        name__in=GRUPPI_STATISTICHE,
    ).exists()


def _media_minuti(durate):
    if not durate:
        return 0.0

    return round(
        sum(durate) / len(durate),
        1,
    )


def _tempi_accessi(ufficio, da_data):
    """
    Calcola i tempi medi reali degli accessi conclusi o avanzati
    sufficientemente nel workflow.

    Tutti i valori sono restituiti in minuti.
    """
    accessi = (
        AccessoVisitatore.objects
        .filter(
            ufficio_destinazione=ufficio,
            ingresso__gte=da_data,
        )
        .only(
            "ingresso",
            "spostato_fuori_ufficio_il",
            "ingresso_ufficio_il",
            "visita_conclusa_il",
        )
    )

    hall = []
    fuori = []
    lavorazione = []

    for accesso in accessi:
        if (
            accesso.ingresso
            and accesso.spostato_fuori_ufficio_il
            and accesso.spostato_fuori_ufficio_il >= accesso.ingresso
        ):
            hall.append(
                (
                    accesso.spostato_fuori_ufficio_il
                    - accesso.ingresso
                ).total_seconds() / 60
            )

        if (
            accesso.spostato_fuori_ufficio_il
            and accesso.ingresso_ufficio_il
            and accesso.ingresso_ufficio_il
            >= accesso.spostato_fuori_ufficio_il
        ):
            fuori.append(
                (
                    accesso.ingresso_ufficio_il
                    - accesso.spostato_fuori_ufficio_il
                ).total_seconds() / 60
            )

        if (
            accesso.ingresso_ufficio_il
            and accesso.visita_conclusa_il
            and accesso.visita_conclusa_il
            >= accesso.ingresso_ufficio_il
        ):
            minuti = (
                (
                    accesso.visita_conclusa_il
                    - accesso.ingresso_ufficio_il
                ).total_seconds() / 60
            )

            # Stessa protezione usata da CapacityService contro
            # durate palesemente anomale.
            if 1 <= minuti <= 240:
                lavorazione.append(minuti)

    return {
        "hall": _media_minuti(hall),
        "fuori": _media_minuti(fuori),
        "lavorazione": _media_minuti(lavorazione),
        "campioni_hall": len(hall),
        "campioni_fuori": len(fuori),
        "campioni_lavorazione": len(lavorazione),
    }


def _visitatori_medi_per_giorno(ufficio, da_data, adesso):
    """
    Media degli accessi registrati per ciascun giorno della settimana.

    La media è calcolata sul numero effettivo di date di quel giorno
    comprese nel periodo, comprese le giornate con zero accessi.
    """
    da_giorno = timezone.localtime(da_data).date()
    a_giorno = timezone.localtime(adesso).date()

    date_per_weekday = defaultdict(int)

    giorno = da_giorno
    while giorno <= a_giorno:
        date_per_weekday[giorno.weekday()] += 1
        giorno += timedelta(days=1)

    conteggi = defaultdict(int)

    ingressi = (
        AccessoVisitatore.objects
        .filter(
            ufficio_destinazione=ufficio,
            ingresso__gte=da_data,
            ingresso__lte=adesso,
        )
        .values_list("ingresso", flat=True)
    )

    for ingresso in ingressi:
        locale = timezone.localtime(ingresso)
        conteggi[locale.weekday()] += 1

    risultato = []

    for numero, nome in GIORNI:
        giorni_periodo = date_per_weekday[numero]
        totale = conteggi[numero]

        media = (
            round(totale / giorni_periodo, 1)
            if giorni_periodo
            else 0.0
        )

        risultato.append(
            {
                "numero": numero,
                "nome": nome,
                "totale": totale,
                "giorni_periodo": giorni_periodo,
                "media": media,
            }
        )

    return risultato


def _medie_snapshot_per_weekday(ufficio, da_data):
    """
    Media degli snapshot presenza distinta per giorno della settimana.
    """
    valori = {
        numero: {
            "dipendenti": [],
            "sportellisti": [],
        }
        for numero, _ in GIORNI
    }

    snapshots = (
        SnapshotPresenzaUfficio.objects
        .filter(
            ufficio=ufficio,
            rilevato_il__gte=da_data,
        )
        .only(
            "rilevato_il",
            "dipendenti_presenti",
            "sportellisti_presenti",
        )
    )

    for snapshot in snapshots:
        locale = timezone.localtime(snapshot.rilevato_il)
        weekday = locale.weekday()

        valori[weekday]["dipendenti"].append(
            snapshot.dipendenti_presenti
        )
        valori[weekday]["sportellisti"].append(
            snapshot.sportellisti_presenti
        )

    return {
        numero: {
            "dipendenti": (
                round(
                    sum(dati["dipendenti"])
                    / len(dati["dipendenti"]),
                    1,
                )
                if dati["dipendenti"]
                else 0.0
            ),
            "sportellisti": (
                round(
                    sum(dati["sportellisti"])
                    / len(dati["sportellisti"]),
                    1,
                )
                if dati["sportellisti"]
                else 0.0
            ),
        }
        for numero, dati in valori.items()
    }


def _minuti_apertura_per_weekday(ufficio):
    """
    Minuti complessivi di apertura configurati per ciascun giorno.
    """
    minuti = {
        numero: 0
        for numero, _ in GIORNI
    }

    aperture = (
        CalendarioApertura.objects
        .filter(ufficio=ufficio)
        .only(
            "giorno",
            "ora_inizio",
            "ora_fine",
        )
    )

    for apertura in aperture:
        inizio = (
            apertura.ora_inizio.hour * 60
            + apertura.ora_inizio.minute
        )
        fine = (
            apertura.ora_fine.hour * 60
            + apertura.ora_fine.minute
        )

        minuti[apertura.giorno] += max(
            fine - inizio,
            0,
        )

    return minuti


def _capacita_media_settimanale(
    ufficio,
    da_data,
    visitatori_settimana,
):
    """
    Stima della capacità media storica per giorno della settimana.

    capacità =
        sportellisti medi presenti
        × minuti apertura
        / tempo medio di servizio

    È una stima diagnostica: mostra i fattori usati e permette
    il confronto immediato con i visitatori medi.
    """
    presenze = _medie_snapshot_per_weekday(
        ufficio,
        da_data,
    )

    aperture = _minuti_apertura_per_weekday(
        ufficio
    )

    tempo_medio = CapacityService.tempo_medio_servizio(
        ufficio
    )

    visitatori_by_day = {
        riga["numero"]: riga
        for riga in visitatori_settimana
    }

    risultato = []

    for numero, nome in GIORNI:
        sportellisti = presenze[numero]["sportellisti"]
        dipendenti = presenze[numero]["dipendenti"]
        minuti_apertura = aperture[numero]

        capacita = (
            round(
                sportellisti
                * minuti_apertura
                / tempo_medio,
                1,
            )
            if tempo_medio > 0
            else 0.0
        )

        domanda = visitatori_by_day[numero]["media"]

        risultato.append(
            {
                "numero": numero,
                "nome": nome,
                "dipendenti_presenti": dipendenti,
                "sportellisti_presenti": sportellisti,
                "minuti_apertura": minuti_apertura,
                "tempo_medio": tempo_medio,
                "capacita_media": capacita,
                "visitatori_medi": domanda,
                "margine": round(
                    capacita - domanda,
                    1,
                ),
            }
        )

    return risultato


@user_passes_test(_puo_vedere_statistiche)
def statistiche_uffici(request):
    """
    Dashboard diagnostica per dirigenti/EQ.

    Mostra:
    - tempi medi hall / fuori ufficio / lavorazione;
    - visitatori medi per giorno della settimana;
    - ultimo snapshot e medie presenza;
    - capacità media storica;
    - valori correnti usati da CapacityService.
    """
    adesso = timezone.now()

    try:
        periodo_giorni = int(
            request.GET.get("giorni", "90")
        )
    except ValueError:
        periodo_giorni = 90

    if periodo_giorni not in {
        30,
        90,
        180,
        365,
    }:
        periodo_giorni = 90

    da_data = adesso - timedelta(
        days=periodo_giorni
    )

    righe = []

    uffici = (
        Ufficio.objects
        .filter(attivo=True)
        .order_by("nome")
    )

    for ufficio in uffici:
        ultimo_snapshot = (
            SnapshotPresenzaUfficio.objects
            .filter(ufficio=ufficio)
            .order_by("-rilevato_il")
            .first()
        )

        medie_presenza = (
            SnapshotPresenzaUfficio.objects
            .filter(
                ufficio=ufficio,
                rilevato_il__gte=da_data,
            )
            .aggregate(
                dipendenti_presenti=Avg(
                    "dipendenti_presenti"
                ),
                sportellisti_presenti=Avg(
                    "sportellisti_presenti"
                ),
                dipendenti_totali=Avg(
                    "dipendenti_totali"
                ),
                sportellisti_totali=Avg(
                    "sportellisti_totali"
                ),
            )
        )

        tempi = _tempi_accessi(
            ufficio,
            da_data,
        )

        visitatori_settimana = (
            _visitatori_medi_per_giorno(
                ufficio,
                da_data,
                adesso,
            )
        )

        capacita_media = (
            _capacita_media_settimanale(
                ufficio,
                da_data,
                visitatori_settimana,
            )
        )

        capacita_corrente = (
            CapacityService.capacita_residua(
                ufficio,
                data_ora=adesso,
            )
        )

        righe.append(
            {
                "ufficio": ufficio,
                "ultimo_snapshot": ultimo_snapshot,
                "medie_presenza": medie_presenza,
                "tempi": tempi,
                "visitatori_settimana": visitatori_settimana,
                "capacita_media": capacita_media,
                "capacita": capacita_corrente,
            }
        )

    return render(
        request,
        "dashboard/statistiche_uffici.html",
        {
            "righe": righe,
            "periodo_giorni": periodo_giorni,
            "adesso": adesso,
        },
    )
