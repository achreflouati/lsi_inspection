"""Ouverture aux testeurs : devis groupé par défaut, devis natif de l'opportunité réservé au rôle « Devis hors EFT »."""

import os

import frappe

from lsi_inspection.tests.compat import IntegrationTestCase

JS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "js", "opportunity.js")


class TestOuverture(IntegrationTestCase):
	def test_devis_groupe_format_par_defaut(self):
		self.assertEqual(frappe.get_meta("Quotation").default_print_format, "Devis groupe")
		self.assertTrue(frappe.db.exists("Print Format", "Devis groupe"))

	def test_role_devis_hors_eft_livre(self):
		self.assertTrue(frappe.db.exists("Role", "Devis hors EFT"))
		with open(JS) as f:
			js = f.read()
		self.assertIn('has_role("Devis hors EFT")', js)
		self.assertIn('remove_custom_button(__("Quotation"), __("Create"))', js)
