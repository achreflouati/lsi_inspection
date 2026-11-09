"""Parcours des phases d'un type d'opportunité (table « Parcours Phase ») et contrôles de sa configuration."""

import frappe
from frappe import _
from frappe.utils import cint

from lsi_inspection.constants import GAGNEE, PERDUE


def type_parcours(opportunity_type):
	"""Type dont le parcours (et les notifications) s'appliquent : le type lui-même s'il a un parcours, sinon le type par défaut."""
	if opportunity_type and frappe.db.exists("Parcours Phase", {"parent": opportunity_type, "parenttype": "Opportunity Type"}):
		return opportunity_type
	return frappe.db.get_value("Opportunity Type", {"lsi_parcours_defaut": 1}, "name")


def phases_parcours(opportunity_type):
	"""Phases du parcours dans l'ordre ; plusieurs lignes d'une même phase = co-responsables."""
	t = type_parcours(opportunity_type)
	if not t:
		return []
	out = {}
	for r in frappe.get_all("Parcours Phase", filters={"parent": t, "parenttype": "Opportunity Type"}, fields=["ordre", "phase",
			"type_responsable", "role", "utilisateur", "departement", "duree_cible", "evenement_fin", "obligatoire", "phase_finale",
			"evenement_annulation"],
			order_by="ordre asc, idx asc"):
		ph = out.setdefault(r.phase, frappe._dict(phase=r.phase, ordre=cint(r.ordre), lignes=[], duree_cible=0, evenement_fin=None,
			obligatoire=0, phase_finale=None, evenement_annulation=None))
		ph.lignes.append(r)
		ph.duree_cible = ph.duree_cible or cint(r.duree_cible)
		ph.evenement_fin = ph.evenement_fin or r.evenement_fin
		ph.obligatoire = ph.obligatoire or cint(r.obligatoire)
		ph.phase_finale = ph.phase_finale or r.phase_finale
		ph.evenement_annulation = ph.evenement_annulation or r.evenement_annulation
	return sorted(out.values(), key=lambda x: x.ordre)


def type_validate(doc, method=None):
	"""Opportunity Type : un seul parcours par défaut, une seule phase finale de chaque sorte, Gagnée en dernier."""
	if cint(doc.get("lsi_parcours_defaut")):
		autre = frappe.db.get_value("Opportunity Type", {"lsi_parcours_defaut": 1, "name": ("!=", doc.name)})
		if autre:
			frappe.throw(_("Le type {0} porte déjà le parcours par défaut.").format(autre))
	finales = {}
	for r in doc.get("lsi_parcours") or []:
		if r.phase_finale:
			finales.setdefault(r.phase_finale, set()).add(r.phase)
	for f, phases in finales.items():
		if len(phases) > 1:
			frappe.throw(_("Une seule phase finale « {0} » par parcours ({1}).").format(f, ", ".join(sorted(phases))))
	gagnee = finales.get(GAGNEE)
	if gagnee:
		g = next(iter(gagnee))
		max_ordre = max((cint(r.ordre) for r in doc.lsi_parcours if r.phase_finale != PERDUE), default=0)
		if any(cint(r.ordre) < max_ordre for r in doc.lsi_parcours if r.phase == g):
			frappe.throw(_("La phase finale « Gagnée » ({0}) doit être la dernière du parcours (hors phase Perdue).").format(g))
