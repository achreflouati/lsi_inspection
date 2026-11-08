"""Moteur générique des phases commerciales de l'opportunité.

Tout se lit dans la configuration (aucune valeur métier ici) :
- parcours : table « Parcours Phase » du type d'opportunité (ou du type « parcours par défaut ») ;
- événements de fin : doctype « Evenement Phase » (Manuel, Création, Validation, État du workflow, Changement de statut,
  Annulation) ;
- notifications : table « Notification Phase » du type (moment, destinataires, canal, modèle d'e-mail natif).

Suivi : table lsi_phases (état courant) ; historique lsi_historique_phases en ajout seul ; en-tête lsi_responsable_phase,
lsi_echeance_phase et sales_stage (phase en cours) calculés dans validate.
Les événements « valeur » (état du workflow, statut) sont évalués juste avant la validation de la transaction, sur la valeur
finale : ERPNext peut écrire plusieurs statuts successifs dans une même transaction (ex. devis perdu alors qu'un autre est
ouvert : Lost puis Quotation). Une erreur du moteur ne bloque jamais le document déclencheur.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, cstr, get_datetime, get_url_to_form, now_datetime, time_diff_in_hours

TABLE, HISTO = "lsi_phases", "lsi_historique_phases"
A_VENIR, EN_COURS, TERMINEE, SAUTEE, SAUTEE_AUTO = "À venir", "En cours", "Terminée", "Sautée", "Sautée (auto)"
ANNULEE = "Annulée"  # phase finale annulée par son événement d'annulation (réouverture) ; peut être de nouveau atteinte
FAITES = (TERMINEE, SAUTEE, SAUTEE_AUTO)
GAGNEE, PERDUE = "Gagnée", "Perdue"
FERMEES = ("Converted", "Lost", "Closed")  # statuts natifs : opportunité close, son tableau n'est plus reconstruit
ENTREE, FIN, RETARD = "Entrée dans la phase", "Fin de phase", "Retard"
DECLENCHEURS = {"after_insert": "Création", "on_submit": "Validation", "on_cancel": "Annulation"}
AVEC_VALEUR = ("État du workflow", "Changement de statut")
QUITTE = "Quitte la valeur"
CHAMPS_HISTO = ("date", "de_phase", "vers_phase", "action", "par", "evenement", "document_type", "document_name", "motif", "commentaire")
CLE_CACHE = "lsi_evenements_phase"
# statut natif de l'opportunité → document source à rattacher dans l'historique (sémantique ERPNext : devis perdu / commandé)
SOURCE_STATUT = {"Lost": ("Quotation", "Lost"), "Converted": ("Quotation", "Ordered")}


# ------------------------------------------------------------------ parcours d'un type
def type_parcours(opportunity_type):
	"""Type dont le parcours (et les notifications) s'appliquent : le type lui-même s'il a un parcours, sinon le type par défaut."""
	if opportunity_type and frappe.db.exists("Parcours Phase", {"parent": opportunity_type, "parenttype": "Opportunity Type"}):
		return opportunity_type
	return frappe.db.get_value("Opportunity Type", {"lsi_parcours_defaut": 1}, "name")


def phases_parcours(opportunity_type):
	"""Phases du parcours dans l'ordre ; plusieurs lignes d'une même phase = co-responsables."""
	t = type_parcours(opportunity_type)
	if not t:
		return []
	out = {}
	for r in frappe.get_all("Parcours Phase", filters={"parent": t, "parenttype": "Opportunity Type"}, fields=["ordre", "phase",
			"type_responsable", "role", "utilisateur", "departement", "duree_cible", "evenement_fin", "obligatoire", "phase_finale",
			"evenement_annulation"],
			order_by="ordre asc, idx asc"):
		ph = out.setdefault(r.phase, frappe._dict(phase=r.phase, ordre=cint(r.ordre), lignes=[], duree_cible=0, evenement_fin=None,
			obligatoire=0, phase_finale=None, evenement_annulation=None))
		ph.lignes.append(r)
		ph.duree_cible = ph.duree_cible or cint(r.duree_cible)
		ph.evenement_fin = ph.evenement_fin or r.evenement_fin
		ph.obligatoire = ph.obligatoire or cint(r.obligatoire)
		ph.phase_finale = ph.phase_finale or r.phase_finale
		ph.evenement_annulation = ph.evenement_annulation or r.evenement_annulation
	return sorted(out.values(), key=lambda x: x.ordre)


def type_validate(doc, method=None):
	"""Opportunity Type : un seul parcours par défaut, une seule phase finale de chaque sorte, Gagnée en dernier."""
	if cint(doc.get("lsi_parcours_defaut")):
		autre = frappe.db.get_value("Opportunity Type", {"lsi_parcours_defaut": 1, "name": ("!=", doc.name)})
		if autre:
			frappe.throw(_("Le type {0} porte déjà le parcours par défaut.").format(autre))
	finales = {}
	for r in doc.get("lsi_parcours") or []:
		if r.phase_finale:
			finales.setdefault(r.phase_finale, set()).add(r.phase)
	for f, phases in finales.items():
		if len(phases) > 1:
			frappe.throw(_("Une seule phase finale « {0} » par parcours ({1}).").format(f, ", ".join(sorted(phases))))
	gagnee = finales.get(GAGNEE)
	if gagnee:
		g = next(iter(gagnee))
		max_ordre = max((cint(r.ordre) for r in doc.lsi_parcours if r.phase_finale != PERDUE), default=0)
		if any(cint(r.ordre) < max_ordre for r in doc.lsi_parcours if r.phase == g):
			frappe.throw(_("La phase finale « Gagnée » ({0}) doit être la dernière du parcours (hors phase Perdue).").format(g))


def type_on_update(doc, method=None):
	"""Le parcours a changé : les opportunités ouvertes concernées suivent (phases faites conservées)."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.lsi_chargement_config:
		return
	types = [doc.name]
	if cint(doc.get("lsi_parcours_defaut")):
		types += [t for t in frappe.get_all("Opportunity Type", pluck="name") if t != doc.name and type_parcours(t) == doc.name]
	for name in frappe.get_all("Opportunity", filters={"opportunity_type": ("in", types), "status": ("not in", FERMEES)}, pluck="name"):
		opp = frappe.get_doc("Opportunity", name)
		if construire(opp, raison=_("Parcours du type {0} modifié").format(doc.name)):
			opp.flags.lsi_moteur = True
			opp.save(ignore_permissions=True)


# ------------------------------------------------------------------ responsables
def _utilisateurs_actifs(users):
	users = [u for u in dict.fromkeys(u for u in users if u and u != "Guest")]
	if not users:
		return []
	actifs = set(frappe.get_all("User", filters={"name": ("in", users), "enabled": 1}, pluck="name"))
	return [u for u in users if u in actifs]


def _utilisateurs_departements(departements):
	departements = [d for d in departements if d]
	if not departements:
		return []
	return frappe.get_all("Employee", filters={"department": ("in", departements), "status": "Active", "user_id": ("is", "set")},
		pluck="user_id")


def _ligne_principale(opp):
	lignes = opp.get("lsi_departements") or []
	return next((r for r in lignes if cint(r.principal)), lignes[0] if lignes else None)


def _pilote(opp, departement=None):
	if departement:
		r = next((r for r in opp.get("lsi_departements") or [] if r.departement == departement), None)
		if r and r.utilisateur_pilote:
			return r.utilisateur_pilote
		emp = frappe.db.get_value("Department", departement, "lsi_responsable")
		return frappe.db.get_value("Employee", emp, "user_id") if emp else None
	r = _ligne_principale(opp)
	return r.utilisateur_pilote if r else None


def _commercial(opp):
	return opp.get("opportunity_owner") or opp.owner


def responsables(opp, phase):
	users = []
	for r in phase.lignes:
		if r.type_responsable == "Rôle" and r.role:
			from frappe.utils.user import get_users_with_role

			users += get_users_with_role(r.role)
		elif r.type_responsable == "Utilisateur":
			users.append(r.utilisateur)
		elif r.type_responsable == "Pilote du département":
			users.append(_pilote(opp, r.departement))
		else:
			users.append(_commercial(opp))
	return _utilisateurs_actifs(users)


# ------------------------------------------------------------------ tableau des phases
def _lignes(opp):
	return sorted(opp.get(TABLE) or [], key=lambda r: (cint(r.ordre), r.idx or 0))


def courante(opp):
	return next((r for r in _lignes(opp) if r.statut == EN_COURS), None)


def _sequence(opp):
	"""Phases de la séquence normale (la phase finale Perdue est hors séquence)."""
	return [r for r in _lignes(opp) if r.phase_finale != PERDUE]


def _demarrer(opp, ligne, maintenant):
	ligne.statut, ligne.debut, ligne.fin, ligne.retard_notifie = EN_COURS, maintenant, None, 0
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
	ligne.statut, ligne.debut, ligne.fin, ligne.echeance, ligne.duree_jours, ligne.retard_notifie = A_VENIR, None, None, None, 0, 0
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
	if opp.get("status") not in FERMEES and not courante(opp):
		faites = [r for r in _sequence(opp) if r.statut in FAITES]
		suivante = next((r for r in _sequence(opp) if r.statut == A_VENIR and (not faites or cint(r.ordre) > cint(faites[-1].ordre))), None)
		if suivante and not any(r.phase_finale and r.statut in FAITES for r in _lignes(opp)):
			_demarrer(opp, suivante, now_datetime())
	change = avant != [(r.phase, r.statut, cint(r.ordre)) for r in _lignes(opp)]
	if change and raison and avant:
		cur = courante(opp)
		_historique(opp, None, cur.phase if cur else None, "Reconstruction", commentaire=raison)
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


# ------------------------------------------------------------------ hooks de l'opportunité
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


def opportunity_validate(doc, method=None):
	principales = [r for r in doc.get("lsi_departements") or [] if cint(r.principal)]
	if len(principales) > 1:
		frappe.throw(_("Un seul département principal par opportunité (lignes {0}).").format(", ".join(str(r.idx) for r in principales)))
	_historique_inchange(doc)
	avant = doc.get_doc_before_save()
	if doc.is_new() or not doc.get(TABLE):
		construire(doc)
	elif avant and avant.opportunity_type != doc.opportunity_type and doc.status not in FERMEES and not doc.flags.lsi_moteur:
		construire(doc, raison=_("Type {0} → {1}").format(avant.opportunity_type or "-", doc.opportunity_type or "-"))
	_entete(doc)


def opportunity_on_update(doc, method=None):
	"""Après enregistrement : tâches (ToDo natif) et notifications des phases quittées / commencées. Jamais bloquant."""
	actions, doc.flags.lsi_actions = doc.flags.lsi_actions or [], []
	for quoi, phase in sorted(actions, key=lambda a: a[0] != "fin"):
		ligne = next((r for r in doc.get(TABLE) or [] if r.phase == phase), None)
		if not ligne:
			continue
		try:
			if quoi == "fin":
				_fermer_todos(doc, phase)
				notifier(doc, ligne, FIN)
			else:
				_affecter(doc, ligne)
				notifier(doc, ligne, ENTREE)
		except Exception:
			frappe.log_error(title=_("Phases : actions de la phase {0}").format(phase), reference_doctype="Opportunity", reference_name=doc.name)


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


# ------------------------------------------------------------------ « Terminer ma phase »
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
		_historique(opp, cur.phase, cible.phase, "Retour arrière", commentaire=commentaire, maintenant=maintenant)
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


# ------------------------------------------------------------------ événements de fin
def vider_cache_evenements():
	frappe.cache.delete_value(CLE_CACHE)


def evenements():
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
	evs = evenements().get(doc.doctype)
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
			for ev in evenements().get(dt, []):
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
			_terminer(opp, r, SAUTEE_AUTO, maintenant)
			r.commentaire = f"{evenement} : {origine.doctype} {origine.name}"
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
	_historique(opp, finale.phase, reprise.phase if reprise else None, "Réouverture", evenement=evenement,
		source=_source_reouverture(opp, source), maintenant=maintenant)


# ------------------------------------------------------------------ notifications par phase
def regles(opp, phase, moment):
	t = type_parcours(opp.opportunity_type)
	if not t:
		return []
	rows = frappe.get_all("Notification Phase", filters={"parent": t, "parenttype": "Opportunity Type", "actif": 1, "moment": moment},
		fields=["phase", "destinataires", "role", "utilisateur", "departement", "systeme", "email", "modele"], order_by="idx")
	return [r for r in rows if not r.phase or r.phase == phase]


def destinataires(opp, regle, ligne):
	d = regle.destinataires
	if d == "Responsable de phase":
		users = cstr(ligne.responsables).split(", ")
	elif d == "Commercial":
		users = [_commercial(opp)]
	elif d == "Rôle":
		from frappe.utils.user import get_users_with_role

		users = get_users_with_role(regle.role) if regle.role else []
	elif d == "Utilisateur":
		users = [regle.utilisateur]
	elif d == "Pilote":
		users = [r.utilisateur_pilote for r in opp.get("lsi_departements") or []]
	elif d == "Département principal":
		p = _ligne_principale(opp)
		users = _utilisateurs_departements([p.departement] if p else [])
	elif d == "Départements concernés (tous)":
		users = _utilisateurs_departements([r.departement for r in opp.get("lsi_departements") or []])
	elif d == "Département précis":
		users = _utilisateurs_departements([regle.departement])
	else:
		users = []
	return _utilisateurs_actifs(users)


def notifier(opp, ligne, moment):
	"""Applique les règles actives du moment ; chaque règle est indépendante et ne bloque jamais."""
	n = 0
	for regle in regles(opp, ligne.phase, moment):
		try:
			users = destinataires(opp, regle, ligne)
			if not users or not (cint(regle.systeme) or cint(regle.email)):
				continue
			tpl = frappe.get_doc("Email Template", regle.modele)
			ctx = dict(doc=opp, phase=ligne.phase, moment=moment, ligne=ligne, lien=get_url_to_form("Opportunity", opp.name))
			sujet = frappe.render_template(tpl.subject or "", ctx)
			corps = frappe.render_template((tpl.response_html if cint(tpl.use_html) else tpl.response) or "", ctx)
			if cint(regle.systeme):
				from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

				enqueue_create_notification(users, dict(type="Alert", document_type="Opportunity", document_name=opp.name, subject=sujet,
					email_content=corps, from_user=frappe.session.user))
			if cint(regle.email):
				emails = [e for e in frappe.get_all("User", filters={"name": ("in", users)}, pluck="email") if e]
				if emails:
					frappe.sendmail(recipients=emails, subject=sujet, message=corps, reference_doctype="Opportunity", reference_name=opp.name)
			n += 1
		except Exception:
			frappe.log_error(title=_("Phases : notification {0} / {1}").format(moment, ligne.phase), reference_doctype="Opportunity",
				reference_name=opp.name)
	return n


def retards_quotidiens():
	"""Tâche quotidienne : règles « Retard » des notifications par phase (une fois par phase en retard).
	La Notification native « Days After » couvre l'alerte fixe ; elle ne sait pas lire les règles par phase (table enfant,
	modèle d'e-mail, destinataires calculés) : d'où cette tâche, limitée aux opportunités ouvertes en retard."""
	maintenant = now_datetime()
	for name in frappe.get_all("Opportunity", filters={"status": ("not in", FERMEES), "lsi_echeance_phase": ("<", maintenant)}, pluck="name"):
		try:
			opp = frappe.get_doc("Opportunity", name)
			cur = courante(opp)
			if cur and not cint(cur.retard_notifie) and cur.echeance and get_datetime(cur.echeance) < maintenant:
				notifier(opp, cur, RETARD)
				frappe.db.set_value("Phase Opportunite", cur.name, "retard_notifie", 1, update_modified=False)
		except Exception:
			frappe.log_error(title=_("Phases : retards"), reference_doctype="Opportunity", reference_name=name)
