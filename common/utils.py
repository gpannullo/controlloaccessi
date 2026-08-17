from django.utils import timezone


def now():
    """
    Restituisce sempre una data/ora timezone-aware.
    """
    return timezone.localtime()