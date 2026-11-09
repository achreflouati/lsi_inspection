# Code et données obsolètes — propositions de nettoyage (rien n'est supprimé sans accord)

| # | Élément | Où | État | Proposition |
|---|---|---|---|---|
| 1 | Doctype **Notification Phase**, champ `Opportunity Type.lsi_notifications_phase`, champ `Phase Opportunite.retard_notifie` | commercial/doctype, fixtures | inactif (remplacé par les notifications natives) ; 3 lignes sur « Appel d'offres » | appliquer la branche `lot2-suppression-ancien` (patch prêt) |
| 2 | Modèles d'e-mail « Phase - entree », « Phase - retard » | profil tic (`email_template.json`, cités par `opportunity_type.json`) | utilisés seulement par l'ancien mécanisme (1) | supprimer avec (1) |
| 3 | Colonne `naming_series` de `tabChiffrage` | base tic | champ retiré du doctype (nom = `<EFT>-<lettre>`) ; colonne laissée par Frappe | `bench --site … trim-tables` (supprime les colonnes orphelines, après sauvegarde) |
| 4 | Champ `Quotation Item.lsi_eft_position` | fixture | contient le n° de **ligne de chiffrage** ; nom hérité | renommer en `lsi_position_chiffrage` (patch : copie puis retrait) |
| 5 | Fichiers générés vides : `chiffrage/doctype/{chiffrage,gamme,modele_chiffrage,type_position}/*.js`, `test_*.py` des dossiers de doctype | app | 0 ligne utile | supprimer (les tests réels sont dans `tests/`) |
| 6 | Modèle commenté de Frappe en tête de `hooks.py` (≈ 250 lignes de commentaires) | hooks.py | non utilisé | supprimer pour ne garder que les blocs actifs |
| 7 | `docs/specs/lot3-eft.md` | docs | décrit l'ancien modèle « EFT = chiffrage » | garder comme historique, renvoyer vers `lot3b-variantes.md` (fait) |
| 8 | Types « Article à coût », « Article de la position à prix fixe » ; types consommables en double | profil tic | décision du 09/11 : renommer en « Frais… », consommables en pool | lot correctif (étape 7 du plan) |
| 9 | `lsi_bu` / `lsi_service` (Opportunity, Quotation) et `bu` / `service` (EFT, Chiffrage) | fixtures, doctypes | décision : axes analytiques natifs | lot correctif (étape 6 du plan) |
| 10 | EFT reprises sans opportunité : EFT-2026-0003, 0006, 0007, 0008, 0009 (essais à l'écran) | données tic | créées par la reprise pour garder chaque ancien chiffrage | à supprimer ou rattacher à une opportunité, sur accord |
| 11 | Événements « Devis validé », « Opportunité convertie » | configuration | plus utilisés par le parcours tic (remplacés par Variante retenue / Commande validée) | garder (génériques, utiles à d'autres parcours) ou désactiver |
