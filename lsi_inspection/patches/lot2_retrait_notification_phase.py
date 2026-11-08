"""Lot 2 — retrait de l'ancien mécanisme « Notification Phase » (remplacé par les Notifications natives).

À appliquer APRÈS validation des tests à l'écran. Supprime : les champs lsi_sb_notifications / lsi_notifications_phase
d'Opportunity Type, le doctype enfant Notification Phase (et sa table), les modèles d'e-mail « Phase - entree » et
« Phase - retard » s'ils ne sont cités par aucune Notification active, la tâche planifiée phases.retards_quotidiens.
Le champ retard_notifie est retiré du doctype Phase Opportunite (la colonne reste en base, sans effet).
"""

import frappe

MODELES = ("Phase - entree", "Phase - retard")


def execute():
	for fieldname in ("lsi_notifications_phase", "lsi_sb_notifications"):
		name = frappe.db.get_value("Custom Field", {"dt": "Opportunity Type", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	if frappe.db.exists("DocType", "Notification Phase"):
		frappe.delete_doc("DocType", "Notification Phase", ignore_permissions=True, force=True)
	for modele in MODELES:
		if not frappe.db.exists("Email Template", modele):
			continue
		cite = frappe.db.sql("""select name from `tabNotification` where enabled = 1 and (message like %(m)s or subject like %(m)s)""",
			{"m": f"%{modele}%"})
		if not cite:
			frappe.delete_doc("Email Template", modele, ignore_permissions=True, force=True)
	for job in frappe.get_all("Scheduled Job Type", filters={"method": ("like", "%phases.retards_quotidiens")}, pluck="name"):
		frappe.delete_doc("Scheduled Job Type", job, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype="Opportunity Type")
