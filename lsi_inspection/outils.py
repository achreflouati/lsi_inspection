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


def _famille(df):
	"""Famille du référentiel visée par un champ Link vers Type Metier (lue dans ses link_filters)."""
	try:
		for f in frappe.parse_json(df.get("link_filters") or "[]") or []:
			if len(f) >= 4 and f[1] == "famille" and f[2] == "=":
				return f[3]
	except Exception:
		return None
	return None


def _defaut(famille, cache):
	if famille not in cache:
		cache[famille] = frappe.db.get_value("Type Metier", {"famille": famille, "par_defaut": 1, "actif": 1})
	return cache[famille]


def defauts_referentiel(doc, method=None):
	"""Champs vides pointant vers le référentiel (Type Metier filtré par famille) : valeur « Par défaut » de la famille.
	Document et lignes de ses tables. Aucune valeur en dur : la famille vient du champ, la valeur du référentiel."""
	cache = {}

	def visible(d, df):
		"""Champ affiché ? (condition d'affichage du champ ou de sa section)"""
		conds = [df.get("depends_on")]
		section = None
		for f in d.meta.fields:
			if f.fieldtype in ("Section Break", "Tab Break"):
				section = f
			if f.fieldname == df.fieldname:
				break
		if section:
			conds.append(section.get("depends_on"))
		ctx = {"doc": d.as_dict(), "parent": doc.as_dict()}
		return all(frappe.safe_eval(c[5:], None, ctx) for c in conds if c and c.startswith("eval:"))

	def remplir(d):
		for df in d.meta.get_link_fields():
			if df.options == "Type Metier" and not d.get(df.fieldname) and visible(d, df):
				famille = _famille(df)
				if famille and _defaut(famille, cache):
					d.set(df.fieldname, _defaut(famille, cache))

	remplir(doc)
	for tdf in doc.meta.get_table_fields():
		for row in doc.get(tdf.fieldname) or []:
			remplir(row)
