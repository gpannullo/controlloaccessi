from django.urls import path

from dashboard.live_views import (
    stato_dashboard_portineria,
)
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
]