"""Resolve the same AD username independently of the casing entered at login."""
import logging
from django.contrib.auth import get_user_model
from django.db.models import Case, When, Value, IntegerField

logger = logging.getLogger(__name__)


def find_directory_user(username):
    canonical = username.strip().lower()
    # Stable choice even when legacy duplicates exist. Never select by the
    # casing supplied by the caller, and never merge historical relations here.
    matches = list(get_user_model().objects.filter(username__iexact=canonical).annotate(
        canonical_rank=Case(When(username=canonical, then=Value(0)),
                            default=Value(1), output_field=IntegerField())
    ).order_by('canonical_rank', 'pk')[:2])
    if len(matches) > 1:
        logger.warning('Duplicate directory identities require reconciliation; selected user id=%s', matches[0].pk)
    return matches[0] if matches else None


def get_or_create_directory_user(username):
    canonical = username.strip().lower()
    if not canonical:
        raise ValueError('Username directory vuoto.')
    user = find_directory_user(canonical)
    if user is not None:
        return user, False
    # All application callers create using the same value. The existing unique
    # username constraint makes simultaneous first logins converge on one row.
    return get_user_model().objects.get_or_create(username=canonical)
