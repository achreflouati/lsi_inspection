"""Hooks de l'opportunité et actions de l'écran : « Terminer ma phase », informations pour le bandeau."""

import frappe
from frappe import _
from frappe.utils import cint, cstr, now_datetime

from lsi_inspection.constants import A_VENIR, EN_COURS, OPP_FERMEES, RETOUR_ARRIERE, SAUTEE, TERMINEE
from lsi_inspection.commercial.phases.parcours import type_parcours
from lsi_inspection.commercial.phases.tableau import TABLE, _action, _affecter, _demarrer, _entete, _fermer_todos, _historique, _historique_inchange, _remettre, _sequence, _terminer, construire, courante


def opportunity_validate(doc, method=None):
	principales = [r for r in doc.get("lsi_departements") or [] if cint(r.principal)]
	if len(principales) > 1:
		frappe.throw(_("Un seul département principal par opportunité (lignes {0}).").format(", ".join(str(r.idx) for r in principales)))
	_historique_inchange(doc)
	avant = doc.get_doc_before_save()
	if doc.is_new() or not doc.get(TABLE):
		construire(doc)
	elif avant and avant.opportunity_type != doc.opportunity_type and doc.status not in OPP_FERMEES and not doc.flags.lsi_moteur:
		construire(doc, raison=_("Type {0} → {1}").format(avant.opportunity_type or "-", doc.opportunity_type or "-"))
	_entete(doc)


def opportunity_on_update(doc, method=None):
	"""Après enregistrement : tâches (ToDo natif) des phases quittées / commencées. Jamais bloquant.
	Les notifications d'entrée / de retard sont des Notifications natives (Value Change sur sales_stage, Days After sur
	lsi_echeance_phase), paramétrées à l'écran."""
	actions, doc.flags.lsi_actions = doc.flags.lsi_actions or [], []
	for quoi, phase in sorted(actions, key=lambda a: a[0] != "fin"):
		ligne = next((r for r in doc.get(TABLE) or [] if r.phase == phase), None)
		if not ligne:
			continue
		try:
			if quoi == "fin":
				_fermer_todos(doc, phase)
			else:
				_affecter(doc, ligne)
		except Exception:
			frappe.log_error(title=_("Phases : actions de la phase {0}").format(phase), reference_doctype="Opportunity", reference_name=doc.name)


def _peut_terminer(opp, cur, user=None):
	user = user or frappe.session.user
	return bool(cur) and (user in cstr(cur.responsables).split(", ") or "System Manager" in frappe.get_roles(user))


@frappe.whitelist()
def infos_phases(opportunity):
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	cur = courante(opp)
	seq = _sequence(opp)
	suivante = next((r for r in seq if cur and cint(r.ordre) > cint(cur.ordre) and r.statut == A_VENIR), None)
	return dict(courante=cur.phase if cur else None, finale=cur.phase_finale if cur else None, suivante=suivante.phase if suivante else None,
		peut_terminer=_peut_terminer(opp, cur) and not (cur and cur.phase_finale), choix=[dict(phase=r.phase, ordre=r.ordre, statut=r.statut,
		obligatoire=r.obligatoire, retour=bool(cur and cint(r.ordre) < cint(cur.ordre))) for r in seq if not cur or r.phase != cur.phase])


@frappe.whitelist(methods=["POST"])
def terminer_phase(opportunity, vers=None, commentaire=None):
	"""Termine la phase en cours et passe à « vers » (par défaut la suivante) ; une phase antérieure = retour arrière."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("write")
	cur = courante(opp)
	if not cur:
		frappe.throw(_("Aucune phase en cours."))
	if not _peut_terminer(opp, cur):
		frappe.throw(_("Seuls les responsables de la phase « {0} » peuvent la terminer.").format(cur.phase))
	if cur.phase_finale:
		frappe.throw(_("La phase finale « {0} » se termine par son événement, pas à la main.").format(cur.phase))
	seq = _sequence(opp)
	if vers:
		cible = next((r for r in seq if r.phase == vers), None)
		if not cible:
			frappe.throw(_("La phase {0} n'est pas dans le parcours (ou est hors séquence).").format(vers))
		if cible.phase == cur.phase:
			frappe.throw(_("Choisissez une autre phase que la phase en cours."))
	else:
		cible = next((r for r in seq if cint(r.ordre) > cint(cur.ordre) and r.statut == A_VENIR), None)
	maintenant = now_datetime()
	if cible and cint(cible.ordre) < cint(cur.ordre):
		for r in seq:
			if cint(cible.ordre) < cint(r.ordre) <= cint(cur.ordre):
				if r.statut == EN_COURS:
					_action(opp, "fin", r.phase)
				_remettre(r)
		_demarrer(opp, cible, maintenant)
		_historique(opp, cur.phase, cible.phase, RETOUR_ARRIERE, commentaire=commentaire, maintenant=maintenant)
	else:
		entre = [r for r in seq if cible and cint(cur.ordre) < cint(r.ordre) < cint(cible.ordre) and r.statut == A_VENIR]
		bloquantes = [r.phase for r in entre if cint(r.obligatoire)]
		if bloquantes:
			frappe.throw(_("Phase obligatoire, elle ne peut pas être sautée : {0}.").format(", ".join(bloquantes)))
		_terminer(opp, cur, TERMINEE, maintenant)
		for r in entre:
			_terminer(opp, r, SAUTEE, maintenant)
			r.commentaire = _("Sautée par {0}").format(frappe.utils.get_fullname(frappe.session.user))
		if cible:
			_demarrer(opp, cible, maintenant)
		texte = (_("Sautées : {0}").format(", ".join(r.phase for r in entre)) + (" — " if commentaire else "")) if entre else ""
		_historique(opp, cur.phase, cible.phase if cible else None, SAUTEE if entre else TERMINEE,
			commentaire=(texte + cstr(commentaire)) or None, maintenant=maintenant)
	opp.flags.lsi_moteur = True
	opp.save(ignore_permissions=True)
	return courante(opp).phase if courante(opp) else None


def type_on_update(doc, method=None):
	"""Le parcours a changé : les opportunités ouvertes concernées suivent (phases faites conservées)."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.lsi_chargement_config:
		return
	types = [doc.name]
	if cint(doc.get("lsi_parcours_defaut")):
		types += [t for t in frappe.get_all("Opportunity Type", pluck="name") if t != doc.name and type_parcours(t) == doc.name]
	for name in frappe.get_all("Opportunity", filters={"opportunity_type": ("in", types), "status": ("not in", OPP_FERMEES)}, pluck="name"):
		opp = frappe.get_doc("Opportunity", name)
		if construire(opp, raison=_("Parcours du type {0} modifié").format(doc.name)):
			opp.flags.lsi_moteur = True
			opp.save(ignore_permissions=True)
