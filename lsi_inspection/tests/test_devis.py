"""Offre client (chiffrage/devis.py) : lignes vendues seulement, lignes cochées, remise native, lignes tarif."""

import frappe
from frappe.utils import flt

from lsi_inspection.chiffrage import devis
from lsi_inspection.tests.chiffrage_contexte import PRIX, TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestDevis(TestChiffrageBase):
	def test_devis_positions_vendues_seulement(self):
		doc = self.valider_chiffrage(self.eft_exemple())
		q = frappe.get_doc("Quotation", devis.creer_devis(doc.name))
		vendues = [p for p in doc.positions if not p.parente]
		self.assertEqual([i.lsi_numero_position for i in q.items], [p.numero for p in vendues])
		self.assertFalse([i for i in q.items if i.lsi_numero_position.count(".") == 2])  # aucune sous-position
		self.assertEqual(q.lsi_chiffrage, doc.name)
		tarif = next(i for i in q.items if i.lsi_numero_position == "1.2")
		self.assertEqual((tarif.qty, tarif.rate, tarif.amount, tarif.lsi_tarif), (0, PRIX["1.2"], 0, 1))
		self.assertAlmostEqual(q.net_total, doc.total_prix, 2)
		self.assertEqual(next(i for i in q.items if i.lsi_numero_position == "4.1").lsi_groupe_titre, "Transport & Indemnité")
		html = frappe.get_print("Quotation", q.name, print_format="Devis groupe", doc=q)
		self.assertIn("Transport &amp; Indemnité", html.replace("Transport & Indemnité", "Transport &amp; Indemnité"))
		self.assertIn("Sous-total", html)
		self.assertNotIn("FILM MX125", html)

	def test_devis_refuse_si_quantite_zero_non_autorisee(self):
		doc = self.valider_chiffrage(self.eft_exemple())
		frappe.db.set_single_value("Selling Settings", "allow_zero_qty_in_quotation", 0)
		with self.assertRaises(frappe.ValidationError):
			devis.creer_devis(doc.name)

	def test_offre_client_lignes_cochees_et_remise(self):
		doc = self.valider_chiffrage(self.eft_exemple())
		choisies = [self.pos(doc, n).name for n in ("1.1", "1.17", "2.1")]
		q = frappe.get_doc("Quotation", devis.creer_devis(doc.name, frappe.as_json(choisies), 10))
		self.assertEqual(sorted(i.lsi_numero_position for i in q.items), ["1.1", "1.17", "2.1"])  # seulement les lignes cochées
		self.assertEqual((q.apply_discount_on, q.additional_discount_percentage), ("Net Total", 10))
		self.assertAlmostEqual(q.net_total, sum(flt(i.amount) for i in q.items) * 0.9, 2)
		with self.assertRaises(frappe.ValidationError):
			devis.creer_devis(doc.name, "[]")
