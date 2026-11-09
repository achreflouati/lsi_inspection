# Lot 3b — EFT unique, variantes de chiffrage, liens devis, phases automatiques

Branche `lot3b-variantes` (depuis `ouverture-tests` = lot3-eft + corrections du 09/11 utilisées par le site).

## Objet
Une opportunité → **une EFT** (étude technique) → **plusieurs variantes de chiffrage** → **un devis par variante**. Tout est relié
dans les deux sens ; la phase commerciale avance seule à chaque étape ; les bonnes personnes sont notifiées (natif).

## Ce qui a changé

| Avant | Après |
|---|---|
| « EFT » = document de chiffrage | **Chiffrage** = une variante (même moteur, même écran) ; **EFT** = étude technique |
| EFT Position / Groupe / Etape / Repartition / Total Etape, Modele EFT | Chiffrage Position / … , Modele Chiffrage |
| OT = impression du chiffrage | OT = impression de l'EFT ; l'ancienne devient « Fiche chiffrage » |
| Rapport « Besoins EFT » | « Besoins Chiffrage » (par variante) |
| `Quotation.lsi_eft` = chiffrage | `Quotation.lsi_chiffrage` = variante, `Quotation.lsi_eft` = EFT (idem demande de prix) |

### EFT (étude technique)
Opportunité (une seule EFT active), client, commercial, BU / Service, responsable du service ; faisabilité (Faisable / Non faisable /
À clarifier, motif du référentiel `MOTIF_FAISABILITE`, commentaire) ; lieu, zone (territoire), normes ; ressources et inspecteurs
pressentis ; demande du client et pièces jointes de l'opportunité ; onglet Chiffrages (comparaison calculée des variantes).
Workflow : Brouillon → Validée (faisabilité obligatoire) → Annulée. « Non faisable » : bouton « Déclarer l'opportunité perdue »
(méthode native, motifs « Opportunity Lost Reason »).

### Chiffrage (variante)
Lien EFT obligatoire ; variante A, B, C… automatique ; libellé libre ; nom `<EFT>-<lettre>` ; une copie reçoit une nouvelle lettre,
une nouvelle version (amend) garde la sienne. Workflow : Brouillon → Chiffrée → Validée → Retenue / Non retenue (réversible) →
Annulée. Une seule Retenue par EFT : retenir une variante passe les autres « Non retenue ». Devis commandé → sa variante Retenue.
« Nouvelle variante » (EFT) : vide, prestations de l'opportunité (gammes), ou copie d'une variante (coûts recalculés).

### Phases et notifications (configuration)
Événements communs ajoutés : Chiffrage créé, Chiffrage validé, Variante retenue (état du workflow), EFT non faisable (faisabilité),
Devis créé, Devis envoyé (champ `Quotation.lsi_envoye` coché au premier e-mail envoyé depuis le devis). Profil tic : Étude technique
→ EFT validée ; Chiffrage → Chiffrage validé ; Validation Direction → Variante retenue ; Offre envoyée → Devis envoyé ; Gagnée →
Commande validée. Notifications natives (profil tic) : EFT non faisable (commercial + responsable du service), Chiffrage validé et
Variante retenue (commercial + Sales Manager), Devis validé et Devis envoyé (commercial), Opportunité gagnée (commercial +
responsable du service), Opportunité perdue (commercial + pilotes), en plus de l'entrée de phase et de l'Étude technique (pilotes).

## Reprise de l'existant — méthode et justification
1. **Renommage natif** (`patches/lot3b_renommer_eft_en_chiffrage`, avant synchronisation) : `frappe.rename_doc` sur les doctypes,
   le rapport, le format et le workflow. Les tables sont **renommées**, pas copiées : aucune ligne ne bouge, Frappe met à jour
   options de liens, versions, commentaires. C'est la méthode la plus sûre (pas de double écriture, pas de correspondance d'ids).
2. **Reprise** (`patches/lot3b_reprise_eft_variantes`, après synchronisation) : chaque ancienne EFT racine devient la variante A
   d'une nouvelle EFT qui **reprend son ancien nom** (les numéros connus des utilisateurs restent valables) ; deux anciennes EFT
   de la même opportunité deviennent A et B de la même EFT ; les versions suivent (`…-A-1`) ; statuts conservés ; devis et
   demandes de prix reliés au chiffrage et à l'EFT ; registre DÉMO repris.
3. **Contrôle** : chiffrages, positions et devis reliés comptés avant / après ; écart → exception, migrate arrêté, transaction annulée.
   Résultat sur tic (09/11) : 12 chiffrages, 188 positions, 3 devis avant = après ; 9 EFT créées.
4. **Retour arrière** : restaurer la sauvegarde prise juste avant le migrate
   (`bench --site tic.erpsys.ovh restore <fichier>`), puis revenir à la branche `ouverture-tests` et redémarrer.

## Fiche de test T3b (à l'écran)

| N° | Action | Attendu |
|---|---|---|
| T3b.1 | Opportunité → Créer → EFT (étude technique), deux fois | la même EFT s'ouvre ; une 2e EFT pour la même opportunité est refusée |
| T3b.2 | EFT : Actions → Valider sans faisabilité | refusé ; avec « Faisable » : Validée, phase « Étude technique » terminée (historique : EFT validée) |
| T3b.3 | EFT : « Nouvelle variante » → Prestations de l'opportunité | Chiffrage `<EFT>-A` avec les prestations et leurs gammes |
| T3b.4 | « Nouvelle variante » → Copie de A, libellé « Sans transport » | `<EFT>-B`, mêmes lignes, coûts recalculés, statut Brouillon |
| T3b.5 | EFT, onglet Chiffrages | tableau A / B : coût, prix, marge, marge %, statut, devis |
| T3b.6 | Valider A puis B (Chiffrer → Valider) | phase Chiffrage terminée ; notification « Chiffrage validé » (commercial, Sales Manager) |
| T3b.7 | B : Actions → Retenir | B Retenue, A Non retenue ; phase Validation Direction terminée ; notification « Variante retenue » |
| T3b.8 | A : Retenir (changement d'avis) | A Retenue, B Non retenue (réversible) |
| T3b.9 | A puis B : Créer → Créer l'offre client | un devis par variante ; Connexions : devis ↔ chiffrage ↔ EFT ↔ opportunité |
| T3b.10 | Devis B : Valider puis envoyer par e-mail au client | notifications « Devis validé » et « Devis envoyé » ; phase Offre envoyée terminée |
| T3b.11 | Devis B → Créer → Commande client, valider | B Retenue, A Non retenue ; opportunité Converted, phase Gagnée ; notification « Commande validée » |
| T3b.12 | Autre opportunité : EFT « Non faisable » + motif, enregistrer | notification « EFT non faisable » ; bouton « Déclarer l'opportunité perdue » → opportunité Perdue |
| T3b.13 | Type d'opportunité : changer l'événement de fin d'une phase (ex. Chiffrage → « Chiffrage créé ») | pris en compte dès la variante suivante, sans code |
| T3b.14 | Ancienne EFT (ex. EFT-2026-0002) | EFT en brouillon + variantes A (et B), devis reliés, chiffrage inchangé |

Tests automatiques : `test_variantes`, `test_etude` (+ toute la suite, 143 tests).
