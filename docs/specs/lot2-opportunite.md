# Lot 2 — Opportunité (branche lot2-opportunite)

**Principe directeur** : l'équipe TIC paramètre elle-même tout le processus commercial de l'opportunité depuis les écrans
(phases par type, responsables, durées, événements de fin, départements à notifier, canal, contenu des messages). Le code ne
contient que le moteur générique, aucune valeur TIC.

Hors périmètre : Dossier AO, Avant-projet, Plan Action, EFT (ajoutés par les lots suivants, par configuration pour les
événements « EFT créé / chiffré »).

## 1. Éléments livrés

Livraison : **S** = fichier standard du module, **F** = fixture filtrée, **D** = données de configuration (insertion seule).

| # | Élément | Nature | Livraison |
|---|---|---|---|
| 1 | Série native `OFF-.YYYY.-.####` par défaut ; « Phase commerciale » (sales_stage) en lecture seule, tenue par le moteur | Paramétré (Property Setter) | F |
| 2 | Référentiel : **Famille de Type** (code, libellé, actif) et **Type Metier** (famille, code, libellé, actif, ordre ; nom = famille-code, donc code unique par famille) | Doctypes, sans logique | S (module Referentiel) |
| 3 | `lsi_canal_demande` (Type Metier filtré par `link_filters` natif, famille CANAL_DEMANDE), `lsi_origine_demande` (Employee). Pas de type de consultation : `opportunity_type` natif | Paramétré | F |
| 4 | Workflow **Validation demande d'offre** sur `lsi_statut_validation` : À valider → Valider / Refuser / Demander clarification ; Clarification → Remettre à valider. « Allow edit » : Sales User et Validateur à chaque état. `lsi_motif_non_validation` (Type Metier, famille MOTIF_NON_VALIDATION) obligatoire en « Non validée » | Paramétré | F |
| 4b | Contrôle **côté serveur** des champs `lsi_` « obligatoires si » (`mandatory_depends_on`) : v15 ne le contrôle que dans le navigateur, une action de workflow passerait outre | Code générique (`outils.verifier_obligatoires`) | S |
| 5 | **Evenement Phase** : libellé, déclencheur (Manuel / Création / Validation / État du workflow / Changement de statut / Annulation), document, champ du statut, valeur attendue, champ de lien (si indirect), actif | Doctype | S |
| 6 | **Parcours Phase** sur Opportunity Type (`lsi_parcours`) : ordre, phase (Sales Stage), responsable (Commercial / Rôle / Utilisateur / Pilote du département), durée cible, événement de fin, obligatoire, **phase finale** (Gagnée / Perdue) ; `lsi_parcours_defaut` (un seul type) | Doctype enfant + champs | S + F |
| 7 | **Notification Phase** sur Opportunity Type (`lsi_notifications_phase`) : phase (vide = toutes), moment (Entrée / Fin / Retard), destinataires (Départements concernés (tous) / Département principal / Pilote / Responsable de phase / Commercial / Rôle / Utilisateur / Département précis), Système et/ou E-mail, **Email Template natif** (Jinja : `doc`, `phase`, `moment`, `ligne`, `lien`), actif | Doctype enfant + champ | S + F |
| 8 | Suivi `lsi_phases` (Phase Opportunite) + `lsi_echeance_phase`, `lsi_responsable_phase` en en-tête, calculés dans `validate` | Doctype enfant + champs | S + F |
| 9 | **Historique** `lsi_historique_phases` (Historique Phase) : date, de, vers, action (Terminée / Sautée / Sautée (auto) / Retour arrière / Reconstruction / Gagnée / Perdue), par, événement, document source, motif, commentaire. Ajout seul : toute modification ou suppression d'une ligne est refusée | Doctype enfant + contrôle | S + F |
| 10 | **Moteur** `commercial/phases.py` (détail §2) | Code | S |
| 11 | **Départements concernés** `lsi_departements` (département, pilote, utilisateur du pilote, principal) ; `lsi_responsable` sur Department ; pilote par `fetch_from` natif ; une seule ligne principale | Doctype enfant + champs + 1 contrôle | S + F |
| 12 | Notifications natives fixes : **Nouvelle opportunite** (rôle Etude technique) ; **Retard phase opportunite** (Days After 1 jour sur `lsi_echeance_phase`, opportunité ouverte ; destinataires `lsi_responsable_phase` et `opportunity_owner`) | Paramétré | F |
| 13 | Rôles **Validateur demande d'offre**, **Etude technique**, **Paramétreur commercial** (créer / modifier : Opportunity Type, Sales Stage, Evenement Phase, Type Metier, Famille de Type, Email Template ; rien d'autre) | Paramétré (Role, Custom DocPerm, permissions des doctypes) | F + S |
| 14 | Workspace : carte « Paramétrage commercial » complétée | Fichier standard | S |
| 15 | Configuration initiale `config_initiale/commun` + `profils/<profil>` (clé site_config `lsi_profil`) | Données | D |
| 16 | Export `bench --site <site> execute lsi_inspection.config.exporter_profil --kwargs '{"profil": "tic"}'` | Code | S |

## 2. Moteur des phases

- **Construction** depuis le parcours du type (ou du type « parcours par défaut ») ; lignes d'une même phase = co-responsables.
  **Reconstruction** au changement de type ou de parcours, opportunités ouvertes seulement : phases faites et phase en cours
  conservées (« hors parcours » si retirées), phases à venir recalculées ; ligne « Reconstruction » dans l'historique.
- **Terminer ma phase** (bouton + dialogue) : responsables de la phase ou System Manager ; phase suivante par défaut, saut
  (refusé si une phase obligatoire est sautée), retour arrière (phases suivantes remises « À venir »). Une phase finale ne se
  termine que par son événement.
- **Événements** : `doc_events "*"` (after_insert, on_submit, on_cancel, on_change) avec **sortie immédiate** si le doctype
  n'est dans aucun Evenement Phase actif (liste en cache, invalidée à chaque modification d'un événement). Les événements de
  valeur (état du workflow, statut) sont **évalués juste avant la validation de la transaction**, sur la valeur finale.
  Opportunités liées : le document lui-même, le champ de lien indiqué, sinon un lien vers Opportunité, sinon vers un Devis lié
  (tables comprises : la commande retrouve l'opportunité par ses lignes).
- **Phases finales** : Gagnée = dernière phase de la séquence, terminée par « Opportunité convertie » (les phases restantes
  passent « Sautée (auto) »). Perdue = hors séquence : à « Opportunité perdue », les phases restantes passent « Sautée (auto) »,
  la phase Perdue est enregistrée et l'historique reçoit le **devis source** et le **motif de perte natif** (raisons + détail).
- **ToDo natif** aux responsables à l'entrée d'une phase (marqué `[phase]`), fermé à la sortie.
- **Notifications par phase** : Notification Log natif (type Alert) et/ou `frappe.sendmail` (file d'attente) ; chaque règle est
  indépendante.
- **Jamais bloquant** : toute erreur du moteur est annulée (savepoint), journalisée (`frappe.log_error`) et signalée par un
  message ; le document déclencheur est enregistré.
- **Tâche quotidienne** `retards_quotidiens` : uniquement pour les règles « Retard » par phase (une fois par phase). La
  Notification native « Days After » couvre l'alerte fixe mais ne sait pas lire des règles en table enfant avec modèle d'e-mail
  et destinataires calculés.

## 3. Fin du parcours pilotée par le devis — comportement natif ERPNext (v15)

Le moteur suit **uniquement le statut de l'opportunité**, mis à jour par ERPNext (rien n'est recodé) :

| Action | Statut de l'opportunité (natif) |
|---|---|
| Devis validé | `Quotation` |
| Commande validée depuis le devis | `Converted` (devis « Ordered ») → phase **Gagnée** |
| Déclarer perdu (devis), aucun autre devis ouvert | `Lost` → phase **Perdue** (devis + motif dans l'historique) |
| Déclarer perdu (devis), **un autre devis encore ouvert** | ERPNext écrit `Lost` puis recalcule : `Quotation` (devis actif) ; statut final `Quotation` → **aucune phase finale** |
| Annulation du devis | `Open` / `Quotation` recalculé |

Ordre des règles natives (`status_updater`, dernière vraie l'emporte) : Lost (perdue) < Lost (devis perdu) < Quotation (devis
actif) < Converted (devis commandé) < Closed. D'où l'évaluation des événements de statut **avant commit** : la valeur
intermédiaire `Lost` ne déclenche rien.

Non traité (à décider) : une opportunité « Lost » rouverte (devis annulé) ne revient pas automatiquement sur ses phases.

## 4. Configuration initiale et profils

- `config_initiale/manifeste.json` : doctypes et ordre de chargement (configuration). `export: references` : seuls les
  documents cités sont exportés (modèles d'e-mail utilisés par les règles).
- `commun/` : familles CANAL_DEMANDE et MOTIF_NON_VALIDATION ; événements Manuel, Devis validé, Commande validée,
  Opportunité convertie, Opportunité perdue.
- `profils/tic/` : types Spot / Appel d'offres (parcours par défaut) / Contrat cadre / Renouvellement, canaux, motifs, étapes,
  événement Devis envoyé (inactif de fait tant que le devis n'a pas de workflow « Envoyée »), modèles « Phase - entree » et
  « Phase - retard », règles de notification. L'export contient aussi les étapes et types natifs d'ERPNext (sans effet :
  insertion seule).
- `charger()` en `after_sync` (installation, après les fixtures) et `after_migrate` : insère ce qui manque, ne modifie jamais.
- Circuit : TIC paramètre à l'écran → export → commit Git → la production l'insère à la migration.

## 5. Repris de tic_demo / réécrit

| Repris | Réécrit ou abandonné |
|---|---|
| Parcours sur Opportunity Type, phases = Sales Stage, tableau de suivi, Sautée (auto), obligatoires, opportunités closes figées | Événements : constantes → doctype **Evenement Phase** ; fin de parcours par le **statut natif** |
| Départements concernés + pilote | Pilote : `fetch_from` natif ; partage codé abandonné |
| États / transitions du workflow de validation | Workflow : script de démo → fixture ; motif contrôlé côté serveur |
| | Historique des étapes (Opportunite Etape) → **Historique Phase** en ajout seul |
| | N° d'offre codé → série native ; type de consultation / Select → opportunity_type + référentiel |
| | Alertes codées → Notifications natives + règles par phase paramétrables |
| | Champs créés au migrate → fixtures |

## 6. Tests (47, transaction annulée, configuration propre aux tests)

`tests/test_phases.py`, `test_notifications.py`, `test_validation.py`, `test_config.py`, `test_workspace.py`,
`test_installation.py`. Couvrent : construction, type sans parcours, Terminer ma phase + ToDo, obligatoire, historique
(terminer / sauter / retour ; ni modifié ni supprimé), échéance, parcours modifié (ouvertes seulement), changement de type,
événement ajouté par configuration seule, devis validé, **commande → Gagnée**, **Déclarer perdu → Perdue + motif**, **deux
devis (un perdu, un ouvert) → aucune phase finale**, erreur du moteur non bloquante, document hors événements sans appel au
moteur ; Paramétreur commercial seul (phase + règle → Notification Log + e-mail en file au département principal), règle
inactive, modèle en erreur non bloquant, sans compte sortant, destinataires, retard une seule fois, Days After natif ;
workflow (refus sans motif, clarification, commercial non autorisé), statut natif inchangé, série OFF, link_filters, code
unique par famille, pilote et ligne principale ; chargement idempotent, valeur modifiée conservée, nouvel élément inséré,
site sans profil, export jamais dans commun, ré-export identique, export → import sur base vide = mêmes données.

## 7. Fiche de test (testeurs TIC)

Prérequis : utilisateurs avec Sales User (commercial), Validateur demande d'offre, Etude technique, Paramétreur commercial ;
un département avec un responsable (employé lié à un utilisateur) ; **un compte e-mail sortant** pour les e-mails (sinon seules
les notifications système partent).

| # | Faire | Attendu |
|---|---|---|
| T2.1 | Inspection → Opportunité → Nouveau : client, type **Appel d'offres**, canal « Demande écrite », un département concerné (principal) | N° **OFF-2026-0001** ; validation **À valider** ; pilote rempli ; tableau des phases : Création **En cours**, puis Étude technique… Gagnée, Perdue ; notification « Nouvelle opportunité » au rôle Etude technique ; ToDo « [Création] » au commercial |
| T2.2 | En Validateur : **Refuser** sans motif, puis avec un motif | Refus « Champ(s) obligatoire(s) : Motif de non-validation » ; puis état « Non validée » |
| T2.3 | Sur une autre opportunité : **Valider** ; **Demander clarification** puis **Remettre à valider** | États Validée / Clarification / À valider ; le statut natif reste « Open » |
| T2.4 | **Terminer ma phase** (phase suivante proposée) | Création « Terminée », Étude technique « En cours », ToDo aux utilisateurs du rôle Etude technique ; historique « Terminée » |
| T2.5 | En Paramétreur : type **Appel d'offres** → ajouter « Visite de site » en ordre 15 | Elle apparaît dans l'opportunité ouverte (historique « Reconstruction ») ; une opportunité gagnée ou perdue ne change pas |
| T2.6 | Cocher « Obligatoire » sur Étude technique, puis Terminer ma phase vers une phase plus loin | Refus « Phase obligatoire, elle ne peut pas être sautée » |
| T2.7 | Durée cible 1 jour sur la phase en cours ; le surlendemain (tâches planifiées actives) | Notification « Phase en retard » au responsable et au commercial |
| T2.8 | Workspace Inspection | « Mes opportunités ouvertes » compte l'opportunité ; graphique par phase |
| T2.9 | En **Paramétreur commercial** : type Appel d'offres → Notifications par phase → ligne « Visite de site / Entrée dans la phase / Département principal / Système + E-mail / modèle Phase - entree » ; puis (commercial) Terminer ma phase jusqu'à Visite de site | Cloche (Notification Log) et e-mail en file pour les employés du département principal ; aucun code touché |
| T2.10 | Terminer, sauter une phase, puis **Retour à** une phase antérieure ; essayer de modifier l'historique | Une ligne par action (Terminée, Sautée, Retour arrière), les anciennes inchangées ; historique en lecture seule |
| T2.11 | **Gagnée par la commande** : devis depuis l'opportunité → Valider (soumettre) → Commande client depuis le devis → Valider | Statut natif « Converted » ; phases restantes « Sautée (auto) », **Gagnée « Terminée »** ; historique « Gagnée » avec le devis |
| T2.12 | **Perdue par le devis** : sur un devis validé, **Déclarer perdu** (motif + détail) ; recommencer avec deux devis ouverts dont un seul déclaré perdu | 1er cas : statut « Lost », phases restantes « Sautée (auto) », **Perdue « Terminée »**, historique « Perdue » avec le devis et le motif. 2e cas : statut « Quotation », aucune phase finale |
