"""Gammes : liste type des lignes d'une prestation, appliquée au chiffrage (une fois par prestation)."""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from lsi_inspection.chiffrage.moteur.actions import _chiffrage_brouillon
from lsi_inspection.chiffrage.moteur.couts import type_par_defaut
from lsi_inspection.chiffrage.moteur.organisation import _prochain_groupe


def numeros_gamme(lignes):
	"""N° relatif de chaque ligne : n° imposé, sinon automatique (lignes principales 1, 2, 3… ; sous-lignes <parente>.1, .2…)."""
	nums, imposes = {}, {cstr(l.numero) for l in lignes if l.numero}
	compteur, sous = 0, {}
	for l in sorted(lignes, key=lambda x: x.idx):
		if cint(l.get("parente_ligne")):
			parent = nums.get(cint(l.parente_ligne))
			if not parent:
				frappe.throw(_("Gamme, ligne {0} : la ligne parente n° {1} doit précéder la sous-ligne.").format(l.idx, l.parente_ligne))
			if l.numero:
				nums[l.idx] = cstr(l.numero)
			else:
				sous[parent] = sous.get(parent, 0) + 1
				nums[l.idx] = f"{parent}.{sous[parent]}"
		elif l.numero:
			nums[l.idx] = cstr(l.numero)
		else:
			compteur += 1
			while str(compteur) in imposes:
				compteur += 1
			nums[l.idx] = str(compteur)
	return nums


def appliquer_gamme(doc, etape):
	"""La gamme de la prestation crée le groupe et préremplit positions et sous-positions (× quantité de l'étape)."""
	nom = frappe.db.get_value("Gamme", {"prestation": etape.prestation, "actif": 1})
	if not nom:
		return False
	gamme = frappe.get_doc("Gamme", nom)
	n = cstr(_prochain_groupe(doc))
	nums = numeros_gamme(gamme.lignes)
	doc.append("groupes", dict(numero=n, titre=gamme.titre_groupe))
	for l in gamme.lignes:
		parent = nums.get(cint(l.get("parente_ligne"))) if cint(l.get("parente_ligne")) else None
		doc.append("positions", dict(numero=f"{n}.{nums[l.idx]}", groupe=n, etape=etape.prestation, parente=f"{n}.{parent}" if parent else None,
			type_position=l.type_position or type_par_defaut(l.item_code), item_code=l.item_code, designation_2=l.designation_2,
			qty=flt(l.qty) * flt(etape.qty or 1), uom=l.uom))
	doc.append("repartitions", dict(cible=n, etape=etape.prestation))
	etape.gamme_appliquee = 1
	return True


def appliquer_gammes(doc):
	"""Étape (prestation) ajoutée : sa gamme est appliquée une seule fois."""
	for e in doc.get("etapes") or []:
		if not cint(e.gamme_appliquee) and e.prestation:
			appliquer_gamme(doc, e)


@frappe.whitelist(methods=["POST"])
def ajouter_gamme(chiffrage, prestation, qty=1):
	"""Bouton « Ajouter depuis une gamme » : ajoute la prestation (étape) et applique sa gamme immédiatement."""
	doc = _chiffrage_brouillon(chiffrage)
	if not frappe.db.exists("Gamme", {"prestation": prestation, "actif": 1}):
		frappe.throw(_("Aucune gamme active pour la prestation {0}.").format(prestation))
	etape = next((e for e in doc.etapes if e.prestation == prestation and not cint(e.gamme_appliquee)), None)
	if not etape:
		etape = doc.append("etapes", dict(prestation=prestation, qty=flt(qty) or 1))
	else:
		etape.qty = flt(qty) or etape.qty
	appliquer_gamme(doc, etape)
	doc.save()
	return doc.name
