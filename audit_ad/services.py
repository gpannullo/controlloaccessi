"""Indicators requiring human review, never proof of a compromise."""
import hashlib
import ipaddress
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Event, Alert

def normalize(source, row):
    if not isinstance(row, dict):
        raise ValueError('Evento non valido')
    occurred = parse_datetime(str(row.get('time', '')))
    if not occurred or timezone.is_naive(occurred) or occurred > timezone.now() + timedelta(minutes=5):
        raise ValueError('Timestamp con fuso obbligatorio, non futuro')
    event_id, record_id = int(row['event_id']), int(row['record_id'])
    computer = row['computer']
    if not isinstance(computer, str) or not computer or len(computer) > 255 or not (0 < event_id < 65536) or not (0 <= record_id < 2**63):
        raise ValueError('Identificativi non validi')
    data = row.get('data', {})
    if not isinstance(data, dict) or len(data) > 150 or any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 255 or len(v) > 8192 for k, v in data.items()):
        raise ValueError('EventData non valido')
    ip = None
    try:
        parsed = ipaddress.ip_address(data.get('IpAddress', ''))
        ip = str(getattr(parsed, 'ipv4_mapped', None) or parsed)
    except ValueError:
        pass
    identity = f'{source}|{computer.casefold()}|Security|{record_id}|{occurred.isoformat()}|{event_id}'
    return dict(fingerprint=hashlib.sha256(identity.encode()).hexdigest(), source=source,
                computer=computer, record_id=record_id, event_id=event_id, occurred_at=occurred,
                username=(data.get('TargetUserName') or data.get('SubjectUserName') or '')[:255],
                client_ip=ip, workstation=(data.get('WorkstationName') or data.get('Workstation') or '')[:255],
                protocol=data.get('AuthenticationPackageName', '')[:100],
                logon_type=data.get('LogonType', '')[:20], data=data)

def analyze(event):
    def alert(rule, severity, description, evidence=None, key=None):
        Alert.objects.get_or_create(key=key or f'{rule}:{event.pk}', defaults={
            'event': event, 'rule': rule, 'severity': severity,
            'description': description, 'evidence': evidence or {},
        })
    if event.event_id in (1102, 4719):
        alert('audit_changed', 'high', 'Log Security cancellato o policy di audit modificata: verificare se autorizzato.')
    sid = event.data.get('TargetSid', '')
    privileged = sid in ('S-1-5-32-544', 'S-1-5-32-548', 'S-1-5-32-549', 'S-1-5-32-551') or (
        sid.startswith('S-1-5-21-') and sid.rsplit('-', 1)[-1] in ('512', '518', '519', '520'))
    if event.event_id in (4728, 4732, 4756) and privileged:
        alert('privileged_group_member', 'high', 'Aggiunta a gruppo privilegiato: verificare attore e membro.', event.data)
    if event.event_id in (4625, 4771) and event.client_ip:
        start = event.occurred_at - timedelta(minutes=5)
        failures = Event.objects.filter(client_ip=event.client_ip, event_id__in=[4625, 4771],
                                       occurred_at__gte=start, occurred_at__lte=event.occurred_at)
        count = failures.count()
        if count >= settings.AUDIT_AD_FAILURE_THRESHOLD:
            bucket = int(event.occurred_at.timestamp()) // 300
            alert('repeated_failures', 'warning', 'Autenticazioni fallite ripetute dallo stesso IP in 5 minuti: possibile attacco o credenziali errate.',
                  {'count': count, 'event_ids': list(failures.values_list('pk', flat=True)[:100]), 'ip': event.client_ip},
                  key=f'repeated_failures:{event.client_ip}:{bucket}')

@transaction.atomic
def ingest(source, rows):
    normalized = sorted([normalize(source, row) for row in rows], key=lambda e: e['occurred_at'])
    created = 0
    affected = {}
    for values in normalized:
        fingerprint = values.pop('fingerprint')
        event, new = Event.objects.get_or_create(fingerprint=fingerprint, defaults=values)
        created += new
        analyze(event)
        if new and event.client_ip and event.event_id in (4625, 4771):
            window = affected.setdefault(event.client_ip, [event.occurred_at, event.occurred_at])
            window[0] = min(window[0], event.occurred_at)
            window[1] = max(window[1], event.occurred_at)
    # Re-evaluate already stored later events if a delayed DC batch arrived.
    for ip, (start, end) in affected.items():
        for event in Event.objects.filter(client_ip=ip, event_id__in=[4625, 4771],
                occurred_at__gte=start, occurred_at__lte=end + timedelta(minutes=5)).iterator():
            analyze(event)
    return created
