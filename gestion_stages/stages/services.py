import io

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import JournalAudit, Notification, Stage


def notify(user, message):
    """B8.1 : notification interne + e-mail (si l'utilisateur l'accepte, B8.2)."""
    if not user:
        return
    Notification.objects.create(user=user, message=message[:255])
    if user.notif_email and user.email:
        send_mail("Gestion des stages", message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


def audit(user, action):
    JournalAudit.objects.create(user=user, action=action[:255])


def stages_visibles(user):
    """NF5.2 : chacun ne voit que ses propres dossiers."""
    qs = Stage.objects.select_related("etudiant__user", "entreprise", "encadrant_acad__user")
    if user.role in ("responsable", "admin"):
        return qs
    if user.role == "etudiant":
        return qs.filter(etudiant__user=user)
    if user.role == "entreprise":
        return qs.filter(entreprise__user=user)
    if user.role == "encadrant":
        return qs.filter(Q(encadrant_acad__user=user) | Q(soutenance__jury__user=user)).distinct()
    return qs.none()


def build_pdf(titre, lignes):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, h = A4
    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, titre)
    y -= 40
    c.setFont("Helvetica", 11)
    for ligne in lignes:
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = h - 60
        c.drawString(50, y, ligne)
        y -= 20
    c.save()
    return buf.getvalue()


def lignes_stage(s):
    return [
        f"Étudiant : {s.etudiant.user} (CIN {s.etudiant.cin})",
        f"Entreprise : {s.entreprise.raison_sociale}",
        f"Sujet : {s.sujet}",
        f"Type : {s.get_type_display()} – année {s.annee}",
        f"Période : {s.date_debut or '?'} au {s.date_fin or '?'}",
        f"Encadrant académique : {s.encadrant_acad or 'non affecté'}",
        f"Encadrant professionnel : {s.encadrant_pro_nom or '-'}",
    ]


def pdf_convention(s):
    return build_pdf("CONVENTION DE STAGE", lignes_stage(s) + [
        "", "Signatures (dans l'ordre) : étudiant, entreprise, établissement."])


def pdf_pv(s):
    so = s.soutenance
    return build_pdf("PROCÈS-VERBAL DE SOUTENANCE", lignes_stage(s) + [
        f"Date : {so.date:%d/%m/%Y %H:%M} – Salle : {so.salle}",
        "Jury : " + ", ".join(str(j) for j in so.jury.all()),
        f"Note finale : {s.note_finale()} / 20"])


def pdf_attestation(s):
    return build_pdf("ATTESTATION DE STAGE", [
        f"Nous attestons que {s.etudiant.user} a effectué un {s.get_type_display()}",
        f"au sein de {s.entreprise.raison_sociale} du {s.date_debut or '?'} au {s.date_fin or '?'}.",
        f"Sujet : {s.sujet}"])
