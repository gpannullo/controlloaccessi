from django.urls import path

from . import views

app_name = "spid_cie"

urlpatterns = [
    path("gateway/identita/", views.gateway_identity, name="gateway_identity"),
    path("gateway/completa/", views.gateway_complete, name="gateway_complete"),
    path("accedi/<str:provider>/", views.login, name="login"),
    path("callback/", views.callback, name="callback"),
    path("esci/", views.logout, name="logout"),
]
