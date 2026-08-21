from django.shortcuts import redirect
from django.urls import reverse


class ProfileCompletionMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        user = request.user
        excluded = {reverse("profile_completion"), reverse("logout"), reverse("login"), reverse("initial_password_change")}
        if user.is_authenticated and request.path not in excluded and (not user.email_personale or not user.cellulare_personale):
            return redirect("profile_completion")
        return self.get_response(request)
