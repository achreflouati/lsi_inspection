"""Contrôles de base : installation et respect des règles de livraison (voir README)."""

import frappe

from lsi_inspection import hooks
from lsi_inspection.tests.compat import IntegrationTestCase


class TestInstallation(IntegrationTestCase):
	def test_app_installee(self):
		self.assertIn("lsi_inspection", frappe.get_installed_apps())

	def test_apps_requises_installees(self):
		installees = frappe.get_installed_apps()
		for app in hooks.required_apps:
			self.assertIn(app, installees, f"app requise non installée : {app}")

	def test_fixtures_toujours_filtrees(self):
		"""Règle : chaque fixture est un dict {"dt": ..., "filters": [...]} non vide."""
		for f in hooks.fixtures:
			self.assertIsInstance(f, dict, f"fixture sans filtre : {f}")
			self.assertTrue(f.get("filters"), f"fixture sans filtre : {f.get('dt') or f.get('doctype')}")
