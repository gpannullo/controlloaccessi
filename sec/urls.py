from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.generic import CreateView, ListView
from .models import Verbale

urlpatterns = [
    path("verbali/", login_required(ListView.as_view(model=Verbale, template_name="sec/verbali.html", context_object_name="verbali")), name="verbali"),
    path("verbali/nuovo/", login_required(CreateView.as_view(model=Verbale, fields=("comune", "tipologia", "tornata", "numero", "data_verbale", "iscritti_precedenti", "aggiunti", "cancellati", "pdf"), template_name="sec/verbale_form.html", success_url="/sec/verbali/")), name="verbale_nuovo"),
]
