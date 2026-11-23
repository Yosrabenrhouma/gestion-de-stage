from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """NF5.1 : chaque utilisateur n'accède qu'aux fonctions de son rôle."""
    def deco(view):
        @wraps(view)
        @login_required
        def wrapper(request, *a, **kw):
            if request.user.role not in roles and request.user.role != "admin":
                raise PermissionDenied
            return view(request, *a, **kw)
        return wrapper
    return deco
