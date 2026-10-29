from django.urls import path
from . import views

app_name = 'presenze_qr'
urlpatterns = [
    path('', views.personale, name='personale'),
    path('scan/', views.scan, name='scan'),
    path('registra/', views.registra, name='registra'),
    path('<int:pk>/inverti/', views.inverti, name='inverti'),
]
