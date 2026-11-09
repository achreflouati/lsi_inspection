"""Moteur générique de chiffrage. Aucune valeur métier : tout vient de la configuration (Type Position, gammes, pools) et des
fiches natives (employés, immobilisations, prix d'achat, offres fournisseurs).

Modules (une responsabilité chacun) :
- formules      : calculs purs (marge %, prix conseillé, règle, tri des n°) — sans base de données ;
- couts         : coût unitaire d'une ligne selon son type (pool, article, fournisseur, manuel, prix fixe « règle ») ;
- organisation  : prestation → groupe, numérotation, sous-lignes ;
- gammes        : application des gammes ;
- calcul        : calcul complet du document (hook validate) ;
- apercu        : calcul en temps réel sans enregistrer ;
- actions       : actions de l'écran (menu Positions) ;
- modeles       : modèles réutilisables.

API publique (utilisée par les autres modules de l'app, les tests et l'écran) : importée ci-dessous.
"""

from lsi_inspection.chiffrage.moteur.actions import (  # noqa: F401
	choisir_ressource, demander_prix, historique_achat, offre_fournisseur, partager_groupe, repartir_prorata, voir_ressources)
from lsi_inspection.chiffrage.moteur.apercu import apercu  # noqa: F401
from lsi_inspection.chiffrage.moteur.calcul import calculer, eft_validate  # noqa: F401
from lsi_inspection.chiffrage.moteur.couts import candidat_retenu, facteur_uom, prix_fournisseurs, stock_disponible, type_par_defaut, valorisation  # noqa: F401
from lsi_inspection.chiffrage.moteur.formules import cle_numero  # noqa: F401
from lsi_inspection.chiffrage.moteur.gammes import ajouter_gamme, appliquer_gammes, numeros_gamme  # noqa: F401
from lsi_inspection.chiffrage.moteur.modeles import charger_modele, enregistrer_modele, modele_validate  # noqa: F401
from lsi_inspection.chiffrage.moteur.organisation import organiser  # noqa: F401
