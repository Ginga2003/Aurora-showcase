from django.http import HttpResponseForbidden


class AdminAccessMiddleware:
    """Return 403 for every non-staff request to the Django admin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        is_admin_path = path == "/admin" or path.startswith("/admin/")
        user = request.user

        if is_admin_path and not (
            user.is_authenticated and user.is_active and user.is_staff
        ):
            return HttpResponseForbidden("Administrator access required.")

        return self.get_response(request)
