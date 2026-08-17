from django.contrib import admin
from django.urls import include, path

from common.views import (
    access_denied,
    home,
    monitor_home,
    monitor_stato_live,
)


urlpatterns = [
    # Home applicativa
    path(
        "",
        home,
        name="home",
    ),

    # Amministrazione
    path(
        "admin/",
        admin.site.urls,
    ),

    # Autenticazione
    path(
        "accounts/",
        include(
            "django.contrib.auth.urls"
        ),
    ),

    # Dashboard portineria
    path(
        "dashboard/",
        include("dashboard.urls"),
    ),

    # Funzioni portineria
    path(
        "portineria/",
        include(
            (
                "visitors.portineria_urls",
                "portineria",
            ),
            namespace="portineria",
        ),
    ),

    # Gestione uffici
    path(
        "uffici/",
        include(
            (
                "visitors.office_urls",
                "uffici",
            ),
            namespace="uffici",
        ),
    ),

    # Monitor pubblico
    path(
        "monitor/",
        monitor_home,
        name="monitor_home",
    ),

    path(
        "monitor/stato-live/",
        monitor_stato_live,
        name="monitor_stato_live",
    ),

    # Accesso negato
    path(
        "accesso-negato/",
        access_denied,
        name="access_denied",
    ),
]