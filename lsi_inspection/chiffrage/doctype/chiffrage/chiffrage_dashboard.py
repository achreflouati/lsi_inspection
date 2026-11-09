from frappe import _


def get_data():
	"""Connexions du chiffrage : devis et demandes de prix créés depuis lui ; son EFT et son opportunité."""
	return dict(
		fieldname="lsi_chiffrage",
		internal_links={"EFT": "eft", "Opportunity": "opportunity"},
		transactions=[dict(label=_("Étude"), items=["EFT", "Opportunity"]), dict(label=_("Offre client et achats"), items=["Quotation", "Request for Quotation"])],
	)
