from django.views.generic import ListView


class BaseListView(ListView):
    paginate_by = 20

    template_name = "common/list.html"

    context_object_name = "objects"
