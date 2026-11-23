from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from stages.models import Offre, Rencontre, Stage
from stages.services import notify


class Command(BaseCommand):
    help = "À planifier chaque jour (cron) : rappels de rencontres, comptes rendus en retard, archivage des offres."

    def handle(self, *a, **kw):
        now = timezone.now()
        for r in Rencontre.objects.filter(rappel_envoye=False, date__lte=now + timedelta(hours=24), date__gte=now):
            notify(r.stage.etudiant.user, f"Rappel : rencontre le {r.date:%d/%m %H:%M}")        # B5.4
            if r.stage.encadrant_acad:
                notify(r.stage.encadrant_acad.user, f"Rappel : rencontre avec {r.stage.etudiant}")
            r.rappel_envoye = True
            r.save()
        seuil = timezone.localdate() - timedelta(days=settings.JOURS_ALERTE_CR)
        for s in Stage.objects.filter(etat="en_cours", encadrant_acad__isnull=False):            # B5.5
            dernier = s.comptes_rendus.first()
            if (dernier is None and s.date_debut and s.date_debut < seuil) or (dernier and dernier.date < seuil):
                notify(s.encadrant_acad.user, f"Compte rendu en retard : {s.etudiant}")
        self.stdout.write(f"{Offre.archiver_expirees()} offre(s) archivée(s)")                  # B2.5
