from django.urls import path

from dashboard.dirigenza_views import (
    area_dirigenza,
    dettaglio_visitatore,
    log_amministratore,
    ricerca_visitatori,
    stato_amministratori,
)
from dashboard.live_views import (
    stato_dashboard_portineria,
)
from dashboard.statistiche_views import statistiche_uffici
from dashboard.views import dashboard_home


app_name = "dashboard"


urlpatterns = [
    path(
        "",
        dashboard_home,
        name="home",
    ),

    path(
        "stato-live/",
        stato_dashboard_portineria,
        name="stato_live",
    ),

    path(
        "dirigenza/",
        area_dirigenza,
        name="dirigenza_home",
    ),

    path(
        "dirigenza/statistiche/",
        statistiche_uffici,
        name="statistiche_uffici",
    ),

    path(
        "dirigenza/visitatori/",
        ricerca_visitatori,
        name="ricerca_visitatori",
    ),

    path(
        "dirigenza/visitatori/<int:pk>/",
        dettaglio_visitatore,
        name="dettaglio_visitatore",
    ),

    path(
        "dirigenza/amministratori/",
        stato_amministratori,
        name="stato_amministratori",
    ),

    path(
        "dirigenza/amministratori/<int:pk>/",
        log_amministratore,
        name="log_amministratore",
    ),
]
