"""DÉMO logistique (site de test uniquement) : une commande validée dont le chiffrage a un équipement PARTAGÉ.

Lancer : bench --site tic.local execute lsi_inspection.logistique.demo.preparer
Crée, avec les fonctions natives et celles de l'app (aucune écriture directe en base) :
1. une variante « copie » de EFT-2026-0002-A (variantes.nouvelle_variante) ;
2. dans cette variante, un groupe « Transport (partagé) » qui reçoit le véhicule (VEH-J), partagé entre les deux prestations
   par actions.partager_groupe (la fonction du bouton « Partager un groupe ») ;
3. la validation de la variante (workflow natif Chiffrer → Valider), son devis (devis.creer_devis) validé, la commande validée
   (mappage natif Quotation → Sales Order) — la variante devient « Retenue » (hook existant), EFT-2026-0002-A « Non retenue » ;
4. un utilisateur et un salarié « Inspecteur Démo Logistique » (pool Inspecteur RT niveau II, coût 0 : sans effet sur les
   chiffrages, la règle du pool ignore les coûts nuls) pour montrer l'assignation des tâches.
Le besoin logistique N'EST PAS créé : c'est le bouton de la commande qui le crée pendant la démo.
Sortie : dictionnaire des documents créés (à reporter dans docs/logistique/JOURNAL.md).
"""

import json

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, nowdate

EFT, SOURCE = "EFT-2026-0002", "EFT-2026-0002-A"
VEHICULE = "VEH-J"
LIBELLE = "Démo logistique (véhicule partagé)"
USER, EMPLOYE, POOL_RT = "inspecteur.demo@tic.local", "Inspecteur Démo Logistique", "Inspecteur RT niveau II"


def preparer():
	if frappe.local.site != "tic.local":
		frappe.throw("Démo logistique : site tic.local uniquement.")
	cree = {}
	cree["chiffrage"] = _variante()
	cree["devis"] = _devis(cree["chiffrage"])
	cree["commande"] = _commande(cree["devis"])
	cree.update(_inspecteur())
	frappe.db.commit()
	print(json.dumps(cree, indent=1, ensure_ascii=False))
	return cree


def _variante():
	"""Variante copiée de A, véhicule déplacé dans un groupe partagé entre les deux prestations, puis validée."""
	from lsi_inspection.chiffrage.moteur.actions import partager_groupe
	from lsi_inspection.chiffrage.variantes import nouvelle_variante

	nom = nouvelle_variante(EFT, depart="copie", source=SOURCE, libelle=LIBELLE)
	doc = frappe.get_doc("Chiffrage", nom)
	etapes = [e.prestation for e in doc.etapes]
	groupe = str(max(int(g.numero) for g in doc.groupes) + 1)
	doc.append("groupes", dict(numero=groupe, titre="Transport (partagé)"))
	doc.append("repartitions", dict(cible=groupe, etape=etapes[-1]))
	vehicule = next(p for p in doc.positions if p.item_code == VEHICULE and not p.parente)
	vehicule.groupe, vehicule.etape, vehicule.numero = groupe, etapes[-1], None  # renuméroté dans le groupe par organiser
	doc.save()
	partager_groupe(nom, groupe, json.dumps(etapes))
	apply_workflow(frappe.get_doc("Chiffrage", nom), "Chiffrer")
	apply_workflow(frappe.get_doc("Chiffrage", nom), "Valider")
	return nom


def _devis(chiffrage):
	"""Devis du chiffrage (chemin unique de l'app), lignes de quantité > 0, validé."""
	from lsi_inspection.chiffrage.devis import creer_devis

	doc = frappe.get_doc("Chiffrage", chiffrage)
	lignes = [p.name for p in doc.positions if not p.parente and p.qty]
	q = frappe.get_doc("Quotation", creer_devis(chiffrage, json.dumps(lignes)))
	q.submit()
	return q.name


def _commande(devis):
	"""Commande native depuis le devis, validée (le hook existant retient la variante)."""
	from erpnext.selling.doctype.quotation.quotation import make_sales_order

	so = make_sales_order(devis)
	so.delivery_date = add_days(nowdate(), 30)
	for it in so.items:
		it.delivery_date = so.delivery_date
	so.insert()
	so.submit()
	return so.name


def _inspecteur():
	"""Utilisateur + salarié du pool RT niveau II (coût 0), pour l'assignation des tâches. Rien si déjà présents."""
	out = {}
	if not frappe.db.exists("User", USER):
		u = frappe.get_doc(dict(doctype="User", email=USER, first_name=EMPLOYE, send_welcome_email=0, enabled=1))
		u.append("roles", dict(role="Projects User"))
		u.insert(ignore_permissions=True)
		out["utilisateur"] = u.name
	if not frappe.db.exists("Employee", {"user_id": USER}):
		e = frappe.get_doc(dict(doctype="Employee", first_name=EMPLOYE, gender=frappe.get_all("Gender", pluck="name", limit=1)[0],
			date_of_birth="1990-01-01", date_of_joining="2026-01-01", company=frappe.db.get_value("Company", {}, "name"),
			designation=POOL_RT, status="Active", user_id=USER, lsi_cout_journalier=0))
		e.insert()
		out["salarie"] = e.name
	return out
