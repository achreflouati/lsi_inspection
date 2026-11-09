"""Alignements ponctuels appelés par les patchs de migration (jamais au chargement normal, qui reste en insertion seule).

- aligner_evenements_communs : les événements du profil COMMUN sont des définitions de l'app (aucune valeur métier) ; quand
  l'app change une définition (ex. « Devis envoyé »), l'existant est mis à jour sur les champs de définition.
- aligner_fins_de_parcours : quand un lot change les événements de fin demandés dans le profil du site, ils sont appliqués au
  parcours existant (phase par phase), seulement si l'événement existe ; le reste du parcours n'est pas touché.
"""

import os

import frappe

from lsi_inspection.config import _lire, dossiers, racine

CHAMPS_EVENEMENT = ("declencheur", "document_type", "champ_statut", "valeur", "sens", "champ_lien")


def aligner_evenements_communs():
	"""Met à jour la définition des événements communs existants ; renvoie le nombre d'événements modifiés."""
	n = 0
	for e in _lire(os.path.join(racine(), "commun"), "Evenement Phase"):
		if not frappe.db.exists("Evenement Phase", e["name"]):
			continue
		actuel = frappe.db.get_value("Evenement Phase", e["name"], CHAMPS_EVENEMENT, as_dict=True)
		ecarts = {c: e.get(c) for c in CHAMPS_EVENEMENT if (actuel.get(c) or None) != (e.get(c) or None)}
		if ecarts:
			frappe.db.set_value("Evenement Phase", e["name"], ecarts)
			n += 1
	return n


def aligner_fins_de_parcours(profil=None):
	"""Applique au parcours de chaque type d'opportunité les événements de fin du profil du site ; renvoie le nombre de lignes."""
	dossier = dossiers(profil)[-1]
	n = 0
	for t in _lire(dossier, "Opportunity Type"):
		if not frappe.db.exists("Opportunity Type", t["name"]):
			continue
		fins = {l["phase"]: l.get("evenement_fin") for l in t.get("lsi_parcours") or []}
		doc = frappe.get_doc("Opportunity Type", t["name"])
		modifie = False
		for ligne in doc.get("lsi_parcours") or []:
			cible = fins.get(ligne.phase)
			if cible and cible != ligne.evenement_fin and frappe.db.exists("Evenement Phase", cible):
				ligne.evenement_fin = cible
				modifie, n = True, n + 1
		if modifie:
			doc.flags.ignore_permissions = True
			doc.save()
	return n
