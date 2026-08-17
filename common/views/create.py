from django.views.generic import CreateView


class BaseCreateView(CreateView):

    template_name = "common/form.html"