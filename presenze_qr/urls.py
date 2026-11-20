from django.urls import path
from . import views

app_name = 'presenze_qr'
urlpatterns = [
    path('', views.personale, name='personale'),
    path('scan/', views.scan, name='scan'),
    path('registra/', views.registra, name='registra'),
    path('<int:pk>/inverti/', views.inverti, name='inverti'),
    path('autodichiarazione/<uuid:token>/approva/', views.approva_autodichiarazione, name='approva_autodichiarazione'),
    path('referente/', views.referente_presenze, name='referente'),
    path('referente/utente/<int:pk>/', views.referente_utente, name='referente_utente'),
    path('referente/giustificativo/<int:pk>/', views.gestisci_giustificativo, name='gestisci_giustificativo'),
]
