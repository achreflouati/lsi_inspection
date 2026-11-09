"""Calcul complet d'un chiffrage : contrôle de structure, coûts, prix fixes, prix et marges, totaux par groupe, par prestation
et du document. Appelé à chaque enregistrement d'un brouillon (validate) et par l'aperçu en temps réel."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from lsi_inspection.constants import PRIX_FIXE, REGLE_SOUS, SOUS_POSITION
from lsi_inspection.chiffrage.moteur.couts import _cout_regle_sous, _cout_securise, _types, _valeur_groupe, stock_disponible
from lsi_inspection.chiffrage.moteur.formules import cle_numero, libelle_parts, prix_conseille, taux
from lsi_inspection.chiffrage.moteur.gammes import appliquer_gammes
from lsi_inspection.chiffrage.moteur.organisation import organiser


def valider_chiffrage(doc, method=None):
	"""Chiffrage.validate : brouillon → gammes appliquées, organisation, calcul ; document validé : coûts figés."""
	if doc.docstatus != 0:
		return
	appliquer_gammes(doc)
	organiser(doc)
	calculer(doc)


def calculer(doc):
	"""Calcule toutes les lignes et tous les totaux du document (sans enregistrer)."""
	positions = doc.get("positions") or []
	types = _types(doc)
	par_num, enfants = _structure(positions, types)
	_couts_lignes(positions, types)
	_couts_prix_fixe(positions, enfants, types)
	_prix_et_marges(positions)
	libelles = {e.prestation: e.libelle or e.prestation for e in doc.get("etapes") or []}
	vendues = [p for p in positions if not p.parente]
	for p in positions:
		p.etapes = libelle_parts(_etapes_de(doc, p, par_num), libelles)
	_totaux_groupes(doc, vendues, par_num, libelles)
	_totaux_etapes(doc, vendues, par_num, libelles)
	_totaux_document(doc, vendues)
	doc.set("positions", sorted(positions, key=lambda p: cle_numero(p.numero)))
	for i, p in enumerate(doc.positions, 1):
		p.idx = i


def _structure(positions, types):
	"""Contrôle la structure (n° uniques, sous-ligne sous un prix fixe) ; renvoie (positions par n°, sous-lignes par parente)."""
	par_num = {}
	for p in positions:
		if not p.numero:
			continue  # ligne en cours de saisie
		if p.numero in par_num:
			frappe.throw(_("Position {0} en double.").format(p.numero))
		par_num[p.numero] = p
	enfants = defaultdict(list)
	for p in positions:
		t = types.get(p.type_position)
		p.mode = t.mode if t else None
		if p.parente:
			parent = par_num.get(p.parente)
			if not parent or (types.get(parent.type_position) and types[parent.type_position].mode != PRIX_FIXE):
				frappe.throw(_("Position {0} : la parente {1} doit être une position à prix fixe.").format(p.numero, p.parente))
			if p.mode == PRIX_FIXE:
				frappe.throw(_("Position {0} : une sous-position ne peut pas être à prix fixe.").format(p.numero))
			enfants[p.parente].append(p)
			p.groupe = p.groupe or parent.groupe
		elif p.mode == SOUS_POSITION:
			frappe.throw(_("Position {0} : le type {1} ne s'emploie que sous une position à prix fixe.").format(p.numero, p.type_position))
		p.tarif = 1 if not p.parente and flt(p.qty) == 0 else 0
		p.stock_disponible = stock_disponible(p.item_code) if frappe.db.get_value("Item", p.item_code, "is_stock_item") else 0
	return par_num, enfants


def _couts_lignes(positions, types):
	"""Coût unitaire et total de chaque ligne qui n'est pas un prix fixe."""
	for p in positions:
		if not p.item_code:  # ligne en cours de saisie : pas encore d'article
			p.cout_unitaire, p.cout_total, p.cout_manquant, p.source_cout = 0, 0, 1, _("article à choisir")
		elif p.mode == PRIX_FIXE:
			continue
		elif p.type_position in types:
			_cout_securise(p, types[p.type_position])
			p.cout_total = flt(p.cout_unitaire) * flt(p.qty)
		else:
			p.cout_unitaire, p.cout_total, p.cout_manquant = 0, 0, 1
			p.source_cout = _("type de position à choisir (ni sur la ligne, ni sur l'article, ni sur son groupe)")


def _couts_prix_fixe(positions, enfants, types):
	"""Prix fixe : coût manuel, sinon la sous-ligne retenue / la règle (type « règle »), sinon la somme des sous-lignes."""
	for p in positions:
		if p.mode != PRIX_FIXE:
			continue
		if not flt(p.qty_base):
			p.qty_base = p.qty
		kids = enfants.get(p.numero, [])
		p.cout_manquant = p.cout_en_attente = 0
		t = types.get(p.type_position)
		if cint(p.cout_manuel):
			p.source_cout = _("coût saisi")
			p.cout_total = flt(p.cout_unitaire) * flt(p.qty)
		elif t and t.source_cout == REGLE_SOUS:
			_cout_regle_sous(p, kids, t)
		else:
			p.cout_total = sum(flt(k.cout_total) for k in kids)
			p.cout_unitaire = p.cout_total / flt(p.qty) if flt(p.qty) else p.cout_total
			p.cout_manquant = 1 if not kids or any(cint(k.cout_manquant) for k in kids) else 0
			p.cout_en_attente = 1 if any(cint(k.cout_en_attente) for k in kids) else 0
			p.source_cout = _("somme de {0} sous-position(s)").format(len(kids)) if kids else _("aucune sous-position")


def _prix_et_marges(positions):
	"""Prix, marge et prix conseillé des lignes vendues ; une sous-ligne n'a ni prix ni marge."""
	for p in positions:
		if p.parente:
			p.prix_unitaire = p.prix_total = p.marge = p.taux_marge = p.prix_conseille = 0
			continue
		p.prix_total = flt(p.prix_unitaire) * flt(p.qty)
		p.marge = p.prix_total - flt(p.cout_total)
		p.taux_marge = taux(p.marge, p.prix_total)
		p.prix_conseille = prix_conseille(flt(p.cout_unitaire), flt(_valeur_groupe(p.item_code, "lsi_marge_cible")))


def _totaux_groupes(doc, vendues, par_num, libelles):
	"""Coût, prix, marge et prestations de chaque groupe."""
	for g in doc.get("groupes") or []:
		lignes = [p for p in vendues if cstr(p.groupe) == cstr(g.numero)]
		g.cout_total = sum(flt(p.cout_total) for p in lignes)
		g.prix_total = sum(flt(p.prix_total) for p in lignes)
		g.marge = g.prix_total - g.cout_total
		g.taux_marge = taux(g.marge, g.prix_total)
		parts = _etapes_de(doc, frappe._dict(numero=None, groupe=g.numero, parente=None), par_num)
		g.etapes = ", ".join(libelles.get(e, e) for e, _f in parts) or None


def _totaux_etapes(doc, vendues, par_num, libelles):
	"""Totaux par prestation (une ligne partagée compte pour sa part)."""
	totaux = defaultdict(lambda: [0.0, 0.0])
	for p in vendues:
		for e, f in _etapes_de(doc, p, par_num):
			totaux[e][0] += flt(p.cout_total) * f
			totaux[e][1] += flt(p.prix_total) * f
	doc.set("totaux_etapes", [])
	ordre = [e.prestation for e in doc.get("etapes") or []] + [e for e in totaux if e not in libelles]
	for e in dict.fromkeys(ordre):
		cout, prix = totaux.get(e, (0, 0))
		doc.append("totaux_etapes", dict(etape=e, cout_total=cout, prix_total=prix, marge=prix - cout, taux_marge=taux(prix - cout, prix)))


def _totaux_document(doc, vendues):
	"""Totaux du document ; « coût incomplet » si une ligne vendue a un coût manquant ou en attente."""
	doc.total_cout = sum(flt(p.cout_total) for p in vendues)
	doc.total_prix = sum(flt(p.prix_total) for p in vendues)
	doc.total_marge = doc.total_prix - doc.total_cout
	doc.taux_marge = taux(doc.total_marge, doc.total_prix)
	doc.cout_incomplet = 1 if any(cint(p.cout_manquant) or cint(p.cout_en_attente) for p in vendues) else 0


def _etapes_de(doc, p, par_num):
	"""[(étape, fraction)] : répartition de la position, sinon de son groupe, sinon l'étape unique du chiffrage."""
	if p.parente and p.parente in par_num:
		return _etapes_de(doc, par_num[p.parente], par_num)
	for cible in (p.numero, p.groupe):
		lignes = [r for r in doc.get("repartitions") or [] if cstr(r.cible) == cstr(cible) and r.etape]
		if lignes:
			total = sum(flt(r.part) for r in lignes)
			if total:
				return [(r.etape, flt(r.part) / total) for r in lignes]
			return [(r.etape, 1 / len(lignes)) for r in lignes]
	etapes = [e.prestation for e in doc.get("etapes") or [] if e.prestation]
	return [(etapes[0], 1)] if len(etapes) == 1 else []
