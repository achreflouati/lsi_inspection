"""Variantes de chiffrage d'une EFT : lettres A, B, C…, création (vide, prestations de l'opportunité ou copie), comparaison,
une seule variante « Retenue » par EFT (les autres passent « Non retenue », réversible)."""

import string

import frappe
from frappe import _
from frappe.utils import cint, flt

from lsi_inspection.constants import NON_RETENUE, RETENUE


# ------------------------------------------------------------------ lettres (fonction pure)
def lettre_suivante(lettres):
	"""Première lettre libre : A, B… Z, puis AA, AB… ; `lettres` = lettres déjà prises."""
	prises = set(lettres)
	alphabet = string.ascii_uppercase
	candidates = list(alphabet) + [a + b for a in alphabet for b in alphabet]
	return next(x for x in candidates if x not in prises)


# ------------------------------------------------------------------ nommage (Chiffrage.autoname)
def nommer(doc):
	"""Chiffrage.autoname : nom « <EFT>-<variante> », lettre libre suivante ; une nouvelle version (amend) garde la sienne (nommage natif)."""
	# autoname n'est appelé que pour un nouveau document hors version (amend) : toujours une nouvelle lettre (copie comprise)
	ancienne = doc.variante
	lettres = frappe.get_all("Chiffrage", filters={"eft": doc.eft}, pluck="variante")
	doc.variante = lettre_suivante([x for x in lettres if x])
	if not doc.libelle_variante or doc.libelle_variante == _("Variante {0}").format(ancienne):
		doc.libelle_variante = _("Variante {0}").format(doc.variante)
	doc.name = f"{doc.eft}-{doc.variante}"


# ------------------------------------------------------------------ création
@frappe.whitelist(methods=["POST"])
def nouvelle_variante(eft, depart="vide", source=None, libelle=None):
	"""Nouvelle variante de l'EFT. depart : « vide », « opportunite » (prestations demandées, gammes appliquées) ou « copie »
	(de `source` : lignes reprises, coûts recalculés). Renvoie le nom du chiffrage créé."""
	etude = frappe.get_doc("EFT", eft)
	etude.check_permission("read")
	if etude.docstatus == 2:
		frappe.throw(_("L'EFT {0} est annulée.").format(eft))
	if depart == "copie":
		doc = _copie(source, eft)
	else:
		doc = frappe.new_doc("Chiffrage")
		doc.update(dict(eft=eft, titre=etude.titre or etude.name))
		if depart == "opportunite":
			for it in frappe.get_doc("Opportunity", etude.opportunity).get("items") or []:
				if it.item_code:
					doc.append("etapes", dict(prestation=it.item_code, qty=flt(it.qty) or 1, uom=it.uom))
	doc.libelle_variante = libelle or None
	doc.insert()
	return doc.name


def _copie(source, eft):
	"""Copie d'une variante de la même EFT : structure et prix repris, nouvelle lettre, brouillon, coûts recalculés à l'insertion."""
	src = frappe.get_doc("Chiffrage", source)
	src.check_permission("read")
	if src.eft != eft:
		frappe.throw(_("La variante {0} n'appartient pas à l'EFT {1}.").format(source, eft))
	doc = frappe.copy_doc(src)
	doc.update(dict(variante=None, libelle_variante=None, workflow_state=None, amended_from=None))
	for p in doc.positions:
		p.retenue = 0 if not p.parente else p.retenue
	return doc


# ------------------------------------------------------------------ comparaison (tableau de l'EFT, calculé)
@frappe.whitelist()
def comparaison(eft):
	"""Dernière version de chaque variante de l'EFT : coût, prix, marge, marge %, statut et devis liés."""
	frappe.get_doc("EFT", eft).check_permission("read")
	versions = frappe.get_all("Chiffrage", filters={"eft": eft}, order_by="creation asc",
		fields=["name", "variante", "libelle_variante", "workflow_state", "docstatus", "total_cout", "total_prix", "total_marge", "taux_marge"])
	derniere = {}
	for v in versions:
		derniere[v.variante] = v  # la plus récente gagne (ordre de création)
	lignes = sorted(derniere.values(), key=lambda v: (len(v.variante or ""), v.variante or ""))
	for v in lignes:
		v.devis = frappe.get_all("Quotation", filters={"lsi_chiffrage": v.name, "docstatus": ("<", 2)}, fields=["name", "status", "docstatus"])
	return lignes


# ------------------------------------------------------------------ variante retenue
def apres_changement(doc):
	"""Chiffrage.on_change : une variante devient « Retenue » → les autres variantes validées de l'EFT passent « Non retenue »."""
	avant = doc.get_doc_before_save()
	if doc.workflow_state != RETENUE or (avant and avant.workflow_state == RETENUE):
		return
	for autre in frappe.get_all("Chiffrage", filters={"eft": doc.eft, "name": ("!=", doc.name), "docstatus": 1,
			"workflow_state": ("!=", NON_RETENUE)}, pluck="name"):
		frappe.get_doc("Chiffrage", autre).db_set("workflow_state", NON_RETENUE)


def retenir(chiffrage):
	"""Passe la variante « Retenue » (ex. devis commandé) ; les autres suivent par apres_changement. Sans effet si déjà retenue."""
	doc = frappe.get_doc("Chiffrage", chiffrage)
	if cint(doc.docstatus) == 1 and doc.workflow_state != RETENUE:
		doc.db_set("workflow_state", RETENUE)  # on_change → apres_changement (autres variantes), événements et notifications
