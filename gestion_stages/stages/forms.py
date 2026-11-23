from django import forms
from django.utils import timezone

from accounts.models import Enseignant
from .models import (Candidature, CompteRendu, Entreprise, Evaluation, Offre, Rapport,
                     Rencontre, Soutenance, Stage)

D = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
DT = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class Bootstrap:
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            cls = "form-select" if isinstance(f.widget, forms.Select) else "form-control"
            if isinstance(f.widget, forms.CheckboxInput):
                cls = "form-check-input"
            f.widget.attrs["class"] = cls


class OffreForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Offre
        fields = ["titre", "description", "technologies", "type", "duree_semaines", "lieu", "date_limite"]
        widgets = {"date_limite": D}

    def clean_date_limite(self):
        d = self.cleaned_data["date_limite"]
        if d < timezone.localdate():
            raise forms.ValidationError("La date limite est dépassée.")
        return d


class CandidatureForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Candidature
        fields = ["cv", "lettre"]


class SujetForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Stage
        fields = ["sujet", "type", "entreprise", "date_debut", "date_fin"]
        widgets = {"date_debut": D, "date_fin": D}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["entreprise"].queryset = Entreprise.objects.filter(etat="validee")


class GestionStageForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Stage
        fields = ["encadrant_acad", "encadrant_pro_nom", "encadrant_pro_email", "date_debut", "date_fin",
                  "date_limite_rapport", "derogation_rapport"]
        widgets = {"date_debut": D, "date_fin": D, "date_limite_rapport": D}


class CompteRenduForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = CompteRendu
        fields = ["periodicite", "contenu"]


class CommentaireForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = CompteRendu
        fields = ["commentaire"]


class RapportForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Rapport
        fields = ["fichier"]


class EvaluationForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = ["criteres", "note", "commentaire"]


class RencontreForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Rencontre
        fields = ["date", "lieu"]
        widgets = {"date": DT}


class SoutenanceForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Soutenance
        fields = ["date", "salle", "jury"]
        widgets = {"date": DT, "jury": forms.SelectMultiple}

    def __init__(self, *a, stage=None, **kw):
        super().__init__(*a, **kw)
        self.stage = stage

    def clean(self):                      # B6.4 : conflits de planning
        data = super().clean()
        date, salle, jury = data.get("date"), data.get("salle"), data.get("jury")
        if not (date and jury):
            return data
        h = timezone.timedelta(hours=1)
        autres = Soutenance.objects.exclude(stage=self.stage).filter(date__gt=date - h, date__lt=date + h)
        for j in jury:
            if autres.filter(jury=j).exists():
                self.add_error("jury", f"Conflit de planning pour {j}.")
        if salle and autres.filter(salle=salle).exists():
            self.add_error("salle", "Cette salle est déjà occupée sur ce créneau.")
        return data


class EntrepriseRegisterForm(Bootstrap, forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Mot de passe")
    raison_sociale = forms.CharField(max_length=150)
    secteur = forms.CharField(max_length=100, required=False)
    adresse = forms.CharField(max_length=255, required=False)
    contact = forms.CharField(max_length=100, required=False)
