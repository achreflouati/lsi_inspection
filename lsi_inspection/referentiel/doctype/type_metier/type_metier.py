# Copyright (c) 2026, achref louati and Contributors
# See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TypeMetier(Document):
	def validate(self):
		if self.par_defaut:
			autre = frappe.db.get_value("Type Metier", {"famille": self.famille, "par_defaut": 1, "name": ("!=", self.name)})
			if autre:
				frappe.throw(_("La famille {0} a déjà une valeur par défaut : {1}.").format(self.famille, autre))
