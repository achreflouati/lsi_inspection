"""Lot 1 — workspace « Inspection » : livré en fichier standard du module, liens natifs valides, page chargeable."""

import json
import os

import frappe

from lsi_inspection.tests.compat import IntegrationTestCase

WORKSPACE = "Inspection"
DOSSIER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lsi_inspection", "workspace", "inspection")


def _fichier():
	with open(os.path.join(DOSSIER, "inspection.json")) as f:
		return json.load(f)


class TestWorkspace(IntegrationTestCase):
	def test_livre_en_fichier_standard(self):
		d = _fichier()
		self.assertEqual(d["name"], WORKSPACE)
		self.assertEqual(d["module"], "LSI Inspection")
		self.assertTrue(d["public"])
		self.assertNotIn("tic", d["name"].lower())

	def test_liens_vers_doctypes_existants(self):
		d = _fichier()
		cibles = [(l.get("link_type") or "DocType", l["link_to"]) for l in d["links"] if l["type"] == "Link"]
		cibles += [("DocType", s["link_to"]) for s in d["shortcuts"]]
		self.assertTrue(cibles)
		for typ, cible in cibles:
			self.assertTrue(frappe.db.exists(typ, cible), f"{typ} absent : {cible}")

	def test_blocs_du_contenu_references(self):
		"""Chaque bloc du contenu (carte, raccourci, graphique) correspond à un élément déclaré."""
		d = _fichier()
		cartes = {l["label"] for l in d["links"] if l["type"] == "Card Break"}
		raccourcis = {s["label"] for s in d["shortcuts"]}
		graphiques = {c["chart_name"] for c in d["charts"]}
		for b in json.loads(d["content"]):
			if b["type"] == "card":
				self.assertIn(b["data"]["card_name"], cartes)
			elif b["type"] == "shortcut":
				self.assertIn(b["data"]["shortcut_name"], raccourcis)
			elif b["type"] == "chart":
				self.assertIn(b["data"]["chart_name"], graphiques)
				self.assertTrue(frappe.db.exists("Dashboard Chart", b["data"]["chart_name"]))

	def test_graphique_par_phase_native(self):
		c = frappe.get_doc("Dashboard Chart", "Opportunites par phase")
		self.assertEqual((c.chart_type, c.document_type, c.group_by_based_on), ("Group By", "Opportunity", "sales_stage"))
		self.assertTrue(c.is_standard)

	def test_page_chargeable(self):
		from frappe.desk.desktop import get_desktop_page

		page = get_desktop_page(json.dumps({"name": WORKSPACE, "title": WORKSPACE, "public": 1}))
		self.assertTrue({"Commercial", "Paramétrage commercial", "Chiffrage", "Paramétrage chiffrage"} <= {c.label for c in page["cards"]["items"]})
		self.assertEqual(len(page["shortcuts"]["items"]), 2)
		self.assertEqual(len(page["charts"]["items"]), 1)
