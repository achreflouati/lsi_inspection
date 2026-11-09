"""Offre client : création du devis natif depuis un chiffrage validé (lignes cochées, remise native)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, nowdate


@frappe.whitelist(methods=["POST"])
def creer_devis(eft, lignes=None, remise=None):
	"""Un seul chemin (« Créer l'offre client ») : chaque POSITION VENDUE cochée = une ligne de devis natif ; jamais les
	sous-positions. lignes : positions retenues (toutes si absent) ; remise : % sur le total net, remise native du devis."""
	doc = frappe.get_doc("EFT", eft)
	doc.check_permission("read")
	lignes = frappe.parse_json(lignes) if lignes else None
	remise = flt(remise)
	if lignes is not None and not lignes:
		frappe.throw(_("Cochez au moins une ligne pour l'offre client."))
	if not 0 <= remise < 100:
		frappe.throw(_("La remise doit être comprise entre 0 et 100 %."))
	if doc.docstatus != 1:
		frappe.throw(_("L'EFT doit être validée avant de créer le devis."))
	vendues = [p for p in doc.positions if not p.parente and (lignes is None or p.name in lignes)]
	if any(cint(p.tarif) for p in vendues) and not cint(frappe.db.get_single_value("Selling Settings", "allow_zero_qty_in_quotation")):
		frappe.throw(_("Des lignes tarif (quantité 0) existent : activez « Allow Quotation with Zero Quantity » dans les paramètres de vente."))
	if not doc.customer:
		frappe.throw(_("Renseignez le client de l'EFT."))
	titres = {cstr(g.numero): g.titre for g in doc.groupes}
	q = frappe.new_doc("Quotation")
	q.update(dict(quotation_to="Customer", party_name=doc.customer, company=doc.company, transaction_date=nowdate(),
		valid_till=add_days(nowdate(), 30), opportunity=doc.opportunity, lsi_eft=doc.name, lsi_bu=doc.bu, lsi_service=doc.service,
		ignore_pricing_rule=1))
	for p in vendues:
		q.append("items", dict(item_code=p.item_code, qty=flt(p.qty), uom=p.uom, conversion_factor=1, rate=flt(p.prix_unitaire),
			description=" — ".join(x for x in (p.designation or p.item_code, p.designation_2) if x),
			lsi_groupe_numero=p.groupe, lsi_groupe_titre=titres.get(cstr(p.groupe)), lsi_numero_position=p.numero,
			lsi_designation_2=p.designation_2, lsi_etapes=p.etapes, lsi_tarif=p.tarif, lsi_eft_position=p.name))
	if remise:
		q.apply_discount_on = "Net Total"
		q.additional_discount_percentage = remise
	q.insert()
	return q.name
