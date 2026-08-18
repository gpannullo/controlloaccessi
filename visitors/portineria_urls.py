from django.urls import path

from visitors.views import (
    cerca_visitatore,
    chiudi_accesso,
    libera_badge_rientro,
    nuova_registrazione,
    nuovo_ricevimento,
    nuova_visita,
    registrazione_completata,
    rientro_badge,
    ristampa_ticket,
    amministratori,
    registra_transito_amministratore,
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
    path(
        "rientro-badge/",
        rientro_badge,
        name="rientro_badge",
    ),
    path(
        "rientro-badge/<int:badge_id>/libera/",
        libera_badge_rientro,
        name="libera_badge_rientro",
    ),
    path(
        "amministratori/",
        amministratori,
        name="amministratori",
    ),
    path(
        "amministratori/<int:pk>/transito/",
        registra_transito_amministratore,
        name="registra_transito_amministratore",
    ),
]
