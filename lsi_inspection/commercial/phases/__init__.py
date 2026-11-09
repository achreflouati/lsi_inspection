"""Moteur générique des phases commerciales de l'opportunité. Aucune valeur métier : tout vient de la configuration.

- parcours     : table « Parcours Phase » du type d'opportunité (ou du type « parcours par défaut ») et ses contrôles ;
- responsables : qui est responsable d'une phase (commercial, rôle, utilisateur, pilote du département) ;
- tableau      : tableau des phases de l'opportunité, historique en ajout seul, en-tête (sales_stage), ToDo ;
- evenements   : événements de fin de phase (Evenement Phase) détectés sur n'importe quel document ;
- ecran        : hooks de l'opportunité et du type d'opportunité, bouton « Terminer ma phase ».

Notifications : 100 % natives (Value Change sur sales_stage, Days After sur lsi_echeance_phase…), configurées à l'écran.
API publique ci-dessous (hooks, écran, tests).
"""

from lsi_inspection.commercial.phases.ecran import (  # noqa: F401
	infos_phases, opportunity_on_update, opportunity_validate, terminer_phase, type_on_update)
from lsi_inspection.commercial.phases.evenements import evenements_actifs, sur_document, traiter_differes, vider_cache_evenements  # noqa: F401
from lsi_inspection.commercial.phases.parcours import phases_parcours, type_parcours, type_validate  # noqa: F401
from lsi_inspection.commercial.phases.tableau import CHAMPS_HISTO, construire, courante  # noqa: F401
