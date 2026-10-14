import uuid
from datetime import timedelta, time
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from .models import Postazione, Timbratura, Attivita

SALT = 'presenze-qr-v1'


class TimbraturaError(ValueError):
    pass


def abilitato(user):
    return user.is_authenticated and user.is_active and user.tipo_attivita != 'DIS' and not (user.badge or '').strip('0')


def automatico(now):
    ora = now.astimezone(ZoneInfo('Europe/Rome')).time()
    if time(8) <= ora <= time(9, 30):
        return 'I'
    if time(12, 30) <= ora <= time(14):
        return 'U'
    return None


def storico_personale(user):
    origine = 'AUTOMATICO' if (user.badge or '').strip('0') else 'QR'
    rows = list(Timbratura.objects.filter(utente=user, origine=origine)[:10])
    latest = Timbratura.objects.filter(utente=user).values_list('pk', flat=True).first()
    now = timezone.now()
    for row in rows:
        row.modificabile = (row.pk == latest and row.origine == 'QR' and abilitato(user)
                           and settings.PRESENZE_QR_ENABLED
                           and now < row.registrata_il + timedelta(seconds=60))
    return rows


def log(user, azione, ip, postazione=None, timbratura=None, prima='', dopo=''):
    Attivita.objects.create(utente=user if user.is_authenticated else None, azione=azione,
                           ip=ip, postazione=postazione, timbratura=timbratura,
                           verso_prima=prima, verso_dopo=dopo)


@transaction.atomic
def emetti(pk, user, ip):
    station = Postazione.objects.select_for_update().get(pk=pk, attiva=True)
    now = timezone.now()
    if not station.scade_il or station.scade_il <= now or station.consumato_il:
        station.generazione = uuid.uuid4()
        station.scade_il = now + timedelta(seconds=30)
        station.consumato_il = None
        station.save(update_fields=['generazione', 'scade_il', 'consumato_il'])
        log(user, 'QR_GENERATO', ip, station)
    token = signing.Signer(salt=SALT).sign('%s:%s' % (station.pk, station.generazione))
    return station, token


def aggiorna_presenza(user, timbro):
    # A correction to an older punch must not overwrite a later movement.
    if user.ultima_timbratura_il and user.ultima_timbratura_il > timbro.registrata_il:
        return
    get_user_model().objects.filter(pk=user.pk).update(
        stato_presenza='PRE' if timbro.verso == 'I' else 'ASS', presenza_fonte='QR',
        presenza_verificata_il=timezone.now(), ultima_timbratura_il=timbro.registrata_il,
        ultima_timbratura_verso=timbro.verso, ultima_timbratura_causale='QR',
    )


@transaction.atomic
def timbra(user, token, verso, ip):
    try:
        pk, generation = signing.Signer(salt=SALT).unsign(token).split(':')
        generation = uuid.UUID(generation)
        station = Postazione.objects.select_for_update().get(pk=int(pk), attiva=True)
    except (ValueError, signing.BadSignature, Postazione.DoesNotExist):
        raise TimbraturaError('QR non valido. Inquadra il nuovo codice sul monitor.')
    user = get_user_model().objects.select_for_update().get(pk=user.pk)
    if not abilitato(user):
        raise TimbraturaError('La timbratura QR è riservata agli utenti attivi senza badge.')
    # Idempotent retry: it never creates another punch or reopens correction time.
    previous = Timbratura.objects.filter(generazione=generation).first()
    if previous:
        if previous.utente_id == user.pk:
            return previous, False
        raise TimbraturaError('QR già utilizzato. Inquadra il nuovo codice.')
    now = timezone.now()
    if station.generazione != generation or station.consumato_il or not station.scade_il or station.scade_il <= now:
        raise TimbraturaError('QR scaduto o già utilizzato. Inquadra il nuovo codice.')
    minuto = now.replace(second=0, microsecond=0)
    if Timbratura.objects.filter(utente=user, registrata_il__gte=minuto,
                                registrata_il__lt=minuto + timedelta(minutes=1)).exists():
        raise TimbraturaError('Hai già registrato un passaggio in questo minuto. Attendi il minuto successivo.')
    if verso == 'auto':
        verso = automatico(now)
    if verso not in ('I', 'U'):
        raise TimbraturaError('Seleziona Entrata oppure Uscita.')
    record = Timbratura.objects.create(utente=user, postazione=station, generazione=generation,
        registrata_il=now, verso=verso, verso_originale=verso, ip=ip)
    station.consumato_il = now
    station.save(update_fields=['consumato_il'])
    aggiorna_presenza(user, record)
    log(user, 'TIMBRATURA', ip, station, record, dopo=verso)
    return record, True


@transaction.atomic
def correggi(user, pk, atteso, ip):
    user = get_user_model().objects.select_for_update().get(pk=user.pk)
    if not abilitato(user):
        raise TimbraturaError('Utente non abilitato alla timbratura QR.')
    try:
        record = Timbratura.objects.select_for_update().get(pk=pk, utente=user, origine='QR')
    except Timbratura.DoesNotExist:
        raise TimbraturaError('Timbratura non disponibile.')
    if Timbratura.objects.filter(utente=user).values_list('pk', flat=True).first() != record.pk:
        raise TimbraturaError('Puoi correggere soltanto l’ultima timbratura.')
    if timezone.now() >= record.registrata_il + timedelta(seconds=60):
        raise TimbraturaError('Sono trascorsi 60 secondi: la timbratura non è più modificabile.')
    if atteso != record.verso:
        raise TimbraturaError('La timbratura è già stata modificata. Aggiorna la pagina.')
    prima = record.verso
    record.verso = 'U' if prima == 'I' else 'I'
    record.save(update_fields=['verso'])
    aggiorna_presenza(user, record)
    log(user, 'CORREZIONE', ip, record.postazione, record, prima, record.verso)
    return record
