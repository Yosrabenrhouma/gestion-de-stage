from django.contrib.auth.backends import ModelBackend
from .models import User


class LockoutBackend(ModelBackend):
    """Verrouille le compte après 5 échecs consécutifs (NF5.3)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get("email", username)
        if not email or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            User().set_password(password)   # temps constant
            return None
        if user.locked:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            if user.failed_attempts:
                user.failed_attempts = 0
                user.save(update_fields=["failed_attempts"])
            return user
        user.failed_attempts += 1
        user.save(update_fields=["failed_attempts"])
        return None
