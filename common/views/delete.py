from django.views.generic import DeleteView


class BaseDeleteView(DeleteView):

    template_name = "common/confirm_delete.html"