"""Responsables d'une phase : commercial, rôle, utilisateur ou pilote du département (selon le parcours)."""

import frappe
from frappe.utils import cint

from lsi_inspection.outils import utilisateur_responsable
from lsi_inspection.constants import RESP_PILOTE, RESP_ROLE, RESP_UTILISATEUR


def _utilisateurs_actifs(users):
	users = [u for u in dict.fromkeys(u for u in users if u and u != "Guest")]
	if not users:
		return []
	actifs = set(frappe.get_all("User", filters={"name": ("in", users), "enabled": 1}, pluck="name"))
	return [u for u in users if u in actifs]


def _ligne_principale(opp):
	lignes = opp.get("lsi_departements") or []
	return next((r for r in lignes if cint(r.principal)), lignes[0] if lignes else None)


def _pilote(opp, departement=None):
	if departement:
		r = next((r for r in opp.get("lsi_departements") or [] if r.departement == departement), None)
		if r and r.utilisateur_pilote:
			return r.utilisateur_pilote
		return utilisateur_responsable(departement)
	r = _ligne_principale(opp)
	return r.utilisateur_pilote if r else None


def _commercial(opp):
	return opp.get("opportunity_owner") or opp.owner


def responsables(opp, phase):
	users = []
	for r in phase.lignes:
		if r.type_responsable == RESP_ROLE and r.role:
			from frappe.utils.user import get_users_with_role

			users += get_users_with_role(r.role)
		elif r.type_responsable == RESP_UTILISATEUR:
			users.append(r.utilisateur)
		elif r.type_responsable == RESP_PILOTE:
			users.append(_pilote(opp, r.departement))
		else:
			users.append(_commercial(opp))
	return _utilisateurs_actifs(users)
