import hashlib
import hmac
import ipaddress
import json
import re
import time
from django.conf import settings
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .services import ingest

@csrf_exempt
@require_POST
def receive(request):
    if not settings.AUDIT_AD_ENABLED:
        raise Http404
    if not request.is_secure():
        return JsonResponse({'error': 'HTTPS richiesto'}, status=403)
    source = request.headers.get('X-AD-Source', '')
    secret = settings.AUDIT_AD_SOURCES.get(source)
    peer = request.META.get('REMOTE_ADDR', '')
    if peer in settings.AUDIT_AD_TRUSTED_PROXIES:
        peer = request.headers.get('X-Real-IP', '')
    try:
        peer = str(ipaddress.ip_address(peer))
    except ValueError:
        peer = ''
    if not secret or len(secret) < 32 or peer != source:
        return JsonResponse({'error': 'Accesso negato'}, status=403)
    if len(request.body) > 1024 * 1024:
        return JsonResponse({'error': 'Batch troppo grande'}, status=413)
    timestamp = request.headers.get('X-AD-Timestamp', '')
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError
    except ValueError:
        return JsonResponse({'error': 'Timestamp non valido'}, status=403)
    signature = hmac.new(secret.encode(), timestamp.encode() + b'.' + request.body, hashlib.sha256).hexdigest()
    supplied = request.headers.get('X-AD-Signature', '')
    if not re.fullmatch(r'[0-9a-f]{64}', supplied) or not hmac.compare_digest(signature, supplied):
        return JsonResponse({'error': 'Firma non valida'}, status=403)
    try:
        payload = json.loads(request.body)
        rows = payload['events']
        if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
            raise ValueError
        created = ingest(source, rows)
    except (ValueError, TypeError, KeyError, OverflowError):
        return JsonResponse({'error': 'Batch non valido: nessun evento acquisito'}, status=400)
    return JsonResponse({'received': len(rows), 'created': created, 'duplicates': len(rows) - created})
