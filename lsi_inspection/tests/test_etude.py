"""Lot 3b — EFT (étude technique) : non faisable → phase, notification, opportunité déclarée perdue ; reprise de l'existant."""

import frappe

from lsi_inspection.chiffrage import etude
from lsi_inspection.commercial import phases
from lsi_inspection.patches import lot3b_reprise_eft_variantes as reprise
from lsi_inspection.tests.chiffrage_contexte import TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestEtude(TestChiffrageBase):
	def test_non_faisable_phase_notification_puis_perdue(self):
		ev = self.evenement
		parcours = self.type_parcours(f"{P} Parcours étude", [
			(10, "T Création", "Commercial", ev("Manuel")),
			(20, "T Étude", "Commercial", ev("EFT non faisable", "Changement de statut", document_type="EFT", champ_statut="faisabilite",
				valeur="Non faisable")),
			(30, "T Suite", "Commercial", ev("Manuel")),
			(99, "T Perdue", "Commercial", ev("Opportunité perdue", "Changement de statut", document_type="Opportunity", champ_statut="status",
				valeur="Lost"), {"phase_finale": "Perdue"}),
		])
		commercial = self.utilisateur(f"commercial.{P.lower()}@example.com", ["Sales User", "Sales Manager"])
		o = self.opportunite(parcours, opportunity_owner=commercial)
		e = frappe.get_doc("EFT", etude.ouvrir_ou_creer(o.name))
		motif = frappe.get_all("Type Metier", filters={"famille": "MOTIF_FAISABILITE"}, pluck="name", limit=1)
		e.update(dict(faisabilite="Non faisable", motif_faisabilite=motif[0] if motif else None, commentaire_faisabilite="Hors compétence"))
		e.save()
		phases.traiter_differes()
		o = self.recharger(o)
		self.assertEqual((o.sales_stage, o.lsi_historique_phases[-1].evenement), ("T Suite", "EFT non faisable"))
		if frappe.db.exists("Notification", "EFT non faisable"):
			self.assertTrue(frappe.db.exists("Notification Log", {"document_type": "EFT", "document_name": e.name}))
		raison = frappe.get_doc(dict(doctype="Opportunity Lost Reason", lost_reason=f"{P} hors compétence")).insert().name
		etude.declarer_perdue(e.name, frappe.as_json([raison]))
		phases.traiter_differes()
		o = self.recharger(o)
		self.assertEqual((o.status, o.sales_stage), ("Lost", "T Perdue"))

	def test_declarer_perdue_reservee_au_non_faisable(self):
		o = self.opportunite(self.parcours_standard())
		e = etude.ouvrir_ou_creer(o.name)
		with self.assertRaises(frappe.ValidationError):
			etude.declarer_perdue(e, "[]")

	def test_reprise_sans_perte(self):
		"""Anciennes EFT (chiffrages sans EFT) : même opportunité → une EFT, variantes A et B ; version amendée → …-A-1 ; devis relié."""
		o = self.opportunite(self.parcours_standard())
		anciens = []
		for i in (1, 2):
			c = self.nouveau_chiffrage()
			c.update(dict(eft=None, titre=f"{P} ancien {i}", company=self.company, customer=self.client()))
			c.flags.ignore_mandatory = True
			c.insert(set_name=f"{P}-ANCIEN-{i}")
			frappe.db.set_value("Chiffrage", c.name, {"eft": None, "opportunity": o.name, "variante": None})
			anciens.append(c.name)
		frappe.db.set_value("Chiffrage", anciens[1], "amended_from", None)
		q = frappe.get_doc(dict(doctype="Quotation", quotation_to="Customer", party_name=self.client(), company=self.company,
			items=[dict(item_code=self.article(), qty=1, rate=10)])).insert()
		frappe.db.set_value("Quotation", q.name, "lsi_eft", None)
		frappe.db.set_value("Quotation", q.name, "lsi_chiffrage", None)
		positions = frappe.db.count("Chiffrage Position")
		correspondance = reprise._reprendre_chiffrages()
		nouvel_a, eft = correspondance[anciens[0]]
		nouvel_b, eft_b = correspondance[anciens[1]]
		self.assertEqual((eft, eft_b, nouvel_a, nouvel_b), (anciens[0], anciens[0], f"{anciens[0]}-A", f"{anciens[0]}-B"))
		self.assertEqual(frappe.db.get_value("EFT", eft, "opportunity"), o.name)
		# pendant la migration, le renommage natif a déjà reporté le nouveau nom du chiffrage dans lsi_eft (alors lien vers Chiffrage)
		frappe.db.set_value("Quotation", q.name, "lsi_eft", nouvel_a, update_modified=False)
		reprise._relier("Quotation")
		self.assertEqual(frappe.db.get_value("Quotation", q.name, ["lsi_chiffrage", "lsi_eft"]), (nouvel_a, eft))
		self.assertEqual(frappe.db.count("Chiffrage Position"), positions)
