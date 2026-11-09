"""Lot 0 — retours des testeurs : Issue natif (types, priorités, document concerné, étape de test), notification native
pour chaque retour bloquant, profil de rôles « Testeur TIC ». Rien ne reste sur le site (transaction annulée, aucun envoi)."""

import frappe

from lsi_inspection.tests.contexte import PREFIXE, TestLot2

DESTINATAIRE = "lsi.louati@gmail.com"


class TestRetours(TestLot2):
	def retour(self, priorite, **kw):
		return frappe.get_doc(dict(doctype="Issue", subject=f"{PREFIXE} retour {priorite}", priority=priorite, issue_type="Erreur",
			description="essai automatique", **kw)).insert(ignore_permissions=True)

	def destinataires(self, issue):
		files = frappe.get_all("Email Queue", filters={"reference_doctype": "Issue", "reference_name": issue}, pluck="name")
		return {r.recipient for f in files for r in frappe.get_all("Email Queue Recipient", filters={"parent": f}, fields=["recipient"])}

	def test_referentiels_des_retours(self):
		self.assertTrue({"Erreur", "Manque", "Mauvaise compréhension", "Suggestion"} <= set(frappe.get_all("Issue Type", pluck="name")))
		self.assertTrue({"Bloquant", "Important", "Mineur"} <= set(frappe.get_all("Issue Priority", pluck="name")))
		for f in ("lsi_etape_test", "lsi_document_type", "lsi_document"):
			self.assertTrue(frappe.get_meta("Issue").get_field(f), f)

	def test_document_concerne(self):
		opp = frappe.get_all("Opportunity", pluck="name", limit=1)
		if not opp:
			self.skipTest("aucune opportunité sur le site")
		i = self.retour("Mineur", lsi_document_type="Opportunity", lsi_document=opp[0], lsi_etape_test="T2.3")
		self.assertEqual((i.lsi_document_type, i.lsi_document, i.lsi_etape_test), ("Opportunity", opp[0], "T2.3"))

	def test_notification_seulement_pour_un_bloquant(self):
		bloquant = self.retour("Bloquant")
		self.assertIn(DESTINATAIRE, self.destinataires(bloquant.name))
		mineur = self.retour("Mineur")
		self.assertNotIn(DESTINATAIRE, self.destinataires(mineur.name))
		mineur.priority = "Bloquant"  # passé en bloquant ensuite
		mineur.save(ignore_permissions=True)
		self.assertIn(DESTINATAIRE, self.destinataires(mineur.name))

	def test_profil_testeur_tic(self):
		email = self.utilisateur(f"{PREFIXE.lower()}-testeur@example.com", [])
		u = frappe.get_doc("User", email)
		if u.meta.has_field("role_profiles"):
			u.append("role_profiles", {"role_profile": "Testeur TIC"})
		else:
			u.role_profile_name = "Testeur TIC"
		u.save(ignore_permissions=True)
		roles = set(frappe.get_roles(email))
		self.assertTrue({"Sales User", "Validateur demande d'offre", "Etude technique", "Chiffreur", "Paramétreur commercial",
			"Paramétreur chiffrage", "Retour de test"} <= roles, roles)
		frappe.set_user(email)
		for dt, droit in (("Issue", "create"), ("Issue Type", "read"), ("Issue Priority", "read"), ("Opportunity", "create"),
				("EFT", "create"), ("Quotation", "create"), ("Gamme", "read")):
			self.assertTrue(frappe.has_permission(dt, droit), f"{dt} {droit}")
		i = frappe.get_doc(dict(doctype="Issue", subject=f"{PREFIXE} retour testeur", priority="Mineur", issue_type="Suggestion")).insert()
		self.assertEqual(i.owner, email)
