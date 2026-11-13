"""Planification d'un Besoin Logistique : affectations complétées, occupations (ressource partagée dépliée par prestation),
statut calculé. Les contrôles sont dans controles.py ; la génération des OM dans om.py.

Vocabulaire :
- ligne prévue  : ligne de la table ressources (extraite du chiffrage), repérée par son n° (numero) ;
- affectation   : ligne de la table affectations (ressource nominative sur une ligne prévue) ;
- occupation    : (prestation, ressource, dates, quantité, part) — une affectation de ressource partagée sans prestation donne une
                  occupation par prestation de sa répartition, avec la part du chiffrage.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from lsi_inspection.constants import ANNULE, BROUILLON, EN_PLANIFICATION, OM_GENERES, PLANIFIE
from lsi_inspection.logistique.pools import nom_ressource


def valider(doc):
	"""Besoin Logistique.validate : affectations complétées, contrôles (controles.py), statut."""
	from lsi_inspection.logistique.controles import controler

	if doc.statut == ANNULE and not doc.flags.changement_statut:
		frappe.throw(_("Le besoin {0} est annulé : il ne peut plus être modifié.").format(doc.name))
	_options_lignes(doc)
	for a in doc.affectations:
		completer(doc, a)
	controler(doc)
	doc.statut = statut(doc)


def _options_lignes(doc):
	"""Options du champ « Ligne (n°) » des affectations = n° des lignes prévues (contrôle côté serveur, l'écran les propose)."""
	numeros = {r.numero for r in doc.ressources}
	for a in doc.affectations:
		if a.ligne_ressource and a.ligne_ressource not in numeros:
			frappe.throw(_("Affectation ligne {0} : n° {1} inconnu (ressources prévues : {2}).").format(
				a.idx, a.ligne_ressource, ", ".join(sorted(numeros)) or "—"))


def doctypes_affectations(doc):
	"""Doctype et type de ressource de chaque affectation, repris de sa ligne prévue (avant le contrôle natif des liens)."""
	for a in doc.affectations:
		r = ligne(doc, a.ligne_ressource)
		if r:
			a.ressource_doctype, a.type_ressource = r.ressource_doctype, r.type_ressource


def ligne(doc, numero):
	"""Ligne prévue (table ressources) de n° donné, ou None."""
	return next((r for r in doc.ressources if r.numero == numero), None)


def parts(doc, numero):
	"""{prestation: part %} d'une ligne partagée (table repartitions)."""
	return {r.prestation: flt(r.part) for r in doc.repartitions if r.numero == numero}


def prestation(doc, nom):
	"""Ligne de la table prestations pour une prestation, ou None."""
	return next((p for p in doc.prestations if p.prestation == nom), None)


def completer(doc, a):
	"""Complète une affectation depuis sa ligne prévue : doctype, type, prestation (ligne simple), dates de la prestation,
	quantité prévue, nom de la ressource. Ne remplace jamais une valeur saisie."""
	r = ligne(doc, a.ligne_ressource)
	if not r:
		return
	a.ressource_doctype, a.type_ressource = r.ressource_doctype, r.type_ressource
	if not cint(r.partagee):
		a.prestation = a.prestation or r.prestation
		a.part = None
	elif a.prestation and not flt(a.part):
		a.part = parts(doc, r.numero).get(a.prestation)
	p = prestation(doc, a.prestation) if a.prestation else None
	if p:
		a.date_debut = a.date_debut or p.date_debut
		a.date_fin = a.date_fin or p.date_fin
	elif cint(r.partagee):  # toutes les prestations : dates de la plus tôt à la plus tardive
		dates = [prestation(doc, e) for e in parts(doc, r.numero)]
		debuts = [getdate(x.date_debut) for x in dates if x and x.date_debut]
		fins = [getdate(x.date_fin) for x in dates if x and x.date_fin]
		a.date_debut = a.date_debut or (min(debuts) if debuts else None)
		a.date_fin = a.date_fin or (max(fins) if fins else None)
	if not flt(a.qty):
		a.qty = r.qty
	a.nom_ressource = nom_ressource(a.ressource_doctype, a.ressource) if a.ressource else None


def occupations(doc):
	"""Occupations du besoin (affectations avec ressource), ressource partagée sans prestation dépliée par prestation.
	Sortie : liste de frappe._dict(affectation, ligne, prestation, doctype, ressource, debut, fin, qty, part)."""
	out = []
	for a in doc.affectations:
		r = ligne(doc, a.ligne_ressource)
		if not a.ressource or not r:
			continue
		cibles = {a.prestation: flt(a.part) or None} if a.prestation else parts(doc, r.numero)
		for e, part in cibles.items():
			out.append(frappe._dict(affectation=a, ligne=r, prestation=e, doctype=a.ressource_doctype, ressource=a.ressource,
				debut=getdate(a.date_debut) if a.date_debut else None, fin=getdate(a.date_fin) if a.date_fin else None,
				qty=flt(a.qty), part=part if cint(r.partagee) else None))
	return out


def statut(doc):
	"""Statut calculé : Annulé et OM générés sont posés par les boutons (om.py) ; sinon Planifié (toutes les prestations
	datées et chaque ligne prévue affectée), En planification (une date ou une affectation saisie), Brouillon."""
	if doc.statut in (ANNULE, OM_GENERES):
		return doc.statut
	datees = all(p.date_debut and p.date_fin for p in doc.prestations)
	affectees = {a.ligne_ressource for a in doc.affectations if a.ressource}
	if doc.prestations and datees and all(r.numero in affectees for r in doc.ressources):
		return PLANIFIE
	if affectees or any(p.date_debut or p.date_fin for p in doc.prestations):
		return EN_PLANIFICATION
	return BROUILLON


@frappe.whitelist(methods=["POST"])
def preparer_affectations(besoin):
	"""Bouton « Préparer les affectations » : une affectation vide (ressource à choisir) par ligne prévue qui n'en a pas.
	Ressource partagée : une ligne sans prestation (= toutes ses prestations). Sortie : nombre de lignes ajoutées."""
	doc = frappe.get_doc("Besoin Logistique", besoin)
	doc.check_permission("write")
	presentes = {a.ligne_ressource for a in doc.affectations}
	ajout = 0
	for r in doc.ressources:
		if r.numero not in presentes:
			doc.append("affectations", dict(ligne_ressource=r.numero, ressource=r.ressource_chiffrage or None))
			ajout += 1
	doc.save()
	return ajout
