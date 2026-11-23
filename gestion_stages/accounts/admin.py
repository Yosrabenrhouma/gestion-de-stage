from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Departement, Enseignant, Etudiant, User


@admin.action(description="Déverrouiller les comptes")
def unlock(modeladmin, request, qs):
    qs.update(failed_attempts=0)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "failed_attempts")
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "last_name")
    actions = [unlock]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "role", "notif_email", "failed_attempts")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),)


admin.site.register([Departement, Etudiant, Enseignant])
