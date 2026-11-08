"""Lot 2 — moteur des phases : construction, Terminer ma phase, obligatoires, retour arrière, historique, échéance,
événements (configuration seule), phases finales Gagnée / Perdue pilotées par le statut natif, performance."""

from unittest.mock import patch

import frappe
from frappe.utils import get_datetime

from lsi_inspection.commercial import phases
from lsi_inspection.tests.contexte import PREFIXE, TestLot2


class TestPhases(TestLot2):
	def test_construction_depuis_le_parcours(self):
		t = self.parcours_standard()
		o = self.opportunite(t)
		self.assertEqual([r.phase for r in o.lsi_phases], ["T Création", "T Étude", "T Chiffrage", "T Validation", "T Offre", "T Gagnée", "T Perdue"])
		self.assertEqual(self.statuts(o)["T Création"], "En cours")
		self.assertEqual(o.sales_stage, "T Création")
		self.assertEqual(o.lsi_responsable_phase, "Administrator")
		self.assertTrue(o.name.startswith("OFF-"), o.name)

	def test_type_sans_parcours_prend_le_defaut(self):
		defaut = frappe.db.get_value("Opportunity Type", {"lsi_parcours_defaut": 1})
		if not defaut:
			defaut = self.parcours_standard(f"{PREFIXE} Défaut")
			frappe.db.set_value("Opportunity Type", defaut, "lsi_parcours_defaut", 1)
		vide = frappe.get_doc(dict(doctype="Opportunity Type", name=f"{PREFIXE} Vide")).insert(set_name=f"{PREFIXE} Vide")
		o = self.opportunite(vide.name)
		self.assertEqual([r.phase for r in o.lsi_phases], [p.phase for p in phases.phases_parcours(defaut)])

	def test_terminer_ma_phase(self):
		o = self.opportunite(self.parcours_standard())
		self.assertEqual(phases.terminer_phase(o.name), "T Étude")
		o = self.recharger(o)
		self.assertEqual(self.statuts(o)["T Création"], "Terminée")
		self.assertEqual(o.sales_stage, "T Étude")
		h = o.lsi_historique_phases[-1]
		self.assertEqual((h.de_phase, h.vers_phase, h.action, h.par), ("T Création", "T Étude", "Terminée", "Administrator"))
		self.assertTrue(frappe.db.exists("ToDo", {"reference_name": o.name, "description": ("like", "[T Étude]%"), "status": "Open"}))
		self.assertFalse(frappe.db.exists("ToDo", {"reference_name": o.name, "description": ("like", "[T Création]%"), "status": "Open"}))

	def test_phase_obligatoire_non_sautable_a_la_main(self):
		o = self.opportunite(self.parcours_standard(options={"T Étude": {"obligatoire": 1}}))
		with self.assertRaises(frappe.ValidationError):
			phases.terminer_phase(o.name, vers="T Chiffrage")
		phases.terminer_phase(o.name, vers="T Étude")

	def test_historique_terminer_sauter_retour(self):
		o = self.opportunite(self.parcours_standard())
		phases.terminer_phase(o.name)  # Création → Étude
		h1 = self.recharger(o).lsi_historique_phases[0].as_dict()
		phases.terminer_phase(o.name, vers="T Validation")  # saute Chiffrage
		phases.terminer_phase(o.name, vers="T Étude", commentaire="retour demandé")  # retour arrière
		o = self.recharger(o)
		self.assertEqual([h.action for h in o.lsi_historique_phases], ["Terminée", "Sautée", "Retour arrière"])
		self.assertIn("T Chiffrage", o.lsi_historique_phases[1].commentaire)
		self.assertEqual({k: h1[k] for k in phases.CHAMPS_HISTO}, {k: o.lsi_historique_phases[0].get(k) for k in phases.CHAMPS_HISTO})
		s = self.statuts(o)
		self.assertEqual((s["T Étude"], s["T Chiffrage"], s["T Validation"]), ("En cours", "À venir", "À venir"))

	def test_historique_ni_modifie_ni_supprime(self):
		o = self.opportunite(self.parcours_standard())
		phases.terminer_phase(o.name)
		o = self.recharger(o)
		o.lsi_historique_phases[0].commentaire = "modifié"
		with self.assertRaises(frappe.ValidationError):
			o.save()
		o = self.recharger(o)
		o.set("lsi_historique_phases", [])
		with self.assertRaises(frappe.ValidationError):
			o.save()

	def test_echeance_depuis_la_duree_cible(self):
		o = self.opportunite(self.parcours_standard(options={"T Création": {"duree_cible": 3}}))
		cur = phases.courante(o)
		self.assertEqual(get_datetime(o.lsi_echeance_phase), get_datetime(cur.echeance))
		self.assertEqual((get_datetime(cur.echeance) - get_datetime(cur.debut)).days, 3)
		phases.terminer_phase(o.name)
		self.assertIsNone(self.recharger(o).lsi_echeance_phase)  # durée vide : pas d'échéance

	def test_parcours_modifie_suit_les_ouvertes_seulement(self):
		t = self.parcours_standard()
		ouverte, perdue = self.opportunite(t), self.opportunite(t)
		frappe.db.set_value("Opportunity", perdue.name, "status", "Lost")
		doc = frappe.get_doc("Opportunity Type", t)
		doc.append("lsi_parcours", dict(ordre=15, phase=self.etape("T Visite"), type_responsable="Commercial", evenement_fin="Manuel"))
		doc.save()
		self.assertIn("T Visite", self.statuts(self.recharger(ouverte)))
		self.assertNotIn("T Visite", self.statuts(self.recharger(perdue)))
		self.assertEqual(self.recharger(ouverte).lsi_historique_phases[-1].action, "Reconstruction")

	def test_changement_de_type_garde_les_phases_faites(self):
		o = self.opportunite(self.parcours_standard())
		phases.terminer_phase(o.name)
		court = self.type_parcours(f"{PREFIXE} Court", [(10, "T Création", "Commercial", "Manuel"), (20, "T Synthèse", "Commercial", "Manuel")])
		o = self.recharger(o)
		o.opportunity_type = court
		o.save()
		s = self.statuts(o)
		self.assertEqual(s["T Création"], "Terminée")
		self.assertEqual(s["T Étude"], "En cours")  # phase en cours poursuivie, hors parcours
		self.assertTrue(next(r for r in o.lsi_phases if r.phase == "T Étude").hors_parcours)
		self.assertEqual(s["T Synthèse"], "À venir")
		self.assertEqual(o.lsi_historique_phases[-1].action, "Reconstruction")

	def test_evenement_ajoute_par_configuration_seule(self):
		evt = self.evenement(f"{PREFIXE} Devis créé", "Création", document_type="Quotation")
		t = self.parcours_standard(options={"T Chiffrage": {"evenement_fin": evt}})
		o = self.opportunite(t)
		self.devis(o, soumettre=False)
		s = self.statuts(self.recharger(o))
		self.assertEqual((s["T Création"], s["T Étude"], s["T Chiffrage"], s["T Validation"]),
			("Sautée (auto)", "Sautée (auto)", "Terminée", "En cours"))
		h = self.recharger(o).lsi_historique_phases[-1]
		self.assertEqual((h.action, h.evenement, h.document_type), ("Sautée (auto)", evt, "Quotation"))

	def test_devis_valide_saute_les_phases_intermediaires(self):
		o = self.opportunite(self.parcours_standard())
		q = self.devis(o)
		o = self.recharger(o)
		s = self.statuts(o)
		self.assertEqual((s["T Étude"], s["T Validation"], s["T Offre"]), ("Sautée (auto)", "Terminée", "En cours"))
		self.assertEqual(o.lsi_historique_phases[-1].document_name, q.name)
		self.assertEqual(o.status, "Quotation")  # statut natif inchangé dans son évolution

	def test_commande_termine_la_phase_gagnee(self):
		o = self.opportunite(self.parcours_standard())
		q = self.devis(o)
		self.commande(q)
		self.commit_simule()
		o = self.recharger(o)
		self.assertEqual(o.status, "Converted")
		s = self.statuts(o)
		self.assertEqual((s["T Offre"], s["T Gagnée"], s["T Perdue"]), ("Sautée (auto)", "Terminée", "À venir"))
		h = o.lsi_historique_phases[-1]
		self.assertEqual((h.action, h.evenement, h.document_type, h.document_name), ("Gagnée", "Opportunité convertie", "Quotation", q.name))
		self.assertIsNone(phases.courante(o))
		self.assertEqual(o.sales_stage, "T Gagnée")

	def _motif(self):
		nom = f"{PREFIXE} Prix trop élevé"
		if not frappe.db.exists("Quotation Lost Reason", nom):
			frappe.get_doc(dict(doctype="Quotation Lost Reason", order_lost_reason=nom)).insert(ignore_permissions=True)
		return nom

	def test_declarer_perdu_sur_le_devis(self):
		o = self.opportunite(self.parcours_standard())
		phases.terminer_phase(o.name)
		q = self.devis(o)
		q.reload()
		q.declare_enquiry_lost([{"lost_reason": self._motif()}], [], detailed_reason="Concurrent moins cher")
		self.commit_simule()
		o = self.recharger(o)
		self.assertEqual(o.status, "Lost")
		s = self.statuts(o)
		self.assertEqual(s["T Perdue"], "Terminée")
		self.assertEqual(s["T Offre"], "Sautée (auto)")
		self.assertEqual(s["T Gagnée"], "Sautée (auto)")
		h = o.lsi_historique_phases[-1]
		self.assertEqual((h.action, h.document_type, h.document_name), ("Perdue", "Quotation", q.name))
		self.assertIn(self._motif(), h.motif)
		self.assertIn("Concurrent moins cher", h.motif)
		self.assertEqual(o.sales_stage, "T Perdue")

	def test_deux_devis_un_perdu_un_ouvert_aucune_phase_finale(self):
		o = self.opportunite(self.parcours_standard())
		q1 = self.devis(o)
		self.devis(o)
		q1.reload()
		q1.declare_enquiry_lost([{"lost_reason": self._motif()}], [])
		self.commit_simule()
		o = self.recharger(o)
		self.assertEqual(o.status, "Quotation")  # natif : un devis encore ouvert → l'opportunité reste « Quotation »
		s = self.statuts(o)
		self.assertEqual((s["T Gagnée"], s["T Perdue"]), ("À venir", "À venir"))
		self.assertNotIn("Perdue", [h.action for h in o.lsi_historique_phases])

	def test_erreur_du_moteur_ne_bloque_pas_le_document(self):
		o = self.opportunite(self.parcours_standard())
		with patch.object(phases, "appliquer_evenement", side_effect=Exception("panne simulée")):
			q = self.devis(o)
		self.assertEqual(q.docstatus, 1)
		self.assertTrue(self.erreurs(o.name))

	def test_document_hors_evenements_sans_appel_au_moteur(self):
		self.parcours_standard()
		phases.evenements()
		with patch.object(phases, "declencher") as d, patch.object(phases, "_noter_valeurs") as n:
			frappe.get_doc(dict(doctype="ToDo", description="hors événements")).insert(ignore_permissions=True)
		d.assert_not_called()
		n.assert_not_called()
		self.assertNotIn("ToDo", phases.evenements())
