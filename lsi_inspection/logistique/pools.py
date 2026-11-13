"""Pools de ressources côté logistique : quelles ressources nominatives (Employee, Asset, Item) appartiennent au pool d'une
ligne prévue, et la ressource est-elle qualifiée pour la mission.

Mêmes filtres que le chiffrage (chiffrage/moteur/couts.py, _ressources) : {Type Position.champ_appartenance: pool} complété
par Type Position.filtres_ressources (JSON, ex. {"status": "Active"}). Le calcul des coûts de _ressources n'est pas repris :
la logistique n'a besoin que de l'appartenance.
"""

import json

import frappe
from frappe import _


def filtres_pool(type_position, pool):
	"""Filtres frappe.get_all des ressources du pool : {champ d'appartenance: pool} + filtres du type de position.
	Entrées : nom du Type Position, nom du pool (ex. une Designation). Sortie : (doctype des ressources, filtres)."""
	t = frappe.get_cached_doc("Type Position", type_position)
	filtres = {t.champ_appartenance: pool}
	filtres.update(json.loads(t.filtres_ressources or "{}") or {})
	return t.ressource_doctype, filtres


def ressource_qualifiee(ressource, pool, date=None):
	"""POINT D'ENTRÉE UNIQUE : la ressource peut-elle être affectée sur une ligne de ce pool à cette date ?
	- ressource : {"doctype": "Employee", "name": "HR-EMP-00002"} ;
	- pool : {"type_position": …, "pool": …} (ligne prévue du Besoin Logistique) ;
	- date : date de début de l'affectation (inutilisée aujourd'hui ; servira aux certifications avec expiration).
	Sortie : (True, None) ou (False, raison lisible).
	Aujourd'hui : appartenance au pool seulement. À enrichir ici (certifications, habilitations…) et nulle part ailleurs."""
	ressource, pool = frappe._dict(ressource), frappe._dict(pool)
	doctype, filtres = filtres_pool(pool.type_position, pool.pool)
	if doctype != ressource.doctype:
		return False, _("{0} n'est pas un(e) {1}.").format(ressource.name, _(doctype))
	if not frappe.get_all(doctype, filters=dict(filtres, name=ressource.name), limit=1):
		return False, _("{0} n'appartient pas au pool {1} (ou n'est pas disponible : {2}).").format(
			ressource.name, pool.pool, _("filtres du type de position {0}").format(pool.type_position))
	return True, None


@frappe.whitelist()
def ressources_du_pool(type_position, pool):
	"""Écran : filtres de la liste déroulante « Ressource » d'une affectation (mêmes filtres que le contrôle serveur).
	Sortie : {"doctype": doctype des ressources, "filters": filtres}."""
	frappe.has_permission("Besoin Logistique", "read", throw=True)
	doctype, filtres = filtres_pool(type_position, pool)
	return dict(doctype=doctype, filters=filtres)


def nom_ressource(doctype, name):
	"""Libellé lisible d'une ressource (champ titre du doctype : employee_name, asset_name, item_name…)."""
	titre = frappe.get_meta(doctype).get_title_field()
	return (frappe.db.get_value(doctype, name, titre) if titre and titre != "name" else None) or name
