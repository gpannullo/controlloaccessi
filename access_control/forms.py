from common.forms.base import BaseForm

from .models import Ufficio


class UfficioForm(BaseForm):

    class Meta:
        model = Ufficio

        fields = "__all__"