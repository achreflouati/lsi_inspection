# Lot 3 — EFT / chiffrage (branche lot3-eft)

Référence métier : `docs/references/exemple_projet.csv` (feuille Projet + 3 missions de TIC). Le modèle reproduit exactement la
feuille Projet (33 positions, 5 groupes) — vérifié par `tests/test_chiffrage.py::test_reproduction_exemple_complet`.

## Livré
| Élément | Nature | Livraison |
|---|---|---|
| Module **Chiffrage** ; doctypes **EFT** (soumissible, amend / Dupliquer natifs), EFT Etape, EFT Groupe, EFT Position (sous-positions via « parente »), EFT Repartition, EFT Total Etape, **Type Position**, **Gamme** + Gamme Ligne, **Modele EFT** | Doctypes | Fichiers standard |
| Champs : Employee.lsi_cout_journalier (**permlevel 1**), Asset.lsi_cout_journalier, Item (pool, source du coût, marge cible), Item Group (source du coût, marge cible), Quotation / Quotation Item (lien EFT, groupe, n°, désignation 2, étapes, tarif), Request for Quotation (lien EFT) | Paramétré | Fixtures |
| Rôles Chiffreur, Paramétreur chiffrage ; permissions ; workflow EFT Brouillon → Chiffrée → Validée (Annulée) | Paramétré | Fixtures |
| Moteur `chiffrage/moteur.py` (pool générique, articles, prix fournisseurs, prix fixe, tarifs à 0, répartition, totaux, gammes, modèles, prorata, demande de prix, devis) ; `public/js/eft.js` ; bouton Opportunité > Créer > EFT | Code | Standard |
| Formats **Devis groupe** (Quotation) et **OT** (EFT) ; rapport **Besoins EFT** (calculé) ; cartes Chiffrage / Paramétrage chiffrage | Standard | Standard |
| Événements « EFT créée » / « EFT validée » | Configuration | Profil commun (aucun code) |
| 7 types de position, Jour → Heure = 8 (UOM Conversion Factor), Allow Quotation with Zero Quantity, 4 gammes, modèle « Transport & Indemnité » | Configuration | Profil tic |
| Jeu **DÉMO lot 3** + annuler | Données | `lsi_inspection/demo/lot3.py` (hors profil) |

Paramètres sans document unique : liste de prix d'achat = Buying Settings ; heures / jour = UOM Conversion Factor ; marge cible et
source du coût = Item Group (exception sur Item) ; répartition = parts indiquées, sinon parts égales.

## Règles
- Position vendue = sans parente (à coût ou prix fixe) ; sous-position = parente à prix fixe : coût seulement, jamais vendue ni au devis.
- Quantité 0 = tarif annoncé : prix unitaire affiché, total 0, hors totaux ; repris au devis grâce à l'option native.
- Brouillon : recalcul à chaque enregistrement (sauf coût manuel) ; validée : figée ; Dupliquer / Amender : recalcul.
- Coût manquant : signalé (position, prix fixe, EFT « coût incomplet »), jamais compté à 0 en silence.
- Coûts individuels des salariés : lus seulement par Paramétreur chiffrage, HR Manager, System Manager ; le Chiffreur voit le coût retenu et les noms.
- Gammes / modèle du profil : mis **en attente** tant que leurs articles n'existent pas (insérés au chargement suivant).
  **Ne pas exporter le profil avant que les articles existent** (l'export reflète la base).

## Points v15 / v16
Pas de table dans une table (répartition au niveau de l'EFT) ; quantité 0 au devis et UOM Conversion Factor natifs (v15, v16) ;
pas de surcharge de classe ; `frappe.copy_doc` serveur garde `docstatus` (l'interface le remet à 0) ; revérifier en v16 la demande de
prix / offre fournisseur et l'interface des workspaces.

## Fiche de test (testeurs TIC, comptes lsi.louati@gmail.com / meddhiaajaziri@gmail.com)
Prérequis : `bench --site tic.erpsys.ovh execute lsi_inspection.demo.lot3.run` (annuler : `… lsi_inspection.demo.lot3.annuler`).

| # | Faire | Attendu |
|---|---|---|
| T3.1 | Paramétrage : types de position, coûts journaliers (salariés, actifs), prix d'achat, conversion Jour → Heure | Écrans natifs ; coûts salariés invisibles sans rôle autorisé |
| T3.2 | Gammes RT, DMOS, Découpage, Électricité ; modèle « Transport & Indemnité » | Lignes de l'exemple, quantités par unité, tarifs à 0 |
| T3.3 | Opportunité > Créer > **EFT** | EFT créée ; la phase réglée sur « EFT créée » se termine |
| T3.4 | EFT « DÉMO lot 3 » (ou ajouter une prestation) | Groupes 1, 2, 3, 5 préremplis par les gammes |
| T3.5 | Groupe 4 « Transport & Indemnité » partagé RT + Découpage | Totaux par étape à parts égales ; modifier les parts → totaux suivent |
| T3.6 | Positions > Voir les ressources sur 1.1 ; choisir une autre ressource ; 5.1.1 | Pool au plus élevé, trace ; 5.1.1 en heures (÷ 8) |
| T3.7 | 3.2 Essai de traction : Positions > Demander un prix | Demande de prix brouillon ; « coût en attente » ; offre fournisseur validée → coût |
| T3.8 | Prix de vente | Marges, prix conseillé, totaux groupe / étape / EFT |
| T3.9 | Chiffrer puis Valider | EFT soumise, coûts figés ; événement « EFT validée » |
| T3.10 | Créer > Créer le devis ; impression « Devis groupe » | Positions vendues seulement, lignes tarif à 0, en-têtes et sous-totaux |
| T3.11 | Impression OT ; rapport Besoins EFT | Groupes sans prix ; jours par désignation / équipement |
| T3.12 | Annuler, Amender ; Dupliquer | Nouvelle version recalculée |
| T3.13 | Enregistrer comme modèle, charger sur une autre EFT | Structure sans coûts, recalcul immédiat |
| T3.14 | Paramétreur chiffrage : nouveau type de position ; Chiffreur : coûts salariés | Fonctionne sans code ; coûts individuels invisibles |
