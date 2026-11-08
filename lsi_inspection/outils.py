"""Outils génériques (aucune valeur métier)."""

import frappe
from frappe import _


def verifier_obligatoires(doc, method=None):
	"""Contrôle côté serveur des champs de l'app (préfixe lsi_) « obligatoires si » (mandatory_depends_on).

	Frappe v15 ne l'évalue que dans le navigateur : une action de workflow, l'API ou un import passeraient outre.
	La condition est celle du champ (fixture) : elle se règle à l'écran, pas dans le code."""
	manquants = []
	for df in doc.meta.fields:
		cond = df.get("mandatory_depends_on") or ""
		if not df.fieldname.startswith("lsi_") or not cond.startswith("eval:") or doc.get(df.fieldname):
			continue
		if frappe.safe_eval(cond[5:], None, {"doc": doc.as_dict()}):
			manquants.append(_(df.label or df.fieldname))
	if manquants:
		frappe.throw(_("Champ(s) obligatoire(s) : {0}").format(", ".join(manquants)), frappe.MandatoryError, title=_("Champs manquants"))
