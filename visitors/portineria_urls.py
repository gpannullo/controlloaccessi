from django.urls import path

from visitors.views import (
    cerca_visitatore,
    chiudi_accesso,
    nuova_registrazione,
    nuovo_ricevimento,
    nuova_visita,
    registrazione_completata,
    ristampa_ticket,
)


app_name = "portineria"


urlpatterns = [
    path(
        "nuovo-ricevimento/",
        nuovo_ricevimento,
        name="nuovo_ricevimento",
    ),

    path(
        "nuova-visita/",
        nuova_visita,
        name="nuova_visita",
    ),

    path(
        "nuova-registrazione/",
        nuova_registrazione,
        name="nuova_registrazione",
    ),

    path(
        "registrazione-completata/<int:pk>/",
        registrazione_completata,
        name="registrazione_completata",
    ),

    path(
        "cerca-visitatore/",
        cerca_visitatore,
        name="cerca_visitatore",
    ),

    path(
        "accessi/<int:pk>/chiudi/",
        chiudi_accesso,
        name="chiudi_accesso",
    ),

    path(
        "accessi/<int:pk>/ristampa-ticket/",
        ristampa_ticket,
        name="ristampa_ticket",
    ),
]