"""Module Logistique : de la commande client validée aux ordres de mission (OM).

Circuit : Commande client (validée) → bouton « Créer projet et besoin logistique » → Projet natif + Besoin Logistique (ressources
prévues extraites du chiffrage retenu) → la logistique planifie (dates, lieu, affectations nominatives, contrôles) → bouton
« Générer les OM » → un Ordre de Mission par prestation + une Tâche native par inspecteur.

Fichiers (une responsabilité chacun) :
- extraction    : bouton de la commande ; projet natif ; extraction des prestations et des ressources du chiffrage ;
- pools         : ressources d'un pool (mêmes filtres que le chiffrage) ; ressource_qualifiee (point d'entrée unique) ;
- planification : affectations complétées, occupations (ressource partagée dépliée), statut du besoin ;
- controles     : contrôles des affectations (pool, prestation, actif hors service, conflits, congés) ;
- om            : génération des OM et des tâches, annulation du besoin ;
- doctype/      : Besoin Logistique (+ Prestation, Ressource, Repartition, Affectation), Ordre de Mission (+ Ressource) ;
- public/       : écran de la commande client (sales_order.js).
"""
