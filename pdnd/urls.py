from django.urls import path

from . import views


app_name = "pdnd"

urlpatterns = [
    path("", views.home, name="home"),
    path("<str:servizio>/", views.interroga, name="interroga"),
]
