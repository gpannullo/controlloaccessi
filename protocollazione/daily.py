"""Daily immutable snapshots; all remote writes go through protocollazione.services."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone

from .contracts import Documento, RichiestaProtocollo, TipoProtocollo, ConfigurazioneProtocolloError, Firmatario
from .models import ReportGiornaliero
from .services import protocolla, get_backend

ROME = ZoneInfo('Europe/Rome')


def build_document(kind, day, generated, author):
    if kind == 'qr':
        from presenze_qr.qr_report import report_rows, build_qr_report
        return build_qr_report(report_rows(day, day, generated), day, day, generated, author)
    from visitors.models import AccessoVisitatore, EventoAccesso
    from visitors.services.visitor_report_service import build_visitor_report
    begin = datetime.combine(day, time.min, tzinfo=ROME)
    finish = datetime.combine(day + timedelta(days=1), time.min, tzinfo=ROME)
    activity = Q(ingresso__lt=finish) & (Q(uscita__gte=begin) | Q(uscita__isnull=True))
    activity |= Q(eventi__timestamp__gte=begin, eventi__timestamp__lt=finish)
    for field in ('ingresso', 'uscita', 'spostato_fuori_ufficio_il', 'ingresso_ufficio_il', 'visita_conclusa_il'):
        activity |= Q(**{field+'__gte': begin, field+'__lt': finish})
    records = AccessoVisitatore.objects.filter(activity, ingresso__lte=generated).distinct().select_related(
        'visitatore', 'badge', 'ufficio_destinazione').prefetch_related(
        Prefetch('eventi', queryset=EventoAccesso.objects.filter(timestamp__lte=generated).select_related('operatore')),
        Prefetch('accessi_successivi', queryset=AccessoVisitatore.objects.select_related('ufficio_destinazione'))
    ).order_by('visitatore__cognome', 'visitatore__nome', 'visitatore_id', 'ingresso', 'pk')
    return build_visitor_report(list(records), day, day, generated, author)


def request_for(pdf, params):
    return RichiestaProtocollo(
        oggetto=params['oggetto'], tipo=TipoProtocollo.INTERNO,
        documento=Documento(params['nome'], pdf), classificazione=params['classificazione'],
        ufficio=params['ufficio'], riservato=True,
        firmatari=tuple(Firmatario(**item) for item in params['firmatari']))


def process_report(kind, day, operator, *, send=False):
    key = f'report-giornaliero:{kind}:{day.isoformat()}'
    snapshot = ReportGiornaliero.objects.filter(chiave=key).first()
    if snapshot:
        request = request_for(bytes(snapshot.documento), snapshot.parametri)
    else:
        config = settings.REPORT_PROTOCOLLO
        classification = config.get('CLASSIFICAZIONE_' + kind.upper(), '')
        if not classification:
            raise ConfigurazioneProtocolloError(f'Classificazione mancante per {kind}.')
        params = {
            'oggetto': f"Report giornaliero {'visitatori' if kind == 'visitatori' else 'entrate e uscite QR'} del {day:%d/%m/%Y}",
            'nome': f'report-{kind}-{day:%Y%m%d}.pdf',
            'classificazione': classification, 'ufficio': config.get('UFFICIO', ''),
            'firmatari': [{'codice': config.get('FIRMATARIO', ''), 'ufficio': config.get('UFFICIO_FIRMATARIO', '')}],
        }
        pdf = build_document(kind, day, timezone.now(), operator.get_full_name() or operator.username)
        request = request_for(pdf, params)
        get_backend().valida(request)
        if send:
            # Unique key selects a single immutable snapshot even with concurrent jobs.
            snapshot, _ = ReportGiornaliero.objects.get_or_create(chiave=key, defaults={
                'giorno': day, 'tipo': kind, 'documento': pdf, 'parametri': params})
            request = request_for(bytes(snapshot.documento), snapshot.parametri)
    if not send:
        get_backend().valida(request)
        return None
    return protocolla(request, chiave=key, operatore=operator)
