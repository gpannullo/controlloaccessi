from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from access_control.models import CalendarioApertura, Ufficio

from .models import Prenotazione


def uffici_prenotabili():
    return Ufficio.objects.filter(attivo=True, riceve_pubblico=True, aperture__su_appuntamento=True).distinct().order_by("nome")


def slot_disponibili(ufficio, data):
    if data < timezone.localdate() or data > timezone.localdate() + timedelta(days=settings.PRENOTAZIONI_MAX_GIORNI):
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
