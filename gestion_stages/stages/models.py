import os
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import Enseignant, Etudiant

TYPES = [("PFA", "PFA"), ("ETE", "Stage d'été"), ("PFE", "PFE")]


def validate_upload(f):
    """NF3.8 : PDF, DOCX, JPG, PNG – 5 Mo max."""
    if os.path.splitext(f.name)[1].lower() not in settings.ALLOWED_EXT:
        raise ValidationError("Formats acceptés : PDF, DOCX, JPG, PNG.")
    if f.size > settings.MAX_UPLOAD:
        raise ValidationError("Fichier trop volumineux (5 Mo maximum).")


def validate_pdf(f):
    validate_upload(f)
    if not f.name.lower().endswith(".pdf"):
        raise ValidationError("Le rapport doit être au format PDF.")


def annee_courante():
    return timezone.localdate().year


class Entreprise(models.Model):
    ETATS = [("en_attente", "En attente"), ("validee", "Validée"), ("refusee", "Refusée")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entreprise")
    raison_sociale = models.CharField(max_length=150)
    secteur = models.CharField(max_length=100, blank=True)
    adresse = models.CharField(max_length=255, blank=True)
    contact = models.CharField(max_length=100, blank=True)
    etat = models.CharField(max_length=12, choices=ETATS, default="en_attente")

    def __str__(self):
        return self.raison_sociale


class Offre(models.Model):
    ETATS = [("en_attente", "En attente de validation"), ("publiee", "Publiée"),
             ("refusee", "Refusée"), ("archivee", "Archivée")]
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name="offres")
    titre = models.CharField(max_length=200)
    description = models.TextField()
    technologies = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=3, choices=TYPES)
    duree_semaines = models.PositiveSmallIntegerField("durée (semaines)")
    lieu = models.CharField(max_length=100)
    date_limite = models.DateField("date limite de candidature")
    etat = models.CharField(max_length=12, choices=ETATS, default="en_attente")

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.titre

    @classmethod
    def archiver_expirees(cls):          # B2.5
        return cls.objects.filter(etat="publiee", date_limite__lt=timezone.localdate()).update(etat="archivee")


class Stage(models.Model):
    ETATS = [("propose", "Sujet proposé"), ("refuse", "Sujet refusé"), ("valide", "Validé"),
             ("en_cours", "En cours"), ("termine", "Terminé"), ("cloture", "Clôturé")]
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="stages")
    entreprise = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name="stages")
    offre = models.ForeignKey(Offre, null=True, blank=True, on_delete=models.SET_NULL)
    sujet = models.CharField(max_length=255)
    type = models.CharField(max_length=3, choices=TYPES)
    annee = models.PositiveSmallIntegerField(default=annee_courante)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    etat = models.CharField(max_length=10, choices=ETATS, default="valide")
    encadrant_acad = models.ForeignKey(Enseignant, null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="stages_encadres")
    encadrant_pro_nom = models.CharField(max_length=100, blank=True)
    encadrant_pro_email = models.EmailField(blank=True)
    date_limite_rapport = models.DateField(null=True, blank=True)
    derogation_rapport = models.BooleanField("Dérogation de dépôt tardif", default=False)

    class Meta:
        ordering = ["-annee", "-id"]
        constraints = [models.UniqueConstraint(fields=["etudiant", "type", "annee"], name="un_stage_par_type_et_annee")]

    def __str__(self):
        return f"{self.get_type_display()} {self.annee} – {self.etudiant}"

    def demarrer(self):                  # B4.4
        conv = getattr(self, "convention", None)
        if not conv or conv.etat != "signee":
            raise ValidationError("Impossible de démarrer le stage sans convention signée.")
        if self.etat != "valide":
            raise ValidationError("Le stage doit être validé avant de démarrer.")
        self.etat = "en_cours"
        self.save(update_fields=["etat"])

    def depot_rapport_autorise(self):    # B6.2
        if self.derogation_rapport or not self.date_limite_rapport:
            return True
        return timezone.localdate() <= self.date_limite_rapport

    def note_finale(self):               # B6.7
        notes = {e.type: e.note for e in self.evaluations.all()}
        poids = settings.NOTE_WEIGHTS
        if set(poids) - set(notes):
            return None
        return round(sum(Decimal(str(poids[k])) * notes[k] for k in poids), 2)


class Candidature(models.Model):
    ETATS = [("en_attente", "En attente"), ("acceptee", "Acceptée"), ("refusee", "Refusée")]
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="candidatures")
    offre = models.ForeignKey(Offre, on_delete=models.CASCADE, related_name="candidatures")
    date = models.DateTimeField(auto_now_add=True)
    cv = models.FileField(upload_to="cv/", validators=[validate_upload])
    lettre = models.FileField("lettre de motivation", upload_to="lettres/", validators=[validate_upload])
    etat = models.CharField(max_length=12, choices=ETATS, default="en_attente")

    class Meta:
        unique_together = ("etudiant", "offre")
        ordering = ["-date"]


class Convention(models.Model):
    ETATS = [("brouillon", "Brouillon"), ("en_attente", "En attente de signature"),
             ("signee", "Signée"), ("refusee", "Refusée")]
    ORDRE = ["etudiant", "entreprise", "etablissement"]       # B4.3
    stage = models.OneToOneField(Stage, on_delete=models.CASCADE, related_name="convention")
    fichier = models.FileField(upload_to="conventions/", blank=True)
    etat = models.CharField(max_length=12, choices=ETATS, default="brouillon")
    signe_etudiant = models.DateTimeField(null=True, blank=True)
    signe_entreprise = models.DateTimeField(null=True, blank=True)
    signe_etablissement = models.DateTimeField(null=True, blank=True)

    def prochaine_partie(self):
        return next((p for p in self.ORDRE if not getattr(self, "signe_" + p)), None)

    def signer(self, partie):
        if self.etat != "en_attente":
            raise ValidationError("La convention n'est pas en attente de signature.")
        if self.prochaine_partie() != partie:
            raise ValidationError("Ordre de signature : étudiant, entreprise, établissement.")
        setattr(self, "signe_" + partie, timezone.now())
        if self.prochaine_partie() is None:
            self.etat = "signee"
        self.save()


class CompteRendu(models.Model):
    PERIODES = [("hebdo", "Hebdomadaire"), ("mensuel", "Mensuel")]
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="comptes_rendus")
    date = models.DateField(default=timezone.localdate)
    periodicite = models.CharField(max_length=8, choices=PERIODES, default="hebdo")
    contenu = models.TextField()
    commentaire = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]


class Message(models.Model):                                  # B5.3
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="messages")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    contenu = models.TextField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]


class Rencontre(models.Model):                                # B5.4
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="rencontres")
    date = models.DateTimeField()
    lieu = models.CharField(max_length=100, blank=True)
    rappel_envoye = models.BooleanField(default=False)

    class Meta:
        ordering = ["date"]


class Rapport(models.Model):
    stage = models.OneToOneField(Stage, on_delete=models.CASCADE, related_name="rapport")
    fichier = models.FileField(upload_to="rapports/", validators=[validate_pdf])
    date_depot = models.DateTimeField(auto_now_add=True)


class Soutenance(models.Model):
    stage = models.OneToOneField(Stage, on_delete=models.CASCADE, related_name="soutenance")
    date = models.DateTimeField()
    salle = models.CharField(max_length=50)
    jury = models.ManyToManyField(Enseignant, related_name="soutenances")


class Evaluation(models.Model):
    TYPES_EVAL = [("pro", "Encadrant professionnel"), ("acad", "Encadrant académique"), ("jury", "Jury")]
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="evaluations")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    type = models.CharField(max_length=4, choices=TYPES_EVAL)
    criteres = models.TextField("critères d'évaluation", blank=True)
    note = models.DecimalField(max_digits=4, decimal_places=2)
    commentaire = models.TextField(blank=True)

    class Meta:
        unique_together = ("stage", "type")

    def clean(self):
        if self.note is not None and not (0 <= self.note <= 20):
            raise ValidationError({"note": "La note doit être comprise entre 0 et 20."})


class Notification(models.Model):                             # B8.1
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    lu = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]


class JournalAudit(models.Model):                             # NF5.8
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=255)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
