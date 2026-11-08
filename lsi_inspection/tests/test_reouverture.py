"""Lot 2b — réouverture : le statut final de l'opportunité quitte « Lost » (devis annulé) → la phase Perdue passe « Annulée »,
la phase qui était en cours avant la perte redevient « En cours », ligne « Réouverture » dans l'historique."""

import frappe

from lsi_inspection.commercial import phases
from lsi_inspection.tests.contexte import PREFIXE, TestLot2


class TestReouverture(TestLot2):
	def _motif(self):
		nom = f"{PREFIXE} Prix trop élevé"
		if not frappe.db.exists("Quotation Lost Reason", nom):
			frappe.get_doc(dict(doctype="Quotation Lost Reason", order_lost_reason=nom)).insert(ignore_permissions=True)
		return nom

	def _perdre(self, annulation=True):
		o = self.opportunite(self.parcours_standard(annulation=annulation))
		q = self.devis(o)  # Devis validé : Création, Étude, Chiffrage sautées (auto), Validation terminée, Offre en cours
		q.reload()
		q.declare_enquiry_lost([{"lost_reason": self._motif()}], [], detailed_reason="Trop cher")
		self.commit_simule()
		o = self.recharger(o)
		self.assertEqual((o.status, self.statuts(o)["T Perdue"]), ("Lost", "Terminée"))
		return o, q

	def test_devis_annule_rouvre_l_opportunite(self):
		o, q = self._perdre()
		q.reload()
		q.cancel()
		self.commit_simule()
		o = self.recharger(o)
		self.assertNotEqual(o.status, "Lost")
		s = self.statuts(o)
		self.assertEqual(s["T Perdue"], "Annulée")
		self.assertEqual(s["T Offre"], "En cours")  # phase en cours avant la perte
		self.assertEqual(s["T Gagnée"], "À venir")  # sautée par la perte : remise à venir
		self.assertEqual((s["T Étude"], s["T Validation"]), ("Sautée (auto)", "Terminée"))  # avant la perte : inchangées
		self.assertEqual(o.sales_stage, "T Offre")
		h = o.lsi_historique_phases[-1]
		self.assertEqual((h.action, h.de_phase, h.vers_phase, h.par, h.evenement), ("Réouverture", "T Perdue", "T Offre", "Administrator",
			"Opportunité rouverte"))
		self.assertEqual((h.document_type, h.document_name), ("Quotation", q.name))
		self.assertEqual([x.action for x in o.lsi_historique_phases][-2:], ["Perdue", "Réouverture"])

	def test_sans_evenement_d_annulation_rien_ne_change(self):
		o, q = self._perdre(annulation=False)
		q.reload()
		q.cancel()
		self.commit_simule()
		o = self.recharger(o)
		self.assertNotEqual(o.status, "Lost")
		self.assertEqual(self.statuts(o)["T Perdue"], "Terminée")
		self.assertNotIn("Réouverture", [x.action for x in o.lsi_historique_phases])

	def test_perdue_de_nouveau_apres_reouverture(self):
		o, q = self._perdre()
		q.reload()
		q.cancel()
		self.commit_simule()
		q2 = self.devis(self.recharger(o))
		q2.reload()
		q2.declare_enquiry_lost([{"lost_reason": self._motif()}], [])
		self.commit_simule()
		o = self.recharger(o)
		self.assertEqual((o.status, self.statuts(o)["T Perdue"]), ("Lost", "Terminée"))
		self.assertEqual([x.action for x in o.lsi_historique_phases][-3:], ["Perdue", "Réouverture", "Perdue"])

	def test_sens_quitte_la_valeur_ne_se_declenche_pas_a_l_arrivee(self):
		self.parcours_standard()
		ev = frappe._dict(phases.evenements())
		rouverte = next(e for e in ev["Opportunity"] if e.name == "Opportunité rouverte")
		self.assertEqual(rouverte.sens, "Quitte la valeur")
		o, _ = self._perdre()  # l'arrivée en « Lost » ne déclenche pas la réouverture
		self.assertNotIn("Réouverture", [x.action for x in o.lsi_historique_phases])
