# Copyright (c) 2026, achref louati and contributors
# For license information, please see license.txt
"""Besoin Logistique : un par commande client (extraction : logistique/extraction.py ; planification et contrôles :
logistique/planification.py et logistique/controles.py ; OM : logistique/om.py)."""

from frappe.model.document import Document

from lsi_inspection.logistique import planification


class BesoinLogistique(Document):
	def _validate_links(self):
		# Le contrôle natif des liens passe AVANT validate : le doctype du lien dynamique « Ressource » d'une affectation doit
		# déjà être connu. L'écran le pose ; un appel API (ou un script) peut l'omettre : on le déduit ici de la ligne prévue.
		planification.doctypes_affectations(self)
		super()._validate_links()

	def validate(self):
		planification.valider(self)
