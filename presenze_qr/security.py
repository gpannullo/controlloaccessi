from ipaddress import ip_address, ip_network
from django.conf import settings
from django.core.exceptions import PermissionDenied


def in_reti(value, networks):
    try:
        addr = ip_address(value)
        return any(addr in ip_network(net.strip()) for net in networks if net.strip())
    except ValueError:
        return False


def client_ip(request):
    peer = request.META.get('REMOTE_ADDR', '')
    if in_reti(peer, settings.PRESENZE_QR_PROXY_ATTENDIBILI):
        # Nginx must overwrite this header, not append it or pass the client's.
        peer = request.META.get('HTTP_X_REAL_IP', '')
    try:
        return str(ip_address(peer))
    except ValueError:
        return None


def controlla_rete(request, monitor=False):
    ip = client_ip(request)
    if monitor or settings.PRESENZE_QR_SOLO_RETE_COMUNALE:
        if not ip or not in_reti(ip, settings.PRESENZE_QR_RETI_CONSENTITE):
            raise PermissionDenied('Funzione consentita solo dalla rete comunale.')
    if monitor and request.get_host().split(':')[0].lower() != settings.INTERNAL_APPLICATION_HOST:
        raise PermissionDenied('Monitor disponibile solo sul portale interno.')
    return ip
