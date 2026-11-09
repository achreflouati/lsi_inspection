"""EFT (étude technique) : une par opportunité. Faisabilité, lieu, normes, ressources pressenties, demande du client et pièces
jointes de l'opportunité. « Non faisable » : proposition de déclarer l'opportunité perdue (motif natif)."""

import frappe
from frappe import _

from lsi_inspection.constants import NON_FAISABLE
from lsi_inspection.outils import utilisateur_responsable


@frappe.whitelist(methods=["POST"])
def ouvrir_ou_creer(opportunity):
	"""EFT active de l'opportunité ; créée si elle n'existe pas encore (une seule EFT par opportunité). Renvoie son nom."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	existante = eft_active(opportunity)
	if existante:
		return existante
	doc = frappe.new_doc("EFT")
	doc.update(dict(opportunity=opp.name, company=opp.company,
		customer=opp.party_name if opp.opportunity_from == "Customer" else None))
	doc.insert()
	return doc.name


def eft_active(opportunity, sauf=None):
	"""Nom de l'EFT non annulée de l'opportunité (hors `sauf`), sinon None."""
	filtres = {"opportunity": opportunity, "docstatus": ("<", 2)}
	if sauf:
		filtres["name"] = ("!=", sauf)
	return frappe.db.get_value("EFT", filtres)


def valider(doc):
	"""EFT.validate : une seule EFT active par opportunité (une nouvelle version remplace l'ancienne) ; responsable du service."""
	autre = eft_active(doc.opportunity, sauf=doc.name)
	if autre and autre != doc.amended_from:
		frappe.throw(_("L'opportunité {0} a déjà une EFT : {1}.").format(doc.opportunity, autre))
	doc.responsable_service = utilisateur_responsable(doc.service)


def avant_validation(doc):
	"""EFT.before_submit : la faisabilité est obligatoire pour valider."""
	if not doc.faisabilite:
		frappe.throw(_("Indiquez la faisabilité avant de valider l'EFT."))


@frappe.whitelist()
def demande_opportunite(opportunity):
	"""Pour l'étude technique : articles demandés et pièces jointes de l'opportunité (droit de lecture vérifié)."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	articles = [dict(item_code=it.item_code, item_name=it.item_name, qty=it.qty, uom=it.uom, description=it.description)
		for it in opp.get("items") or []]
	fichiers = frappe.get_all("File", filters={"attached_to_doctype": "Opportunity", "attached_to_name": opp.name, "is_folder": 0},
		fields=["file_name", "file_url", "is_private", "creation"], order_by="creation asc")
	return dict(articles=articles, fichiers=fichiers)


@frappe.whitelist(methods=["POST"])
def declarer_perdue(eft, motifs, detail=None):
	"""EFT non faisable → l'opportunité est déclarée perdue par la méthode native (motifs « Opportunity Lost Reason »)."""
	doc = frappe.get_doc("EFT", eft)
	if doc.faisabilite != NON_FAISABLE:
		frappe.throw(_("L'EFT {0} n'est pas « Non faisable ».").format(eft))
	opp = frappe.get_doc("Opportunity", doc.opportunity)
	opp.check_permission("write")
	raisons = [dict(lost_reason=m) for m in frappe.parse_json(motifs) or []]
	opp.declare_enquiry_lost(raisons, [], detail or doc.commentaire_faisabilite)
	return opp.name
