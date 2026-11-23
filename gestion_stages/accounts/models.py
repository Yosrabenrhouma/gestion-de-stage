from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("L'e-mail est obligatoire")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)       # mot de passe haché (NF5.6)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", "admin")
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    ROLES = [
        ("etudiant", "Étudiant"), ("encadrant", "Encadrant académique"),
        ("entreprise", "Entreprise / encadrant professionnel"),
        ("responsable", "Responsable des stages"), ("admin", "Administrateur"),
    ]
    username = None
    email = models.EmailField("e-mail", unique=True)
    role = models.CharField(max_length=20, choices=ROLES, default="etudiant")
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    notif_email = models.BooleanField("Recevoir les notifications par e-mail", default=True)  # B8.2

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    @property
    def locked(self):
        return self.failed_attempts >= 5

    def __str__(self):
        return self.get_full_name() or self.email


class Departement(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nom


class Etudiant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="etudiant")
    cin = models.CharField(max_length=8, blank=True)
    niveau = models.CharField(max_length=30, blank=True)
    filiere = models.CharField(max_length=100, blank=True)
    departement = models.ForeignKey(Departement, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return str(self.user)


class Enseignant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="enseignant")
    grade = models.CharField(max_length=50, blank=True)
    departement = models.ForeignKey(Departement, null=True, blank=True, on_delete=models.SET_NULL)
    est_chef = models.BooleanField("Chef de département", default=False)

    def __str__(self):
        return str(self.user)
