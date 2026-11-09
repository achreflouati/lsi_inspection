from frappe import _


def get_data():
	"""Connexions de l'EFT : ses variantes de chiffrage, ses devis ; son opportunité."""
	return dict(
		fieldname="eft",
		non_standard_fieldnames={"Quotation": "lsi_eft"},
		internal_links={"Opportunity": "opportunity"},
		transactions=[dict(label=_("Chiffrage"), items=["Chiffrage"]), dict(label=_("Offre client"), items=["Quotation"]),
			dict(label=_("Opportunité"), items=["Opportunity"])],
	)
