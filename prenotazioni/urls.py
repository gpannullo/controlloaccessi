from django.urls import path

from . import views

app_name = "prenotazioni"

urlpatterns = [
    path("", views.wizard, name="wizard"),
    path("slot-disponibili/", views.slot_disponibili_json, name="slot_disponibili"),
    path("conferma/<str:codice>/", views.conferma, name="conferma"),
]
