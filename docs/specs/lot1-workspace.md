# Lot 1 — Workspace « Inspection »

## Structure des modules

| Module | Contenu | Créé |
|---|---|---|
| **LSI Inspection** (module de base de l'app) | Workspace « Inspection », graphiques et raccourcis transverses, paramètres généraux | lot 1 |
| Referentiel | Référentiel générique des types (Famille de type, Type), données de configuration partagées | lot 2 |
| Commercial | Opportunité (parcours des phases, suivi), puis chiffrage / EFT, offre | lot 2 |
| Execution | Ordres de mission, équipe, matériel, bons de sortie / retour | plus tard |
| Saisies | Temps, frais, comptes rendus d'intervention | plus tard |
| Pilotage | Rapports, tableaux de bord, alertes de direction | plus tard |

Un module n'est créé que lorsqu'un lot y livre quelque chose. Noms techniques sans accents ; aucun ne reprend un module
d'ERPNext / HRMS.

## Livré

Fichiers standard du module « LSI Inspection » (exportés en mode développeur, synchronisés par `migrate`) :
- `workspace/inspection/inspection.json` — workspace public « Inspection » :
  - carte **Commercial** : Opportunité, Devis, Client, Prospect ;
  - carte **Paramétrage commercial** : Type d'opportunité, Étape de vente, Source, Motif de perte, Département ;
  - raccourcis à compteur : **Mes opportunités ouvertes** (`opportunity_owner = utilisateur connecté`, statut Open) et
    **Opportunités ouvertes** ;
  - graphique **Opportunités ouvertes par phase**.
- `dashboard_chart/opportunites_par_phase/` — Dashboard Chart natif « Group By » sur `sales_stage` (opportunités non
  converties / perdues / fermées). Les phases sont lues dans les données : aucune phase écrite dans le code.

Aucun code Python ni JavaScript : liens natifs uniquement.

## Workspaces : v15 → v16

| v15 | v16 | Comment on reste compatible |
|---|---|---|
| Workspace = doctype `Workspace` (contenu en blocs JSON : en-tête, raccourci, carte, graphique, carte chiffrée) | Le doctype `Workspace` reste ; la barre latérale et l'accueil sont refondus (bureau par application, icônes de bureau, barre latérale de workspace configurable) | Workspace livré en fichier standard du module, blocs **natifs uniquement** (pas de bloc personnalisé, pas de HTML) : il se resynchronise tel quel |
| Barre latérale = liste des workspaces publics | Navigation par application : le workspace doit être rattaché à l'app | Workspace rattaché au module de l'app ; à la migration v16, ajouter si besoin l'entrée d'app (`add_to_apps_screen` / icône de bureau) **dans hooks ou en fichier standard**, jamais à la main |
| Compteurs de raccourcis : `stats_filter` évalué en JavaScript (`frappe.session.user`) | Même mécanisme à vérifier | Filtre simple, testé ; en repli : carte chiffrée native avec filtre dynamique |
| Graphique « Group By » | Inchangé à notre connaissance | Rien à faire |

À revérifier sur une instance v16 avant migration : chargement du workspace, compteurs, graphique (test
`tests/test_workspace.py`).

## Tests

`lsi_inspection/tests/test_workspace.py` : fichier standard (nom générique, module, public), liens vers des doctypes
existants, blocs du contenu tous déclarés, graphique sur la phase native, page chargeable par l'API du bureau.
