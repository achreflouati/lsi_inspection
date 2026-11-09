# Copyright (c) 2026, achref louati and contributors
# For license information, please see license.txt
"""Chiffrage = une variante de l'EFT (moteur : lsi_inspection.chiffrage.moteur ; variantes : lsi_inspection.chiffrage.variantes)."""

from frappe.model.document import Document

from lsi_inspection.chiffrage import variantes
from lsi_inspection.chiffrage.moteur.calcul import valider_chiffrage


class Chiffrage(Document):
	def autoname(self):
		variantes.nommer(self)

	def validate(self):
		valider_chiffrage(self)

	def on_change(self):
		variantes.apres_changement(self)
