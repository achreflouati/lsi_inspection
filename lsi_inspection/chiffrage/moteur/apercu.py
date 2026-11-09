"""Calcul en temps réel (sans enregistrer) : même moteur que l'enregistrement."""

import frappe
from frappe import _
from frappe.utils import cstr

from lsi_inspection.chiffrage.moteur.calcul import _etapes_de, calculer
from lsi_inspection.chiffrage.moteur.organisation import organiser


CHAMPS_APERCU_POSITION = ("numero", "groupe", "parente", "etape", "type_position", "mode", "tarif", "stock_disponible", "etapes",
	"cout_unitaire", "cout_total", "source_cout", "ressource", "ressource_doctype", "cout_manquant", "cout_en_attente", "prix_unitaire",
	"prix_total", "prix_conseille", "marge", "taux_marge", "retenue")


@frappe.whitelist(methods=["POST"])
def apercu(doc):
	"""Calcul en temps réel (sans enregistrer) : même moteur qu'à l'enregistrement. Renvoie les valeurs calculées par ligne,
	l'étape principale de chaque position (couleurs) et les totaux. Une erreur de structure est renvoyée comme message."""
	d = frappe.get_doc(frappe.parse_json(doc))
	if not frappe.has_permission("Chiffrage", "write") and not frappe.has_permission("Chiffrage", "create"):
		frappe.throw(_("Pas de droit sur le chiffrage."), frappe.PermissionError)
	if d.docstatus != 0:
		return {}
	try:
		organiser(d)  # n° et groupes donnés pendant la saisie, comme à l'enregistrement
		calculer(d)
	except frappe.ValidationError as e:
		frappe.clear_messages()
		return dict(erreur=cstr(e))
	par_num = {p.numero: p for p in d.positions}
	return dict(
		positions={p.name: dict({c: p.get(c) for c in CHAMPS_APERCU_POSITION}, etape_principale=(_etapes_de(d, p, par_num) or [(None, 0)])[0][0])
			for p in d.positions},
		groupes={g.name: dict(cout_total=g.cout_total, prix_total=g.prix_total, marge=g.marge, taux_marge=g.taux_marge, etapes=g.etapes)
			for g in d.groupes},
		totaux_etapes=[dict(etape=t.etape, cout_total=t.cout_total, prix_total=t.prix_total, marge=t.marge, taux_marge=t.taux_marge)
			for t in d.totaux_etapes],
		total_cout=d.total_cout, total_prix=d.total_prix, total_marge=d.total_marge, taux_marge=d.taux_marge, cout_incomplet=d.cout_incomplet,
	)
