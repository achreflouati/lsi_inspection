"""Lot 2 — configuration initiale (insertion seule) et export de profil."""

import filecmp
import json
import os
import tempfile

import frappe

from lsi_inspection import config
from lsi_inspection.tests.contexte import PREFIXE, TestLot2


def _identiques(a, b):
	c = filecmp.dircmp(a, b)
	return not (c.left_only or c.right_only or c.diff_files)


class TestConfig(TestLot2):
	def test_chargement_idempotent(self):
		config.charger()
		self.assertEqual(config.charger(), 0)

	def test_valeur_modifiee_a_l_ecran_conservee(self):
		config.charger()
		nom = "CANAL_DEMANDE"
		frappe.db.set_value("Famille de Type", nom, "libelle", "Libellé modifié par TIC")
		config.charger()
		self.assertEqual(frappe.db.get_value("Famille de Type", nom, "libelle"), "Libellé modifié par TIC")

	def test_nouvel_element_insere(self):
		with tempfile.TemporaryDirectory() as d:
			with open(os.path.join(d, "famille_de_type.json"), "w") as f:
				json.dump([{"name": f"{PREFIXE}_NOUVELLE", "code": f"{PREFIXE}_NOUVELLE", "libelle": "Nouvelle famille", "actif": 1}], f)
			self.assertEqual(config.charger_dossier(d), 1)
			self.assertTrue(frappe.db.exists("Famille de Type", f"{PREFIXE}_NOUVELLE"))
			self.assertEqual(config.charger_dossier(d), 0)

	def test_site_sans_profil_commun_seul(self):
		self.assertEqual(config.dossiers(""), [os.path.join(config.racine(), "commun")])
		self.assertEqual(len(config.dossiers("tic")), 2)

	def test_export_jamais_dans_commun(self):
		with self.assertRaises(frappe.ValidationError):
			config.exporter_profil("tic", dossier=os.path.join(config.racine(), "commun"))

	def test_reexport_sans_changement_identique(self):
		with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
			config.exporter_profil("tic", dossier=a)
			config.exporter_profil("tic", dossier=b)
			self.assertTrue(_identiques(a, b))

	def test_export_puis_import_sur_base_vide(self):
		with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
			config.exporter_profil("tic", dossier=a)
			# base « vide » pour ces doctypes (dans la transaction de test, annulée ensuite)
			for e in config.manifeste():
				if e.get("single"):
					continue  # réglage natif (document unique) : jamais supprimé
				dt = e["doctype"]
				noms = [d["name"] for d in config._lire(a, dt)]
				if not noms:
					continue
				for tdf in frappe.get_meta(dt).get_table_fields():
					frappe.db.delete(tdf.options, {"parent": ("in", noms), "parenttype": dt})
				frappe.db.delete(dt, {"name": ("in", noms)})
			frappe.clear_cache()
			self.assertGreater(config.charger_dossier(a), 0)
			config.exporter_profil("tic", dossier=b)
			self.assertTrue(_identiques(a, b))
