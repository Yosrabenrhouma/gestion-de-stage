from django.contrib import admin
from . import models

for m in [models.Entreprise, models.Offre, models.Stage, models.Candidature, models.Convention,
          models.CompteRendu, models.Rapport, models.Soutenance, models.Evaluation, models.JournalAudit]:
    admin.site.register(m)
