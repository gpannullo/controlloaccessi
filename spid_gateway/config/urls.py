from django.urls import include, path

from gateway.urls import urlpatterns as gateway_urlpatterns


urlpatterns = [path("", include((gateway_urlpatterns, "djangosaml2_spid"), namespace="djangosaml2_spid"))]
