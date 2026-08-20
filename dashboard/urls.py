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
from dashboard.directory_admin_views import (
    directory_action,
    directory_bulk_action,
    directory_groups,
    directory_group_rename,
    directory_home,
    directory_user,
    directory_user_create,
    directory_user_create_submit,
    directory_username_suggestion,
    directory_users,
)


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
    path("directory/", directory_home, name="directory_home"),
    path("directory/utenti/", directory_users, name="directory_users"),
    path("directory/utenti/nuovo/", directory_user_create, name="directory_user_create"),
    path("directory/utenti/nuovo/crea/", directory_user_create_submit, name="directory_user_create_submit"),
    path("directory/utenti/nuovo/username/", directory_username_suggestion, name="directory_username_suggestion"),
    path("directory/azioni-massive/", directory_bulk_action, name="directory_bulk_action"),
    path("directory/gruppi/", directory_groups, name="directory_groups"),
    path("directory/gruppi/rinomina/", directory_group_rename, name="directory_group_rename"),
    path("directory/utenti/<int:pk>/", directory_user, name="directory_user"),
    path("directory/utenti/<int:pk>/azione/", directory_action, name="directory_action"),
]
