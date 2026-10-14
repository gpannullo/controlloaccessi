from django.conf import settings
from .services import abilitato


def presenze(request):
    return {'presenze_qr_enabled': settings.PRESENZE_QR_ENABLED,
            'presenze_qr_abilitato': settings.PRESENZE_QR_ENABLED and abilitato(request.user)}
