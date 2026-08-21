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
    directory_staff,
    directory_sync_mail_from_upn,
    directory_user,
    directory_user_create,
    directory_user_create_submit,
    directory_username_suggestion,
    directory_users,
)


app_name = "dashboard"


urlpatterns = [
    path("", dashboard_home, name="home"),

    path("stato-live/", stato_dashboard_portineria, name="stato_live"),

    path("dirigenza/", area_dirigenza, name="dirigenza_home"),

    path("dirigenza/statistiche/", statistiche_uffici, name="statistiche_uffici"),

    path("dirigenza/visitatori/", ricerca_visitatori, name="ricerca_visitatori"),

    path("dirigenza/visitatori/<int:pk>/", dettaglio_visitatore, name="dettaglio_visitatore"),

    path("dirigenza/amministratori/", stato_amministratori, name="stato_amministratori"),

    path("dirigenza/amministratori/<int:pk>/", log_amministratore, name="log_amministratore"),
    path("gestione-account/", directory_home, name="directory_home"),
    path("gestione-account/users/", directory_users, name="directory_users"),
    path("gestione-account/users/new/", directory_user_create, name="directory_user_create"),
    path("gestione-account/users/new/create/", directory_user_create_submit, name="directory_user_create_submit"),
    path("gestione-account/users/new/username/", directory_username_suggestion, name="directory_username_suggestion"),
    path("gestione-account/bulk-actions/", directory_bulk_action, name="directory_bulk_action"),
    path("gestione-account/users/sync-email-upn/", directory_sync_mail_from_upn, name="directory_sync_mail_from_upn"),
    path("gestione-account/groups/", directory_groups, name="directory_groups"),
    path("gestione-account/personale/", directory_staff, name="directory_staff"),
    path("gestione-account/groups/rename/", directory_group_rename, name="directory_group_rename"),
    path("gestione-account/users/<int:pk>/", directory_user, name="directory_user"),
    path("gestione-account/users/<int:pk>/action/", directory_action, name="directory_action"),
]
