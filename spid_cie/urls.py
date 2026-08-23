from django.urls import path

from . import views

app_name = "spid_cie"

urlpatterns = [
    path("accedi/<str:provider>/", views.login, name="login"),
    path("callback/", views.callback, name="callback"),
    path("esci/", views.logout, name="logout"),
]
