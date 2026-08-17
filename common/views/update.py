from django.views.generic import UpdateView


class BaseUpdateView(UpdateView):

    template_name = "common/form.html"