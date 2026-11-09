"""Constantes métier centralisées : valeurs des listes de choix des doctypes de l'app (jamais de valeur TIC ici).

Toute chaîne comparée dans le code (mode, source du coût, statut, état de workflow…) est définie ici une seule fois ; les
listes de choix des doctypes (fichiers JSON) emploient les mêmes libellés.
"""

# ------------------------------------------------------------------ chiffrage : Type Position
A_COUT, PRIX_FIXE, SOUS_POSITION = "À coût", "Prix fixe", "Sous-position"  # mode
POOL, ARTICLE, FOURNISSEUR, MANUEL = "Pool de ressources", "Article", "Prix fournisseur", "Manuel"  # source du coût
SOMME = "Somme des sous-positions"  # prix fixe : coût = somme des sous-lignes
REGLE_SOUS = "Règle sur les sous-positions"  # prix fixe : les sous-lignes sont des choix ; coût = la retenue, sinon la règle
PLUS_ELEVE, MOINS_ELEVE, MOYENNE = "Plus élevé", "Moins élevé", "Moyenne"  # règle d'un pool ou d'un prix fixe « règle »

# Source du coût d'un article (Item / Item Group, champ lsi_source_cout)
DERNIER_PRIX, VALORISATION, LISTE_PRIX = "Dernier prix d'achat", "Valorisation", "Liste de prix d'achat"

# Champs de coût et de prix d'une position (vidés dans un modèle)
CHAMPS_COUT = ("cout_unitaire", "cout_total", "source_cout", "ressource", "ressource_doctype", "cout_manquant", "cout_en_attente",
	"demande_prix", "cout_manuel", "prix_unitaire", "prix_total", "prix_conseille", "marge", "taux_marge")

# ------------------------------------------------------------------ phases commerciales (Opportunity.lsi_phases)
A_VENIR, EN_COURS, TERMINEE, SAUTEE, SAUTEE_AUTO = "À venir", "En cours", "Terminée", "Sautée", "Sautée (auto)"
ANNULEE = "Annulée"  # phase finale annulée par son événement d'annulation (réouverture) ; peut être de nouveau atteinte
FAITES = (TERMINEE, SAUTEE, SAUTEE_AUTO)
GAGNEE, PERDUE = "Gagnée", "Perdue"  # phases finales (Parcours Phase.phase_finale)

# Déclencheurs d'un Evenement Phase
MANUEL_PHASE, CREATION, VALIDATION, ETAT_WORKFLOW, CHANGEMENT_STATUT, ANNULATION = (
	"Manuel", "Création", "Validation", "État du workflow", "Changement de statut", "Annulation")
QUITTE = "Quitte la valeur"  # sens d'un événement « valeur »

# Actions écrites dans l'historique des phases (en plus de TERMINEE, SAUTEE, SAUTEE_AUTO, GAGNEE, PERDUE)
REOUVERTURE, RETOUR_ARRIERE, RECONSTRUCTION = "Réouverture", "Retour arrière", "Reconstruction"

# Responsable d'une phase (Parcours Phase.type_responsable)
RESP_COMMERCIAL, RESP_ROLE, RESP_UTILISATEUR, RESP_PILOTE = "Commercial", "Rôle", "Utilisateur", "Pilote du département"

# Statuts natifs ERPNext lus par le code
OPP_FERMEES = ("Converted", "Lost", "Closed")  # opportunité close : son tableau des phases n'est plus reconstruit
