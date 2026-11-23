from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Departement, Enseignant, Etudiant, User
from .models import Convention, Entreprise, Evaluation, Stage


class Base(TestCase):
    def setUp(self):
        dep = Departement.objects.create(nom="Info")
        self.resp = User.objects.create_user("r@t.tn", "Passw0rd!x", role="responsable")
        self.etu_u = User.objects.create_user("e@t.tn", "Passw0rd!x", role="etudiant")
        self.etu = Etudiant.objects.create(user=self.etu_u, departement=dep)
        self.ent_u = User.objects.create_user("c@t.tn", "Passw0rd!x", role="entreprise")
        self.ent = Entreprise.objects.create(user=self.ent_u, raison_sociale="ACME", etat="validee")
        self.stage = Stage.objects.create(etudiant=self.etu, entreprise=self.ent, sujet="X", type="PFE")
        Convention.objects.create(stage=self.stage)


class RecetteTests(Base):
    def test_B4_4_demarrage_sans_convention_refuse(self):
        with self.assertRaises(ValidationError):
            self.stage.demarrer()

    def test_B4_3_ordre_signature_et_demarrage(self):
        c = self.stage.convention
        c.etat = "en_attente"; c.save()
        with self.assertRaises(ValidationError):
            c.signer("entreprise")                 # pas avant l'étudiant
        for p in ("etudiant", "entreprise", "etablissement"):
            c.signer(p)
        self.assertEqual(c.etat, "signee")
        self.stage.demarrer()
        self.assertEqual(self.stage.etat, "en_cours")

    def test_B6_2_rapport_apres_date_limite_rejete(self):
        self.stage.date_limite_rapport = timezone.localdate() - timedelta(days=1)
        self.stage.save()
        self.client.login(username="e@t.tn", password="Passw0rd!x")
        f = SimpleUploadedFile("r.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("rapport_depot", args=[self.stage.pk]), {"fichier": f})
        self.assertFalse(hasattr(Stage.objects.get(pk=self.stage.pk), "rapport"))
        self.stage.derogation_rapport = True; self.stage.save()
        f = SimpleUploadedFile("r.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("rapport_depot", args=[self.stage.pk]), {"fichier": f})
        self.assertTrue(hasattr(Stage.objects.get(pk=self.stage.pk), "rapport"))

    def test_B6_7_note_finale(self):
        for t, n in (("pro", 16), ("acad", 14), ("jury", 15)):
            Evaluation.objects.create(stage=self.stage, auteur=self.resp, type=t, note=n)
        self.assertEqual(float(self.stage.note_finale()), 15.0)   # .3*16+.3*14+.4*15

    def test_NF5_3_verrouillage_apres_5_echecs(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "e@t.tn", "password": "mauvais"})
        self.assertFalse(self.client.login(username="e@t.tn", password="Passw0rd!x"))

    def test_NF5_2_etudiant_ne_voit_que_ses_dossiers(self):
        autre_u = User.objects.create_user("a@t.tn", "Passw0rd!x", role="etudiant")
        Etudiant.objects.create(user=autre_u)
        self.client.login(username="a@t.tn", password="Passw0rd!x")
        self.assertEqual(self.client.get(reverse("stage_detail", args=[self.stage.pk])).status_code, 404)

    def test_un_stage_par_type_et_par_annee(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stage.objects.create(etudiant=self.etu, entreprise=self.ent, sujet="Y", type="PFE")

    def test_NF5_1_acces_par_role(self):
        self.client.login(username="e@t.tn", password="Passw0rd!x")
        self.assertEqual(self.client.get(reverse("stats")).status_code, 403)
        self.client.logout(); self.client.login(username="r@t.tn", password="Passw0rd!x")
        self.assertEqual(self.client.get(reverse("stats")).status_code, 200)
        self.assertEqual(self.client.get(reverse("stats") + "?export=xlsx").status_code, 200)
        self.assertEqual(self.client.get(reverse("stats") + "?export=pdf").status_code, 200)
