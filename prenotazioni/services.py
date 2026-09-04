from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from access_control.models import CalendarioApertura, IndisponibilitaUfficio, Ufficio

from .models import Prenotazione


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
