"""Événements de fin de phase (Evenement Phase) : détection sur n'importe quel document (doc_events « * »), lien vers
l'opportunité, application au tableau des phases, réouverture. Les événements « valeur » sont évalués avant le commit."""

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_datetime, now_datetime

from lsi_inspection.constants import ANNULATION, ANNULEE, A_VENIR, CHANGEMENT_STATUT, CREATION, EN_COURS, ETAT_WORKFLOW, FAITES, GAGNEE, PERDUE, QUITTE, REOUVERTURE, SAUTEE_AUTO, TERMINEE, VALIDATION
from lsi_inspection.commercial.phases.tableau import HISTO, _demarrer, _historique, _lignes, _remettre, _sequence, _terminer, courante


CLE_CACHE = "lsi_evenements_phase"
DECLENCHEURS = {"after_insert": CREATION, "on_submit": VALIDATION, "on_cancel": ANNULATION}  # événement Frappe → déclencheur
AVEC_VALEUR = (ETAT_WORKFLOW, CHANGEMENT_STATUT)
# statut natif de l'opportunité → document source à rattacher dans l'historique (sémantique ERPNext : devis perdu / commandé)
SOURCE_STATUT = {"Lost": ("Quotation", "Lost"), "Converted": ("Quotation", "Ordered")}


def vider_cache_evenements():
	frappe.cache.delete_value(CLE_CACHE)


def evenements_actifs():
	"""{doctype: [événements actifs]} — en cache, invalidé à chaque modification d'un Evenement Phase."""

	def charger():
		out = {}
		for e in frappe.get_all("Evenement Phase", filters={"actif": 1, "declencheur": ("!=", "Manuel")},
				fields=["name", "declencheur", "document_type", "valeur", "champ_statut", "champ_lien", "sens"]):
			if e.document_type:
				out.setdefault(e.document_type, []).append(e)
		return out

	return frappe.cache.get_value(CLE_CACHE, charger) or {}


def _champ_valeur(ev):
	if ev.declencheur == "Changement de statut":
		return ev.champ_statut or "status"
	from frappe.model.workflow import get_workflow_name

	wf = get_workflow_name(ev.document_type)
	return frappe.db.get_value("Workflow", wf, "workflow_state_field") if wf else None


def sur_document(doc, method=None):
	"""doc_events « * » : sortie immédiate si le doctype n'est dans aucun événement actif."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import or frappe.flags.lsi_chargement_config:
		return
	evs = evenements_actifs().get(doc.doctype)
	if not evs:
		return
	try:
		if method == "on_change":
			_noter_valeurs(doc, [e for e in evs if e.declencheur in AVEC_VALEUR])
		elif method in DECLENCHEURS:
			for ev in evs:
				if ev.declencheur == DECLENCHEURS[method]:
					declencher(ev, doc)
	except Exception:
		frappe.log_error(title=_("Phases : événement sur {0}").format(doc.doctype), reference_doctype=doc.doctype, reference_name=doc.name)


def _noter_valeurs(doc, evs):
	"""Mémorise la valeur AVANT (première vue de la transaction) ; l'évaluation se fait avant la validation (before_commit)."""
	if not evs:
		return
	avant = doc.get_doc_before_save()
	attente = getattr(frappe.local, "lsi_evenements_differes", None)
	if attente is None:
		attente = frappe.local.lsi_evenements_differes = {}
	valeurs = attente.setdefault((doc.doctype, doc.name), {})
	for ev in evs:
		champ = _champ_valeur(ev)
		if champ and champ not in valeurs:
			valeurs[champ] = avant.get(champ) if avant else None
	# une seule inscription par transaction (un rollback vide la file : on se réinscrit) ; sans accès à la file, inscription
	# à chaque fois (traiter_differes est sans effet quand il n'y a plus rien en attente)
	file = getattr(frappe.db.before_commit, "_functions", None)
	if file is None or traiter_differes not in file:
		frappe.db.before_commit.add(traiter_differes)


def traiter_differes():
	"""Évalue les événements « valeur » sur la valeur finale de la transaction : valeur attendue atteinte et différente d'avant."""
	attente = getattr(frappe.local, "lsi_evenements_differes", None) or {}
	frappe.local.lsi_evenements_differes = {}
	for (dt, name), avant in attente.items():
		try:
			if not frappe.db.exists(dt, name):
				continue
			doc = None
			for ev in evenements_actifs().get(dt, []):
				if ev.declencheur not in AVEC_VALEUR:
					continue
				champ = _champ_valeur(ev)
				if not champ or champ not in avant:
					continue
				actuel, precedent, attendu = cstr(frappe.db.get_value(dt, name, champ)), cstr(avant[champ]), cstr(ev.valeur)
				if ev.sens == QUITTE:
					atteint = precedent == attendu and actuel != attendu
				else:
					atteint = actuel == attendu and precedent != actuel
				if atteint:
					doc = doc or frappe.get_doc(dt, name)
					declencher(ev, doc)
		except Exception:
			frappe.log_error(title=_("Phases : événement différé sur {0}").format(dt), reference_doctype=dt, reference_name=name)


def opportunites_de(doc, champ_lien=None):
	"""Opportunités liées au document : lui-même, le champ indiqué, sinon un lien vers Opportunité, sinon vers un Devis lié."""
	if doc.doctype == "Opportunity":
		return [doc.name]
	meta = frappe.get_meta(doc.doctype)
	noms = []

	def ajouter(valeur, cible):
		if not valeur:
			return
		if cible == "Opportunity":
			noms.append(valeur)
		elif cible == "Quotation":
			noms.append(frappe.db.get_value("Quotation", valeur, "opportunity"))

	if champ_lien:
		df = meta.get_field(champ_lien)
		ajouter(doc.get(champ_lien), df.options if df else None)
	else:
		for cible in ("Opportunity", "Quotation"):
			for df in meta.get_link_fields():
				if df.options == cible:
					ajouter(doc.get(df.fieldname), cible)
			for tdf in meta.get_table_fields():
				for df in frappe.get_meta(tdf.options).get_link_fields():
					if df.options == cible:
						for row in doc.get(tdf.fieldname) or []:
							ajouter(row.get(df.fieldname), cible)
			if any(noms):
				break
	return [n for n in dict.fromkeys(noms) if n]


def declencher(ev, source):
	"""Applique l'événement aux opportunités liées. Jamais bloquant : erreur → journal + message, le document source continue."""
	for opp in opportunites_de(source, ev.champ_lien):
		sp = "lsi_phase"
		try:
			frappe.db.savepoint(sp)
			appliquer_evenement(opp, ev.name, source)
		except Exception:
			frappe.db.rollback(save_point=sp)
			frappe.log_error(title=_("Phases : événement {0}").format(ev.name), reference_doctype="Opportunity", reference_name=opp)
			frappe.msgprint(_("Phases de l'opportunité {0} non mises à jour (événement {1}) : voir le journal des erreurs.").format(opp, ev.name),
				indicator="orange", alert=True)


def _source_native(opp, source):
	"""Pour un changement de statut de l'opportunité : le devis qui l'a provoqué (perdu / commandé), sinon l'opportunité."""
	if source.doctype != "Opportunity" or source.status not in SOURCE_STATUT:
		return source
	dt, statut = SOURCE_STATUT[source.status]
	q = frappe.get_all(dt, filters={"opportunity": opp.name, "status": statut, "docstatus": 1}, order_by="modified desc", limit=1, pluck="name")
	return frappe.get_doc(dt, q[0]) if q else source


def _motif_perte(doc):
	raisons = [r.lost_reason for r in doc.get("lost_reasons") or [] if r.get("lost_reason")]
	detail = doc.get("order_lost_reason")
	return " ; ".join([", ".join(raisons)] * bool(raisons) + [cstr(detail)] * bool(detail)) or None


def appliquer_evenement(opportunity, evenement, source):
	opp = frappe.get_doc("Opportunity", opportunity)
	annulees = [r for r in _lignes(opp) if r.phase_finale and r.evenement_annulation == evenement and r.statut == TERMINEE]
	if annulees:
		for r in annulees:
			_rouvrir(opp, r, evenement, source)
		opp.flags.lsi_moteur = True
		opp.save(ignore_permissions=True)
		return True
	cible = next((r for r in _lignes(opp) if r.evenement_fin == evenement and r.statut not in FAITES), None)
	if not cible:
		return False
	maintenant = now_datetime()
	cur = courante(opp)
	origine = _source_native(opp, source)
	if cible.phase_finale == PERDUE:
		restantes = [r for r in _sequence(opp) if r.statut in (A_VENIR, EN_COURS)]
		for r in restantes:
			_terminer(opp, r, SAUTEE_AUTO, maintenant)
			r.commentaire = f"{evenement} : {origine.doctype} {origine.name}"
		_terminer(opp, cible, TERMINEE, maintenant)
		_historique(opp, cur.phase if cur else None, cible.phase, PERDUE, evenement=evenement, source=origine,
			motif=_motif_perte(origine) or _motif_perte(opp),
			commentaire=_("Sautées (auto) : {0}").format(", ".join(r.phase for r in restantes)) if restantes else None, maintenant=maintenant)
	else:
		sautees = [r for r in _sequence(opp) if r.statut in (A_VENIR, EN_COURS) and cint(r.ordre) < cint(cible.ordre)]
		for r in sautees:
			# la phase en cours a été traitée : terminée par l'événement ; seules les phases jamais commencées sont sautées
			_terminer(opp, r, TERMINEE if r.statut == EN_COURS else SAUTEE_AUTO, maintenant)
			r.commentaire = f"{evenement} : {origine.doctype} {origine.name}"
		sautees = [r for r in sautees if r.statut == SAUTEE_AUTO]
		_terminer(opp, cible, TERMINEE, maintenant)
		suivante = None
		if not cible.phase_finale:
			suivante = next((r for r in _sequence(opp) if cint(r.ordre) > cint(cible.ordre) and r.statut == A_VENIR), None)
			if suivante:
				_demarrer(opp, suivante, maintenant)
		action = GAGNEE if cible.phase_finale == GAGNEE else (SAUTEE_AUTO if sautees else TERMINEE)
		_historique(opp, cur.phase if cur else cible.phase, suivante.phase if suivante else cible.phase, action, evenement=evenement,
			source=origine, commentaire=_("Sautées (auto) : {0}").format(", ".join(r.phase for r in sautees)) if sautees else None,
			maintenant=maintenant)
	opp.flags.lsi_moteur = True
	opp.save(ignore_permissions=True)
	return True


def _source_reouverture(opp, source):
	"""Réouverture par le statut natif : le dernier devis modifié de l'opportunité (annulé, rouvert…), sinon l'opportunité."""
	if source.doctype != "Opportunity":
		return source
	q = frappe.get_all("Quotation", filters={"opportunity": opp.name}, order_by="modified desc", limit=1, pluck="name")
	return frappe.get_doc("Quotation", q[0]) if q else source


def _rouvrir(opp, finale, evenement, source):
	"""Annule une phase finale : elle passe « Annulée » ; les phases sautées par cette fin reviennent « À venir » ; la phase qui
	était en cours avant redevient « En cours » (sinon la première phase à venir de la séquence)."""
	fin = next((h for h in reversed(opp.get(HISTO) or []) if h.vers_phase == finale.phase and h.action in (GAGNEE, PERDUE)), None)
	quand = get_datetime(fin.date) if fin else None
	finale.statut = ANNULEE
	for r in _sequence(opp):
		if r is not finale and r.statut == SAUTEE_AUTO and quand and r.fin and get_datetime(r.fin) == quand:
			_remettre(r)
	reprise = next((r for r in _sequence(opp) if fin and r.phase == fin.de_phase and r is not finale), None)
	if not reprise or reprise.statut in FAITES:
		reprise = next((r for r in _sequence(opp) if r.statut == A_VENIR and r is not finale), None)
	maintenant = now_datetime()
	if reprise:
		_demarrer(opp, reprise, maintenant)
	_historique(opp, finale.phase, reprise.phase if reprise else None, REOUVERTURE, evenement=evenement,
		source=_source_reouverture(opp, source), maintenant=maintenant)
