from django.views.generic import DetailView


class BaseDetailView(DetailView):

    template_name = "common/detail.html"