from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from access_control.models import CalendarioApertura, IndisponibilitaUfficio, Ufficio

from .models import AppuntamentoWordPress, Prenotazione


def _normalizza_nominativo(valore):
    return " ".join((valore or "").casefold().split())


def appuntamento_wordpress_per_checkin(visitatore, ufficio, data=None):
    """Restituisce l'appuntamento WordPress verificato per il check-in.

    Il codice fiscale è il criterio prevalente; se non è disponibile viene
    usato il nominativo completo, limitato allo stesso ufficio e giorno.
    """
    data = data or timezone.localdate()
    candidati = (
        AppuntamentoWordPress.objects
        .filter(
            ufficio=ufficio,
            data_ora_inizio__date=data,
            appuntamento__isnull=False,
            appuntamento__accesso__isnull=True,
            appuntamento__stato__in=["PR", "CO"],
        )
        .select_related("appuntamento")
    )
    codice_fiscale = (visitatore.codice_fiscale or "").strip().upper()
    if codice_fiscale:
        candidati = candidati.filter(codice_fiscale=codice_fiscale)
    else:
        nominativo = _normalizza_nominativo(
            f"{visitatore.nome} {visitatore.cognome}"
        )
        candidati = [
            appuntamento
            for appuntamento in candidati
            if _normalizza_nominativo(appuntamento.nome_prenotato) == nominativo
            or _normalizza_nominativo(" ".join(reversed(appuntamento.nome_prenotato.split()))) == nominativo
        ]

    candidati = list(candidati)
    if not candidati:
        return None
    ora = timezone.now()
    appuntamento_wp = min(
        candidati,
        key=lambda candidato: abs(
            (candidato.data_ora_inizio - ora).total_seconds()
        ),
    )
    return appuntamento_wp.appuntamento


def uffici_prenotabili():
    return Ufficio.objects.filter(attivo=True, riceve_pubblico=True, aperture__su_appuntamento=True).distinct().order_by("nome")


def date_disponibili(ufficio):
    oggi = timezone.localdate()
    limite = oggi + timedelta(days=settings.PRENOTAZIONI_MAX_GIORNI)
    return [giorno for giorno in (oggi + timedelta(days=offset) for offset in range((limite - oggi).days + 1)) if slot_disponibili(ufficio, giorno)]


def slot_disponibili(ufficio, data):
    if data < timezone.localdate() or data > timezone.localdate() + timedelta(days=settings.PRENOTAZIONI_MAX_GIORNI):
        return []
    if IndisponibilitaUfficio.objects.filter(
        ufficio=ufficio,
        attiva=True,
        data_inizio__lte=data,
        data_fine__gte=data,
    ).exists():
        return []
    aperture = CalendarioApertura.objects.filter(ufficio=ufficio, giorno=data.weekday(), su_appuntamento=True).order_by("ora_inizio")
    minuti = settings.PRENOTAZIONI_DURATA_SLOT_MINUTI
    esistenti = set(Prenotazione.objects.filter(ufficio=ufficio, data_ora__date=data, stato__in=[Prenotazione.Stato.PRENOTATA, Prenotazione.Stato.CONFERMATA]).values_list("data_ora", flat=True))
    slots = []
    for apertura in aperture:
        corrente = timezone.make_aware(datetime.combine(data, apertura.ora_inizio))
        fine = timezone.make_aware(datetime.combine(data, apertura.ora_fine))
        while corrente + timedelta(minutes=minuti) <= fine:
            if corrente not in esistenti:
                slots.append(corrente)
            corrente += timedelta(minutes=minuti)
    return slots
