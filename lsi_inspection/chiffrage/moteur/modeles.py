"""Modèles de chiffrage : structure réutilisable (sans coûts ni prix)."""

import frappe
from frappe.utils import cstr

from lsi_inspection.constants import CHAMPS_COUT
from lsi_inspection.chiffrage.moteur.actions import _chiffrage_brouillon
from lsi_inspection.chiffrage.moteur.organisation import _prochain_groupe


def modele_validate(doc, method=None):
	"""Un modèle de chiffrage ne garde jamais de coût ni de prix."""
	for p in doc.get("positions") or []:
		for c in CHAMPS_COUT:
			p.set(c, None if c in ("source_cout", "ressource", "ressource_doctype", "demande_prix") else 0)
	for g in doc.get("groupes") or []:
		g.cout_total = g.prix_total = g.marge = g.taux_marge = 0
	for e in doc.get("etapes") or []:
		e.gamme_appliquee = 1


@frappe.whitelist(methods=["POST"])
def enregistrer_modele(chiffrage, titre):
	doc = frappe.get_doc("Chiffrage", chiffrage)
	doc.check_permission("read")
	m = frappe.new_doc("Modele Chiffrage")
	m.titre = titre
	for champ in ("etapes", "groupes", "positions", "repartitions"):
		for r in doc.get(champ) or []:
			d = r.as_dict()
			for k in ("name", "parent", "parentfield", "parenttype", "idx", "creation", "modified", "owner", "modified_by", "docstatus"):
				d.pop(k, None)
			m.append(champ, d)
	m.insert()
	return m.name


@frappe.whitelist(methods=["POST"])
def charger_modele(chiffrage, modele):
	"""Ajoute la structure du modèle (groupes renumérotés après les groupes existants) ; coûts recalculés immédiatement."""
	doc = _chiffrage_brouillon(chiffrage)
	m = frappe.get_doc("Modele Chiffrage", modele)
	decalage, correspondance = _prochain_groupe(doc) - 1, {}
	for g in m.groupes:
		nouveau = cstr(int(g.numero) + decalage) if cstr(g.numero).isdigit() else g.numero
		correspondance[cstr(g.numero)] = nouveau
		doc.append("groupes", dict(numero=nouveau, titre=g.titre))

	def renum(numero):
		if not numero:
			return numero
		tete, _sep, reste = cstr(numero).partition(".")
		return correspondance.get(tete, tete) + (f".{reste}" if reste else "")

	presentes = {e.prestation for e in doc.etapes}
	for e in m.etapes:
		if e.prestation not in presentes:
			doc.append("etapes", dict(prestation=e.prestation, libelle=e.libelle, qty=e.qty, uom=e.uom, gamme_appliquee=1))
	for p in m.positions:
		doc.append("positions", dict(numero=renum(p.numero), groupe=renum(p.groupe), etape=p.etape, parente=renum(p.parente), type_position=p.type_position,
			item_code=p.item_code, designation_2=p.designation_2, qty=p.qty, uom=p.uom))
	for r in m.repartitions:
		doc.append("repartitions", dict(cible=renum(r.cible), etape=r.etape, part=r.part))
	doc.save()
	return doc.name
