"""Lot 3b — une opportunité = une EFT ; plusieurs variantes de chiffrage ; un devis par variante ; variante retenue ;
phases qui avancent seules à chaque étape (configuration du test, aucune dépendance au profil du site)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, nowdate

from lsi_inspection.chiffrage import devis, etude, variantes
from lsi_inspection.commercial import phases
from lsi_inspection.tests.chiffrage_contexte import TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestVariantes(TestChiffrageBase):
	# ------------------------------------------------------------------ contexte : parcours dont les fins sont les événements du lot 3b
	def parcours_lot3b(self, fin_chiffrage=None):
		ev = self.evenement
		return self.type_parcours(f"{P} Parcours 3b", [
			(10, "T Création", "Commercial", ev("Manuel")),
			(20, "T Étude", "Commercial", ev("EFT validée", "Validation", document_type="EFT")),
			(30, "T Chiffrage", "Commercial", fin_chiffrage or ev("Chiffrage validé", "Validation", document_type="Chiffrage")),
			(40, "T Validation", "Commercial", ev("Variante retenue", "État du workflow", document_type="Chiffrage", champ_statut="workflow_state",
				valeur="Retenue")),
			(50, "T Offre", "Commercial", ev("Devis envoyé", "Changement de statut", document_type="Quotation", champ_statut="lsi_envoye", valeur="1")),
			(60, "T Gagnée", "Commercial", ev("Commande validée", "Validation", document_type="Sales Order"), {"phase_finale": "Gagnée"}),
		])

	def affaire(self, fin_chiffrage=None):
		"""Opportunité (commercial = utilisateur temporaire) + son EFT validée « Faisable » ; renvoie (opportunité, EFT)."""
		commercial = self.utilisateur(f"commercial.{P.lower()}@example.com", ["Sales User", "Sales Manager", "Chiffreur"])
		o = self.opportunite(self.parcours_lot3b(fin_chiffrage), opportunity_owner=commercial)
		eft = etude.ouvrir_ou_creer(o.name)
		frappe.db.set_value("EFT", eft, "faisabilite", "Faisable")
		apply_workflow(frappe.get_doc("EFT", eft), "Valider")
		self._etude = eft  # les chiffrages de l'exemple sont rattachés à cette EFT
		return self.recharger(o), eft

	def valider(self, nom):
		apply_workflow(frappe.get_doc("Chiffrage", nom), "Chiffrer")
		return apply_workflow(frappe.get_doc("Chiffrage", nom), "Valider")

	def etat(self, nom):
		return frappe.db.get_value("Chiffrage", nom, "workflow_state")

	def derniere_phase(self, o):
		o = self.recharger(o)
		h = o.lsi_historique_phases[-1]
		return o.sales_stage, h.evenement, h.document_type, h.document_name

	# ------------------------------------------------------------------ T3b.1 une opportunité = une EFT
	def test_une_seule_eft_par_opportunite(self):
		o = self.opportunite(self.parcours_standard())
		eft = etude.ouvrir_ou_creer(o.name)
		self.assertEqual(etude.ouvrir_ou_creer(o.name), eft)  # la 2e demande ouvre la même
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(dict(doctype="EFT", opportunity=o.name, company=self.company)).insert()

	def test_eft_validee_exige_la_faisabilite(self):
		o = self.opportunite(self.parcours_standard())
		e = frappe.get_doc("EFT", etude.ouvrir_ou_creer(o.name))
		with self.assertRaises(frappe.ValidationError):
			e.submit()

	# ------------------------------------------------------------------ T3b.2 variantes : lettres, copie, comparaison
	def test_lettres(self):
		self.assertEqual(variantes.lettre_suivante([]), "A")
		self.assertEqual(variantes.lettre_suivante(["A", "C"]), "B")
		self.assertEqual(variantes.lettre_suivante(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")), "AA")

	def test_deux_variantes_dont_une_copie_et_comparaison(self):
		_o, eft = self.affaire()
		a = self.eft_exemple()
		b = frappe.get_doc("Chiffrage", variantes.nouvelle_variante(eft, "copie", source=a.name, libelle="Sans transport"))
		self.assertEqual((a.name, b.name), (f"{eft}-A", f"{eft}-B"))
		self.assertEqual((b.variante, b.libelle_variante, b.workflow_state), ("B", "Sans transport", "Brouillon"))
		self.assertEqual(len(b.positions), len(a.positions))
		self.assertAlmostEqual(b.total_cout, a.total_cout, 3)  # coûts recalculés : mêmes ressources, même total
		vide = frappe.get_doc("Chiffrage", variantes.nouvelle_variante(eft, "vide"))
		self.assertEqual((vide.variante, len(vide.positions)), ("C", 0))
		lignes = {v.variante: v for v in variantes.comparaison(eft)}
		self.assertEqual(set(lignes), {"A", "B", "C"})
		self.assertAlmostEqual(lignes["A"].total_prix, a.total_prix, 3)

	def test_copie_d_une_autre_eft_refusee(self):
		_o, eft = self.affaire()
		a = self.eft_exemple()
		autre = etude.ouvrir_ou_creer(self.opportunite(self.parcours_standard()).name)
		with self.assertRaises(frappe.ValidationError):
			variantes.nouvelle_variante(autre, "copie", source=a.name)

	# ------------------------------------------------------------------ T3b.3 variante retenue (une seule, réversible)
	def test_retenir_puis_changer_d_avis(self):
		_o, eft = self.affaire()
		a = self.eft_exemple()
		b = variantes.nouvelle_variante(eft, "copie", source=a.name)
		self.valider(a.name)
		self.valider(b)
		apply_workflow(frappe.get_doc("Chiffrage", b), "Retenir")
		self.assertEqual((self.etat(b), self.etat(a.name)), ("Retenue", "Non retenue"))
		apply_workflow(frappe.get_doc("Chiffrage", a.name), "Retenir")  # réversible
		self.assertEqual((self.etat(a.name), self.etat(b)), ("Retenue", "Non retenue"))
		apply_workflow(frappe.get_doc("Chiffrage", a.name), "Ne pas retenir")
		self.assertEqual(self.etat(a.name), "Non retenue")

	# ------------------------------------------------------------------ T3b.4 scénario complet : phases, devis A et B, commande sur B
	def test_scenario_complet(self):
		o, eft = self.affaire()
		self.assertEqual(self.derniere_phase(o), ("T Chiffrage", "EFT validée", "EFT", eft))
		a = self.eft_exemple()
		b = variantes.nouvelle_variante(eft, "copie", source=a.name)
		self.valider(a.name)
		self.assertEqual(self.derniere_phase(o), ("T Validation", "Chiffrage validé", "Chiffrage", a.name))
		self.notifie("Chiffrage", a.name, "Chiffrage validé")
		self.valider(b)
		apply_workflow(frappe.get_doc("Chiffrage", b), "Retenir")
		phases.traiter_differes()
		self.assertEqual(self.derniere_phase(o), ("T Offre", "Variante retenue", "Chiffrage", b))
		self.notifie("Chiffrage", b, "Variante retenue")
		qa = frappe.get_doc("Quotation", devis.creer_devis(a.name))
		# B sans les lignes tarif (quantité 0) : une commande native exige des quantités (comportement ERPNext documenté)
		lignes_b = [p.name for p in frappe.get_doc("Chiffrage", b).positions if not p.parente and p.qty]
		qb = frappe.get_doc("Quotation", devis.creer_devis(b, frappe.as_json(lignes_b)))
		self.assertEqual((qa.lsi_chiffrage, qa.lsi_eft, qb.lsi_chiffrage, qb.lsi_eft), (a.name, eft, b, eft))
		self.assertEqual(frappe.db.count("Quotation", {"opportunity": o.name, "docstatus": ("<", 2)}), 2)
		qb.submit()
		self.notifie("Quotation", qb.name, "Devis validé")
		self._envoyer(qb.name)
		phases.traiter_differes()
		self.assertTrue(frappe.db.get_value("Quotation", qb.name, "lsi_envoye"))
		self.assertEqual(self.derniere_phase(o), ("T Gagnée", "Devis envoyé", "Quotation", qb.name))
		self.notifie("Quotation", qb.name, "Devis envoyé")
		apply_workflow(frappe.get_doc("Chiffrage", a.name), "Retenir")  # changement d'avis… puis le client commande B
		self._commander(qb.name)
		phases.traiter_differes()
		self.assertEqual((self.etat(b), self.etat(a.name)), ("Retenue", "Non retenue"))
		o = self.recharger(o)
		self.assertEqual(o.status, "Converted")
		self.assertEqual(self.derniere_phase(o)[1], "Commande validée")
		self.notifie("Opportunity", o.name, "Commande validée")

	def notifie(self, doctype, nom, sujet):
		"""Une notification native (profil du site) a été émise pour ce document (cloche ; e-mail en file jamais envoyé : test annulé)."""
		sujets = frappe.get_all("Notification Log", filters={"document_type": doctype, "document_name": nom}, pluck="subject")
		self.assertTrue(any(sujet in (m or "") for m in sujets), f"aucune notification « {sujet} » pour {doctype} {nom} : {sujets}")

	def _envoyer(self, devis_nom):
		frappe.get_doc(dict(doctype="Communication", communication_type="Communication", communication_medium="Email", sent_or_received="Sent",
			subject="Offre", content="Offre", recipients="client@example.com", reference_doctype="Quotation", reference_name=devis_nom)).insert(
			ignore_permissions=True)

	def _commander(self, devis_nom):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		so = make_sales_order(devis_nom)
		so.delivery_date = add_days(nowdate(), 7)
		for it in so.items:
			it.delivery_date = so.delivery_date
		so.insert()
		so.submit()
		return so.name

	# ------------------------------------------------------------------ T3b.5 rattachement modifié à l'écran, sans code
	def test_rattachement_modifie_a_l_ecran(self):
		fin = self.evenement("Chiffrage créé", "Création", document_type="Chiffrage")
		o, eft = self.affaire(fin_chiffrage=fin)  # le paramétreur a choisi « Chiffrage créé » pour terminer la phase Chiffrage
		variantes.nouvelle_variante(eft, "vide")
		self.assertEqual(self.derniere_phase(o)[:2], ("T Validation", "Chiffrage créé"))

	# ------------------------------------------------------------------ T3b.6 connexions natives
	def test_connexions(self):
		data = devis.connexions_devis({})
		self.assertEqual(data["internal_links"], {"Chiffrage": "lsi_chiffrage", "EFT": "lsi_eft"})
		self.assertIn("EFT", devis.connexions_opportunite({})["transactions"][0]["items"])
		from lsi_inspection.chiffrage.doctype.eft.eft_dashboard import get_data

		self.assertEqual(get_data()["non_standard_fieldnames"]["Quotation"], "lsi_eft")
