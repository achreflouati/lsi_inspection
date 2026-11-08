"""Lot 2 — workflow « Validation demande d'offre », motif obligatoire côté serveur, statut natif, départements, référentiel."""

import frappe
from frappe.model.workflow import apply_workflow

from lsi_inspection.tests.contexte import PREFIXE, TestLot2

VALIDEUR = f"valideur.{PREFIXE.lower()}@example.com"


class TestValidation(TestLot2):
	def _opp(self):
		return self.opportunite(self.parcours_standard())

	def test_etat_initial_et_refus_sans_motif(self):
		o = self._opp()
		self.assertEqual(o.lsi_statut_validation, "À valider")
		self.utilisateur(VALIDEUR, ["Sales User", "Validateur demande d'offre"])
		frappe.set_user(VALIDEUR)
		with self.assertRaises(frappe.MandatoryError):
			apply_workflow(self.recharger(o), "Refuser")
		o = self.recharger(o)
		o.lsi_motif_non_validation = self._motif()
		o.save()
		o = apply_workflow(self.recharger(o), "Refuser")
		self.assertEqual(o.lsi_statut_validation, "Non validée")

	def test_valider_et_clarification(self):
		self.utilisateur(VALIDEUR, ["Sales User", "Validateur demande d'offre"])
		o = self._opp()
		frappe.set_user(VALIDEUR)
		o = apply_workflow(self.recharger(o), "Demander clarification")
		self.assertEqual(o.lsi_statut_validation, "Attente clarification client")
		o = apply_workflow(self.recharger(o), "Remettre à valider")
		o = apply_workflow(self.recharger(o), "Valider")
		self.assertEqual(o.lsi_statut_validation, "Validée")

	def test_commercial_ne_peut_pas_valider(self):
		u = self.utilisateur(f"commercial.{PREFIXE.lower()}@example.com", ["Sales User"])
		o = self._opp()
		frappe.set_user(u)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(self.recharger(o), "Valider")

	def test_statut_natif_evolue_normalement(self):
		self.utilisateur(VALIDEUR, ["Sales User", "Validateur demande d'offre"])
		o = self._opp()
		self.assertEqual(o.status, "Open")
		frappe.set_user(VALIDEUR)
		apply_workflow(self.recharger(o), "Valider")
		frappe.set_user("Administrator")
		self.assertEqual(self.recharger(o).status, "Open")
		q = self.devis(o)
		self.assertEqual(self.recharger(o).status, "Quotation")
		self.commande(q)
		self.commit_simule()
		o = self.recharger(o)
		self.assertEqual((o.status, o.lsi_statut_validation), ("Converted", "Validée"))

	def test_serie_native_off(self):
		self.assertTrue(self._opp().name.startswith("OFF-"))

	def test_canal_filtre_par_famille(self):
		lf = frappe.get_meta("Opportunity").get_field("lsi_canal_demande").link_filters
		self.assertIn("CANAL_DEMANDE", lf)
		self.assertIn("MOTIF_NON_VALIDATION", frappe.get_meta("Opportunity").get_field("lsi_motif_non_validation").link_filters)

	def test_code_unique_par_famille(self):
		fam = frappe.get_doc(dict(doctype="Famille de Type", code=f"{PREFIXE}_FAM", libelle="Famille test")).insert()
		frappe.get_doc(dict(doctype="Type Metier", famille=fam.name, code="A", libelle="A")).insert()
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc(dict(doctype="Type Metier", famille=fam.name, code="A", libelle="A bis")).insert()

	def test_departements_pilote_et_principal(self):
		u = self.utilisateur(f"pilote.{PREFIXE.lower()}@example.com", ["Employee"])
		dep = self.departement(f"{PREFIXE} Pilotage")
		emp = self.employe("Pilote", dep, u)
		frappe.db.set_value("Department", dep, "lsi_responsable", emp)
		o = self.opportunite(self.parcours_standard(), lsi_departements=[dict(departement=dep, principal=1)])
		self.assertEqual((o.lsi_departements[0].pilote, o.lsi_departements[0].utilisateur_pilote), (emp, u))
		dep2 = self.departement(f"{PREFIXE} Autre")
		o.append("lsi_departements", dict(departement=dep2, principal=1))
		with self.assertRaises(frappe.ValidationError):
			o.save()

	def _motif(self):
		fam = "MOTIF_NON_VALIDATION"
		if not frappe.db.exists("Famille de Type", fam):
			frappe.get_doc(dict(doctype="Famille de Type", code=fam, libelle="Motif")).insert()
		nom = f"{fam}-{PREFIXE}"
		if not frappe.db.exists("Type Metier", nom):
			frappe.get_doc(dict(doctype="Type Metier", famille=fam, code=PREFIXE, libelle="Motif test")).insert()
		return nom
