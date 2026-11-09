"""Formules pures du chiffrage (sans base de données)."""

import unittest

from lsi_inspection.chiffrage.moteur.formules import appliquer_regle, cle_numero, libelle_parts, prix_conseille, taux
from lsi_inspection.constants import MOINS_ELEVE, MOYENNE, PLUS_ELEVE


class TestFormules(unittest.TestCase):
	def test_taux(self):
		self.assertEqual(taux(25, 100), 25)
		self.assertEqual(taux(10, 0), 0)

	def test_prix_conseille(self):
		self.assertAlmostEqual(prix_conseille(70, 30), 100)
		self.assertEqual(prix_conseille(70, 0), 0)
		self.assertEqual(prix_conseille(70, 100), 0)
		self.assertEqual(prix_conseille(0, 30), 0)

	def test_regle(self):
		self.assertEqual(appliquer_regle([12, 15, 10], PLUS_ELEVE), 15)
		self.assertEqual(appliquer_regle([12, 15, 10], None), 15)
		self.assertEqual(appliquer_regle([12, 15, 10], MOINS_ELEVE), 10)
		self.assertAlmostEqual(appliquer_regle([12, 15, 9], MOYENNE), 12)
		self.assertIsNone(appliquer_regle([], PLUS_ELEVE))

	def test_cle_numero(self):
		self.assertEqual(sorted(["1.10", "1.9", "", "1.17.1", "1.2"], key=cle_numero), ["1.2", "1.9", "1.10", "1.17.1", ""])

	def test_libelle_parts(self):
		self.assertEqual(libelle_parts([("RT", 1)], {"RT": "Radio"}), "Radio")
		self.assertEqual(libelle_parts([("RT", .5), ("D", .5)], {}), "RT (50 %), D (50 %)")
		self.assertIsNone(libelle_parts([], {}))
