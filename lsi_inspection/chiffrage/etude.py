"""Étude technique : création depuis l'opportunité et demande du client (articles, texte, pièces jointes)."""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def make_eft(opportunity):
	"""Opportunité → EFT : étapes = articles de l'opportunité (leurs gammes s'appliquent à l'enregistrement)."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	doc = frappe.new_doc("EFT")
	doc.update(dict(titre=opp.get("title") or opp.name, opportunity=opp.name, company=opp.company, bu=opp.get("lsi_bu"),
		service=opp.get("lsi_service"),
		customer=opp.party_name if opp.opportunity_from == "Customer" else None))
	for it in opp.get("items") or []:
		if it.item_code:  # ligne sans article (demande seulement décrite en texte) : l'équipe technique choisira les prestations
			doc.append("etapes", dict(prestation=it.item_code, qty=flt(it.qty) or 1, uom=it.uom))
	doc.insert()
	return doc.name


@frappe.whitelist()
def demande_opportunite(opportunity):
	"""Pour l'étude technique dans l'EFT : articles demandés et pièces jointes de l'opportunité (droit de lecture vérifié)."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	articles = [dict(item_code=it.item_code, item_name=it.item_name, qty=it.qty, uom=it.uom, description=it.description)
		for it in opp.get("items") or []]
	fichiers = frappe.get_all("File", filters={"attached_to_doctype": "Opportunity", "attached_to_name": opp.name, "is_folder": 0},
		fields=["file_name", "file_url", "is_private", "creation"], order_by="creation asc")
	return dict(articles=articles, fichiers=fichiers)
