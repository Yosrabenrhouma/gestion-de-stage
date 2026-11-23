import csv
import io

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.utils.crypto import get_random_string

from stages.services import audit
from .decorators import role_required
from .forms import CSVImportForm, RoleAuthenticationForm
from .models import Departement, Enseignant, Etudiant, User




class RoleLoginView(LoginView):
    """Page de connexion avec sélection et vérification du profil."""
    authentication_form = RoleAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

@role_required("admin")
def import_csv(request):
    """B1.5 : import en masse de comptes depuis un fichier CSV."""
    form = CSVImportForm(request.POST or None, request.FILES or None)
    rapport = []
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data["fichier"].read().decode("utf-8-sig")
        for i, row in enumerate(csv.DictReader(io.StringIO(data)), start=2):
            email = (row.get("email") or "").strip().lower()
            role = (row.get("role") or "etudiant").strip()
            if not email or role not in dict(User.ROLES):
                rapport.append((i, email, "Ignoré : e-mail ou rôle invalide", ""))
                continue
            if User.objects.filter(email=email).exists():
                rapport.append((i, email, "Ignoré : existe déjà", ""))
                continue
            pwd = get_random_string(12)
            u = User.objects.create_user(email, pwd, first_name=row.get("prenom", ""),
                                         last_name=row.get("nom", ""), role=role)
            dep = None
            if row.get("departement"):
                dep, _ = Departement.objects.get_or_create(nom=row["departement"].strip())
            if role == "etudiant":
                Etudiant.objects.create(user=u, cin=row.get("cin", ""), niveau=row.get("niveau", ""),
                                        filiere=row.get("filiere", ""), departement=dep)
            elif role == "encadrant":
                Enseignant.objects.create(user=u, grade=row.get("grade", ""), departement=dep,
                                          est_chef=(row.get("est_chef", "").strip().lower() in ("1", "oui", "true")))
            rapport.append((i, email, "Créé", pwd))
        audit(request.user, f"Import CSV de {len(rapport)} lignes")
        messages.success(request, "Import terminé. Communiquez les mots de passe initiaux de façon sécurisée.")
    return render(request, "import_csv.html", {"form": form, "rapport": rapport})
