"""Lot 2 — notifications de phase NATIVES (Notification : Value Change sur sales_stage, New, Days After), créées à l'écran par
le Paramétreur commercial, sans code. Le moteur ne fait que tenir sales_stage (phase en cours) à jour."""

import frappe
from frappe.utils import add_days, nowdate

from lsi_inspection.commercial import phases
from lsi_inspection.tests.contexte import PREFIXE, TestLot2

PARAM = f"param.{PREFIXE.lower()}@example.com"
PILOTE = f"pilote.{PREFIXE.lower()}@example.com"
TECH = f"tech.{PREFIXE.lower()}@example.com"


class TestNotificationsNatives(TestLot2):
	def setUp(self):
		super().setUp()
		# isolement : les notifications du site (structure et configuration) sont désactivées dans la transaction de test
		for n in frappe.get_all("Notification", filters={"document_type": "Opportunity", "enabled": 1}, pluck="name"):
			frappe.db.set_value("Notification", n, "enabled", 0)
		frappe.cache.hdel("notifications", "Opportunity")

	def _departement_pilote(self):
		self.utilisateur(PILOTE, ["Employee"])
		dep = self.departement(f"{PREFIXE} Service")
		emp = self.employe("Pilote", dep, PILOTE)
		frappe.db.set_value("Department", dep, "lsi_responsable", emp)
		return dep

	def _compte_sortant(self):
		if frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}):
			return
		frappe.get_doc(dict(doctype="Email Account", email_account_name=f"{PREFIXE} Sortant", email_id="noreply-lsi-test@example.com",
			enable_outgoing=1, default_outgoing=1, enable_incoming=0, smtp_server="localhost", smtp_port=25, no_smtp_authentication=1)).insert(
			ignore_permissions=True)
		self.addCleanup(lambda: frappe.local.__setattr__("outgoing_email_account", {}))

	def _notification(self, nom, condition, recipients, event="Value Change", enabled=1):
		n = frappe.new_doc("Notification")
		n.update(dict(document_type="Opportunity", event=event, channel="Email", send_system_notification=1, enabled=enabled,
			subject="{{ doc.name }} : {{ doc.sales_stage }}", message="<p>Phase {{ doc.sales_stage }}</p>", condition=condition))
		if event == "Value Change":
			n.value_changed = "sales_stage"
		for r in recipients:
			n.append("recipients", r)
		n.insert(set_name=nom)
		frappe.cache.hdel("notifications", "Opportunity")
		return n

	def _logs(self, opp, user):
		return frappe.get_all("Notification Log", filters={"document_name": opp, "for_user": user}, pluck="subject")

	# ------------------------------------------------------------------ créée à l'écran, sans code
	def test_parametreur_cree_phase_et_notification_sans_code(self):
		self._compte_sortant()
		dep = self._departement_pilote()
		t = self.parcours_standard()
		self.utilisateur(PARAM, ["Paramétreur commercial"])
		frappe.set_user(PARAM)
		frappe.get_doc(dict(doctype="Sales Stage", stage_name="T Visite")).insert()
		doc = frappe.get_doc("Opportunity Type", t)
		doc.append("lsi_parcours", dict(ordre=15, phase="T Visite", type_responsable="Commercial", evenement_fin="Manuel"))
		doc.save()
		self._notification(f"{PREFIXE} Visite : pilotes", 'doc.sales_stage == "T Visite"',
			[dict(receiver_by_document_field="utilisateur_pilote,lsi_departements")])
		frappe.set_user("Administrator")
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		self.assertEqual(o.lsi_departements[0].utilisateur_pilote, PILOTE)
		self.assertFalse(self._logs(o.name, PILOTE))
		self.assertEqual(phases.terminer_phase(o.name), "T Visite")
		self.assertEqual(self._logs(o.name, PILOTE), [f"{o.name} : T Visite"])
		q = frappe.get_all("Email Queue", filters={"reference_name": o.name}, pluck="name")
		self.assertIn(PILOTE, frappe.get_all("Email Queue Recipient", filters={"parent": ("in", q)}, pluck="recipient"))

	def test_droits_du_parametreur(self):
		self.utilisateur(PARAM, ["Paramétreur commercial"])
		for dt in ("Notification", "Opportunity Type", "Sales Stage", "Evenement Phase", "Type Metier", "Famille de Type", "Email Template"):
			self.assertTrue(frappe.has_permission(dt, "create", user=PARAM), dt)
		self.assertFalse(frappe.has_permission("Opportunity", "read", user=PARAM))

	# ------------------------------------------------------------------ conditions, destinataires, désactivation
	def test_condition_d_une_autre_phase_n_envoie_rien(self):
		dep = self._departement_pilote()
		self._notification(f"{PREFIXE} Offre", 'doc.sales_stage == "T Offre"', [dict(receiver_by_document_field="utilisateur_pilote,lsi_departements")])
		o = self.opportunite(self.parcours_standard(), lsi_departements=[dict(departement=dep, principal=1)])
		phases.terminer_phase(o.name)  # → T Étude
		self.assertFalse(self._logs(o.name, PILOTE))

	def test_notification_desactivee_n_envoie_rien(self):
		dep = self._departement_pilote()
		self._notification(f"{PREFIXE} Étude", 'doc.sales_stage == "T Étude"', [dict(receiver_by_document_field="utilisateur_pilote,lsi_departements")],
			enabled=0)
		o = self.opportunite(self.parcours_standard(), lsi_departements=[dict(departement=dep, principal=1)])
		phases.terminer_phase(o.name)
		self.assertFalse(self._logs(o.name, PILOTE))

	def test_destinataires_par_role_et_champ_du_document(self):
		self.utilisateur(TECH, ["Sales User", "Etude technique"])
		self._notification(f"{PREFIXE} Étude par rôle", 'doc.sales_stage == "T Étude"', [dict(receiver_by_role="Etude technique")])
		t = self.type_parcours(f"{PREFIXE} Rôle", [(10, "T Création", "Commercial", self.evenement("Manuel")),
			(20, "T Étude", f"Utilisateur:{TECH}", "Manuel")])
		self._notification(f"{PREFIXE} Étude par responsable", 'doc.sales_stage == "T Étude"', [dict(receiver_by_document_field="lsi_responsable_phase")])
		o = self.opportunite(t)
		phases.terminer_phase(o.name)
		alertes = frappe.get_all("Notification Log", filters={"document_name": o.name, "for_user": TECH, "type": "Alert"}, pluck="subject")
		self.assertEqual(len(alertes), 2)  # par le rôle et par le champ « responsable de la phase »

	def test_changement_de_phase_par_evenement_notifie(self):
		dep = self._departement_pilote()
		self._notification(f"{PREFIXE} Offre", 'doc.sales_stage == "T Offre"', [dict(receiver_by_document_field="utilisateur_pilote,lsi_departements")])
		o = self.opportunite(self.parcours_standard(), lsi_departements=[dict(departement=dep, principal=1)])
		self.devis(o)  # Devis validé : T Validation terminée, T Offre en cours
		self.assertEqual(self.recharger(o).sales_stage, "T Offre")
		self.assertEqual(len(self._logs(o.name, PILOTE)), 1)

	def test_premiere_phase_evenement_nouveau(self):
		"""Value Change ne se déclenche pas à la création (natif) : la première phase se notifie par l'événement « New »."""
		dep = self._departement_pilote()
		self._notification(f"{PREFIXE} Création VC", 'doc.sales_stage == "T Création"', [dict(receiver_by_document_field="utilisateur_pilote,lsi_departements")])
		self._notification(f"{PREFIXE} Création New", 'doc.sales_stage == "T Création"', [dict(receiver_by_document_field="utilisateur_pilote,lsi_departements")],
			event="New")
		o = self.opportunite(self.parcours_standard(), lsi_departements=[dict(departement=dep, principal=1)])
		self.assertEqual(len(self._logs(o.name, PILOTE)), 1)

	def test_modele_errone_ne_bloque_pas_comportement_natif(self):
		"""Comportement NATIF : une erreur dans le sujet / message d'une Notification est journalisée, le passage de phase se fait."""
		self._notification(f"{PREFIXE} Cassée", 'doc.sales_stage == "T Étude"', [dict(receiver_by_document_field="lsi_responsable_phase")])
		frappe.db.set_value("Notification", f"{PREFIXE} Cassée", "subject", "{{ doc.name | filtre_inexistant }}")
		o = self.opportunite(self.parcours_standard())
		self.assertEqual(phases.terminer_phase(o.name), "T Étude")
		self.assertEqual(phases.courante(self.recharger(o)).phase, "T Étude")
		self.assertTrue(self.log_error.called)

	# ------------------------------------------------------------------ retard : Days After natif
	def test_retard_days_after(self):
		o = self.opportunite(self.parcours_standard(options={"T Création": {"duree_cible": 1}}))
		frappe.db.set_value("Opportunity", o.name, "lsi_echeance_phase", add_days(nowdate(), -1) + " 10:00:00")
		n = frappe.get_doc("Notification", "Retard phase opportunite")
		self.assertIn(o.name, [d.name for d in n.get_documents_for_today()])
		frappe.db.set_value("Opportunity", o.name, "status", "Lost")
		from frappe.email.doctype.notification.notification import get_context

		self.assertFalse(frappe.safe_eval(n.condition, None, get_context(self.recharger(o))))

	def test_ancien_mecanisme_retire(self):
		self.assertFalse(hasattr(phases, "notifier") or hasattr(phases, "retards_quotidiens"))
		self.assertNotIn("lsi_inspection.commercial.phases.retards_quotidiens", str(frappe.get_hooks("scheduler_events")))
		self.assertTrue(frappe.get_meta("Opportunity Type").get_field("lsi_notifications_phase").read_only)
