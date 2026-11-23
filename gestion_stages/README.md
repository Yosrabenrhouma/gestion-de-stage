# Système de gestion des stages (PFA, stage d'été, PFE)

Application web Django réalisée d'après le cahier des charges (MDW32).

## Installation
```bash
python -m venv venv && source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # comptes de démonstration (facultatif)
python manage.py runserver
```
Ouvrir http://127.0.0.1:8000 — comptes démo (mot de passe `Demo12345!`) :
`admin@demo.tn`, `responsable@demo.tn`, `chef@demo.tn`, `encadrant@demo.tn`, `etudiant@demo.tn`, `entreprise@demo.tn`.

Tests : `python manage.py test`
Tâche quotidienne (cron) : `python manage.py envoyer_rappels`

## Production
Variables d'environnement : `DEBUG=0`, `SECRET_KEY`, `ALLOWED_HOSTS`, `DB_ENGINE=postgres` (+ `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`),
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` (+ `EMAIL_HOST`, `EMAIL_PORT`…). Servir derrière HTTPS (gunicorn + nginx).

## Couverture des exigences
| Exigence | Implémentation |
|---|---|
| B1 comptes, rôles, reset, CSV | `accounts/` (User + rôles, `import_csv`, reset via `django.contrib.auth`) |
| B2 entreprises & offres, archivage | `stages/views.py` (`register_entreprise`, `offre_*`, `validations`), `Offre.archiver_expirees` |
| B3 candidatures, sujet propre, validation chef, affectation | `candidature_decide`, `sujet_new/decide`, `stage_gestion` |
| B4 convention PDF, états, ordre de signature, blocage | `Convention.signer`, `Stage.demarrer`, `services.pdf_convention` |
| B5 comptes rendus, messages, rencontres, rappels, retards | `cr_*`, `message_new`, `rencontre_new`, commande `envoyer_rappels` |
| B6 rapport, délai, jury, conflits, évaluations, note, PV/attestation | `rapport_depot`, `SoutenanceForm.clean`, `evaluation`, `Stage.note_finale`, `document` |
| B7 statistiques & export Excel/PDF | `stats` |
| B8 notifications internes + e-mail + préférences | `services.notify`, `notifications_view` |
| NF3.8 fichiers 5 Mo | `validate_upload` |
| NF5.x sécurité | `LockoutBackend` (5 essais), session 30 min, CSRF/XSS/SQL (ORM), HTTPS, journal d'audit |
| Annexes | modèles = entités du cahier des charges (diagramme de classes à produire avec UML) |

## Reste à faire / pistes
- Interface en arabe (RTL) puis anglais : activer `makemessages` + dossier `locale/`.
- Annuaire LDAP (`django-auth-ldap`) en complément de l'import CSV.
- Sauvegarde nocturne : `pg_dump` en cron (NF3.5).


## Connexion par profil
Sur la page de connexion, choisissez votre profil (Étudiant, Enseignant,
Entreprise, Responsable des stages ou Administrateur), puis saisissez votre
e-mail et votre mot de passe. Le système vérifie que le profil choisi correspond
au rôle associé au compte. Aucun changement de base de données n'est nécessaire.
