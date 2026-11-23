from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Departement, Enseignant, Etudiant, User
from stages.models import Entreprise, Offre


class Command(BaseCommand):
    help = "Crée des données de démonstration (mot de passe : Demo12345!)"

    def handle(self, *a, **kw):
        pwd = "Demo12345!"
        dep, _ = Departement.objects.get_or_create(nom="Informatique")
        def mk(email, role, prenom, nom, **extra):
            u, created = User.objects.get_or_create(email=email, defaults=dict(role=role, first_name=prenom, last_name=nom, **extra))
            if created:
                u.set_password(pwd); u.save()
            return u
        mk("admin@demo.tn", "admin", "Admin", "Système", is_staff=True, is_superuser=True)
        mk("responsable@demo.tn", "responsable", "Salma", "Responsable")
        Enseignant.objects.get_or_create(user=mk("chef@demo.tn", "encadrant", "Karim", "Chef"), defaults=dict(departement=dep, est_chef=True, grade="MC"))
        Enseignant.objects.get_or_create(user=mk("encadrant@demo.tn", "encadrant", "Nadia", "Encadrante"), defaults=dict(departement=dep, grade="MA"))
        Etudiant.objects.get_or_create(user=mk("etudiant@demo.tn", "etudiant", "Yosra", "Étudiante"), defaults=dict(cin="12345678", niveau="L3", filiere="DSI", departement=dep))
        e = mk("entreprise@demo.tn", "entreprise", "TechCorp", "")
        ent, _ = Entreprise.objects.get_or_create(user=e, defaults=dict(raison_sociale="TechCorp", secteur="IT", adresse="Sfax", contact="M. Tuteur", etat="validee"))
        Offre.objects.get_or_create(entreprise=ent, titre="Application web de gestion", defaults=dict(
            description="Développement Django/React", technologies="Django, PostgreSQL", type="PFE",
            duree_semaines=16, lieu="Sfax", date_limite=timezone.localdate() + timedelta(days=60), etat="publiee"))
        self.stdout.write(self.style.SUCCESS(f"Comptes démo créés (…@demo.tn / {pwd})"))
