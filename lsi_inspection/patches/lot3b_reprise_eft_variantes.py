"""Lot 3b (après synchronisation) : reprise de l'existant. Chaque ancienne EFT (désormais un Chiffrage) devient la variante A
d'une nouvelle EFT (étude technique) portant son ancien nom ; ses versions (amend) suivent (…-A-1, …-A-2) ; statuts conservés ;
devis et demandes de prix reliés au chiffrage ET à l'EFT. Comptes contrôlés avant / après : en cas d'écart, exception
(le migrate s'arrête, la transaction est annulée). Retour arrière : restauration de la sauvegarde prise avant le migrate."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from lsi_inspection import config
from lsi_inspection.config import alignement
from lsi_inspection.chiffrage.variantes import lettre_suivante


def execute():
	if frappe.db.exists("Chiffrage", {"eft": ("is", "set")}) or not frappe.db.count("Chiffrage"):
		return  # déjà repris, ou rien à reprendre
	avant = _comptes("lsi_eft")  # avant reprise, lsi_eft du devis désigne l'ancienne EFT (le chiffrage)
	_champs()
	correspondance = _reprendre_chiffrages()
	_relier("Quotation")
	_relier("Request for Quotation")
	_evenements_et_configuration()
	_registre_demo(correspondance)
	apres = _comptes("lsi_chiffrage")
	if avant != apres:
		raise Exception(f"Reprise lot 3b : comptes différents avant {avant} / après {apres}")
	print(f"lsi_inspection : reprise lot 3b — avant {avant}, après {apres}, EFT créées : {frappe.db.count('EFT')}")


def _comptes(champ_devis):
	return dict(chiffrages=frappe.db.count("Chiffrage"), positions=frappe.db.count("Chiffrage Position"),
		devis=frappe.db.count("Quotation", {champ_devis: ("is", "set")}))


def _champs():
	"""Champs nécessaires à la reprise, créés ici car les fixtures ne sont chargées qu'après les patchs (mêmes définitions)."""
	lien = lambda dt: [dict(fieldname="lsi_chiffrage", fieldtype="Link", options="Chiffrage", label="Chiffrage (variante)", read_only=1,
		allow_on_submit=1, insert_after="lsi_eft", module="Chiffrage")]
	create_custom_fields({"Quotation": lien("Quotation"), "Request for Quotation": lien("Request for Quotation")}, update=True)


def _chaine(racine):
	"""La racine puis ses versions successives (amended_from)."""
	chaine, courant = [racine], racine
	while True:
		suivant = frappe.db.get_value("Chiffrage", {"amended_from": courant}, "name")
		if not suivant:
			return chaine
		chaine.append(suivant)
		courant = suivant


def _reprendre_chiffrages():
	"""Une EFT par opportunité (ou par ancienne EFT sans opportunité) ; variantes A, B… dans l'ordre de création."""
	racines = frappe.get_all("Chiffrage", filters={"amended_from": ("is", "not set")}, order_by="creation asc",
		fields=["name", "opportunity", "customer", "company", "bu", "service", "titre", "date"])
	groupes = {}
	for r in racines:
		groupes.setdefault(r.opportunity or r.name, []).append(r)
	correspondance = {}
	for liste in groupes.values():
		eft = _creer_eft(liste[0])
		lettres = []
		for r in liste:
			lettre = lettre_suivante(lettres)
			lettres.append(lettre)
			for ancien in _chaine(r.name):
				nouveau = ancien.replace(r.name, f"{eft}-{lettre}", 1)
				frappe.rename_doc("Chiffrage", ancien, nouveau, force=True)
				frappe.db.set_value("Chiffrage", nouveau, {"eft": eft, "variante": lettre, "libelle_variante": f"Variante {lettre}"},
					update_modified=False)
				correspondance[ancien] = (nouveau, eft)
	return correspondance


def _creer_eft(r):
	"""EFT (étude technique) portant l'ancien nom, en brouillon, faisabilité à renseigner."""
	doc = frappe.get_doc(dict(doctype="EFT", opportunity=r.opportunity, customer=r.customer, company=r.company, bu=r.bu, service=r.service,
		titre=r.titre, date=r.date, workflow_state="Brouillon"))
	doc.flags.ignore_validate = not r.opportunity  # ancienne EFT sans opportunité : reprise telle quelle
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_permissions = True
	doc.insert(set_name=r.name)
	return doc.name


def _relier(doctype):
	"""lsi_eft contenait le chiffrage (après renommage) : il passe dans lsi_chiffrage, lsi_eft reçoit l'EFT."""
	nom_cf = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": "lsi_eft"})
	if nom_cf:
		frappe.db.set_value("Custom Field", nom_cf, {"options": "EFT", "label": "EFT (étude technique)"})
	for d in frappe.get_all(doctype, filters={"lsi_eft": ("is", "set")}, fields=["name", "lsi_eft"]):
		eft = frappe.db.get_value("Chiffrage", d.lsi_eft, "eft")
		if eft:
			frappe.db.set_value(doctype, d.name, {"lsi_chiffrage": d.lsi_eft, "lsi_eft": eft}, update_modified=False)
	frappe.clear_cache(doctype=doctype)


def _evenements_et_configuration():
	"""Événements EFT : document = EFT (le renommage les avait pointés sur Chiffrage). Définitions communes changées (ex. « Devis
	envoyé ») alignées sur le profil commun ; configuration insérée ; événements de fin du parcours alignés sur le profil du site."""
	for nom in frappe.get_all("Evenement Phase", filters={"document_type": "Chiffrage", "name": ("like", "EFT %")}, pluck="name"):
		frappe.db.set_value("Evenement Phase", nom, "document_type", "EFT")
	alignement.aligner_evenements_communs()
	config.charger()
	alignement.aligner_fins_de_parcours()


def _registre_demo(correspondance):
	"""Registre du jeu DÉMO : anciens noms d'EFT → chiffrages renommés + nouvelles EFT (l'annulation reste exacte)."""
	from lsi_inspection.demo import lot3

	lot3.renommer_registre(correspondance)
