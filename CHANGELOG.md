# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Une entrée par lot (branche), les plus récents en haut.

## [Non publié]

### Lot 2 — opportunité (branche lot2-opportunite)
- Modules Referentiel et Commercial ; référentiel générique Famille de Type / Type Metier.
- Opportunité : série OFF-.YYYY.-.####, canal et origine de la demande, workflow « Validation demande d'offre » (motif
  obligatoire contrôlé côté serveur), départements concernés + pilote (fetch_from).
- Phases paramétrables par type d'opportunité (Parcours Phase), événements de fin configurables (Evenement Phase, dont
  « Changement de statut »), phases finales Gagnée / Perdue pilotées par le statut natif, tableau de suivi, historique en
  ajout seul, ToDo natif, notifications par phase (Notification Phase + Email Template natif).
- Notifications natives fixes : nouvelle opportunité, retard de phase (Days After). Tâche quotidienne limitée aux règles
  « Retard » par phase.
- Rôles Validateur demande d'offre, Etude technique, Paramétreur commercial.
- Configuration initiale commun + profil (lsi_profil), chargement en insertion seule, export de profil.
- 47 tests ; spécification et fiche de test `docs/specs/lot2-opportunite.md`.

### Lot 1 — workspace (branche lot1-workspace)
- Workspace standard « Inspection » (module LSI Inspection) : cartes Commercial et Paramétrage commercial (liens natifs),
  raccourcis à compteur « Mes opportunités ouvertes » et « Opportunités ouvertes », graphique « Opportunités ouvertes par phase ».
- Tests du workspace ; spécification `docs/specs/lot1-workspace.md` (structure des modules, points v16).

### Initialisation

### Ajouté
- Squelette de l'application : README (objet, règles), CHANGELOG, `fixtures/`, `tests/` (classe de base v15/v16, tests
  d'installation et de règles), `docs/specs/`.
- Apps requises : ERPNext, HRMS. Compatibilité déclarée : Frappe / ERPNext / HRMS v15 et v16.
