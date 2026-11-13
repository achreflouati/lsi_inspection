"""Calendrier des ressources : vue Calendrier native de « Ordre de Mission »
(doctype/ordre_de_mission/ordre_de_mission_calendar.js), UN ÉVÉNEMENT PAR RESSOURCE AFFECTÉE (ligne de l'OM), pas un par OM.

- titre : « <nom de la ressource> · <OM> · <lieu> » ; dates : celles de l'affectation, sinon celles de l'OM ;
- couleur : selon le type de ressource (COULEURS ci-dessous) ;
- clic : ouvre l'OM ; pas de glisser-déposer (les dates se changent dans le besoin, où elles sont contrôlées) ;
- filtres : ceux de la barre de filtres de la liste. Champs de l'OM (projet, client, statut…) → appliqués aux OM ;
  champs de la table « Ordre Mission Ressource » (type de ressource, pool, ressource…) → appliqués à chaque ligne.
  Les OM « Annulé » sont masqués, sauf si un filtre porte sur le statut.
"""

import frappe
from frappe.utils import getdate

from lsi_inspection.constants import ANNULE, CONSOMMABLE, EQUIPEMENT, MAIN_OEUVRE

OM, LIGNE = "Ordre de Mission", "Ordre Mission Ressource"
# Couleur par type de ressource : inspecteur (main-d'œuvre), véhicule / équipement, consommable
COULEURS = {MAIN_OEUVRE: "#2490EF", EQUIPEMENT: "#ECAD4B", CONSOMMABLE: "#48BB74"}
COULEUR_AUTRE = "#7C7C7C"
CHAMPS_LIGNE = ["parent", "type_ressource", "ressource_doctype", "ressource", "nom_ressource", "date_debut", "date_fin", "pool",
	"numero", "part"]


@frappe.whitelist()
def evenements(start, end, filters=None, **kwargs):
	"""get_events_method de la vue Calendrier (arguments natifs : start, end, filters).
	Sortie : [{name (OM), title, start, end, all_day, color, docstatus}] — un élément par ressource affectée."""
	frappe.has_permission(OM, "read", throw=True)
	debut, fin = getdate(start), getdate(end)
	filtres = frappe.parse_json(filters) or []
	f_om = [f for f in filtres if f[0] != LIGNE]
	f_ligne = [f for f in filtres if f[0] == LIGNE]
	if not any(f[1] == "statut" for f in f_om):
		f_om.append([OM, "statut", "!=", ANNULE])
	oms = {o.name: o for o in frappe.get_list(OM, filters=f_om,
		fields=["name", "lieu", "date_debut", "date_fin", "besoin_logistique"], limit_page_length=0)}
	if not oms:
		return []
	lignes = frappe.get_all(LIGNE, filters={"parenttype": OM, "parent": ["in", list(oms)]}, fields=CHAMPS_LIGNE, order_by="idx")
	pools = _pools_des_besoins({o.besoin_logistique for o in oms.values() if o.besoin_logistique})
	out = []
	for r in lignes:
		om = oms[r.parent]
		r.pool = r.pool or pools.get((om.besoin_logistique, r.numero))  # OM générés avant le champ « pool »
		d1, d2 = r.date_debut or om.date_debut, r.date_fin or om.date_fin  # getdate(None) donnerait aujourd'hui
		d1, d2 = getdate(d1) if d1 else None, getdate(d2) if d2 else None
		if not d1 or not d2 or d2 < debut or d1 > fin or not all(_correspond(r, f) for f in f_ligne):
			continue
		out.append(dict(name=om.name, title=" · ".join(x for x in (r.nom_ressource or r.ressource, om.name, om.lieu) if x),
			start=str(d1), end=str(d2), all_day=1, convert_to_user_tz=0, color=COULEURS.get(r.type_ressource, COULEUR_AUTRE),
			docstatus=1))  # docstatus > 0 : la vue native rend l'événement non déplaçable (editable = false)
	return out


def _pools_des_besoins(besoins):
	"""{(besoin, n° de ligne): pool} lu sur les ressources prévues des besoins."""
	if not besoins:
		return {}
	return {(r.parent, r.numero): r.pool for r in frappe.get_all("Besoin Logistique Ressource",
		filters={"parenttype": "Besoin Logistique", "parent": ["in", list(besoins)]}, fields=["parent", "numero", "pool"])}


def _correspond(ligne, filtre):
	"""Filtre de liste [doctype, champ, opérateur, valeur] appliqué à une ligne (opérateurs usuels de la barre de filtres)."""
	_dt, champ, op, valeur = filtre[:4]
	v = ligne.get(champ)
	texte = str(v or "").lower()
	if op == "=":
		return str(v or "") == str(valeur or "")
	if op == "!=":
		return str(v or "") != str(valeur or "")
	if op in ("in", "not in"):
		valeurs = valeur if isinstance(valeur, list) else [x.strip() for x in str(valeur or "").split(",")]
		return (str(v or "") in valeurs) == (op == "in")
	if op in ("like", "not like"):
		motif = str(valeur or "").replace("%", "").lower()
		return (motif in texte) == (op == "like")
	if op == "is":
		return bool(v) == (valeur == "set")
	return True  # opérateur non géré : pas de filtrage sur ce critère
