"""The visitors app creates daily PDFs and delegates protocol delivery."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone
from protocollazione.contracts import Documento, Firmatario, RichiestaProtocollo, TipoProtocollo, ConfigurazioneProtocolloError
from protocollazione.models import ReportGiornaliero
from protocollazione.services import get_backend, protocolla

ROME = ZoneInfo('Europe/Rome')

def _pdf(kind, day, generated, author):
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
    records = AccessoVisitatore.objects.filter(activity, ingresso__lte=generated).distinct().select_related('visitatore','badge','ufficio_destinazione').prefetch_related(
        Prefetch('eventi', queryset=EventoAccesso.objects.filter(timestamp__lte=generated).select_related('operatore')),
        Prefetch('accessi_successivi', queryset=AccessoVisitatore.objects.select_related('ufficio_destinazione'))).order_by('visitatore__cognome','visitatore__nome','visitatore_id','ingresso','pk')
    return build_visitor_report(list(records), day, day, generated, author)

def protocolla_report_giornaliero(kind, day, operator, *, send=False):
    key = f'report-giornaliero:{kind}:{day.isoformat()}'
    snapshot = ReportGiornaliero.objects.filter(chiave=key).first()
    config = settings.REPORT_PROTOCOLLO
    if snapshot:
        pdf, params = bytes(snapshot.documento), snapshot.parametri
    else:
        classification = config.get('CLASSIFICAZIONE_'+kind.upper(), '')
        if not classification: raise ConfigurazioneProtocolloError(f'Classificazione mancante per {kind}.')
        params = {'oggetto': f"Report giornaliero {'visitatori' if kind == 'visitatori' else 'entrate e uscite QR'} del {day:%d/%m/%Y}", 'nome': f'report-{kind}-{day:%Y%m%d}.pdf', 'classificazione': classification, 'ufficio': config.get('UFFICIO',''), 'firmatari': [{'codice': config.get('FIRMATARIO',''), 'ufficio': config.get('UFFICIO_FIRMATARIO','')}]}
        pdf = _pdf(kind, day, timezone.now(), operator.get_full_name() or operator.username)
        if send:
            snapshot, _ = ReportGiornaliero.objects.get_or_create(chiave=key, defaults={'giorno': day, 'tipo': kind, 'documento': pdf, 'parametri': params})
            pdf, params = bytes(snapshot.documento), snapshot.parametri
    request = RichiestaProtocollo(oggetto=params['oggetto'], tipo=TipoProtocollo.INTERNO, documento=Documento(params['nome'], pdf), classificazione=params['classificazione'], ufficio=params['ufficio'], riservato=True, firmatari=(Firmatario(**params['firmatari'][0]),))
    get_backend().valida(request)
    return protocolla(request, chiave=key, operatore=operator) if send else None
