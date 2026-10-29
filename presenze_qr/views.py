import base64
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from .models import Postazione, Timbratura
from .services import abilitato, automatico, emetti, timbra, correggi, log, TimbraturaError
from .security import controlla_rete, client_ip


def protetta(monitor=False):
    def decorator(view):
        @wraps(view)
        @never_cache
        def wrapped(request, *args, **kwargs):
            if not settings.PRESENZE_QR_ENABLED:
                raise Http404
            try:
                request.presenze_ip = controlla_rete(request, monitor)
                response = view(request, *args, **kwargs)
            except PermissionDenied:
                log(request.user, 'ACCESSO_NEGATO', client_ip(request))
                raise
            response['Referrer-Policy'] = 'no-referrer'
            return response
        return wrapped
    return decorator


@protetta()
@login_required
@require_GET
def personale(request):
    log(request.user, 'CONSULTAZIONE', request.presenze_ip)
    return redirect(reverse('my_account') + '?tab=presenza')


@protetta()
@require_GET
def scan(request):
    log(request.user, 'APERTURA_SCANSIONE', request.presenze_ip)
    return render(request, 'presenze_qr/scan.html', {
        'abilitato_qr': abilitato(request.user), 'automatico': automatico(timezone.now()) or '',
    })


@protetta()
@login_required
@require_POST
def registra(request):
    try:
        record, created = timbra(request.user, request.POST.get('token', ''), request.POST.get('verso', ''), request.presenze_ip)
    except TimbraturaError as exc:
        log(request.user, 'TIMBRATURA_RIFIUTATA', request.presenze_ip)
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({'success': True, 'id': record.pk, 'created': created, 'verso': record.get_verso_display(), 'url': reverse('presenze_qr:personale')})


@protetta()
@login_required
@require_POST
def inverti(request, pk):
    try:
        correggi(request.user, pk, request.POST.get('verso_atteso'), request.presenze_ip)
        messages.success(request, 'Timbratura corretta.')
    except TimbraturaError as exc:
        log(request.user, 'CORREZIONE_RIFIUTATA', request.presenze_ip)
        messages.error(request, str(exc))
    return redirect('presenze_qr:personale')


@protetta(monitor=True)
@require_GET
def monitor(request, pk=None):
    if pk is None:
        station = Postazione.objects.filter(attiva=True).order_by('pk').first()
        if station is None:
            raise Http404
        pk = station.pk
    station = get_object_or_404(Postazione, pk=pk, attiva=True)
    log(request.user, 'APERTURA_MONITOR', request.presenze_ip, station)
    return render(request, 'presenze_qr/monitor.html', {'postazione': station})


@protetta(monitor=True)
@require_POST
def codice(request, pk):
    from io import BytesIO
    import qrcode
    get_object_or_404(Postazione, pk=pk, attiva=True)
    station, token = emetti(pk, request.user, request.presenze_ip)
    # Fragment is never sent to HTTP access logs or as a Referer.
    url = 'https://' + settings.PUBLIC_ACCOUNT_HOST + reverse('presenze_qr:scan') + '#token=' + token
    output = BytesIO()
    qrcode.make(url).save(output, format='PNG')
    return JsonResponse({'qr': 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode(),
        'generazione': str(station.generazione), 'remaining_ms': max(0, int((station.scade_il-timezone.now()).total_seconds()*1000))})
