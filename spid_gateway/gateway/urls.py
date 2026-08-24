from django.conf import settings
from django.urls import path
from djangosaml2_spid import views as spid_views

from .views import GatewayAssertionConsumerServiceView


urlpatterns = [
    path(f"{settings.SPID_URLS_PREFIX}/login/", spid_views.spid_login, name="spid_login"),
    path(settings.SPID_METADATA_URL_PATH, spid_views.MetadataSpidView.as_view(), name="spid_metadata"),
    path(settings.SPID_ACS_URL_PATH, GatewayAssertionConsumerServiceView.as_view(), name="saml2_acs"),
    path(settings.SPID_SLO_URL_PATH, spid_views.LogoutView.as_view(), name="saml2_ls"),
    path(settings.SPID_SLO_POST_URL_PATH, spid_views.LogoutView.as_view(), name="saml2_ls_post"),
]
