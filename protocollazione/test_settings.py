SECRET_KEY = 'test-only-not-for-deployment'
INSTALLED_APPS = ['django.contrib.auth','django.contrib.contenttypes','protocollazione','cityware']
DATABASES = {'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
PROTOCOLLAZIONE_ENABLED = True
PROTOCOLLAZIONE_BACKEND = 'cityware.backend.CitywareBackend'
CITYWARE = {'ENDPOINT':'https://example.invalid/soap','USERNAME':'test','PASSWORD':'not-a-real-password','DOMAIN_CODE':'test','UFFICIO_OPERATORE':'0001','FIRMATARIO':'0002','UFFICIO_FIRMATARIO':'0001'}
