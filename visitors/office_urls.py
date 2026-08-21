from django.urls import path

from visitors.office_views import (
    aggiorna_coda_fuori,
    autorizza_salita_visita,
    concludi_visita,
    fai_entrare_prossimo,
    fai_entrare_visitatore,
    selezione_ufficio,
    stato_ufficio_live,
    ufficio_dashboard,
    trasferisci_visitatore,
)


app_name = "uffici"


urlpatterns = [
    path("", selezione_ufficio, name="selezione"),

    path("dettaglio/<int:ufficio_id>/", ufficio_dashboard, name="dashboard"),

    path("dettaglio/<int:ufficio_id>/stato-live/", stato_ufficio_live, name="stato_live"),

    path("dettaglio/<int:ufficio_id>/aggiorna-coda-fuori/", aggiorna_coda_fuori, name="aggiorna_coda_fuori"),

    path("dettaglio/<int:ufficio_id>/fai-entrare/", fai_entrare_prossimo, name="fai_entrare_prossimo"),

    path("dettaglio/<int:ufficio_id>/visite/<int:accesso_id>/autorizza-salita/", autorizza_salita_visita, name="autorizza_salita_visita"),

    path("dettaglio/<int:ufficio_id>/visite/<int:accesso_id>/fai-entrare/", fai_entrare_visitatore, name="fai_entrare_visitatore"),

    path("dettaglio/<int:ufficio_id>/accessi/<int:accesso_id>/concludi/", concludi_visita, name="concludi_visita"),

    path("dettaglio/<int:ufficio_id>/accessi/<int:accesso_id>/trasferisci/", trasferisci_visitatore, name="trasferisci_visitatore"),
]
