# Journal — circuit logistique (commande client → Besoin Logistique → OM)

Branche `logistique` créée depuis `travail` (f1f93bb). Site : **tic.local uniquement**. Rien n'est poussé.

---

## 1. Lecture préalable (rien modifié)

### Commande ↔ devis ↔ chiffrage
- `Quotation.lsi_chiffrage` → la variante de chiffrage du devis (créé par `chiffrage/devis.py: creer_devis`).
- Chaque ligne de devis porte `Quotation Item.lsi_eft_position` = **nom (name) de la ligne Chiffrage Position** vendue,
  plus `lsi_numero_position`, `lsi_groupe_numero`, `lsi_etapes`.
- La commande (Sales Order) n'a **aucun champ lsi_** : on remonte par les champs natifs
  `Sales Order Item.prevdoc_docname` (devis) et `Sales Order Item.quotation_item` (ligne de devis).
  Chemin : ligne de commande → ligne de devis → `lsi_eft_position` → ligne du chiffrage.
- `Sales Order.on_submit` → `devis.commande_validee` : la variante devient « Retenue ». Le chiffrage d'une commande
  validée est donc le chiffrage retenu.
- Projet natif : `erpnext…sales_order.make_project(so)` (mappage natif) ; `Project.on_update` écrit lui-même
  `Sales Order.project`. Sur tic.local, SAL-ORD-2026-00001 a déjà PROJ-0001 → il sera **réutilisé**, pas recréé.

### Chiffrage (doctype `Chiffrage`, soumis)
- `etapes` (Chiffrage Etape) : les **prestations** (Item) du chiffrage.
- `positions` (Chiffrage Position) : `numero`, `groupe`, `parente` (sous-position d'un prix fixe), `type_position`,
  `item_code`, `qty`, `uom`, `etape`, `cout_unitaire`, `cout_total`, `ressource_doctype`, `ressource` (ressource choisie au
  chiffrage), `retenue`.
- `groupes` + `repartitions` (cible = n° de groupe ou de position, etape, part %).
- `calcul._etapes_de(doc, p, par_num)` → `[(prestation, fraction)]` : répartition de la position, sinon de son groupe, sinon
  l'étape unique ; une sous-position suit sa parente. **C'est la source de vérité des parts** : je l'importe (pas de copie).
- `actions.partager_groupe(chiffrage, groupe, etapes)` : remplace les répartitions du groupe par une ligne par prestation
  cochée (part vide = parts égales) → un groupe partagé = plusieurs lignes `repartitions` sur la même cible.
- Le rapport `Besoins Chiffrage` fait déjà une extraction proche (prix fixe « règle » : seul le candidat retenu ; prix fixe
  « somme » : ses sous-positions) : je reprends la même logique, en important `candidat_retenu` et `facteur_uom`.

### Pools (Type Position)
- Type « Pool de ressources » : `pool_doctype` (Designation / Asset Category / Item Group), `ressource_doctype`
  (Employee / Asset / Item), `champ_appartenance` (designation / asset_category / item_group), `filtres_ressources` (JSON).
- L'article de la position porte `Item.lsi_pool_doctype` + `Item.lsi_pool`.
- `couts._ressources(t, pool)` : filtres = `{champ_appartenance: pool} + filtres_ressources`. Je reprends **ces mêmes filtres**
  (fonction `filtres_pool`) pour la liste déroulante et le contrôle ; `_ressources` lui-même calcule aussi les coûts (inutile ici).

### Ordre de mission existant ?
- `grep` (py/json/js) sur « ordre de mission / ordre_mission / OM » : **rien** dans l'app.
- Toutes les branches locales et distantes (`git ls-tree`), y compris le commit `fe67dc2 wip` : **rien**.
- Base tic.local (`tabDocType`) : **aucun** doctype OM / Mission / Logistique.
- (L'app `gnparcauto` présente dans le bench mais non installée sur tic.local mentionne « ordre de mission » dans
  `Vehicle Return Discharge` : ce n'est pas un doctype OM, non réutilisé.)
- ⇒ **création d'un doctype « Ordre de Mission » minimal.**
- À noter : `actions.planifier_positions_globales` (wip) crée des Task avec un champ `assigned_to` qui n'existe pas sur Task ;
  non utilisé, non touché.

### Données de tic.local
- SAL-ORD-2026-00001 (validée, client « test client », projet PROJ-0001) ← SAL-QTN-2026-00002 ← chiffrage EFT-2026-0002-A
  (Retenue). Lignes : FORFAIT-ELEC-J (pos. 1.1, prestation FORFAIT-ELEC-J), INSP-RT2-J (2.1) et PHOTO-J (2.6), prestation
  « Contrôle par Radiographie - Rayon Gamma ». Aucun groupe partagé dans ce chiffrage.
- Salariés : 3 « Inspecteur RT niveau II » (HR-EMP-00002..4), sans utilisateur. Actifs : 2 véhicules, 2 appareils photo (Draft).

---

## 2. Plan et décisions

### Notion de « prestation »
Une **prestation = une étape du chiffrage** (Item de `Chiffrage.etapes`), pas une ligne de commande : une commande peut avoir
plusieurs lignes pour la même prestation (ex. INSP-RT2-J + PHOTO-J pour la radiographie). Une prestation est « vendue » si au
moins une ligne de commande la couvre (via `_etapes_de`). Chaque prestation du Besoin garde sa ligne de commande principale
(la première) et la liste de toutes ses lignes. ⇒ **un OM par étape vendue.**

### Extraction (lignes « ressources » du Besoin)
- Pour chaque ligne de commande : position vendue du chiffrage ; quantité = **quantité commandée** (les sous-positions sont mises
  à l'échelle commandée / chiffrée).
- Position à prix fixe : « somme » → ses sous-positions ; « règle » → la sous-position retenue (`candidat_retenu`).
- Seules les lignes **« Pool de ressources »** avec un pool sur l'article sont extraites ; type de ressource déduit du doctype
  des ressources (Employee → Main-d'œuvre, Asset → Équipement, Item → Consommable : constante `TYPE_PAR_DOCTYPE`).
- Les autres (article, sous-traitance, pool absent, quantité 0) sont listées dans « Lignes non extraites » (rien n'est caché).
- Répartition : `_etapes_de` ; une prestation → ligne simple ; plusieurs → **une seule ligne partagée** + table des parts.

### Doctypes (module « Logistique », dossier `lsi_inspection/logistique/`)
- `Besoin Logistique` (un par commande, nom `BL-<commande>`), tables enfants : `Besoin Logistique Prestation`,
  `Besoin Logistique Ressource`, `Besoin Logistique Repartition`, `Besoin Logistique Affectation`.
- `Ordre de Mission` (+ `Ordre Mission Ressource`).

### Contrôles (à l'enregistrement du Besoin)
a) ressource dans le pool → `ressource_qualifiee(ressource, pool, date)` (point d'entrée unique, certifications plus tard) ;
b) conflits employé / actif (même Besoin, autres Besoins non annulés, OM non annulés) ; exception : actif d'une ligne
   **partagée** sur les prestations de sa répartition ;
c) congé approuvé → avertissement (non bloquant) ;
d) actif hors service (`ACTIFS_HORS_SERVICE`) → refus.
+ prestation d'une affectation = prestation de sa ligne (ou une des prestations d'une ligne partagée).

### Statut (calculé à l'enregistrement)
Brouillon → En planification (une date ou une affectation saisie) → Planifié (toutes les prestations datées et chaque ligne
ressource affectée) → OM générés (bouton) ; Annulé (bouton).

### Fichiers hors module (strict minimum)
- `modules.txt` : ajout du module « Logistique » (obligatoire pour un nouveau module Frappe — **signalé**).
- `hooks.py` : `doctype_js` de Sales Order (aucun `doc_events` ni fixture : pas nécessaire).
- `constants.py` : constantes logistiques.
- Workspace « Inspection » (carte v15) et Workspace Sidebar (v16) : section Logistique.

---

## 3. Déroulement
Sauvegarde de tic.local avant le premier migrate : `sites/tic.local/private/backups/20261113_064428-tic_local-database.sql.gz`.

| Étape | Fait | Vérifié |
|---|---|---|
| 0 | lecture, journal, plan | — |
| 1 | doctypes, extraction, bouton de la commande | extraction de SAL-ORD-2026-00001 (console) |
| 2 | affectations, contrôles, écran du besoin | 12 cas (console, transaction annulée) |
| 3 | OM, tâches, annulation, démo | circuit complet + exception « équipement partagé » (console, transaction annulée) ; scénario navigateur (Playwright, vrais boutons) sur SAL-ORD-2026-00002 |
| 4 | workspace (carte v15 + section v16) | migrate, page Inspection affiche « Besoin logistique » |

Incidents et écarts à la méthode :
- **`sudo supervisorctl restart all` demande un mot de passe** : à la place, SIGTERM sur gunicorn et les workers RQ
  (supervisor les relance, `autorestart=true`), puis contrôle `api/method/ping` = 200. Même effet qu'un restart.
- Premier migrate : liste des modules en cache → `bench clear-cache` puis migrate.
- **Bug corrigé** (commit 80c06fc) : la classe Python doit s'appeler `OrdredeMission` (Frappe retire les espaces sans changer la
  casse) ; avec `OrdreDeMission`, le migrate supprimait le doctype « Ordre de Mission » comme orphelin.
- Tests de l'app : `allow_tests` est désactivé sur tic.local ; je n'ai pas changé la config du site. Les tests ont été faits par
  scripts console **dans une transaction annulée** (rollback, `commit` neutralisé) + un scénario navigateur. `pyflakes` absent :
  contrôle des imports par script AST (aucun import inutile).
- `cannot_add_rows` n'est pas une propriété stockée de DocField : posée dans l'écran (JS).

---

## 4. Rapport final

### Commits (branche `logistique`, non poussée)
```
643b6e7 Logistique — écran du besoin : pas d'ajout ni de suppression de prestation (elles viennent de la commande)
ff0c349 Logistique, étape 4 — workspace Inspection : carte Logistique (v15) et section Logistique de la barre latérale (v16)
6d17154 Logistique, étape 3 — génération des OM et des tâches
76a85a3 Logistique, étape 2 — affectations et contrôles
80c06fc Logistique — fix : nom de classe OrdredeMission (sinon le migrate supprime le doctype comme orphelin)
79d0f57 Logistique, étape 1 — Besoin Logistique : création projet + besoin depuis la commande, extraction du chiffrage
26517b2 Logistique, étape 0 — journal : lecture de l'existant et plan
```
(+ le commit de ce journal.)

### Fichiers (`git diff --stat travail..logistique`)
Hors module (minimum autorisé) :
- `lsi_inspection/hooks.py` (+2) : `doctype_js["Sales Order"] = "logistique/public/sales_order.js"` ;
- `lsi_inspection/constants.py` (+12) : `EN_PLANIFICATION, PLANIFIE, OM_GENERES, ANNULE`, `MAIN_OEUVRE, EQUIPEMENT, CONSOMMABLE`,
  `TYPE_PAR_DOCTYPE`, `DOCTYPES_A_CONFLIT`, `ACTIFS_HORS_SERVICE`, `CONGE_APPROUVE`, `TACHE_ANNULEE` ;
- `lsi_inspection/modules.txt` (+1 ligne « Logistique » ; la dernière ligne reçoit son retour à la ligne) ;
- `lsi_inspection/lsi_inspection/workspace/inspection/inspection.json` : carte « Logistique » (6 liens) + bloc de contenu ;
- `lsi_inspection/workspace_sidebar/inspection.json` : section « Logistique » (6 liens).

Module `lsi_inspection/logistique/` (nouveau) :
`__init__.py`, `extraction.py`, `pools.py`, `planification.py`, `controles.py`, `om.py`, `demo.py`, `public/sales_order.js`,
`doctype/besoin_logistique/` (.json, .py, .js, _list.js), `doctype/besoin_logistique_prestation|ressource|repartition|affectation/`,
`doctype/ordre_de_mission/` (.json, .py, .js, _list.js), `doctype/ordre_mission_ressource/`.
Docs : `docs/logistique/JOURNAL.md`.

**Rien n'a été modifié** dans le moteur de chiffrage, l'EFT, l'opportunité, les phases, les profils, les fixtures, les patches.
Fonctions du chiffrage seulement **importées** : `calcul._etapes_de`, `couts.candidat_retenu`, `couts.facteur_uom` (et, dans
`demo.py`, `actions.partager_groupe`, `variantes.nouvelle_variante`, `devis.creer_devis`).

### Doctypes (module Logistique)
**Besoin Logistique** (nom `BL-<commande>`, un par commande : `sales_order` unique ; droits : System Manager, Projects Manager,
Projects User sans suppression) : `sales_order`, `customer`, `customer_name`, `project`, `chiffrage`, `company`, `statut`
(Brouillon / En planification / Planifié / OM générés / Annulé), tables `prestations`, `ressources`, `repartitions`,
`affectations`, `non_extraites`, `avertissements`.
- *Besoin Logistique Prestation* : `prestation`, `libelle`, `date_debut`, `date_fin`, `lieu`, `ordre_mission`, `ligne_commande`,
  `item_commande`, `lignes_commande`.
- *Besoin Logistique Ressource* (lecture seule, extraite) : `numero` (n° du chiffrage), `type_ressource`, `item_code`,
  `prestation` (vide si partagée), `partagee`, `repartition` (texte), `pool_doctype`, `pool`, `ressource_doctype`, `type_position`,
  `ressource_chiffrage`, `qty`, `uom`, `cout_unitaire`, `cout_prevu`, `ligne_commande`.
- *Besoin Logistique Repartition* (lecture seule) : `numero`, `prestation`, `part`.
- *Besoin Logistique Affectation* : `ligne_ressource` (n°), `prestation`, `ressource` (lien dynamique), `date_debut`, `date_fin`,
  `qty`, `part`, `nom_ressource`, `type_ressource`, `ressource_doctype`, `remarque` (congé).

**Ordre de Mission** (nom `OM-AAAA-#####`, titre = libellé) : `prestation`, `libelle`, `customer`, `customer_name`, `statut`
(Planifié / Annulé), `date_debut`, `date_fin`, `lieu`, `project`, `besoin_logistique`, `sales_order`, `ligne_commande`,
`item_commande`, table `ressources`, `notes`.
- *Ordre Mission Ressource* : `type_ressource`, `ressource_doctype`, `ressource`, `nom_ressource`, `date_debut`, `date_fin`,
  `qty`, `uom`, `part`, `partagee`, `numero`, `task`.

### Boutons
| Écran | Bouton | Fonction serveur |
|---|---|---|
| Commande client validée | Logistique › Créer projet et besoin logistique | `extraction.creer_projet_et_besoin` |
| Commande client (besoin existant) | Logistique › Ouvrir le besoin logistique | — |
| Besoin | Préparer les affectations | `planification.preparer_affectations` |
| Besoin (Planifié / OM générés) | Actions › Générer les OM | `om.generer_om` |
| Besoin | Actions › Annuler le besoin | `om.annuler_besoin` |
| Besoin | Voir › Projet / Ordres de mission / Commande client | — |
| OM | Voir › Besoin logistique / Projet / Tâches | — |

Listes déroulantes de l'affectation : « Ligne (n°) » = n° des ressources prévues ; « Prestation » = celle de la ligne (ou ses
prestations si partagée) ; « Ressource » = filtres du pool via `pools.ressources_du_pool` (mêmes filtres que `_ressources`).

### Contrôles (à chaque enregistrement du besoin — `controles.controler`, un seul message listant tous les refus)
- dates présentes, fin ≥ début ; n° de ligne connu (`planification._options_lignes`) ;
- prestation = celle de la ligne ; ligne partagée : une de ses prestations ; main-d'œuvre partagée : prestation obligatoire ;
- a) `pools.ressource_qualifiee(ressource, pool, date)` — **point d'entrée unique** (appartenance au pool aujourd'hui) ;
- d) actif hors service (`ACTIFS_HORS_SERVICE` : In Maintenance, Out of Order, Scrapped, Sold) → refus ;
- b) conflits employé/actif : `_conflits_internes` (même besoin, deux prestations, dates qui se chevauchent ; **exception** : actif
  de la même ligne partagée) et `_conflits_externes` (autres besoins non annulés, OM non annulés hors ceux de ce besoin) ;
- c) `_conges` : Leave Application approuvée et validée sur la période → avertissement orange + colonne « Remarque » +
  champ « Avertissements » (non bloquant).
- Besoin « Annulé » : plus modifiable.

### Statut (`planification.statut`)
Brouillon → En planification (une date ou une affectation) → Planifié (toutes les prestations datées ET chaque ressource prévue
affectée) → OM générés (bouton) ; Annulé (bouton).

### Génération des OM (`om.generer_om`)
Besoin réenregistré (contrôles relancés) ; dates prévues du projet élargies pour couvrir les OM (`_dates_projet` : le natif
refuse une tâche après la fin prévue du projet) ; un OM par prestation (`_om`), ressources = occupations de la prestation
(ressource partagée sans prestation : dans chaque OM, avec sa part, aux dates de la prestation) ; une Task par employé
(`_taches`), assignée (ToDo natif, `_assigner`) à `Employee.user_id` s'il existe. Regénérer met à jour les mêmes OM/tâches ;
tâche d'un employé retiré → « Cancelled ».

### Documents créés sur tic.local
| Document | Rôle | État |
|---|---|---|
| BL-SAL-ORD-2026-00001 | besoin de la commande existante (projet PROJ-0001 existant réutilisé) | Brouillon |
| EFT-2026-0002-B, SAL-QTN-2026-00003, SAL-ORD-2026-00002 | variante démo (véhicule partagé) → devis → commande (scénario navigateur) | variante Non retenue (depuis C) |
| PROJ-0002, BL-SAL-ORD-2026-00002 | projet + besoin créés par le bouton (navigateur) | OM générés |
| OM-2026-00001 (FORFAIT-ELEC-J), OM-2026-00002 (Radiographie) | OM générés (navigateur) | Planifié |
| TASK-2026-00001 (assignée inspecteur.demo@tic.local + ToDo), TASK-2026-00002 | tâches des inspecteurs | Open |
| EFT-2026-0002-C, SAL-QTN-2026-00004, **SAL-ORD-2026-00003** | **commande vierge pour la démo live** | variante Retenue |
| User inspecteur.demo@tic.local, Employee HR-EMP-00005 « Inspecteur Démo Logistique » | pool Inspecteur RT niveau II, coût 0 (sans effet sur les chiffrages) | actifs |

Effets de bord natifs : EFT-2026-0002-A est passée « Non retenue » (hook existant `commande_validee` quand B puis C ont été
commandées) ; OFF-2026-0002 (déjà Converted) : aucune phase modifiée. Tous les tests négatifs ont été faits en transaction annulée.

### Scénario de démo (http://172.18.79.47:8001)
1. **Commande client SAL-ORD-2026-00003** → menu **Logistique › Créer projet et besoin logistique**.
   → le besoin `BL-SAL-ORD-2026-00003` s'ouvre, statut Brouillon, projet créé (PROJ-0003) ; 2 prestations (FORFAIT-ELEC-J,
   Radiographie Gamma) ; 5 ressources prévues : 2 main-d'œuvre (2.1, 2.3), film (2.4), appareil photo (2.6) et **véhicule 3.1
   partagé 50 % / 50 %** (table « Répartition ») ; « Lignes non extraites » : 1.1 FORFAIT-ELEC-J (article sans pool).
2. Prestations : saisir début / fin / lieu (ex. FORFAIT 01-12 → 01-12 Sfax ; Radiographie 02-12 → 03-12 Gabès). Enregistrer → « En planification ».
3. **Préparer les affectations** → 5 lignes (le véhicule sans prestation = les deux).
4. Choisir les ressources : la liste ne propose que le pool de la ligne (2.1/2.3 : inspecteurs RT II ; 2.4 : FILM-IX100 /
   FILM-MX125 ; 2.6 : appareils photo ; 3.1 : véhicules). Ex. 2.1 Inspecteur Démo Logistique, 2.3 Hela Mansour, 2.4 FILM-IX100,
   2.6 ACC-ASS-2026-00004, 3.1 ACC-ASS-2026-00002. Enregistrer → « Planifié ».
   - **Démo conflit** : mettre la Radiographie du 24-11 au 25-11 et Sami Trabelsi (déjà sur OM-2026-00002) → refus « Conflit :
     Sami Trabelsi est déjà affecté(e) … sur Ordre de Mission OM-2026-00002 ».
   - **Démo pool** : forcer un véhicule sur la ligne 2.6 (champ saisi à la main) → refus « n'appartient pas au pool Appareils photo ».
   - **Démo exception** : véhicule 3.1 sur les deux prestations aux mêmes dates → accepté.
5. **Actions › Générer les OM** → « 2 OM et 1 tâche(s) » (seul l'Inspecteur Démo a un utilisateur… et Hela Mansour a aussi
   sa tâche, non assignée) ; statut « OM générés » ; colonne « Ordre de mission » remplie.
6. Ouvrir un OM : prestation, dates, lieu, projet, commande, ligne de commande ; ressources (véhicule à 50 %), colonne Tâche.
7. Voir › Projet → onglet / liste des tâches du projet ; la tâche de l'Inspecteur Démo est assignée à inspecteur.demo@tic.local.
8. Page **Inspection** : carte / section « Logistique ».

### Non fait, limites, questions ouvertes
- **Droits** : pas de rôle « Logistique » créé (ce serait une décision métier + une fixture Role) ; droits sur System Manager,
  Projects Manager, Projects User. → Faut-il un rôle dédié ?
- **Lignes non extraites** : positions « Article », « Prix fournisseur » ou sans pool sur l'article ne deviennent pas des
  ressources prévues (listées dans « Lignes non extraites »). → Les consommables « Article » doivent-ils être planifiés ?
- Quantités : l'affectation reprend la quantité prévue (modifiable) ; **aucun contrôle** quantité affectée vs prévue, ni
  conversion Heure → Jour (pas de règle donnée).
- Pas de lien natif « Connexions » de la commande / du projet vers le besoin et les OM (`override_doctype_dashboards` hors du
  périmètre autorisé) : remplacé par les boutons. Annuler la commande n'annule pas le besoin (pas de `doc_events`).
- OM minimal : statut Planifié / Annulé, champs en lecture seule (modifier le besoin puis regénérer) ; pas de format d'impression.
- Conflits vérifiés contre les besoins et les OM seulement (pas les Timesheets, ni d'autres modules).
- Le projet créé garde le nom natif (`project_name` = n° de commande, mappage ERPNext).
- `BesoinLogistique._validate_links` est surchargée pour poser le doctype du lien dynamique avant le contrôle natif des liens
  (utile aux appels API ; l'écran le pose déjà).
- La colonne « Part (%) » affiche 0 % pour une ressource non partagée (champ Percent vide).
- Pas de tests unitaires dans `lsi_inspection/tests/` (hors périmètre autorisé ; tests désactivés sur tic.local) : les scripts
  de test console et Playwright sont hors dépôt. → Les ajouter comme `tests/test_logistique.py` ?
- Code existant non touché mais à signaler : `chiffrage/moteur/actions.planifier_positions_globales` (wip) crée des Task avec un
  champ `assigned_to` inexistant.
- Certifications : à brancher dans `pools.ressource_qualifiee` (la date de début de l'affectation lui est déjà passée).
