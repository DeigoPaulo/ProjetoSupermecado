from django.shortcuts import render


def csrf_failure(request, reason=""):
    """Mantem a protecao CSRF, mas oferece uma recuperacao segura ao usuario."""
    return render(request, "csrf_failure.html", status=403)
