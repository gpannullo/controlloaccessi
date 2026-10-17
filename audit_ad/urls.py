from django.urls import path
from .views import receive
app_name = 'audit_ad'
urlpatterns = [path('events/', receive, name='receive')]
