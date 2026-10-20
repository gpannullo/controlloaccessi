import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from ldap3.utils.conv import escape_filter_chars
from post_office import mail
from accounts.services.active_directory_service import ActiveDirectoryService
from comunicazioni.models import CampagnaPassword2026

END = datetime(2026, 10, 10, 12, tzinfo=ZoneInfo('Europe/Rome'))
URL = 'https://account.comune.aversa.ce.it/account/change-password/'

def changed(row, state):
    return state['pwd'] != row.pwd_last_set or state['guid'] != row.ad_guid

def directory_state(names):
    service = ActiveDirectoryService()
    conn = service._connection()
    try:
        query = '(&(objectCategory=person)(objectClass=user)(|' + ''.join(
            '(sAMAccountName=%s)' % escape_filter_chars(n) for n in names) + '))'
        conn.search(settings.DIRECTORY['BASE_DN'], query,
                    attributes=['sAMAccountName', 'pwdLastSet', 'objectGUID', 'userAccountControl'])
        if conn.result.get('result') != 0:
            raise CommandError('Lettura AD incompleta: nessun invio.')
        result = {}
        for entry in conn.entries:
            raw = entry.entry_raw_attributes
            name = str(entry.sAMAccountName.value).casefold()
            if not raw.get('pwdLastSet') or not raw.get('objectGUID') or name in result:
                raise CommandError('Dati AD mancanti o ambigui: nessun invio.')
            result[name] = {'pwd': raw['pwdLastSet'][0].decode('ascii'),
                            'guid': raw['objectGUID'][0].hex(),
                            'active': not (int(entry.userAccountControl.value) & 2)}
        return result
    finally:
        conn.unbind()

class Command(BaseCommand):
    help = 'Campagna fissa di cambio password entro il 10 ottobre 2026.'

    def add_arguments(self, parser):
        parser.add_argument('--initialize', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if timezone.now() >= END:
            self.stdout.write('Campagna terminata: nessun invio.')
            return
        names = json.loads((Path(__file__).resolve().parents[2] / 'password_campaign_2026.json').read_text())
        state = directory_state(names)
        if options['initialize']:
            users = list(get_user_model().objects.filter(username__in=names, is_active=True, tipo_attivita__in=['AMM', 'SPO']))
            if len(users) != len(names) or any(u.username.casefold() not in state for u in users):
                raise CommandError('Elenco locale/AD incompleto: inizializzazione annullata.')
            if not options['dry_run']:
                with transaction.atomic():
                    for user in users:
                        s = state[user.username.casefold()]
                        CampagnaPassword2026.objects.get_or_create(utente=user, defaults={
                            'username': user.username, 'pwd_last_set': s['pwd'], 'ad_guid': s['guid']})
            self.stdout.write('Destinatari inizializzazione: %s; nessuna email accodata.' % len(users))
            return
        if CampagnaPassword2026.objects.count() != len(names):
            raise CommandError('Inizializzare prima la campagna.')
        stats = dict(accodati=0, candidati=0, completati=0, esclusi=0, duplicati=0)
        for pk in CampagnaPassword2026.objects.values_list('pk', flat=True):
            with transaction.atomic():
                row = CampagnaPassword2026.objects.select_for_update().select_related('utente').get(pk=pk)
                now = timezone.now()
                if now >= END:
                    break
                today = now.astimezone(END.tzinfo).date()
                s = state.get(row.username.casefold())
                if row.completata:
                    stats['completati'] += 1
                    continue
                if s and changed(row, s):
                    if not options['dry_run']:
                        row.completata = True
                        row.save(update_fields=['completata'])
                    stats['completati'] += 1
                    continue
                user = row.utente
                email = (user.email or '').strip()
                try:
                    validate_email(email)
                except ValidationError:
                    email = ''
                if not s or not s['active'] or not user.is_active or user.username != row.username or not email or email.lower().endswith('.local'):
                    stats['esclusi'] += 1
                    continue
                if row.ultimo_invio == today:
                    stats['duplicati'] += 1
                    continue
                stats['candidati'] += 1
                if options['dry_run']:
                    continue
                mail.send(recipients=[email], sender=settings.DEFAULT_FROM_EMAIL,
                          template='campagna_cambio_password',
                          context={'nome': user.get_full_name() or user.username, 'username': user.username,
                                   'url': URL, 'scadenza': END.strftime('%d/%m/%Y alle %H:%M')},
                          priority='medium', expires_at=min(END, datetime.combine(today, datetime.max.time(), tzinfo=END.tzinfo)))
                row.ultimo_invio = today
                row.save(update_fields=['ultimo_invio'])
                stats['accodati'] += 1
        self.stdout.write(str(stats))
