"""Commande client validée → Projet natif + Besoin Logistique (un par commande), en une fois.

Chemin des données : ligne de commande (Sales Order Item.quotation_item, natif) → ligne de devis (Quotation Item.lsi_eft_position)
→ position du chiffrage retenu (Quotation.lsi_chiffrage). Le chiffrage n'est que LU (rien n'y est écrit).

Une PRESTATION est une étape du chiffrage (Chiffrage.etapes) couverte par au moins une ligne de commande ; une ligne de commande
appartient à une ou plusieurs prestations selon la répartition du chiffrage (calcul._etapes_de, la même fonction que les totaux
par étape). Les RESSOURCES PRÉVUES sont les lignes « Pool de ressources » des positions commandées (une position à prix fixe est
représentée par ses sous-positions, comme dans le rapport Besoins Chiffrage), à la quantité commandée.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt

from lsi_inspection.chiffrage.moteur.calcul import _etapes_de
from lsi_inspection.chiffrage.moteur.couts import candidat_retenu, facteur_uom
from lsi_inspection.constants import BROUILLON, POOL, PRIX_FIXE, REGLE_SOUS, TYPE_PAR_DOCTYPE


# ------------------------------------------------------------------ bouton « Créer projet et besoin logistique »
@frappe.whitelist(methods=["POST"])
def creer_projet_et_besoin(sales_order):
	"""Crée (ou réutilise) le Projet natif de la commande et crée son Besoin Logistique extrait du chiffrage.
	Entrée : nom de la commande validée. Sortie : {"besoin", "project", "existait"}."""
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	frappe.has_permission("Besoin Logistique", "create", throw=True)
	if so.docstatus != 1:
		frappe.throw(_("La commande {0} doit être validée.").format(so.name))
	existant = frappe.db.get_value("Besoin Logistique", {"sales_order": so.name})
	if existant:
		return dict(besoin=existant, project=so.project, existait=1)
	chiffrage = _chiffrage_de(so)
	project = so.project or _creer_projet(so)
	besoin = frappe.new_doc("Besoin Logistique")
	besoin.update(dict(sales_order=so.name, customer=so.customer, customer_name=so.customer_name, company=so.company,
		project=project, chiffrage=chiffrage.name, statut=BROUILLON))
	extraire(besoin, so, chiffrage)
	besoin.insert()
	return dict(besoin=besoin.name, project=project, existait=0)


def _chiffrage_de(so):
	"""Chiffrage (unique) des devis de la commande ; message clair s'il n'y en a pas ou s'il y en a plusieurs."""
	devis = {it.prevdoc_docname for it in so.items if it.get("prevdoc_docname")}
	chiffrages = {c for c in (frappe.db.get_value("Quotation", q, "lsi_chiffrage") for q in devis) if c}
	if not chiffrages:
		frappe.throw(_("La commande {0} ne vient pas d'un devis issu d'un chiffrage : aucun besoin à extraire.").format(so.name))
	if len(chiffrages) > 1:
		frappe.throw(_("La commande {0} reprend plusieurs chiffrages ({1}) : un Besoin Logistique ne peut en suivre qu'un.").format(
			so.name, ", ".join(sorted(chiffrages))))
	return frappe.get_doc("Chiffrage", chiffrages.pop())


def _creer_projet(so):
	"""Projet natif par le mappage natif d'ERPNext (Sales Order → Project) ; Project.on_update renseigne Sales Order.project."""
	from erpnext.selling.doctype.sales_order.sales_order import make_project

	projet = make_project(so.name)
	projet.insert()  # dates prévues du projet : posées à la génération des OM (om._dates_projet)
	return projet.name


# ------------------------------------------------------------------ extraction
def extraire(besoin, so, chiffrage):
	"""Remplit les tables prestations, ressources, repartitions et le champ non_extraites du besoin (sans enregistrer)."""
	par_num = {p.numero: p for p in chiffrage.positions if p.numero}
	par_name = {p.name: p for p in chiffrage.positions}
	lignes_devis = dict(frappe.get_all("Quotation Item", filters={"name": ["in", [it.quotation_item for it in so.items
		if it.get("quotation_item")] or [""]]}, fields=["name", "lsi_eft_position"], as_list=True))
	prestations, notes = OrderedDict(), []
	for it in so.items:
		pos = par_name.get(lignes_devis.get(it.get("quotation_item")))
		if not pos:
			notes.append(_("Ligne #{0} {1} : aucune position de chiffrage liée.").format(it.idx, it.item_code))
			continue
		parts = _etapes_de(chiffrage, pos, par_num)
		if not parts:
			notes.append(_("Ligne #{0} {1} : position {2} sans prestation dans le chiffrage.").format(it.idx, it.item_code, pos.numero))
		for etape, _f in parts:
			prestations.setdefault(etape, []).append(it)
		for candidat, qty in _candidats(chiffrage, pos, _qty_commandee(it, pos)):
			_ajouter_ressource(besoin, chiffrage, par_num, candidat, qty, it, notes)
	_ajouter_prestations(besoin, chiffrage, prestations)
	besoin.non_extraites = "\n".join(notes) or None


def _qty_commandee(it, pos):
	"""Quantité commandée exprimée dans l'unité de la position (conversion native si l'unité a changé)."""
	if not it.uom or not pos.uom or it.uom == pos.uom:
		return flt(it.qty)
	return flt(it.qty) * (facteur_uom(it.uom, pos.uom) or 1)


def _candidats(chiffrage, pos, qty):
	"""[(ligne du chiffrage porteuse de ressource, quantité commandée)] pour une position commandée :
	la position elle-même ; prix fixe « somme » : ses sous-positions mises à l'échelle ; prix fixe « règle » : la retenue."""
	if pos.mode != PRIX_FIXE:
		return [(pos, qty)]
	kids = [k for k in chiffrage.positions if k.parente == pos.numero]
	t = frappe.get_cached_doc("Type Position", pos.type_position) if pos.type_position else None
	if t and t.source_cout == REGLE_SOUS:
		k, _c, _l = candidat_retenu(pos, kids, t)
		f = facteur_uom(pos.uom, k.uom) if k and pos.uom and k.uom else 1
		return [(k, qty * (f or 1))] if k else []
	ratio = qty / flt(pos.qty) if flt(pos.qty) else 1
	return [(k, flt(k.qty) * ratio) for k in kids]


def _ajouter_ressource(besoin, chiffrage, par_num, c, qty, it, notes):
	"""Une ligne « ressource prévue » (pool) ; ressource partagée : une seule ligne + ses parts dans repartitions."""
	t = frappe.get_cached_doc("Type Position", c.type_position) if c.type_position else None
	libelle = f"{c.numero} {c.item_code}"
	if not t or t.source_cout != POOL:
		notes.append(_("{0} : source « {1} », pas un pool de ressources.").format(libelle, _(t.source_cout) if t else _("sans type")))
		return
	pool_dt, pool = frappe.db.get_value("Item", c.item_code, ["lsi_pool_doctype", "lsi_pool"]) or (None, None)
	if pool_dt != t.pool_doctype or not pool or t.ressource_doctype not in TYPE_PAR_DOCTYPE:
		notes.append(_("{0} : article sans pool {1}.").format(libelle, _(t.pool_doctype or "")))
		return
	if not flt(qty):
		notes.append(_("{0} : quantité 0 (tarif).").format(libelle))
		return
	existante = next((r for r in besoin.ressources if r.numero == c.numero), None)
	if existante:  # même position sur deux lignes de commande : quantités cumulées
		existante.qty = flt(existante.qty) + flt(qty)
		existante.cout_prevu = flt(existante.cout_unitaire) * existante.qty
		return
	parts = _etapes_de(chiffrage, c, par_num)
	libelles = {e.prestation: e.libelle or e.prestation for e in chiffrage.etapes}
	besoin.append("ressources", dict(numero=c.numero, type_ressource=TYPE_PAR_DOCTYPE[t.ressource_doctype], item_code=c.item_code,
		prestation=parts[0][0] if len(parts) == 1 else None, partagee=1 if len(parts) > 1 else 0,
		repartition=", ".join(f"{libelles.get(e, e)} {round(f * 100, 2)} %" for e, f in parts) if len(parts) > 1 else None,
		type_position=t.name, pool_doctype=pool_dt, pool=pool, ressource_doctype=t.ressource_doctype,
		ressource_chiffrage=c.ressource, qty=qty, uom=c.uom, cout_unitaire=flt(c.cout_unitaire),
		cout_prevu=flt(c.cout_unitaire) * flt(qty), ligne_commande=it.name))
	if len(parts) > 1:
		for e, f in parts:
			besoin.append("repartitions", dict(numero=c.numero, prestation=e, part=round(f * 100, 4)))


def _ajouter_prestations(besoin, chiffrage, prestations):
	"""Une ligne par prestation vendue, dans l'ordre des étapes du chiffrage, avec sa ligne de commande principale."""
	libelles = {e.prestation: e.libelle for e in chiffrage.etapes}
	ordre = [e.prestation for e in chiffrage.etapes if e.prestation in prestations] + [e for e in prestations if e not in libelles]
	for e in ordre:
		lignes = prestations[e]
		besoin.append("prestations", dict(prestation=e, libelle=libelles.get(e) or frappe.db.get_value("Item", e, "item_name") or e,
			ligne_commande=lignes[0].name, item_commande=lignes[0].item_code,
			lignes_commande=", ".join(f"#{it.idx} {it.item_code}" for it in lignes)))
