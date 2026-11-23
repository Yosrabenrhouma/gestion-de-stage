import io
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import Etudiant, User
from . import forms as F
from .models import (Candidature, CompteRendu, Convention, Entreprise, Evaluation, JournalAudit,
                     Message, Notification, Offre, Rapport, Rencontre, Soutenance, Stage)
from .services import (audit, notify, pdf_attestation, pdf_convention, pdf_pv,
                       stages_visibles)

ACTIFS = ["valide", "en_cours", "termine", "cloture"]


def is_chef(u):
    return u.role == "admin" or (u.role == "encadrant" and hasattr(u, "enseignant") and u.enseignant.est_chef)


def get_stage(request, pk):
    return get_object_or_404(stages_visibles(request.user), pk=pk)


# ---------- Authentification / entreprises (B1, B2.1) ----------
def register_entreprise(request):
    form = F.EntrepriseRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        if User.objects.filter(email__iexact=d["email"]).exists():
            form.add_error("email", "Un compte existe déjà avec cet e-mail.")
        else:
            u = User.objects.create_user(d["email"], d["password"], role="entreprise", first_name=d["raison_sociale"])
            Entreprise.objects.create(user=u, raison_sociale=d["raison_sociale"], secteur=d["secteur"],
                                      adresse=d["adresse"], contact=d["contact"])
            for r in User.objects.filter(role="responsable"):
                notify(r, f"Nouvelle entreprise à valider : {d['raison_sociale']}")
            messages.success(request, "Compte créé. Il sera actif après validation par le responsable des stages.")
            return redirect("login")
    return render(request, "form.html", {"form": form, "titre": "Inscription d'une entreprise"})


@login_required
def dashboard(request):
    u = request.user
    ctx = {"stages": stages_visibles(u)[:10]}
    if u.role == "responsable" or u.role == "admin":
        ctx["a_valider"] = Offre.objects.filter(etat="en_attente").count() + Entreprise.objects.filter(etat="en_attente").count()
        ctx["sans_convention"] = Stage.objects.filter(etat="valide").exclude(convention__etat="signee").count()
    if u.role == "etudiant" and hasattr(u, "etudiant"):
        ctx["candidatures"] = u.etudiant.candidatures.select_related("offre")[:5]
    if is_chef(u):
        ctx["nb_sujets"] = Stage.objects.filter(etat="propose").count()
    return render(request, "dashboard.html", ctx)


# ---------- Offres (B2) ----------
@login_required
def offres(request):
    Offre.archiver_expirees()
    qs = Offre.objects.filter(etat="publiee").select_related("entreprise")
    g = request.GET
    if g.get("type"):
        qs = qs.filter(type=g["type"])
    if g.get("duree"):
        qs = qs.filter(duree_semaines__lte=g["duree"])
    if g.get("domaine"):
        qs = qs.filter(technologies__icontains=g["domaine"]) | qs.filter(titre__icontains=g["domaine"])
    if g.get("lieu"):
        qs = qs.filter(lieu__icontains=g["lieu"])
    return render(request, "offres.html", {"offres": qs, "g": g})


@role_required("entreprise")
def offre_new(request):
    ent = get_object_or_404(Entreprise, user=request.user)
    if ent.etat != "validee":
        raise PermissionDenied
    form = F.OffreForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        o = form.save(commit=False)
        o.entreprise = ent
        o.save()
        for r in User.objects.filter(role="responsable"):
            notify(r, f"Nouvelle offre à valider : {o.titre}")
        messages.success(request, "Offre soumise à validation.")
        return redirect("offres")
    return render(request, "form.html", {"form": form, "titre": "Publier une offre"})


@login_required
def offre_detail(request, pk):
    o = get_object_or_404(Offre, pk=pk)
    if o.etat != "publiee" and request.user.role not in ("responsable", "admin") and o.entreprise.user != request.user:
        raise PermissionDenied
    form = None
    if request.user.role == "etudiant" and o.etat == "publiee":
        form = F.CandidatureForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            et = request.user.etudiant
            if Candidature.objects.filter(etudiant=et, offre=o).exists():
                messages.error(request, "Vous avez déjà postulé à cette offre.")
            else:
                c = form.save(commit=False)
                c.etudiant, c.offre = et, o
                c.save()
                notify(o.entreprise.user, f"Nouvelle candidature pour « {o.titre} »")
                messages.success(request, "Candidature envoyée.")
                return redirect("candidatures")
    return render(request, "offre_detail.html", {"o": o, "form": form})


@role_required("responsable")
def validations(request):
    return render(request, "validations.html", {
        "entreprises": Entreprise.objects.filter(etat="en_attente"),
        "offres": Offre.objects.filter(etat="en_attente").select_related("entreprise"),
        "conventions": Convention.objects.filter(etat="en_attente").select_related("stage__etudiant__user"),
    })


@role_required("responsable")
def entreprise_decide(request, pk, decision):
    e = get_object_or_404(Entreprise, pk=pk)
    if request.method == "POST":
        e.etat = "validee" if decision == "valider" else "refusee"
        e.save()
        audit(request.user, f"Entreprise {e} : {e.etat}")
        notify(e.user, f"Votre compte entreprise a été {e.get_etat_display().lower()}.")
    return redirect("validations")


@role_required("responsable")
def offre_decide(request, pk, decision):
    o = get_object_or_404(Offre, pk=pk)
    if request.method == "POST":
        o.etat = "publiee" if decision == "valider" else "refusee"
        o.save()
        audit(request.user, f"Offre {o.titre} : {o.etat}")
        notify(o.entreprise.user, f"Votre offre « {o.titre} » est {o.get_etat_display().lower()}.")
    return redirect("validations")


# ---------- Candidatures et sujets (B3) ----------
@role_required("etudiant", "entreprise")
def candidatures(request):
    if request.user.role == "etudiant":
        qs = Candidature.objects.filter(etudiant__user=request.user)
    else:
        qs = Candidature.objects.filter(offre__entreprise__user=request.user)
    return render(request, "candidatures.html", {"cands": qs.select_related("offre", "etudiant__user")})


@role_required("entreprise")
def candidature_decide(request, pk, decision):
    c = get_object_or_404(Candidature, pk=pk, offre__entreprise__user=request.user)
    if request.method == "POST":
        if decision == "accepter":
            if Stage.objects.filter(etudiant=c.etudiant, type=c.offre.type, annee=timezone.localdate().year).exists():
                messages.error(request, "Cet étudiant a déjà un stage de ce type cette année.")
                return redirect("candidatures")
            c.etat = "acceptee"
            s = Stage.objects.create(etudiant=c.etudiant, entreprise=c.offre.entreprise, offre=c.offre,
                                     sujet=c.offre.titre, type=c.offre.type, etat="valide",
                                     encadrant_pro_nom=c.offre.entreprise.contact)
            Convention.objects.create(stage=s)
            for r in User.objects.filter(role="responsable"):
                notify(r, f"Stage à affecter à un encadrant : {s}")
        else:
            c.etat = "refusee"
        c.save()
        notify(c.etudiant.user, f"Votre candidature « {c.offre.titre} » est {c.get_etat_display().lower()}.")  # B3.3
    return redirect("candidatures")


@role_required("etudiant")
def sujet_new(request):
    form = F.SujetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        s.etudiant, s.etat = request.user.etudiant, "propose"
        if Stage.objects.filter(etudiant=s.etudiant, type=s.type, annee=s.annee).exists():
            form.add_error("type", "Vous avez déjà un stage de ce type pour cette année.")
        else:
            s.save()
            for u in User.objects.filter(enseignant__est_chef=True):
                notify(u, f"Nouveau sujet proposé : {s.sujet}")
            messages.success(request, "Sujet proposé au chef de département.")
            return redirect("stages")
    return render(request, "form.html", {"form": form, "titre": "Proposer mon sujet de stage"})


@login_required
def sujets(request):
    if not is_chef(request.user):
        raise PermissionDenied
    qs = Stage.objects.filter(etat="propose").select_related("etudiant__user", "entreprise")
    if request.user.role != "admin":
        qs = qs.filter(etudiant__departement=request.user.enseignant.departement)
    return render(request, "sujets.html", {"sujets": qs})


@login_required
def sujet_decide(request, pk, decision):
    if not is_chef(request.user):
        raise PermissionDenied
    s = get_object_or_404(Stage, pk=pk, etat="propose")
    if request.method == "POST":
        s.etat = "valide" if decision == "valider" else "refuse"
        s.save()
        if s.etat == "valide":
            Convention.objects.get_or_create(stage=s)
        audit(request.user, f"Sujet {s.sujet} : {s.etat}")
        notify(s.etudiant.user, f"Votre sujet « {s.sujet} » est {s.get_etat_display().lower()}.")
    return redirect("sujets")


# ---------- Stages (B3.6, B4, B5, B6) ----------
@login_required
def stages(request):
    qs = stages_visibles(request.user)
    if request.GET.get("etat"):
        qs = qs.filter(etat=request.GET["etat"])
    return render(request, "stages.html", {"stages": qs, "etats": Stage.ETATS})


@login_required
def stage_detail(request, pk):
    s = get_stage(request, pk)
    u = request.user
    conv = getattr(s, "convention", None)
    partie = {"etudiant": "etudiant", "entreprise": "entreprise", "responsable": "etablissement"}.get(u.role)
    types = []
    if u.role == "entreprise":
        types = ["pro"]
    elif u.role == "encadrant":
        if s.encadrant_acad and s.encadrant_acad.user == u:
            types.append("acad")
        if hasattr(s, "soutenance") and s.soutenance.jury.filter(user=u).exists():
            types.append("jury")
    ctx = {
        "s": s, "conv": conv, "note": s.note_finale(),
        "peut_signer": bool(conv and conv.etat == "en_attente" and partie and conv.prochaine_partie() == partie),
        "eval_types": types,
        "cr_form": F.CompteRenduForm(), "rapport_form": F.RapportForm(), "rdv_form": F.RencontreForm(),
        "evals": s.evaluations.all(),
    }
    return render(request, "stage_detail.html", ctx)


@role_required("responsable")
def stage_gestion(request, pk):
    s = get_stage(request, pk)
    form = F.GestionStageForm(request.POST or None, instance=s)
    if request.method == "POST" and form.is_valid():
        form.save()
        if s.encadrant_acad:
            notify(s.encadrant_acad.user, f"Vous encadrez : {s}")
        notify(s.etudiant.user, f"Votre stage a été mis à jour ({s.encadrant_acad or 'encadrant à venir'}).")
        return redirect("stage_detail", pk=s.pk)
    return render(request, "form.html", {"form": form, "titre": f"Affectation et paramètres – {s}"})


@role_required("responsable")
def stage_demarrer(request, pk):
    s = get_stage(request, pk)
    if request.method == "POST":
        try:
            s.demarrer()
            notify(s.etudiant.user, "Votre stage a démarré.")
        except ValidationError as e:
            messages.error(request, e.messages[0])
    return redirect("stage_detail", pk=pk)


@login_required
def convention_pdf(request, pk):
    s = get_stage(request, pk)
    conv = get_object_or_404(Convention, stage=s)
    if request.method == "POST" and request.user.role in ("responsable", "admin") and conv.etat == "brouillon":
        from django.core.files.base import ContentFile
        conv.fichier.save(f"convention_{s.pk}.pdf", ContentFile(pdf_convention(s)), save=False)
        conv.etat = "en_attente"
        conv.save()
        notify(s.etudiant.user, "La convention est prête : veuillez la signer.")
        return redirect("stage_detail", pk=pk)
    return HttpResponse(pdf_convention(s), content_type="application/pdf")


@login_required
def convention_action(request, pk, action):
    s = get_stage(request, pk)
    conv = get_object_or_404(Convention, stage=s)
    partie = {"etudiant": "etudiant", "entreprise": "entreprise", "responsable": "etablissement"}.get(request.user.role)
    if request.method == "POST" and partie:
        try:
            if action == "signer":
                conv.signer(partie)
                audit(request.user, f"Convention {s.pk} signée par {partie}")
                suivant = conv.prochaine_partie()
                if suivant == "entreprise":
                    notify(s.entreprise.user, f"Convention à signer : {s}")
                elif suivant == "etablissement":
                    for r in User.objects.filter(role="responsable"):
                        notify(r, f"Convention à signer : {s}")
                elif conv.etat == "signee":
                    notify(s.etudiant.user, "Convention signée par toutes les parties.")
            elif action == "refuser" and conv.etat == "en_attente":
                conv.etat = "refusee"
                conv.save()
                audit(request.user, f"Convention {s.pk} refusée par {partie}")
                notify(s.etudiant.user, "La convention a été refusée.")
        except ValidationError as e:
            messages.error(request, e.messages[0])
    return redirect("stage_detail", pk=pk)


@role_required("etudiant")
def cr_new(request, pk):
    s = get_stage(request, pk)
    form = F.CompteRenduForm(request.POST)
    if request.method == "POST" and form.is_valid() and s.etat == "en_cours":
        c = form.save(commit=False)
        c.stage = s
        c.save()
        if s.encadrant_acad:
            notify(s.encadrant_acad.user, f"Nouveau compte rendu de {s.etudiant}")
    return redirect("stage_detail", pk=pk)


@role_required("encadrant")
def cr_comment(request, pk):
    c = get_object_or_404(CompteRendu, pk=pk, stage__encadrant_acad__user=request.user)
    form = F.CommentaireForm(request.POST, instance=c)
    if request.method == "POST" and form.is_valid():
        form.save()
        notify(c.stage.etudiant.user, "Votre encadrant a commenté un compte rendu.")
    return redirect("stage_detail", pk=c.stage_id)


@login_required
def message_new(request, pk):
    s = get_stage(request, pk)
    txt = request.POST.get("contenu", "").strip()
    if request.method == "POST" and txt:
        Message.objects.create(stage=s, auteur=request.user, contenu=txt)
        dests = {s.etudiant.user, s.entreprise.user}
        if s.encadrant_acad:
            dests.add(s.encadrant_acad.user)
        for d in dests - {request.user}:
            notify(d, f"Nouveau message sur le stage {s}")
    return redirect("stage_detail", pk=pk)


@role_required("encadrant", "responsable")
def rencontre_new(request, pk):
    s = get_stage(request, pk)
    form = F.RencontreForm(request.POST)
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.stage = s
        r.save()
        notify(s.etudiant.user, f"Rencontre de suivi le {r.date:%d/%m/%Y à %H:%M}")
    return redirect("stage_detail", pk=pk)


@role_required("etudiant")
def rapport_depot(request, pk):
    s = get_stage(request, pk)
    if request.method == "POST":
        if not s.depot_rapport_autorise():      # B6.2
            messages.error(request, "La date limite de dépôt est dépassée (dérogation requise).")
            return redirect("stage_detail", pk=pk)
        form = F.RapportForm(request.POST, request.FILES, instance=getattr(s, "rapport", None))
        if form.is_valid():
            r = form.save(commit=False)
            r.stage = s
            r.save()
            messages.success(request, "Rapport déposé.")
            if s.encadrant_acad:
                notify(s.encadrant_acad.user, f"Rapport déposé par {s.etudiant}")
        else:
            messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return redirect("stage_detail", pk=pk)


@role_required("responsable")
def soutenance(request, pk):
    s = get_stage(request, pk)
    form = F.SoutenanceForm(request.POST or None, instance=getattr(s, "soutenance", None), stage=s)
    if request.method == "POST" and form.is_valid():
        so = form.save(commit=False)
        so.stage = s
        so.save()
        form.save_m2m()
        for j in so.jury.all():
            notify(j.user, f"Soutenance le {so.date:%d/%m/%Y %H:%M} en salle {so.salle} ({s})")
        notify(s.etudiant.user, f"Votre soutenance : {so.date:%d/%m/%Y %H:%M}, salle {so.salle}")
        return redirect("stage_detail", pk=pk)
    return render(request, "form.html", {"form": form, "titre": f"Planifier la soutenance – {s}"})


@role_required("entreprise", "encadrant")
def evaluation(request, pk):
    s = get_stage(request, pk)
    u = request.user
    allowed = ["pro"] if u.role == "entreprise" else []
    if u.role == "encadrant":
        if s.encadrant_acad and s.encadrant_acad.user == u:
            allowed.append("acad")
        if hasattr(s, "soutenance") and s.soutenance.jury.filter(user=u).exists():
            allowed.append("jury")
    t = request.GET.get("t") or (allowed[0] if allowed else None)
    if t not in allowed:
        raise PermissionDenied
    inst = Evaluation.objects.filter(stage=s, type=t).first()
    form = F.EvaluationForm(request.POST or None, instance=inst)
    if request.method == "POST" and form.is_valid():
        e = form.save(commit=False)
        e.stage, e.type, e.auteur = s, t, u
        e.save()
        audit(u, f"Note {t} {'modifiée' if inst else 'saisie'} pour stage {s.pk}: {e.note}")  # NF5.8
        if s.note_finale() is not None and s.etat == "en_cours":
            s.etat = "termine"
            s.save(update_fields=["etat"])
        return redirect("stage_detail", pk=pk)
    return render(request, "form.html", {"form": form, "titre": f"Évaluation ({dict(Evaluation.TYPES_EVAL)[t]}) – {s}"})


@role_required("responsable", "encadrant")
def document(request, pk, kind):                 # B6.8
    s = get_stage(request, pk)
    if kind == "pv":
        if not hasattr(s, "soutenance") or s.note_finale() is None:
            messages.error(request, "Soutenance et trois notes requises pour générer le PV.")
            return redirect("stage_detail", pk=pk)
        data = pdf_pv(s)
    else:
        data = pdf_attestation(s)
        if s.etat == "termine" and request.user.role == "responsable":
            s.etat = "cloture"
            s.save(update_fields=["etat"])
    return HttpResponse(data, content_type="application/pdf")


# ---------- Statistiques (B7) ----------
@role_required("responsable")
def stats(request):
    par_etat = Stage.objects.values("etat").annotate(n=Count("id")).order_by("etat")
    par_dept = Stage.objects.values("etudiant__departement__nom").annotate(n=Count("id"))
    par_ent = Stage.objects.values("entreprise__raison_sociale").annotate(n=Count("id")).order_by("-n")
    par_periode = Stage.objects.values("annee", "type").annotate(n=Count("id")).order_by("-annee")
    sans = Etudiant.objects.exclude(stages__etat__in=ACTIFS).select_related("user", "departement")
    fmt = request.GET.get("export")
    if fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Stages"
        ws.append(["Étudiant", "Entreprise", "Type", "Année", "État", "Encadrant", "Note finale"])
        for s in Stage.objects.select_related("etudiant__user", "entreprise", "encadrant_acad__user"):
            ws.append([str(s.etudiant), s.entreprise.raison_sociale, s.type, s.annee, s.get_etat_display(),
                       str(s.encadrant_acad or ""), float(s.note_finale() or 0)])
        ws2 = wb.create_sheet("Sans stage")
        ws2.append(["Étudiant", "Département"])
        for e in sans:
            ws2.append([str(e), str(e.departement or "")])
        buf = io.BytesIO()
        wb.save(buf)
        r = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r["Content-Disposition"] = 'attachment; filename="stats_stages.xlsx"'
        return r
    if fmt == "pdf":
        from .services import build_pdf
        lignes = ["Stages par état :"] + [f"  {x['etat']} : {x['n']}" for x in par_etat]
        lignes += ["Stages par entreprise :"] + [f"  {x['entreprise__raison_sociale']} : {x['n']}" for x in par_ent]
        lignes += ["Étudiants sans stage :"] + [f"  {e}" for e in sans]
        return HttpResponse(build_pdf("STATISTIQUES DES STAGES", lignes), content_type="application/pdf")
    return render(request, "stats.html", {"par_etat": par_etat, "par_dept": par_dept, "par_ent": par_ent,
                                          "par_periode": par_periode, "sans": sans})


# ---------- Notifications (B8) ----------
@login_required
def notifications_view(request):
    if request.method == "POST":
        request.user.notif_email = "notif_email" in request.POST     # B8.2
        request.user.save(update_fields=["notif_email"])
        request.user.notifications.update(lu=True)
        return redirect("notifications")
    items = list(request.user.notifications.all()[:50])
    return render(request, "notifications.html", {"items": items})


@role_required("admin")
def journal(request):
    return render(request, "journal.html", {"logs": JournalAudit.objects.select_related("user")[:200]})
