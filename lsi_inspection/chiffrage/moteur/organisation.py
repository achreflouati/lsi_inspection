"""Organisation automatique d'un chiffrage : prestation → groupe, numérotation (aussi pendant la saisie), sous-lignes."""

import frappe
from frappe.utils import cint, cstr

from lsi_inspection.constants import PRIX_FIXE



def etapes_du_groupe(doc, numero):
	return [r.etape for r in doc.get("repartitions") or [] if cstr(r.cible) == cstr(numero) and r.etape]


def groupe_de_etape(doc, etape):
	return next((cstr(g.numero) for g in doc.get("groupes") or [] if etape in etapes_du_groupe(doc, g.numero)), None)


def _creer_groupe(doc, etape):
	n = cstr(_prochain_groupe(doc))
	libelle = next((e.libelle for e in doc.get("etapes") or [] if e.prestation == etape and e.libelle), None)
	doc.append("groupes", dict(numero=n, titre=libelle or frappe.db.get_value("Item", etape, "item_name") or etape))
	doc.append("repartitions", dict(cible=n, etape=etape))
	return n


def _suivant(prefixe, numeros):
	"""Prochain n° « <prefixe>.<k> » libre."""
	ks = [int(x.rsplit(".", 1)[1]) for x in numeros if x.startswith(f"{prefixe}.") and x.count(".") == prefixe.count(".") + 1
		and x.rsplit(".", 1)[1].isdigit()]
	return f"{prefixe}.{max(ks, default=0) + 1}"


def _est_prix_fixe(p):
	return bool(p and p.type_position and frappe.get_cached_value("Type Position", p.type_position, "mode") == PRIX_FIXE)


def organiser(doc, numeroter=True):
	"""L'utilisateur ne travaille que sur les prestations (étapes) : les groupes, la répartition et les n° suivent.
	- une prestation sans groupe (sans gamme) reçoit un groupe vide ;
	- une position reçoit le groupe de sa prestation (ou la prestation de son groupe) ; une sous-position suit sa parente ;
	- une position sans n° reçoit le suivant de son groupe (ou de sa parente)."""
	presentes = [e.prestation for e in doc.get("etapes") or [] if e.prestation]
	for p in doc.get("positions") or []:  # prestation choisie sur une ligne mais absente des étapes : ajoutée
		if p.etape and p.etape not in presentes and not p.parente:
			doc.append("etapes", dict(prestation=p.etape, qty=1, gamme_appliquee=1))
			presentes.append(p.etape)
	for e in doc.get("etapes") or []:
		if e.prestation and not groupe_de_etape(doc, e.prestation):
			if cint(e.gamme_appliquee) or not frappe.db.exists("Gamme", {"prestation": e.prestation, "actif": 1}):
				_creer_groupe(doc, e.prestation)
	positions = doc.get("positions") or []
	par_num = {p.numero: p for p in positions if p.numero}
	for p in sorted(positions, key=lambda x: bool(x.parente)):  # positions principales d'abord
		if p.parente and p.parente in par_num:
			parent = par_num[p.parente]
			p.groupe, p.etape = parent.groupe, parent.etape or p.etape
			continue
		if p.etape and (not p.groupe or p.etape not in etapes_du_groupe(doc, p.groupe)):
			p.groupe = groupe_de_etape(doc, p.etape) or _creer_groupe(doc, p.etape)
		elif not p.etape and p.groupe:
			p.etape = (etapes_du_groupe(doc, p.groupe) or [None])[0]
		elif not p.etape and not p.groupe and len(presentes) == 1:
			p.etape = presentes[0]
			p.groupe = groupe_de_etape(doc, p.etape) or _creer_groupe(doc, p.etape)
	if not numeroter:
		return
	# n° donnés aussi pendant la saisie (aperçu) : une ligne dont le n° ne correspond plus à son groupe ou à sa parente
	# (ex. numérotée 1.21 puis rattachée à 1.20) est renumérotée, et ses sous-lignes la suivent
	numeros = {p.numero for p in positions if p.numero}
	for p in sorted(positions, key=lambda x: bool(x.parente)):  # positions principales d'abord (les sous-lignes suivent)
		prefixe = cstr(p.parente or p.groupe)
		if not prefixe:
			continue
		if p.numero and p.numero.startswith(prefixe + ".") and p.numero.count(".") == prefixe.count(".") + 1:
			continue
		if p.numero and p.parente and not _est_prix_fixe(par_num.get(p.parente)):
			continue  # rattachement invalide : n° conservé, l'erreur de structure le citera tel que l'utilisateur le voit
		ancien = p.numero
		numeros.discard(ancien)
		p.numero = _suivant(prefixe, numeros)
		numeros.add(p.numero)
		if ancien:
			for k in positions:
				if k.parente == ancien:
					k.parente = p.numero


def _prochain_groupe(doc):
	nums = [int(g.numero) for g in doc.get("groupes") or [] if cstr(g.numero).isdigit()]
	return max(nums, default=0) + 1
