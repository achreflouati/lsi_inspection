# Copyright (c) 2026, achref louati and contributors
# For license information, please see license.txt
"""Modèle de chiffrage : structure réutilisable, jamais de coût ni de prix (lsi_inspection.chiffrage.moteur.modeles)."""

from frappe.model.document import Document

from lsi_inspection.chiffrage.moteur.modeles import modele_validate


class ModeleChiffrage(Document):
	def validate(self):
		modele_validate(self)
