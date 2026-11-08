# Copyright (c) 2026, achref louati and Contributors
# See license.txt

import frappe
from frappe import _
from frappe.model.document import Document

AVEC_DOCUMENT = ("Création", "Validation", "État du workflow", "Changement de statut", "Annulation")
AVEC_VALEUR = ("État du workflow", "Changement de statut")


class EvenementPhase(Document):
	def validate(self):
		if self.declencheur in AVEC_DOCUMENT and not self.document_type:
			frappe.throw(_("Indiquez le document qui déclenche l'événement."))
		if self.declencheur == "Manuel":
			self.document_type = self.champ_lien = self.valeur = self.champ_statut = None
		if self.declencheur in AVEC_VALEUR and not self.valeur:
			frappe.throw(_("Indiquez la valeur attendue."))
		if self.declencheur == "Changement de statut":
			self.champ_statut = self.champ_statut or "status"
			if not frappe.get_meta(self.document_type).has_field(self.champ_statut) and self.champ_statut != "docstatus":
				frappe.throw(_("Le champ {0} n'existe pas sur {1}.").format(self.champ_statut, self.document_type))
		if self.champ_lien and not frappe.get_meta(self.document_type).has_field(self.champ_lien):
			frappe.throw(_("Le champ de lien {0} n'existe pas sur {1}.").format(self.champ_lien, self.document_type))

	def on_update(self):
		from lsi_inspection.commercial.phases import vider_cache_evenements

		vider_cache_evenements()

	def on_trash(self):
		from lsi_inspection.commercial.phases import vider_cache_evenements

		vider_cache_evenements()
