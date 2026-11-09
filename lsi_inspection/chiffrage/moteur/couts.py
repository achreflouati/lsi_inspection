"""Coût unitaire d'une ligne selon son type de position : pool de ressources, article, prix fournisseur, manuel,
prix fixe « règle » (candidat retenu). Jamais d'exception : un coût introuvable donne « coût manquant » avec sa raison."""

import json

import frappe
from frappe.query_builder.functions import Sum
from frappe import _
from frappe.utils import cint, cstr, flt, nowdate

from lsi_inspection.constants import ARTICLE, DERNIER_PRIX, FOURNISSEUR, LISTE_PRIX, MANUEL, POOL, VALORISATION
from lsi_inspection.chiffrage.moteur.formules import appliquer_regle, cle_numero




def facteur_uom(de, vers):
	"""Nombre d'unités « vers » dans une unité « de » (UOM Conversion Factor natif, dans un sens ou dans l'autre)."""
	if not de or not vers or de == vers:
		return 1
	v = frappe.db.get_value("UOM Conversion Factor", {"from_uom": de, "to_uom": vers}, "value")
	if flt(v):
		return flt(v)
	v = frappe.db.get_value("UOM Conversion Factor", {"from_uom": vers, "to_uom": de}, "value")
	return 1 / flt(v) if flt(v) else None


def _valeur_groupe(item_code, champ):
	"""Valeur sur l'article, sinon sur son groupe d'articles puis les groupes parents."""
	valeur, groupe = frappe.db.get_value("Item", item_code, [champ, "item_group"]) or (None, None)
	while not valeur and groupe:
		valeur, groupe = frappe.db.get_value("Item Group", groupe, [champ, "parent_item_group"]) or (None, None)
	return valeur


def type_par_defaut(item_code):
	"""Type de position par défaut : celui de l'article, sinon de son groupe d'articles (puis groupes parents)."""
	return _valeur_groupe(item_code, "lsi_type_position") if item_code else None


def _types(doc):
	for p in doc.get("positions") or []:
		if not p.type_position and p.item_code:  # ligne en cours de saisie (sans article) : ignorée ici
			p.type_position = type_par_defaut(p.item_code)  # vide si ni l'article ni son groupe n'en ont : coût manquant
	noms = {p.type_position for p in doc.get("positions") or [] if p.type_position and frappe.db.exists("Type Position", p.type_position)}
	return {n: frappe.get_doc("Type Position", n) for n in noms}


def valorisation(item_code):
	"""Valorisation du stock : moyenne pondérée des entrepôts (Bin natif) ; à défaut, valorisation de la fiche article."""
	Bin = frappe.qb.DocType("Bin")
	r = (frappe.qb.from_(Bin).select(Sum(Bin.stock_value), Sum(Bin.actual_qty))
		.where((Bin.item_code == item_code) & (Bin.actual_qty > 0))).run()
	valeur, qty = r[0] if r else (0, 0)
	return flt(valeur) / flt(qty) if flt(qty) else flt(frappe.db.get_value("Item", item_code, "valuation_rate"))


def stock_disponible(item_code):
	"""Quantité en stock de l'article, tous entrepôts (Bin natif)."""
	Bin = frappe.qb.DocType("Bin")
	return flt(frappe.qb.from_(Bin).select(Sum(Bin.actual_qty)).where(Bin.item_code == item_code).run()[0][0])


def _ressources(t, pool, titre=None):
	"""Ressources du pool avec leur coût. Pool d'articles sans champ de coût : coût de chaque article selon sa propre
	« Source du coût » (article, sinon groupe : dernier prix d'achat, valorisation ou liste de prix d'achat)."""
	filtres = {t.champ_appartenance: pool}
	filtres.update(json.loads(t.filtres_ressources or "{}") or {})
	champs = ["name"] + ([f"{titre} as titre"] if titre else [])
	if t.ressource_doctype == "Item" and not t.champ_cout:
		lignes = frappe.get_all("Item", filters=filtres, fields=champs)
		for r in lignes:
			r.cout = (_cout_article(frappe._dict(item_code=r.name, uom=None))[0]) or 0
		return lignes
	return frappe.get_all(t.ressource_doctype, filters=filtres, fields=champs + [f"{t.champ_cout} as cout"])


def _cout_pool(p, t):
	pool_dt, pool = frappe.db.get_value("Item", p.item_code, ["lsi_pool_doctype", "lsi_pool"]) or (None, None)
	if pool_dt != t.pool_doctype or not pool:
		return None, _("article sans pool {0}").format(_(t.pool_doctype))
	ressources = [r for r in _ressources(t, pool) if flt(r.cout) > 0]
	p.ressource_doctype = t.ressource_doctype
	choisie = next((r for r in ressources if p.ressource and r.name == p.ressource), None)
	if choisie:
		cout, trace = flt(choisie.cout), _("ressource choisie : {0}").format(p.ressource)
	else:
		p.ressource = None
		cout = appliquer_regle([flt(r.cout) for r in ressources], t.regle)
		trace = _("règle du pool : {0} ({1} ressource(s) de {2})").format(_(t.regle or "Plus élevé"), len(ressources), pool)
	if cout is None:
		return None, _("aucune ressource avec un coût dans le pool {0}").format(pool)
	f = facteur_uom(t.uom_cout or p.uom, p.uom)
	if not f:
		return None, _("conversion {0} → {1} absente (UOM Conversion Factor)").format(t.uom_cout, p.uom)
	if f != 1:
		trace += _(" ; converti {0} → {1} (÷ {2})").format(t.uom_cout, p.uom, f)
	return cout / f, trace


def _cout_article(p):
	source = _valeur_groupe(p.item_code, "lsi_source_cout") or DERNIER_PRIX
	item = frappe.db.get_value("Item", p.item_code, ["last_purchase_rate", "valuation_rate", "stock_uom"], as_dict=True)
	if not item:
		return None, _("article introuvable")
	if source == VALORISATION:
		cout = valorisation(p.item_code)
	elif source == LISTE_PRIX:
		liste = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		cout = flt(frappe.db.get_value("Item Price", {"item_code": p.item_code, "price_list": liste, "buying": 1}, "price_list_rate"))
		source = f"{source} ({liste})"
	else:
		cout = flt(item.last_purchase_rate)
	if not cout:
		return None, _("{0} : aucun coût").format(source)
	if p.uom and item.stock_uom and p.uom != item.stock_uom:
		cf = flt(frappe.db.get_value("UOM Conversion Detail", {"parent": p.item_code, "uom": p.uom}, "conversion_factor"))
		if not cf:
			return None, _("unité {0} non définie sur l'article (conversions)").format(p.uom)
		cout *= cf
	return cout, source


def prix_fournisseurs(item_code):
	"""Prix d'achat par fournisseur (Item Price) et offres fournisseurs validées encore valables de l'article."""
	prix = [dict(fournisseur=r.supplier, prix=flt(r.price_list_rate), origine=_("Prix d'achat"), reference=r.name)
		for r in frappe.get_all("Item Price", filters={"item_code": item_code, "buying": 1, "supplier": ("is", "set")},
			fields=["name", "supplier", "price_list_rate"])]
	sq, sqi = frappe.qb.DocType("Supplier Quotation"), frappe.qb.DocType("Supplier Quotation Item")
	offres = (frappe.qb.from_(sqi).join(sq).on(sq.name == sqi.parent).select(sq.name, sq.supplier, sqi.rate)
		.where((sqi.item_code == item_code) & (sq.docstatus == 1) & (sq.valid_till.isnull() | (sq.valid_till >= nowdate())))).run(as_dict=True)
	for r in offres:
		prix.append(dict(fournisseur=r.supplier, prix=flt(r.rate), origine=_("Offre fournisseur"), reference=r.name))
	return [x for x in prix if x["prix"] > 0]


def _cout_fournisseur(p, t):
	prix = prix_fournisseurs(p.item_code)
	if not prix:
		if p.demande_prix:
			p.cout_en_attente = 1
			return None, _("coût en attente : demande de prix {0}").format(p.demande_prix)
		return None, _("aucun prix fournisseur")
	cout = appliquer_regle([x["prix"] for x in prix], t.regle)
	return cout, _("prix fournisseurs : {0} ({1} prix)").format(_(t.regle or "Plus élevé"), len(prix))


def _cout_securise(p, t):
	"""Le coût d'une ligne ne bloque jamais le chiffrage : article absent, sans prix, pool vide ou mal paramétré → coût manquant,
	avec la raison dans « Source du coût »."""
	if not frappe.db.exists("Item", p.item_code):
		p.cout_unitaire, p.cout_manquant, p.cout_en_attente = 0, 1, 0
		p.source_cout = _("article introuvable : {0}").format(p.item_code)
		return
	frappe.db.savepoint("lsi_cout")
	try:
		_cout_position(p, t)
	except Exception as e:  # paramétrage incohérent (ex. champ de coût inexistant) : signalé sur la ligne, jamais une erreur
		frappe.db.rollback(save_point="lsi_cout")
		frappe.clear_messages()
		p.cout_unitaire, p.cout_manquant, p.cout_en_attente = 0, 1, 0
		p.source_cout = _("coût non calculable ({0}) : vérifier le type de position {1}").format(cstr(e)[:140], t.name)


def _cout_position(p, t):
	p.cout_manquant = p.cout_en_attente = 0
	if cint(p.cout_manuel) or t.source_cout == MANUEL:
		p.source_cout = _("coût saisi")
		return
	if t.source_cout == POOL:
		cout, trace = _cout_pool(p, t)
	elif t.source_cout == ARTICLE:
		cout, trace = _cout_article(p)
	elif t.source_cout == FOURNISSEUR:
		cout, trace = _cout_fournisseur(p, t)
	else:
		cout, trace = None, _("source {0} : réservée aux positions à prix fixe").format(t.source_cout)
	p.source_cout = trace
	if cout is None:
		p.cout_unitaire = 0
		p.cout_manquant = 0 if p.cout_en_attente else 1
	else:
		p.cout_unitaire = cout


def candidat_retenu(p, kids, t):
	"""Prix fixe « règle » : (sous-position retenue, coût ramené à l'unité de la ligne, liste des candidats).
	La sous-position cochée « Retenue » l'emporte ; sinon la règle du type (plus élevé par défaut) sur les coûts unitaires."""
	candidats = []
	for k in sorted(kids, key=lambda x: cle_numero(x.numero)):
		f = facteur_uom(p.uom, k.uom) if k.uom and p.uom else 1  # unités de la sous-position dans une unité de la ligne
		candidats.append((k, flt(k.cout_unitaire) * f if f else None))
	cochees = [c for c in candidats if cint(c[0].get("retenue"))]
	for k, _v in cochees[1:]:
		k.retenue = 0  # une seule sous-position retenue
	if cochees:
		return cochees[0][0], cochees[0][1], candidats
	valeurs = [v for _k, v in candidats if v is not None and not cint(_k.cout_manquant)]
	cible = appliquer_regle(valeurs, t.regle)
	if cible is None:
		return None, None, candidats
	k = min((c for c in candidats if c[1] is not None), key=lambda c: abs(c[1] - cible))[0]
	return k, cible, candidats


def _cout_regle_sous(p, kids, t):
	"""Les sous-positions (ex. 3 films) gardent leur coût réel et ne sont pas additionnées : la ligne prend le coût de la
	retenue, sinon le plus élevé (règle du type) ; coût total = coût unitaire × quantité. « Coût manuel » reste possible."""
	p.cout_en_attente = 1 if any(cint(k.cout_en_attente) for k in kids) else 0
	if not kids:
		p.cout_unitaire, p.cout_total, p.cout_manquant, p.source_cout = 0, 0, 1, _("aucune sous-position")
		return
	k, cout, candidats = candidat_retenu(p, kids, t)
	if k is None or cout is None or (cint(k.get("retenue")) and cint(k.cout_manquant)):
		p.cout_unitaire, p.cout_total, p.cout_manquant = 0, 0, 1
		p.source_cout = _("aucune sous-position avec un coût") if k is None else _("sous-position {0} sans coût ou sans conversion d'unité").format(k.numero or k.item_code)
		return
	p.cout_unitaire, p.cout_manquant = cout, 0
	p.cout_total = flt(cout) * flt(p.qty)
	nom = k.designation or k.item_code
	p.source_cout = (_("sous-position retenue : {0}").format(nom) if cint(k.get("retenue"))
		else _("{0} de {1} sous-position(s) : {2}").format(_(t.regle or "Plus élevé"), len(candidats), nom))
