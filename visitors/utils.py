from django.urls import path

from visitors.views import nuova_registrazione


app_name = "visitors"


urlpatterns = [
    path(
        "nuova-registrazione/",
        nuova_registrazione,
        name="nuova_registrazione",
    ),
]