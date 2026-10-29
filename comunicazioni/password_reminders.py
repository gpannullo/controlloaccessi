from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from post_office import mail

from .models import PromemoriaPassword

ROME = ZoneInfo('Europe/Rome')


def eligible(user, now):
    expiry = user.scadenza_password
    return bool(user.is_active and not user.password_senza_scadenza and expiry
                and now < expiry <= now + timedelta(days=15))


def queue_reminders(dry_run=False):
    now = timezone.now()
    day = now.astimezone(ROME).date()
    stats = dict(accodati=0, candidati=0, duplicati=0, senza_email_valida=0)
    users = get_user_model().objects.filter(
        is_active=True, password_senza_scadenza=False,
        scadenza_password__gt=now, scadenza_password__lte=now + timedelta(days=15),
    )
    for pk in users.values_list('pk', flat=True).iterator():
        # Serializza esecuzioni concorrenti e salva registro + coda insieme.
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=pk)
            current = timezone.now()
            if not eligible(user, current):
                continue
            address = (user.email or '').strip()  # Indirizzo istituzionale, mai personale.
            try:
                validate_email(address)
            except ValidationError:
                stats['senza_email_valida'] += 1
                continue
            if PromemoriaPassword.objects.filter(utente=user, giorno=day).exists():
                stats['duplicati'] += 1
                continue
            stats['candidati'] += 1
            if dry_run:
                continue
            expiry = user.scadenza_password.astimezone(ROME)
            context = {'nome': user.get_full_name() or user.username, 'username': user.username,
                       'scadenza': expiry.strftime('%d/%m/%Y alle %H:%M'),
                       'url': 'https://account.comune.aversa.ce.it/account/change-password/'}
            mail.send(
                recipients=[address], sender=settings.DEFAULT_FROM_EMAIL,
                template='password_in_scadenza', context=context,
                priority='medium', expires_at=user.scadenza_password,
            )
            PromemoriaPassword.objects.create(utente=user, giorno=day, scadenza=user.scadenza_password, destinatario=address)
            stats['accodati'] += 1
    return stats
