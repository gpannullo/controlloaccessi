from django.contrib import admin
from django.urls import include, path

from common.views import (
    access_denied,
    home,
    monitor_home,
    monitor_pubblico,
    monitor_pubblico_stato_live,
    monitor_scarica_avvio,
    monitor_stato_live,
)
from accounts.views import DirectoryLoginView, initial_password_change, my_account, change_own_password, profile_completion
from dashboard.directory_admin_views import directory_home
from visitors.public_views import ticket_status
from presenze_qr import views as presenze_qr_views


urlpatterns = [
    path("account/presenze/", include("presenze_qr.urls")),
    path("monitor-presenze/<int:pk>/", presenze_qr_views.monitor, name="monitor_presenze"),
    path("monitor-presenze/<int:pk>/codice/", presenze_qr_views.codice, name="monitor_presenze_codice"),
    # Pagina pubblica consultabile esclusivamente con il token casuale del QR.
    path("attesa/<str:token>/", ticket_status, name="ticket_status"),

    # Servizi pubblici per i cittadini.
    path("prenotazioni/", include(("prenotazioni.urls", "prenotazioni"), namespace="prenotazioni")),
    path("identita/", include(("spid_cie.urls", "spid_cie"), namespace="spid_cie")),
    path("pdnd/", include(("pdnd.urls", "pdnd"), namespace="pdnd")),

    # Home applicativa
    path("", home, name="home"),

    # Amministrazione
    path("admin/", admin.site.urls),

    # Autenticazione
    path("account/", my_account, name="my_account"),
    path("account/change-password/", change_own_password, name="change_own_password"),
    path("account/completa-profilo/", profile_completion, name="profile_completion"),
    path("account/cambio-password-iniziale/", initial_password_change, name="initial_password_change"),
    path("accounts/", my_account, name="accounts_management"),
    path("accounts/login/", DirectoryLoginView.as_view(), name="login"),
    path("accounts/gestione-account/", directory_home, name="gestione_account"),
    path("accounts/", include("django.contrib.auth.urls")),

    # Dashboard portineria
    path("dashboard/", include("dashboard.urls")),

    # Funzioni portineria
    path("portineria/", include(("visitors.portineria_urls", "portineria"), namespace="portineria")),

    # Gestione uffici
    path("uffici/", include(("visitors.office_urls", "uffici"), namespace="uffici")),

    # Monitor portineria
    path("monitor/scarica-avvio/", monitor_scarica_avvio, name="monitor_scarica_avvio"),
    path("monitor/pubblico/<str:token>/", monitor_pubblico, name="monitor_pubblico"),
    path("monitor/pubblico/<str:token>/stato-live/", monitor_pubblico_stato_live, name="monitor_pubblico_stato_live"),
    path("monitor/", monitor_home, name="monitor_home"),

    path("monitor/stato-live/", monitor_stato_live, name="monitor_stato_live"),

    # Accesso negato
    path("accesso-negato/", access_denied, name="access_denied"),
]
