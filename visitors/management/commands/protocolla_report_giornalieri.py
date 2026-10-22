from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from visitors.services.report_protocol_service import ROME, protocolla_report_giornaliero

# Configurazione specifica dei report. Non contiene credenziali.
REPORT_CONFIG = {
    'operatore': 'g.pannullo',
    'classificazione': 'DA_CONFIGURARE',
    'ufficio_destinatario': 'DA_CONFIGURARE',
    'firmatario': 'DA_CONFIGURARE',
    'ufficio_firmatario': 'DA_CONFIGURARE',
}

class Command(BaseCommand):
    help = 'Genera i report applicativi e li invia al protocollo.'
    def add_arguments(self, parser):
        parser.add_argument('--data', type=date.fromisoformat)
        parser.add_argument('--invia', action='store_true')
        parser.add_argument('--tipo', choices=['entrambi','visitatori','qr'], default='entrambi')
    def handle(self, *args, **options):
        day = options['data'] or timezone.localdate(timezone=ROME) - timedelta(days=1)
        if day >= timezone.localdate(timezone=ROME): raise CommandError('Sono consentite soltanto giornate concluse.')
        if options['invia'] and not settings.PROTOCOLLAZIONE_ENABLED: raise CommandError('PROTOCOLLAZIONE_ENABLED non abilitato.')
        operator = get_user_model().objects.filter(username=REPORT_CONFIG['operatore']).first()
        if not operator or not operator.is_active or not operator.has_perm('protocollazione.add_registrazioneprotocollo'): raise CommandError('Operatore non configurato.')
        errors=[]
        for kind in (['visitatori','qr'] if options['tipo']=='entrambi' else [options['tipo']]):
            try:
                result=protocolla_report_giornaliero(kind, day, operator, REPORT_CONFIG, send=options['invia'])
                self.stdout.write(f'{day} {kind}: '+(f'protocollo {result.numero}/{result.anno}' if result else 'VALIDATO, nessun invio'))
            except Exception as exc:
                errors.append(kind); self.stderr.write(f'{kind}: {type(exc).__name__}; verificare configurazione.')
        if errors: raise CommandError('Report non completati: '+', '.join(errors))
