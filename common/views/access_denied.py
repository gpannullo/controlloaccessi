from django.shortcuts import render


def access_denied(request):
    return render(
        request,
        "common/access_denied.html",
        status=403,
    )