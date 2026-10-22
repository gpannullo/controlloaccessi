from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from protocollazione.daily import process_report, ROME


class Command(BaseCommand):
    help = 'Valida i report del giorno precedente; --invia abilita la protocollazione reale.'

    def add_arguments(self, parser):
        parser.add_argument('--data', type=date.fromisoformat, help='YYYY-MM-DD; default ieri, Europe/Rome')
        parser.add_argument('--invia', action='store_true')
        parser.add_argument('--tipo', choices=['entrambi', 'visitatori', 'qr'], default='entrambi')

    def handle(self, *args, **options):
        day = options['data'] or timezone.localdate(timezone=ROME) - timedelta(days=1)
        if day >= timezone.localdate(timezone=ROME):
            raise CommandError('Sono consentite soltanto giornate concluse.')
        if options['invia'] and not settings.PROTOCOLLAZIONE_ENABLED:
            raise CommandError('PROTOCOLLAZIONE_ENABLED non abilitato.')
        operator = get_user_model().objects.filter(username=settings.REPORT_PROTOCOLLO['OPERATORE']).first()
        if not operator or not operator.is_active or not operator.has_perm('protocollazione.add_registrazioneprotocollo'):
            raise CommandError('Configurare un operatore attivo con permesso di protocollazione.')
        errors = []
        for kind in (['visitatori', 'qr'] if options['tipo'] == 'entrambi' else [options['tipo']]):
            try:
                result = process_report(kind, day, operator, send=options['invia'])
                self.stdout.write(f'{day} {kind}: ' + (f'protocollo {result.numero}/{result.anno}' if result else 'VALIDATO, nessun invio'))
            except Exception as exc:
                # Avoid logging credentials, document contents or SOAP responses.
                errors.append(kind)
                self.stderr.write(f'{kind}: {type(exc).__name__}; verificare configurazione e registro protocolli. Nessun reinvio automatico.')
        if errors:
            raise CommandError('Report non completati: ' + ', '.join(errors))
