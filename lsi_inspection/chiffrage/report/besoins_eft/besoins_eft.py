# Copyright (c) 2026, achref louati and Contributors
# See license.txt
"""Besoins de l'EFT — calculés (rien de stocké) : par étape, jours d'inspecteurs par désignation, jours d'équipements par
catégorie, articles, sous-traitance. Lignes : positions à coût vendues (quantité > 0) et sous-positions ; les positions à prix
fixe sont représentées par leurs sous-positions ; répartition par étape selon l'EFT. Conversion en jours : UOM Conversion Factor."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from lsi_inspection.chiffrage.moteur import PRIX_FIXE, POOL, FOURNISSEUR, REGLE_SOUS, _etapes_de, candidat_retenu, facteur_uom


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.eft:
		return colonnes(), []
	doc = frappe.get_doc("EFT", filters.eft)
	doc.check_permission("read")
	return colonnes(), besoins(doc)


def colonnes():
	return [
		dict(fieldname="etape", label=_("Étape"), fieldtype="Link", options="Item", width=260),
		dict(fieldname="categorie", label=_("Catégorie"), fieldtype="Data", width=170),
		dict(fieldname="ressource", label=_("Pool / article"), fieldtype="Data", width=260),
		dict(fieldname="quantite", label=_("Quantité"), fieldtype="Float", width=100),
		dict(fieldname="uom", label=_("Unité"), fieldtype="Link", options="UOM", width=90),
		dict(fieldname="jours", label=_("En jours"), fieldtype="Float", width=90),
	]


def besoins(doc):
	par_num = {p.numero: p for p in doc.positions}
	types = {t: frappe.get_cached_value("Type Position", t, ["source_cout", "pool_doctype"], as_dict=True)
		for t in {p.type_position for p in doc.positions if p.type_position}}
	cumul = defaultdict(float)
	# prix fixe « règle » (ex. Film et ses 3 films possibles) : seul le candidat retenu est un besoin, pour la quantité de la ligne
	remplaces = {}
	for p in doc.positions:
		if p.mode == PRIX_FIXE and p.type_position and types[p.type_position].source_cout == REGLE_SOUS:
			kids = [k for k in doc.positions if k.parente == p.numero]
			t = frappe.get_cached_doc("Type Position", p.type_position)
			k, _c, _l = candidat_retenu(p, kids, t)
			for x in kids:
				remplaces[x.name] = (k is not None and x.name == k.name, p)
	for p in doc.positions:
		if p.name in remplaces:
			retenu, parent = remplaces[p.name]
			if not retenu:
				continue
			p = frappe._dict(p.as_dict(), qty=flt(parent.qty) * (facteur_uom(parent.uom, p.uom) or 1) if parent.uom and p.uom else flt(parent.qty))
		if p.mode == PRIX_FIXE or not flt(p.qty) or not p.type_position:
			continue
		t = types[p.type_position]
		if t.source_cout == POOL:
			categorie = _(t.pool_doctype)
			ressource = frappe.db.get_value("Item", p.item_code, "lsi_pool") or p.item_code
		elif t.source_cout == FOURNISSEUR:
			categorie, ressource = _("Sous-traitance"), p.item_code
		else:
			categorie, ressource = _("Article"), p.item_code
		for etape, part in _etapes_de(doc, p, par_num) or [(None, 1)]:
			cumul[(etape, categorie, ressource, p.uom)] += flt(p.qty) * part
	lignes = []
	for (etape, categorie, ressource, uom), qty in sorted(cumul.items(), key=lambda x: (x[0][0] or "", x[0][1], x[0][2])):
		f = facteur_uom(uom, "Jour") if uom else None  # nombre de jours dans une unité (Heure → 1/8), None si pas de conversion
		jours = qty * f if f else None
		lignes.append(dict(etape=etape, categorie=categorie, ressource=ressource, quantite=round(qty, 3), uom=uom,
			jours=round(jours, 3) if jours is not None else None))
	return lignes
