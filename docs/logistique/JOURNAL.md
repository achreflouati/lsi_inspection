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
- `hooks.py` : `doctype_js` de Sales Order.
- `constants.py` : constantes logistiques.
- Workspace « Inspection » (carte v15) et Workspace Sidebar (v16) : section Logistique.

---

## 3. Déroulement
