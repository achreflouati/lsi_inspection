"""Lot 2 — notifications par phase paramétrées par TIC (Paramétreur commercial), règles inactives, erreurs non bloquantes,
retards (règle par phase + Notification native « Days After »)."""

import frappe
from frappe.utils import add_days, now_datetime, nowdate

from lsi_inspection.commercial import phases
from lsi_inspection.tests.contexte import PREFIXE, TestLot2

PARAM = f"param.{PREFIXE.lower()}@example.com"
INSPECTEUR = f"inspecteur.{PREFIXE.lower()}@example.com"


class TestNotificationsPhase(TestLot2):
	def _service(self):
		self.utilisateur(INSPECTEUR, ["Employee"])
		dep = self.departement(f"{PREFIXE} Service")
		self.employe("Inspecteur", dep, INSPECTEUR)
		return dep

	def _logs(self, opp, user=INSPECTEUR):
		return frappe.get_all("Notification Log", filters={"document_name": opp, "for_user": user}, pluck="subject")

	def _emails(self, opp):
		return frappe.get_all("Email Queue", filters={"reference_name": opp}, pluck="name")

	def _compte_sortant(self):
		"""Compte d'e-mail sortant fictif (le site n'en a pas : sans compte, ERPNext refuse la mise en file)."""
		frappe.get_doc(dict(doctype="Email Account", email_account_name=f"{PREFIXE} Sortant", email_id="noreply-lsi-test@example.com",
			enable_outgoing=1, default_outgoing=1, enable_incoming=0, smtp_server="localhost", smtp_port=25, no_smtp_authentication=1)).insert(
			ignore_permissions=True)
		self.addCleanup(frappe.clear_cache)

	def test_sans_compte_sortant_le_systeme_part_et_rien_ne_bloque(self):
		dep = self._service()
		t = self.parcours_standard(notifications=[dict(moment="Entrée dans la phase", destinataires="Département principal", systeme=1, email=1,
			modele=self.modele(f"{PREFIXE} Entrée"), actif=1)])
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		if frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}):
			self.skipTest("le site a un compte sortant")
		self.assertEqual(phases.terminer_phase(o.name), "T Étude")
		self.assertTrue(self._logs(o.name))
		self.assertTrue(frappe.db.exists("Error Log", {"reference_name": o.name}))

	def test_parametreur_seul_ajoute_phase_et_notification(self):
		self._compte_sortant()
		t = self.parcours_standard()
		modele = self.modele(f"{PREFIXE} Entrée")
		dep = self._service()
		self.utilisateur(PARAM, ["Paramétreur commercial"])
		frappe.set_user(PARAM)
		self.assertEqual(frappe.get_roles(PARAM), [r for r in frappe.get_roles(PARAM) if r in ("Paramétreur commercial", "All", "Guest", "Desk User")])
		frappe.get_doc(dict(doctype="Sales Stage", stage_name="T Visite")).insert()
		doc = frappe.get_doc("Opportunity Type", t)
		doc.append("lsi_parcours", dict(ordre=15, phase="T Visite", type_responsable="Commercial", evenement_fin="Manuel"))
		doc.append("lsi_notifications_phase", dict(phase="T Visite", moment="Entrée dans la phase", destinataires="Département principal",
			systeme=1, email=1, modele=modele, actif=1))
		doc.save()
		frappe.set_user("Administrator")
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		self.assertEqual(phases.terminer_phase(o.name), "T Visite")
		self.assertTrue(self._logs(o.name), "Notification Log attendue pour l'inspecteur du département principal")
		self.assertIn("T Visite", self._logs(o.name)[0])
		q = frappe.get_all("Email Queue Recipient", filters={"parent": ("in", self._emails(o.name))}, pluck="recipient")
		self.assertIn(INSPECTEUR, q)

	def test_parametreur_ne_modifie_pas_une_opportunite(self):
		self.utilisateur(PARAM, ["Paramétreur commercial"])
		self.assertFalse(frappe.has_permission("Opportunity", "write", user=PARAM))
		self.assertFalse(frappe.has_permission("Opportunity", "read", user=PARAM))
		for dt in ("Opportunity Type", "Sales Stage", "Evenement Phase", "Type Metier", "Famille de Type", "Email Template"):
			self.assertTrue(frappe.has_permission(dt, "create", user=PARAM), dt)

	def test_regle_inactive_n_envoie_rien(self):
		dep = self._service()
		t = self.parcours_standard(notifications=[dict(phase="T Étude", moment="Entrée dans la phase", destinataires="Département principal",
			systeme=1, email=1, modele=self.modele(f"{PREFIXE} Entrée"), actif=0)])
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		phases.terminer_phase(o.name)
		self.assertFalse(self._logs(o.name))
		self.assertFalse(self._emails(o.name))

	def test_erreur_de_modele_ne_bloque_pas_le_passage(self):
		dep = self._service()
		casse = self.modele(f"{PREFIXE} Cassé", corps="{{ doc.inexistant.plus_loin() }}")
		t = self.parcours_standard(notifications=[dict(moment="Entrée dans la phase", destinataires="Département principal", systeme=1, email=0,
			modele=casse, actif=1)])
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		self.assertEqual(phases.terminer_phase(o.name), "T Étude")
		self.assertEqual(phases.courante(self.recharger(o)).phase, "T Étude")
		self.assertTrue(frappe.db.exists("Error Log", {"reference_name": o.name}))

	def test_destinataires(self):
		dep = self._service()
		t = self.parcours_standard()
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		ligne = phases.courante(o)
		D = lambda **r: phases.destinataires(o, frappe._dict(r), ligne)
		self.assertEqual(D(destinataires="Département principal"), [INSPECTEUR])
		self.assertEqual(D(destinataires="Départements concernés (tous)"), [INSPECTEUR])
		self.assertEqual(D(destinataires="Département précis", departement=dep), [INSPECTEUR])
		self.assertEqual(D(destinataires="Commercial"), ["Administrator"])
		self.assertEqual(D(destinataires="Responsable de phase"), ["Administrator"])
		self.assertEqual(D(destinataires="Utilisateur", utilisateur=INSPECTEUR), [INSPECTEUR])

	def test_retard_regle_par_phase_une_seule_fois(self):
		dep = self._service()
		t = self.parcours_standard(notifications=[dict(moment="Retard", destinataires="Département principal", systeme=1, email=0,
			modele=self.modele(f"{PREFIXE} Retard"), actif=1)], options={"T Création": {"duree_cible": 1}})
		o = self.opportunite(t, lsi_departements=[dict(departement=dep, principal=1)])
		hier = add_days(now_datetime(), -1)
		frappe.db.set_value("Opportunity", o.name, "lsi_echeance_phase", hier)
		frappe.db.set_value("Phase Opportunite", phases.courante(o).name, "echeance", hier)
		phases.retards_quotidiens()
		self.assertEqual(len(self._logs(o.name)), 1)
		phases.retards_quotidiens()
		self.assertEqual(len(self._logs(o.name)), 1)

	def test_notification_native_days_after(self):
		o = self.opportunite(self.parcours_standard(options={"T Création": {"duree_cible": 1}}))
		frappe.db.set_value("Opportunity", o.name, "lsi_echeance_phase", add_days(nowdate(), -1) + " 10:00:00")
		n = frappe.get_doc("Notification", "Retard phase opportunite")
		self.assertIn(o.name, [d.name for d in n.get_documents_for_today()])
		frappe.db.set_value("Opportunity", o.name, "status", "Lost")
		self.assertNotIn(o.name, [d.name for d in n.get_documents_for_today()])
