# Conventions de développement

## Langue et nommage
- **Français partout** (modules, fonctions, variables, champs, messages) ; l'anglais seulement là où Frappe / ERPNext l'impose
  (hooks, méthodes des contrôleurs, champs natifs).
- Champs ajoutés aux doctypes natifs : préfixe **`lsi_`** (Custom Field en fixture). Champs des doctypes de l'app : sans préfixe.
- Fonctions publiques : verbe ou nom explicite (`creer_devis`, `nouvelle_variante`, `apres_changement`) ; fonctions internes au
  module : préfixe `_`.
- Doctypes de l'app : noms français sans accent (`Chiffrage`, `Modele Chiffrage`, `Evenement Phase`).

## Règles du code
- **Aucune valeur métier d'un client dans le code** : listes, libellés, phases, destinataires → profil (`config_initiale/profils`).
- **Chaînes comparées dans le code** (statuts, modes, sources, états de workflow) : une seule définition dans `constants.py`.
- **Natif d'abord** : Notification, Workflow, Connexions, renommage, amend, statuts ERPNext ; jamais d'écriture dans un champ
  calculé par ERPNext.
- **Pas de SQL brut** quand l'API suffit : `frappe.get_all`, `frappe.db.get_value`, `frappe.qb`.
- **Taille** : fichier Python ≤ 400 lignes, fonction ≤ 50 lignes ; au-delà, découper.
- **Docstring courte** sur chaque fonction publique (ce qu'elle fait, entrées, sortie) ; commentaires seulement pour le *pourquoi*.
- **Calcul pur** (sans base) dans des fonctions isolées et testées seules (`chiffrage/moteur/formules.py`, `variantes.lettre_suivante`).
- **Jamais d'exception sur un coût** : un coût introuvable = « coût manquant » avec sa raison (`source_cout`).
- JS : un fichier par doctype, utilitaires partagés dans `public/js/commun/`, aucun calcul métier dans le navigateur.

## Structure et configuration
- Structure (champs, workflows, rôles, droits, formats) : **fixtures filtrées** (`hooks.py`) ou fichiers standard des doctypes.
- Configuration : **profil**, chargé en **insertion seule** à chaque migrate (`config.charger`), exportable
  (`config.exporter_profil`). Une modification à l'écran n'est jamais écrasée. Un changement de définition livré par l'app sur
  l'existant passe par un **patch** (`config/alignement.py`).
- Migration de données : **patch** (`patches.txt`) idempotent, comptes contrôlés avant / après, sauvegarde avant le migrate.

## Tests
- Commande (**toujours** ces options : sans elles, les préparations d'ERPNext et de HRMS modifient le site) :
  ```
  bench --site <site> run-tests --app lsi_inspection --skip-test-records --skip-before-tests
  bench --site <site> run-tests --app lsi_inspection --skip-test-records --skip-before-tests --module lsi_inspection.tests.test_variantes
  ```
- Un fichier de tests par module : `test_formules` (pur), `test_couts`, `test_organisation`, `test_gammes_modeles`, `test_chiffrage`,
  `test_devis`, `test_variantes`, `test_etude`, `test_phases`, `test_reouverture`, `test_ecran`, `test_notifications`,
  `test_validation`, `test_config`, `test_workspace`, `test_retours`, `test_ouverture`.
- Base des tests avec données : `tests/contexte.TestLot2` (transaction annulée, **commit interdit**, **aucun envoi SMTP**,
  `frappe.log_error` neutralisé, contrôle automatique en fin de test : utilisateurs, files d'e-mails, notifications, opportunités,
  retours) et `tests/chiffrage_contexte.TestChiffrageBase` (configuration et exemple du chiffrage construits par le test, aucune
  dépendance au profil du site, préfixe `LSI-T`).
- Contrôle statique : `pyflakes` (hors projet) ; aucun avertissement attendu en dehors des façades `__init__.py`.

## Git
- Une branche par lot, un commit par étape, rien dans `main` sans accord. Message : « Lot X, étape N — résumé » puis le détail.
