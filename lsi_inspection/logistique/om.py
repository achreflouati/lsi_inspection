"""Ordres de mission : génération depuis un Besoin Logistique planifié, tâches natives des inspecteurs, annulation.

Règles (confirmées) :
- UN OM PAR PRESTATION, rattaché au Projet, à la commande et à la ligne de commande principale de la prestation ;
- l'OM reçoit les ressources affectées à sa prestation ; une ressource partagée est présente dans chaque OM concerné avec sa part ;
- pour chaque employé (inspecteur) de l'OM : une Tâche native du Projet aux dates de son affectation, assignée à l'utilisateur
  de l'employé (Employee.user_id) s'il en a un.
Regénérer (après une modification du besoin) met à jour les OM et les tâches existants ; une tâche dont l'employé a quitté l'OM
passe « Cancelled ». Rien n'est jamais supprimé.
"""

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import getdate

from lsi_inspection.constants import ANNULE, OM_GENERES, PLANIFIE, TACHE_ANNULEE
from lsi_inspection.logistique.planification import occupations


@frappe.whitelist(methods=["POST"])
def generer_om(besoin):
	"""Bouton « Générer les OM » : un OM par prestation + tâches. Le besoin est d'abord réenregistré (contrôles relancés).
	Entrée : nom du besoin. Sortie : {"om": [noms], "taches": nombre de tâches créées ou mises à jour}."""
	doc = frappe.get_doc("Besoin Logistique", besoin)
	doc.check_permission("write")
	if doc.statut not in (PLANIFIE, OM_GENERES):
		frappe.throw(_("Le besoin doit être « Planifié » (toutes les prestations datées, chaque ressource prévue affectée)."))
	doc.save()  # contrôles relancés : un autre besoin a pu réserver une ressource entre-temps
	_dates_projet(doc.project, doc.prestations)  # avant les tâches : le natif les refuse après la fin prévue du projet
	occ = occupations(doc)
	noms, taches = [], 0
	for p in doc.prestations:
		om = _om(doc, p, [o for o in occ if o.prestation == p.prestation])
		taches += _taches(doc, om)
		p.ordre_mission = om.name
		noms.append(om.name)
	doc.statut = OM_GENERES
	doc.flags.changement_statut = True
	doc.save()
	return dict(om=noms, taches=taches)


def _om(doc, p, occ):
	"""Crée ou met à jour l'OM d'une prestation avec ses ressources (anciennes tâches gardées par ressource)."""
	om = frappe.get_doc("Ordre de Mission", p.ordre_mission) if p.ordre_mission else frappe.new_doc("Ordre de Mission")
	ancien = {(r.ressource_doctype, r.ressource): r.task for r in om.get("ressources") or [] if r.task}
	om.update(dict(prestation=p.prestation, libelle=p.libelle, customer=doc.customer, customer_name=doc.customer_name,
		statut=PLANIFIE, date_debut=p.date_debut, date_fin=p.date_fin, lieu=p.lieu, project=doc.project,
		besoin_logistique=doc.name, sales_order=doc.sales_order, ligne_commande=p.ligne_commande, item_commande=p.item_commande))
	om.set("ressources", [])
	for o in occ:
		om.append("ressources", dict(type_ressource=o.ligne.type_ressource, ressource_doctype=o.doctype, ressource=o.ressource,
			nom_ressource=o.affectation.nom_ressource, date_debut=o.debut, date_fin=o.fin, qty=o.qty, uom=o.ligne.uom, part=o.part,
			partagee=o.ligne.partagee, numero=o.ligne.numero, pool=o.ligne.pool, task=ancien.pop((o.doctype, o.ressource), None)))
	om.flags.taches_retirees = list(ancien.values())  # employés qui ont quitté l'OM : tâches annulées
	om.save()
	return om


def _taches(doc, om):
	"""Une tâche par employé de l'OM (créée ou mise à jour), assignée à son utilisateur. Sortie : nombre de tâches."""
	n = 0
	for r in om.ressources:
		if r.ressource_doctype != "Employee":
			continue
		t = frappe.get_doc("Task", r.task) if r.task and frappe.db.exists("Task", r.task) else frappe.new_doc("Task")
		t.update(dict(subject=f"{om.name} — {om.libelle or om.prestation} — {r.nom_ressource or r.ressource}"[:140],
			project=doc.project, exp_start_date=r.date_debut, exp_end_date=r.date_fin,
			description=_("Ordre de mission {0}, prestation {1}, lieu : {2}.").format(om.name, om.libelle or om.prestation, om.lieu or "—")))
		if t.status == TACHE_ANNULEE:
			t.status = "Open"
		t.save()
		r.db_set("task", t.name)
		_assigner(t, r.ressource)
		n += 1
	for nom in om.flags.taches_retirees or []:
		_annuler_tache(nom)
	return n


def _assigner(tache, employe):
	"""Assignation native (ToDo) à l'utilisateur de l'employé, s'il en a un et si elle n'existe pas déjà."""
	user = frappe.db.get_value("Employee", employe, "user_id")
	if not user or frappe.db.exists("ToDo", {"reference_type": "Task", "reference_name": tache.name, "allocated_to": user,
			"status": "Open"}):
		return
	assign_to.add(dict(assign_to=[user], doctype="Task", name=tache.name, description=tache.subject))


def _annuler_tache(nom):
	if nom and frappe.db.exists("Task", nom):
		t = frappe.get_doc("Task", nom)
		if t.status != TACHE_ANNULEE:
			t.status = TACHE_ANNULEE
			t.save()


def _dates_projet(project, prestations):
	"""Dates prévues du projet élargies pour couvrir les OM (le natif refuse une tâche après la fin prévue du projet)."""
	debuts = [getdate(p.date_debut) for p in prestations if p.date_debut]
	fins = [getdate(p.date_fin) for p in prestations if p.date_fin]
	if not project or not debuts:
		return
	projet = frappe.get_doc("Project", project)
	debut, fin = min(debuts), max(fins)
	change = False
	if not projet.expected_start_date or getdate(projet.expected_start_date) > debut:
		projet.expected_start_date, change = debut, True
	if not projet.expected_end_date or getdate(projet.expected_end_date) < fin:
		projet.expected_end_date, change = fin, True
	if change:
		projet.save()


@frappe.whitelist(methods=["POST"])
def annuler_besoin(besoin):
	"""Bouton « Annuler le besoin » : besoin « Annulé », ses OM « Annulé », leurs tâches « Cancelled ». Rien n'est supprimé."""
	doc = frappe.get_doc("Besoin Logistique", besoin)
	doc.check_permission("write")
	for nom in frappe.get_all("Ordre de Mission", filters={"besoin_logistique": doc.name}, pluck="name"):
		om = frappe.get_doc("Ordre de Mission", nom)
		for r in om.ressources:
			_annuler_tache(r.task)
		if om.statut != ANNULE:
			om.statut = ANNULE
			om.save()
	doc.statut = ANNULE
	doc.flags.changement_statut = True
	doc.save()
	return doc.name
