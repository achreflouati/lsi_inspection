"""Contrôles des affectations d'un Besoin Logistique, à chaque enregistrement.

Bloquants (toutes les erreurs sont réunies dans un seul message) :
- dates : début et fin renseignés, fin ≥ début ;
- prestation : celle de la ligne prévue (un inspecteur ne fait que sa mission) ; ligne partagée : une de ses prestations ;
  main-d'œuvre partagée : prestation obligatoire (un employé ne peut pas être sur deux prestations en même temps) ;
- a) ressource qualifiée : pools.ressource_qualifiee (appartenance au pool aujourd'hui) ;
- d) actif hors service (Asset.status dans ACTIFS_HORS_SERVICE) ;
- b) conflit : un employé ou un actif sur deux prestations aux mêmes dates — dans ce besoin, dans un autre besoin non annulé,
     dans un OM non annulé. EXCEPTION : un actif d'une ligne PARTAGÉE dans le chiffrage, sur les prestations qu'elle partage.
Non bloquant :
- c) employé en congé approuvé (Leave Application) sur la période → avertissement (message + colonne « Remarque »).
"""

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate

from lsi_inspection.constants import (ACTIFS_HORS_SERVICE, ANNULE, CONGE_APPROUVE, DOCTYPES_A_CONFLIT, MAIN_OEUVRE)
from lsi_inspection.logistique.planification import ligne, occupations, parts
from lsi_inspection.logistique.pools import ressource_qualifiee


def controler(doc):
	"""Lance tous les contrôles ; lève une erreur unique listant les refus ; affiche les avertissements de congé."""
	erreurs = []
	for a in doc.affectations:
		if a.ressource:
			erreurs += _controler_affectation(doc, a)
	if not erreurs:  # conflits seulement sur des affectations valides (dates présentes)
		occ = occupations(doc)
		erreurs += _conflits_internes(occ) + _conflits_externes(doc, occ)
	if erreurs:
		frappe.throw("<br>".join(erreurs), title=_("Affectations refusées"))
	_conges(doc)


def _controler_affectation(doc, a):
	"""Contrôles d'une affectation (dates, prestation, pool, actif hors service). Sortie : liste de messages."""
	r, quoi = ligne(doc, a.ligne_ressource), _("Ligne {0} ({1})").format(a.idx, a.ressource)
	if not r:
		return [_("{0} : ligne prévue introuvable.").format(quoi)]
	out = []
	if not a.date_debut or not a.date_fin:
		out.append(_("{0} : dates de début et de fin obligatoires (ou dates de la prestation).").format(quoi))
	elif getdate(a.date_fin) < getdate(a.date_debut):
		out.append(_("{0} : la fin est avant le début.").format(quoi))
	if cint(r.partagee):
		if a.prestation and a.prestation not in parts(doc, r.numero):
			out.append(_("{0} : la ligne {1} n'est partagée qu'entre {2}.").format(quoi, r.numero, ", ".join(parts(doc, r.numero))))
		if not a.prestation and r.type_ressource == MAIN_OEUVRE:
			out.append(_("{0} : main-d'œuvre partagée — choisissez la prestation (un employé ne fait qu'une mission à la fois).").format(quoi))
	elif a.prestation != r.prestation:
		out.append(_("{0} : la ligne {1} est prévue pour la prestation {2}, pas {3}.").format(quoi, r.numero, r.prestation, a.prestation))
	ok, raison = ressource_qualifiee({"doctype": a.ressource_doctype, "name": a.ressource},
		{"type_position": r.type_position, "pool": r.pool}, a.date_debut)
	if not ok:
		out.append(f"{quoi} : {raison}")
	if a.ressource_doctype == "Asset":
		etat = frappe.db.get_value("Asset", a.ressource, "status")
		if etat in ACTIFS_HORS_SERVICE:
			out.append(_("{0} : actif hors service (statut « {1} »).").format(quoi, _(etat)))
	return out


def _chevauche(d1, f1, d2, f2):
	return d1 and f1 and d2 and f2 and d1 <= f2 and d2 <= f1


def _periode(d, f):
	return _("du {0} au {1}").format(formatdate(d), formatdate(f))


def _conflits_internes(occ):
	"""Même ressource, deux prestations différentes, dates qui se chevauchent, dans ce besoin.
	Exception : un actif de la même ligne partagée (les deux prestations sont dans sa répartition)."""
	out = []
	for i, x in enumerate(occ):
		for y in occ[i + 1:]:
			if x.doctype not in DOCTYPES_A_CONFLIT or (x.doctype, x.ressource) != (y.doctype, y.ressource):
				continue
			if x.prestation == y.prestation or not _chevauche(x.debut, x.fin, y.debut, y.fin):
				continue
			if x.doctype == "Asset" and x.ligne.numero == y.ligne.numero and cint(x.ligne.partagee):
				continue  # équipement partagé dans le chiffrage entre ces prestations : autorisé
			out.append(_("Conflit : {0} est sur {1} et sur {2} aux mêmes dates ({3}).").format(
				x.affectation.nom_ressource or x.ressource, x.prestation, y.prestation, _periode(max(x.debut, y.debut), min(x.fin, y.fin))))
	return list(dict.fromkeys(out))


def _conflits_externes(doc, occ):
	"""Même ressource aux mêmes dates dans un autre besoin non annulé ou un OM non annulé (hors OM de ce besoin)."""
	out = []
	for o in occ:
		if o.doctype not in DOCTYPES_A_CONFLIT or not o.debut or not o.fin:
			continue
		for dt, nom, d, f in _autres_occupations(doc, o):
			out.append(_("Conflit : {0} est déjà affecté(e) {1} sur {2} {3}.").format(
				o.affectation.nom_ressource or o.ressource, _periode(d, f), _(dt), nom))
	return list(dict.fromkeys(out))


def _autres_occupations(doc, o):
	"""[(doctype, document, début, fin)] des autres besoins et OM où la ressource est occupée sur la période de o."""
	out = []
	for parent_dt, enfant_dt, exclure in (("Besoin Logistique", "Besoin Logistique Affectation", "name"),
			("Ordre de Mission", "Ordre Mission Ressource", "besoin_logistique")):
		P, E = frappe.qb.DocType(parent_dt), frappe.qb.DocType(enfant_dt)
		q = (frappe.qb.from_(E).join(P).on(P.name == E.parent)
			.select(P.name, E.date_debut, E.date_fin)
			.where((E.parenttype == parent_dt) & (E.ressource_doctype == o.doctype) & (E.ressource == o.ressource)
				& (E.date_debut <= o.fin) & (E.date_fin >= o.debut) & (P.statut != ANNULE)))
		q = q.where(P[exclure].isnull() | (P[exclure] != (doc.name or "")))
		out += [(parent_dt, n, d, f) for n, d, f in q.run()]
	return out


def _conges(doc):
	"""c) Employé en congé approuvé sur la période : avertissement non bloquant (colonne Remarque + message + résumé)."""
	alertes = []
	for a in doc.affectations:
		a.remarque = None
		if a.ressource_doctype != "Employee" or not a.ressource or not a.date_debut or not a.date_fin:
			continue
		conges = frappe.get_all("Leave Application", filters={"employee": a.ressource, "status": CONGE_APPROUVE, "docstatus": 1,
			"from_date": ["<=", a.date_fin], "to_date": [">=", a.date_debut]}, fields=["name", "from_date", "to_date"])
		if conges:
			a.remarque = "; ".join(_("En congé {0} ({1})").format(_periode(c.from_date, c.to_date), c.name) for c in conges)
			alertes.append(f"{a.nom_ressource or a.ressource} : {a.remarque}")
	doc.avertissements = "\n".join(alertes) or None
	if alertes:
		frappe.msgprint("<br>".join(alertes), title=_("Attention : congés approuvés"), indicator="orange")
