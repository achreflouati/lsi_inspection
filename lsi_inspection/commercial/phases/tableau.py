"""Tableau des phases de l'opportunité (lsi_phases), historique en ajout seul (lsi_historique_phases), en-tête et ToDo."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, cstr, get_datetime, now_datetime, time_diff_in_hours

from lsi_inspection.constants import ANNULEE, A_VENIR, EN_COURS, FAITES, OPP_FERMEES, PERDUE, RECONSTRUCTION, TERMINEE
from lsi_inspection.commercial.phases.parcours import phases_parcours
from lsi_inspection.commercial.phases.responsables import responsables


TABLE, HISTO = "lsi_phases", "lsi_historique_phases"
CHAMPS_HISTO = ("date", "de_phase", "vers_phase", "action", "par", "evenement", "document_type", "document_name", "motif", "commentaire")


def _lignes(opp):
	return sorted(opp.get(TABLE) or [], key=lambda r: (cint(r.ordre), r.idx or 0))


def courante(opp):
	return next((r for r in _lignes(opp) if r.statut == EN_COURS), None)


def _sequence(opp):
	"""Phases de la séquence normale (la phase finale Perdue est hors séquence)."""
	return [r for r in _lignes(opp) if r.phase_finale != PERDUE]


def _demarrer(opp, ligne, maintenant):
	ligne.statut, ligne.debut, ligne.fin = EN_COURS, maintenant, None
	ligne.echeance = add_to_date(maintenant, days=cint(ligne.duree_cible)) if cint(ligne.duree_cible) else None
	ph = next((p for p in phases_parcours(opp.opportunity_type) if p.phase == ligne.phase), None)
	ligne.responsables = ", ".join(responsables(opp, ph)) if ph else ligne.responsables
	_action(opp, "entree", ligne.phase)


def _terminer(opp, ligne, statut, maintenant):
	if ligne.statut == EN_COURS:
		_action(opp, "fin", ligne.phase)
	ligne.statut, ligne.fin = statut, maintenant
	ligne.debut = ligne.debut or maintenant


def _remettre(ligne):
	ligne.statut, ligne.debut, ligne.fin, ligne.echeance, ligne.duree_jours = A_VENIR, None, None, None, 0
	ligne.commentaire = None


def _action(opp, quoi, phase):
	opp.flags.lsi_actions = (opp.flags.lsi_actions or []) + [(quoi, phase)]


def _historique(opp, de, vers, action, evenement=None, source=None, motif=None, commentaire=None, maintenant=None):
	opp.append(HISTO, dict(date=maintenant or now_datetime(), de_phase=de, vers_phase=vers, action=action, par=frappe.session.user,
		evenement=evenement, document_type=source.doctype if source else None, document_name=source.name if source else None,
		motif=motif, commentaire=commentaire))


def construire(opp, raison=None):
	"""(Re)construit le tableau depuis le parcours. Phases faites et phase en cours conservées ; phases à venir recalculées ;
	une phase retirée du parcours est gardée si elle a été faite ou est en cours (« hors parcours »). Renvoie True si changé."""
	avant = [(r.phase, r.statut, cint(r.ordre)) for r in _lignes(opp)]
	existantes = {r.phase: r for r in opp.get(TABLE) or []}
	nouvelles = []
	for ph in phases_parcours(opp.opportunity_type):
		r = existantes.pop(ph.phase, None)
		valeurs = dict(ordre=ph.ordre, evenement_fin=ph.evenement_fin, duree_cible=ph.duree_cible, obligatoire=ph.obligatoire,
			phase_finale=ph.phase_finale, evenement_annulation=ph.evenement_annulation, hors_parcours=0)
		if r and (r.statut in FAITES or r.statut in (EN_COURS, ANNULEE)):
			if r.statut in FAITES:
				valeurs.pop("duree_cible")
			r.update(valeurs)
			nouvelles.append(r)
		else:
			nouvelles.append(frappe._dict(phase=ph.phase, statut=A_VENIR, **valeurs))
	for r in existantes.values():
		if r.statut in FAITES or r.statut in (EN_COURS, ANNULEE):
			r.hors_parcours = 1
			nouvelles.append(r)
	opp.set(TABLE, [])
	for r in sorted(nouvelles, key=lambda x: cint(x.ordre)):
		valeurs = r.as_dict() if isinstance(r, Document) else dict(r)
		valeurs.pop("idx", None)
		opp.append(TABLE, valeurs)
	if opp.get("status") not in OPP_FERMEES and not courante(opp):
		faites = [r for r in _sequence(opp) if r.statut in FAITES]
		suivante = next((r for r in _sequence(opp) if r.statut == A_VENIR and (not faites or cint(r.ordre) > cint(faites[-1].ordre))), None)
		if suivante and not any(r.phase_finale and r.statut in FAITES for r in _lignes(opp)):
			_demarrer(opp, suivante, now_datetime())
	change = avant != [(r.phase, r.statut, cint(r.ordre)) for r in _lignes(opp)]
	if change and raison and avant:
		cur = courante(opp)
		_historique(opp, None, cur.phase if cur else None, RECONSTRUCTION, commentaire=raison)
	return change


def _entete(opp):
	maintenant = now_datetime()
	for r in opp.get(TABLE) or []:
		if r.debut:
			r.duree_jours = round(time_diff_in_hours(r.fin or maintenant, r.debut) / 24, 1)
	cur = courante(opp)
	if cur:
		users = [u for u in cstr(cur.responsables).split(", ") if u]
		opp.lsi_echeance_phase, opp.lsi_phase_depuis = cur.echeance, cur.debut
		opp.lsi_responsable_phase = users[0] if users else None
		opp.lsi_responsables_phase = ", ".join(frappe.utils.get_fullname(u) for u in users) or None
		opp.sales_stage = cur.phase
	else:
		opp.lsi_echeance_phase = opp.lsi_responsable_phase = opp.lsi_phase_depuis = opp.lsi_responsables_phase = None
		faites = [r for r in _lignes(opp) if r.statut == TERMINEE]
		if faites:
			opp.sales_stage = max(faites, key=lambda r: get_datetime(r.fin) if r.fin else get_datetime("1900-01-01")).phase


def _norm(v):
	return cstr(v)[:19]


def _historique_inchange(opp):
	avant = opp.get_doc_before_save()
	if not avant:
		return
	actuelles = {r.name: r for r in opp.get(HISTO) or []}
	for r in avant.get(HISTO) or []:
		a = actuelles.get(r.name)
		if not a or any(_norm(r.get(f)) != _norm(a.get(f)) for f in CHAMPS_HISTO):
			frappe.throw(_("L'historique des phases ne peut être ni modifié ni supprimé."), title=_("Historique des phases"))


def _marque(phase):
	return f"[{phase}]"


def _affecter(opp, ligne):
	from frappe.desk.form import assign_to

	users = [u for u in cstr(ligne.responsables).split(", ") if u]
	if users:
		assign_to.add(dict(doctype="Opportunity", name=opp.name, assign_to=users,
			description=f"{_marque(ligne.phase)} {opp.name} — {opp.get('customer_name') or opp.get('party_name') or ''}"), ignore_permissions=True)


def _fermer_todos(opp, phase):
	for t in frappe.get_all("ToDo", filters={"reference_type": "Opportunity", "reference_name": opp.name, "status": "Open",
			"description": ("like", f"{_marque(phase)}%")}, pluck="name"):
		todo = frappe.get_doc("ToDo", t)
		todo.status = "Closed"
		todo.save(ignore_permissions=True)
