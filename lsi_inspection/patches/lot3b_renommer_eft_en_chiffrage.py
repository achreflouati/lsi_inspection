"""Lot 3b (avant synchronisation des doctypes) : l'ancienne EFT devient « Chiffrage » (une variante), pour libérer le nom « EFT »
pour l'étude technique. Renommage NATIF (frappe.rename_doc) : tables renommées, liens et options mis à jour par Frappe, aucune
donnée copiée ni perdue. Idempotent. Retour arrière : restauration de la sauvegarde prise avant le migrate."""

import frappe

DOCTYPES = [  # (ancien, nouveau) : tables enfants d'abord, puis modèle et document
	("EFT Position", "Chiffrage Position"), ("EFT Groupe", "Chiffrage Groupe"), ("EFT Etape", "Chiffrage Etape"),
	("EFT Repartition", "Chiffrage Repartition"), ("EFT Total Etape", "Chiffrage Total Etape"),
	("Modele EFT", "Modele Chiffrage"), ("EFT", "Chiffrage"),
]
AUTRES = [("Report", "Besoins EFT", "Besoins Chiffrage"), ("Print Format", "OT", "Fiche chiffrage"), ("Workflow", "EFT", "Chiffrage")]


def execute():
	if frappe.db.exists("DocType", "Chiffrage"):
		return  # déjà fait
	for ancien, nouveau in DOCTYPES:
		if frappe.db.exists("DocType", ancien):
			frappe.rename_doc("DocType", ancien, nouveau, force=True)
	for doctype, ancien, nouveau in AUTRES:
		if frappe.db.exists(doctype, ancien) and not frappe.db.exists(doctype, nouveau):
			frappe.rename_doc(doctype, ancien, nouveau, force=True)
	frappe.clear_cache()
