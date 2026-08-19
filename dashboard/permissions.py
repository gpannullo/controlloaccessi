from django.contrib.auth.decorators import user_passes_test


GRUPPI_DIRIGENZA = {
    "Dirigenti",
    "Funzionari_EQ",
}


def puo_accedere_area_dirigenza(user):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.groups.filter(
        name__in=GRUPPI_DIRIGENZA,
    ).exists()


dirigenza_required = user_passes_test(
    puo_accedere_area_dirigenza
)
