"""Offre client : un devis natif par variante de chiffrage validée (chemin unique « Créer l'offre client »), liens dans les deux
sens (Connexions natives), devis envoyé (e-mail natif), devis commandé → variante retenue."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, now_datetime, nowdate

from lsi_inspection.chiffrage import variantes


@frappe.whitelist(methods=["POST"])
def creer_devis(chiffrage, lignes=None, remise=None):
	"""Devis natif depuis un chiffrage validé : une ligne par POSITION VENDUE cochée (jamais les sous-positions).
	lignes : noms des positions retenues (toutes si absent) ; remise : % sur le total net (remise native). Renvoie le devis."""
	doc = frappe.get_doc("Chiffrage", chiffrage)
	doc.check_permission("read")
	lignes = frappe.parse_json(lignes) if lignes else None
	vendues = [p for p in doc.positions if not p.parente and (lignes is None or p.name in lignes)]
	_controler(doc, lignes, flt(remise), vendues)
	q = frappe.new_doc("Quotation")
	q.update(dict(quotation_to="Customer", party_name=doc.customer, company=doc.company, transaction_date=nowdate(),
		valid_till=add_days(nowdate(), 30), opportunity=doc.opportunity, lsi_chiffrage=doc.name, lsi_eft=doc.eft, lsi_bu=doc.bu,
		lsi_service=doc.service, ignore_pricing_rule=1))
	titres = {cstr(g.numero): g.titre for g in doc.groupes}
	for p in vendues:
		q.append("items", _ligne_devis(p, titres))
	if flt(remise):
		q.apply_discount_on = "Net Total"
		q.additional_discount_percentage = flt(remise)
	q.insert()
	return q.name


def _controler(doc, lignes, remise, vendues):
	if lignes is not None and not lignes:
		frappe.throw(_("Cochez au moins une ligne pour l'offre client."))
	if not 0 <= remise < 100:
		frappe.throw(_("La remise doit être comprise entre 0 et 100 %."))
	if doc.docstatus != 1:
		frappe.throw(_("Le chiffrage doit être validé avant de créer l'offre client."))
	if any(cint(p.tarif) for p in vendues) and not cint(frappe.db.get_single_value("Selling Settings", "allow_zero_qty_in_quotation")):
		frappe.throw(_("Des lignes tarif (quantité 0) existent : activez « Allow Quotation with Zero Quantity » dans les paramètres de vente."))
	if not doc.customer:
		frappe.throw(_("Renseignez le client de l'EFT."))


def _ligne_devis(p, titres):
	return dict(item_code=p.item_code, qty=flt(p.qty), uom=p.uom, conversion_factor=1, rate=flt(p.prix_unitaire),
		description=" — ".join(x for x in (p.designation or p.item_code, p.designation_2) if x),
		lsi_groupe_numero=p.groupe, lsi_groupe_titre=titres.get(cstr(p.groupe)), lsi_numero_position=p.numero,
		lsi_designation_2=p.designation_2, lsi_etapes=p.etapes, lsi_tarif=p.tarif, lsi_eft_position=p.name)


# ------------------------------------------------------------------ hooks
def commande_validee(doc, method=None):
	"""Sales Order.on_submit : la variante du devis commandé devient « Retenue » (les autres « Non retenue »)."""
	devis = {it.prevdoc_docname for it in doc.get("items") or [] if it.get("prevdoc_docname")}
	for q in devis:
		chiffrage = frappe.db.get_value("Quotation", q, "lsi_chiffrage")
		if chiffrage:
			variantes.retenir(chiffrage)


def devis_envoye(doc, method=None):
	"""Communication.after_insert : e-mail envoyé depuis un devis → devis marqué envoyé (date), ce qui déclenche l'événement de phase
	et la notification native configurés sur ce champ."""
	if doc.reference_doctype != "Quotation" or doc.sent_or_received != "Sent" or doc.communication_type != "Communication":
		return
	if not frappe.db.exists("Quotation", doc.reference_name):
		return
	q = frappe.get_doc("Quotation", doc.reference_name)
	if not cint(q.get("lsi_envoye")):
		q.db_set({"lsi_envoye": 1, "lsi_date_envoi": now_datetime()})


# ------------------------------------------------------------------ connexions natives (override_doctype_dashboards)
def connexions_opportunite(data):
	"""Opportunité : EFT et chiffrages dans l'onglet Connexions."""
	data.setdefault("transactions", []).insert(0, dict(label=_("Étude et chiffrage"), items=["EFT", "Chiffrage"]))
	return data


def connexions_devis(data):
	"""Devis : son chiffrage et son EFT (liens portés par le devis)."""
	data.setdefault("internal_links", {}).update({"Chiffrage": "lsi_chiffrage", "EFT": "lsi_eft"})
	data.setdefault("transactions", []).insert(0, dict(label=_("Étude et chiffrage"), items=["EFT", "Chiffrage"]))
	return data
