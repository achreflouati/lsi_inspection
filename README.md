# LSI Inspection

Application Frappe pour une société d'**inspection, essais et contrôle (TIC)**, construite sur **ERPNext** et **Frappe HR**
(notes de frais, avances, déplacements, compétences).

- Site : `tic.erpsys.ovh` (seul site où l'app est installée)
- Apps requises : `erpnext`, `hrms`
- Compatibilité visée : **Frappe / ERPNext / HRMS v15 et v16**

## Objet

Couvrir le métier TIC (opportunités et offres, chiffrage, missions d'inspection, ordres de mission, habilitations des
inspecteurs, temps passés, facturation, pilotage) en **s'appuyant d'abord sur ERPNext** et en n'ajoutant que ce qui manque.
Le paramétrage propre à la société TIC (listes de prestations, tarifs, phases, rôles, modèles…) relève de la
**configuration**, pas du code.

## Règles du projet

1. **Natif d'abord.** On utilise les objets et mécanismes standard d'ERPNext / HRMS (doctypes, workflows, champs
   personnalisés, formats d'impression, rapports, espaces de travail, notifications). Du code n'est ajouté que si le natif ne
   suffit pas, et la spécification du lot dit pourquoi.
2. **Configuration plutôt que code en dur.** Aucune valeur métier TIC dans le code : pas de nom de société, de prestation,
   d'article, de tarif, de phase, de rôle, de compte ni de centre de coût écrit en dur. Ces valeurs vivent dans des
   paramètres (doctype de réglages, champs de configuration) modifiables à l'écran.
3. **Tout est livré par fixtures.** Champs personnalisés, Property Setters, workflows, rôles, formats d'impression, rapports,
   espaces de travail… sont exportés dans `lsi_inspection/fixtures/`, **toujours avec un filtre** (jamais un doctype entier).
   Rien n'est paramétré à la main sur un site sans être ramené en fixture.
4. **Jamais d'écriture directe dans les champs calculés.** Totaux, montants, statuts, soldes, quantités facturées ou livrées :
   on passe par les méthodes et documents ERPNext (`save`, `submit`, documents liés), jamais par `db_set` /
   `frappe.db.set_value` / SQL sur ces champs.
5. **Compatibilité v15 et v16** (voir les points d'attention ci-dessous).
6. **Sauvegarde avant chaque migration** :
   `bench --site tic.erpsys.ovh backup --with-files` avant tout `migrate`, toute installation ou tout patch.
7. **Une branche par lot** (`lotNN-<sujet>`), créée depuis `main` ; fusion dans `main` uniquement après validation.
8. **Un commit par étape**, message explicite ; push après chaque étape.
9. **Tests automatiques.** Chaque lot livre ses tests dans `lsi_inspection/tests/` ; la suite complète passe avant chaque
   fusion. Les tests n'écrivent rien de durable (transaction annulée, pas de `commit`).
10. **Rien n'est supprimé.** Pas de suppression de données ni de documents : on annule, on désactive ou on archive. Tout patch
    de données est **réversible** (fonction d'annulation) et présenté pour validation avant application s'il touche plus de
    20 enregistrements.

Autres conventions : noms techniques sans accents (snake_case), libellés en français ; données de démonstration préfixées
« DÉMO » et fournies avec une fonction d'annulation ; une spécification par lot dans `docs/specs/`, validée avant le code.

## Compatibilité v15 / v16 — points d'attention

À revérifier à la sortie de chaque version majeure.

| Sujet | Point d'attention | Règle dans l'app |
|---|---|---|
| Python / Node | v16 exige des versions plus récentes (Python ≥ 3.14, Node ≥ 24) | Code Python sans syntaxe ni module retirés ; pas de dépendance JS lourde |
| Classe de base des tests | `FrappeTestCase` (v15) → `IntegrationTestCase` / `UnitTestCase` (v16) | Toujours importer depuis `lsi_inspection.tests.compat` |
| Surcharge de classes | `override_doctype_class` casse quand ERPNext change ses classes | Préférer `doc_events` ; une surcharge doit être justifiée dans la spec |
| API internes | Fonctions privées (`_xxx`) et chemins internes d'ERPNext changent sans préavis | N'appeler que des API publiques / whitelistées |
| SQL brut | Noms de colonnes et index des tables ERPNext évoluent | `frappe.get_all` / `frappe.qb` ; pas de SQL brut sur les tables d'ERPNext |
| Espaces de travail / barre latérale | Interface de bureau revue en v16 | Espaces de travail simples, livrés en fixtures |
| JavaScript de formulaire | `cur_frm` et API globales dépréciées | Utiliser `frm` dans `frappe.ui.form.on` |
| Formats d'impression | Moteur et styles par défaut évoluent | Formats Jinja autonomes, sans dépendre du CSS interne |
| Fixtures | Champs ajoutés aux doctypes standard entre versions | Fixtures filtrées, réimportables sur les deux versions |
| Versions déclarées | `pyproject.toml` → `[tool.bench.frappe-dependencies]` | Bornes `>=15.0.0,<17.0.0` pour frappe, erpnext, hrms |

## Structure

```
lsi_inspection/
├── README.md, CHANGELOG.md, license.txt, pyproject.toml
├── docs/specs/                 # une spécification par lot
└── lsi_inspection/
    ├── hooks.py                # required_apps, fixtures (filtrées), doc_events
    ├── fixtures/               # paramétrage livré (JSON exporté)
    ├── patches/ , patches.txt  # patches réversibles
    ├── tests/                  # tests automatiques (compat.py = classe de base v15/v16)
    └── lsi_inspection/         # module « LSI Inspection » (doctypes, rapports…)
```

## Installation (sur ce bench)

L'app est installée **uniquement** sur `tic.erpsys.ovh`.

```bash
bench --site tic.erpsys.ovh backup --with-files
bench --site tic.erpsys.ovh install-app lsi_inspection
```

Mise à jour d'un lot : sauvegarde, `git pull` dans `apps/lsi_inspection`, puis `bench --site tic.erpsys.ovh migrate` et
`bench build --app lsi_inspection` (jamais de migration ni de build global sur ce bench multi-sites).

## Tests

```bash
bench --site tic.erpsys.ovh set-config allow_tests true   # une fois
bench --site tic.erpsys.ovh run-tests --app lsi_inspection --skip-test-records --skip-before-tests
```

`--skip-before-tests` est **obligatoire** : sans lui, les préparations de test d'ERPNext et de HRMS s'exécutent sur le site et le
modifient de façon définitive (ERPNext **efface tous les prix d'articles**, change des paramètres de vente et de stock ; HRMS crée
une liste de congés de test). Avec `--module`, ces préparations de **toutes** les apps s'exécutent. `--skip-test-records` est aussi obligatoire : sans lui, le lanceur de Frappe crée et valide en base des « test records » (ex. rôles
« _Test Role ») sur le site. Chaque test tourne dans une transaction annulée ; tout commit et tout envoi d'e-mail SMTP sont
interdits pendant les tests, et un contrôle automatique vérifie en fin de test qu'aucun utilisateur, e-mail, notification ou
opportunité n'a été laissé. Les tests à l'écran se font uniquement avec des comptes réels (jamais d'adresse fictive sur le site).

## Licence

MIT
