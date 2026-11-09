# Copyright (c) 2026, achref louati and contributors
# For license information, please see license.txt
"""EFT = étude technique, une par opportunité (logique : lsi_inspection.chiffrage.etude)."""

from frappe.model.document import Document

from lsi_inspection.chiffrage import etude


class EFT(Document):
	def validate(self):
		etude.valider(self)

	def before_submit(self):
		etude.avant_validation(self)
