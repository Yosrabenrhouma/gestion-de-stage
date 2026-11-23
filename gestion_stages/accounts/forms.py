from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


class RoleAuthenticationForm(AuthenticationForm):
    """Connexion avec choix du profil, conforme aux rôles du diagramme."""

    ROLE_CHOICES = [
        ("etudiant", "Étudiant"),
        ("encadrant", "Enseignant"),
        ("entreprise", "Entreprise"),
        ("responsable", "Responsable des stages"),
        ("admin", "Administrateur"),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        label="Je suis",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        selected_role = cleaned_data.get("role")

        if self.user_cache and selected_role != self.user_cache.role:
            raise ValidationError(
                "Le profil choisi ne correspond pas à ce compte. "
                "Veuillez sélectionner le bon profil.",
                code="role_mismatch",
            )
        return cleaned_data


class CSVImportForm(forms.Form):
    fichier = forms.FileField(help_text="Colonnes : email, nom, prenom, role, cin, niveau, filiere, departement, grade, est_chef")
