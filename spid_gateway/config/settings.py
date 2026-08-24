import os
from pathlib import Path

from saml2.saml import NAMEID_FORMAT_TRANSIENT
import saml2

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ["SPID_GATEWAY_DJANGO_SECRET_KEY"]
DEBUG = os.getenv("SPID_GATEWAY_DEBUG", "False").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [os.getenv("SPID_GATEWAY_HOST", "prenotazioni.comune.aversa.ce.it")]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "djangosaml2",
    "djangosaml2_spid",
    "gateway",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "djangosaml2.middleware.SamlSessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SPID_BASE_URL = os.getenv("SPID_BASE_URL", "https://prenotazioni.comune.aversa.ce.it")
SPID_URLS_PREFIX = "identita/spid"
SPID_ACS_URL_PATH = f"{SPID_URLS_PREFIX}/acs/"
SPID_SLO_POST_URL_PATH = f"{SPID_URLS_PREFIX}/ls/post/"
SPID_SLO_URL_PATH = f"{SPID_URLS_PREFIX}/ls/"
SPID_METADATA_URL_PATH = f"{SPID_URLS_PREFIX}/metadata/"
SPID_CERTS_DIR = os.getenv("SPID_CERTS_DIR", "/etc/controlloaccessi/spid")
SPID_PUBLIC_CERT = os.getenv("SPID_PUBLIC_CERT", f"{SPID_CERTS_DIR}/public.cert")
SPID_PRIVATE_KEY = os.getenv("SPID_PRIVATE_KEY", f"{SPID_CERTS_DIR}/private.key")
SPID_IDENTITY_PROVIDERS_METADATA_DIR = os.getenv("SPID_IDENTITY_PROVIDERS_METADATA_DIR", str(BASE_DIR / "metadata"))
SPID_VALIDATOR_IDP_ACTIVE = os.getenv("SPID_VALIDATOR_IDP_ACTIVE", "False").lower() in {"1", "true", "yes", "on"}
SPID_VALIDATOR_METADATA_URL = "https://validator.spid.gov.it/metadata.xml"
SPID_AUTH_CONTEXT = "https://www.spid.gov.it/SpidL1"
SPID_NAMEID_FORMAT = NAMEID_FORMAT_TRANSIENT
SAML2_DEFAULT_BINDING = saml2.BINDING_HTTP_POST
SPID_DIG_ALG = saml2.xmldsig.DIGEST_SHA256
SPID_SIG_ALG = saml2.xmldsig.SIG_RSA_SHA256
SPID_CONTACTS = [{"contact_type": "other", "telephone_number": os.getenv("SPID_TECHNICAL_PHONE", ""), "email_address": os.environ["SPID_TECHNICAL_EMAIL"], "IPACode": "c_a512", "Public": ""}]
SAML_CONFIG = {"organization": {"name": [("Comune di Aversa", "it")], "display_name": [("Comune di Aversa", "it")], "url": [("https://www.comune.aversa.ce.it", "it")]}, "debug": DEBUG, "disable_ssl_certificate_validation": False}

SPID_APPLICATION_CALLBACK_URL = os.environ["SPID_APPLICATION_CALLBACK_URL"]
SPID_APPLICATION_COMPLETE_URL = os.environ["SPID_APPLICATION_COMPLETE_URL"]
SPID_GATEWAY_SHARED_SECRET = os.environ["SPID_GATEWAY_SHARED_SECRET"]
