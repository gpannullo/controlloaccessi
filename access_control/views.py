from django.shortcuts import render

from access_control.forms import UfficioForm
from access_control.models import Ufficio
# Create your views here.
from access_control.rbac import has_role
from common.views.create import BaseCreateView
from common.views.list import BaseListView
from common.views.update import BaseUpdateView


def dashboard(request):
    if has_role(request.user, "Dirigenti"):
        return render(request, "dashboard_dirigente.html")

    if has_role(request.user, "Protocollo"):
        return render(request, "dashboard_protocollo.html")

    return render(request, "dashboard_base.html")


class UfficioListView(BaseListView):
    model = Ufficio


class UfficioCreateView(BaseCreateView):
    form_class = UfficioForm


class UfficioUpdateView(BaseUpdateView):
    model = Ufficio
    form_class = UfficioForm
