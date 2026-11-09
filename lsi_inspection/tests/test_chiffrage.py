"""Chiffrage — calcul complet et cycle de vie : reproduction de l'exemple TIC (docs/references/exemple_projet.csv),
prix fixe, tarifs, partage, fraîcheur des coûts, droits, rapport des besoins, liens avec l'opportunité."""

import frappe
from frappe.model.workflow import apply_workflow

from lsi_inspection.chiffrage import devis, etude, moteur, variantes
from lsi_inspection.tests.chiffrage_contexte import article, CATEGORIES, DESIGNATIONS, ETAPES, lire_projet, TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestChiffrage(TestChiffrageBase):
	def test_reproduction_exemple_complet(self):
		doc = self.eft_exemple()
		lignes = [l for l in lire_projet() if l["type"] != "En-tête groupe"]
		self.assertEqual([p.numero for p in doc.positions], [l["pos"] for l in lignes])  # 33 positions, ordre et numéros de l'exemple
		self.assertEqual(len(doc.positions), 33)
		self.assertEqual([g.numero for g in doc.groupes], ["1", "2", "3", "4", "5"])
		positions, groupes, etapes = self.attendus()
		for numero, (ct, pt) in positions.items():
			p = self.pos(doc, numero)
			self.assertAlmostEqual(p.cout_total, ct, 3, numero)
			self.assertAlmostEqual(p.prix_total, pt, 3, numero)
		for g in doc.groupes:
			self.assertAlmostEqual(g.cout_total, groupes[g.numero][0], 3, f"groupe {g.numero}")
			self.assertAlmostEqual(g.prix_total, groupes[g.numero][1], 3, f"groupe {g.numero}")
		for t in doc.totaux_etapes:
			self.assertAlmostEqual(t.cout_total, etapes[t.etape][0], 3, t.etape)
			self.assertAlmostEqual(t.prix_total, etapes[t.etape][1], 3, t.etape)
		self.assertAlmostEqual(doc.total_cout, sum(c for c, _p in groupes.values()), 3)
		self.assertAlmostEqual(doc.total_prix, sum(p for _c, p in groupes.values()), 3)
		self.assertAlmostEqual(sum(t.prix_total for t in doc.totaux_etapes), doc.total_prix, 3)
		self.assertTrue(doc.cout_incomplet)  # 3.2 Essai de traction : aucun prix fournisseur
		self.assertTrue(self.pos(doc, "3.2").cout_manquant)

	def test_prix_fixe_somme_des_sous_positions(self):
		doc = self.eft_exemple()
		film = self.pos(doc, "1.17")
		self.assertAlmostEqual(film.cout_total, sum(self.pos(doc, n).cout_total for n in ("1.17.1", "1.17.2", "1.17.3")), 3)
		self.assertAlmostEqual(film.cout_unitaire, film.cout_total / 3, 3)
		for n in ("1.17.1", "2.1.1", "5.1.1"):
			self.assertEqual((self.pos(doc, n).prix_total, self.pos(doc, n).prix_unitaire), (0, 0))  # jamais vendue

	def test_lignes_tarif_hors_totaux(self):
		doc = self.eft_exemple()
		tarifs = [p for p in doc.positions if p.tarif]
		self.assertEqual(sorted(p.numero for p in tarifs), sorted(["1.2", "1.3", "1.4", "1.6", "1.7", "1.8", "4.3", "4.4"], key=moteur.cle_numero))
		for p in tarifs:
			self.assertEqual((p.cout_total, p.prix_total), (0, 0))
			self.assertTrue(p.prix_unitaire)  # prix unitaire annoncé

	def test_groupe_partage_repartition(self):
		doc = self.eft_exemple()
		g4 = next(g for g in doc.groupes if g.numero == "4")
		rt = next(t for t in doc.totaux_etapes if t.etape == ETAPES["Contrôle par Radiographie (RT)"])
		dec = next(t for t in doc.totaux_etapes if t.etape == ETAPES["Découpages et Essais Mécaniques"])
		g1 = next(g for g in doc.groupes if g.numero == "1")
		g3 = next(g for g in doc.groupes if g.numero == "3")
		self.assertAlmostEqual(rt.cout_total, g1.cout_total + g4.cout_total / 2, 3)  # parts égales
		self.assertAlmostEqual(dec.cout_total, g3.cout_total + g4.cout_total / 2, 3)
		for r in doc.repartitions:
			if r.cible == "4":
				r.part = 75 if r.etape == ETAPES["Contrôle par Radiographie (RT)"] else 25
		doc.save()
		rt = next(t for t in doc.totaux_etapes if t.etape == ETAPES["Contrôle par Radiographie (RT)"])
		self.assertAlmostEqual(rt.cout_total, g1.cout_total + g4.cout_total * 0.75, 3)

	def test_cout_manquant_jamais_zero_silencieux(self):
		doc = self.eft_exemple()
		frappe.db.set_value("Employee", {"designation": f"{P} Expert en soudage"}, "lsi_cout_journalier", 0)
		doc.save()
		self.assertTrue(self.pos(doc, "2.1.1").cout_manquant)
		self.assertTrue(self.pos(doc, "2.1").cout_manquant)  # remonte au prix fixe
		self.assertTrue(doc.cout_incomplet)

	def test_recalcul_en_brouillon_sauf_cout_manuel(self):
		doc = self.eft_exemple()
		frappe.db.set_value("Asset", {"asset_name": f"{P} PROJECTEUR GAMMA 2"}, "lsi_cout_journalier", 130)
		self.pos(doc, "1.5").cout_manuel = 1
		self.pos(doc, "1.5").cout_unitaire = 99
		doc.save()
		self.assertEqual(self.pos(doc, "1.9").cout_unitaire, 130)
		self.assertEqual(self.pos(doc, "1.5").cout_unitaire, 99)

	def test_couts_figes_apres_validation(self):
		doc = self.valider_chiffrage(self.eft_exemple())
		self.assertEqual((doc.docstatus, doc.workflow_state), (1, "Validée"))
		frappe.db.set_value("Asset", {"asset_name": f"{P} PROJECTEUR GAMMA 2"}, "lsi_cout_journalier", 130)
		doc = frappe.get_doc("Chiffrage", doc.name)
		self.assertEqual(self.pos(doc, "1.9").cout_unitaire, max(CATEGORIES["PROJECTEUR GAMMA"]))

	def test_dupliquer_et_amend_recalculent(self):
		doc = self.valider_chiffrage(self.eft_exemple())
		frappe.db.set_value("Asset", {"asset_name": f"{P} PROJECTEUR GAMMA 2"}, "lsi_cout_journalier", 130)
		copie = frappe.copy_doc(doc, ignore_no_copy=False)  # comme « Dupliquer » dans l'interface (brouillon, sans les champs non copiés)
		copie.docstatus = 0
		copie.insert()
		self.assertEqual(self.pos(copie, "1.9").cout_unitaire, 130)
		doc = apply_workflow(frappe.get_doc("Chiffrage", doc.name), "Annuler")
		amende = frappe.copy_doc(doc, ignore_no_copy=False)  # comme « Amender » dans l'interface
		amende.docstatus = 0
		amende.amended_from = doc.name
		amende.insert()
		self.assertEqual(frappe.db.get_value("Chiffrage", amende.name, "amended_from"), doc.name)  # version d'origine tracée
		self.assertEqual(self.pos(amende, "1.9").cout_unitaire, 130)

	def test_structure_invalide(self):
		doc = self.eft_exemple()
		self.pos(doc, "1.18").parente = "1.1"  # parente non prix fixe
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_couts_journaliers_invisibles_pour_le_chiffreur(self):
		doc = self.eft_exemple()
		chiffreur = self.utilisateur(f"chiffreur.{P.lower()}@example.com", ["Chiffreur"])
		param = self.utilisateur(f"param2.{P.lower()}@example.com", ["Paramétreur chiffrage"])
		frappe.set_user(chiffreur)
		r = moteur.voir_ressources(doc.name, "1.1")
		self.assertFalse(r["voit_couts"])
		self.assertTrue(r["ressources"] and all(x["cout"] is None for x in r["ressources"]))
		self.assertEqual(r["cout_retenu"], max(DESIGNATIONS["Inspecteur RT niveau II"]))  # coût retenu visible
		self.assertNotIn(1, frappe.get_meta("Employee").get_permlevel_access("read"))
		frappe.set_user(param)
		r = moteur.voir_ressources(doc.name, "1.1")
		self.assertTrue(r["voit_couts"])
		self.assertEqual(sorted(x["cout"] for x in r["ressources"]), sorted(DESIGNATIONS["Inspecteur RT niveau II"]))

	def test_rapport_besoins(self):
		from lsi_inspection.chiffrage.report.besoins_chiffrage.besoins_chiffrage import besoins

		doc = self.eft_exemple()
		lignes = besoins(doc)
		b2 = next(l for l in lignes if l["ressource"] == f"{P} Inspecteur agréé B2")
		self.assertAlmostEqual(b2["jours"], 1.0, 3)  # 6 h + 2 h = 8 h = 1 jour
		vehicule = [l for l in lignes if l["ressource"] == f"{P} VEHICULE"]
		self.assertAlmostEqual(sum(l["jours"] for l in vehicule), 2.0, 3)  # 4.1 (réparti) + 5.1.3
		self.assertFalse([l for l in lignes if l["ressource"] in (article("Film"), article("Forfait /DMOS"))])  # prix fixe : par ses sous-positions

	def test_evenement_eft_creee_fait_avancer_la_phase(self):
		evt = "EFT créée"
		if not frappe.db.exists("Evenement Phase", evt):
			frappe.get_doc(dict(doctype="Evenement Phase", libelle=evt, declencheur="Création", document_type="EFT", actif=1)).insert()
		from lsi_inspection.commercial import phases

		phases.vider_cache_evenements()
		t = self.type_parcours(f"{P} Parcours EFT", [(10, "T Création", "Commercial", self.evenement("Manuel")),
			(20, "T Étude", "Commercial", evt), (30, "T Chiffrage", "Commercial", "Manuel")])
		o = self.opportunite(t)
		phases.terminer_phase(o.name)  # → T Étude
		eft = etude.ouvrir_ou_creer(o.name)
		o = self.recharger(o)
		self.assertEqual(o.sales_stage, "T Chiffrage")
		self.assertEqual(o.lsi_historique_phases[-1].document_name, eft)

	def test_bu_et_service_recopies(self):
		bu = frappe.get_doc(dict(doctype="Branch", branch=f"{P} BU")).insert().name
		service = self.departement(f"{P} SERVICE")
		o = self.opportunite(self.parcours_standard(), lsi_bu=bu, lsi_service=service)
		e = frappe.get_doc("EFT", etude.ouvrir_ou_creer(o.name))
		self.assertEqual((e.bu, e.service), (bu, service))
		doc = self.eft_exemple(bu=bu, service=service)
		doc = self.valider_chiffrage(doc)
		q = frappe.get_doc("Quotation", devis.creer_devis(doc.name))
		self.assertEqual((q.lsi_bu, q.lsi_service), (bu, service))

	def test_demande_client_texte_et_pieces_jointes_dans_l_eft(self):
		"""Le commercial écrit la demande telle quelle (ligne sans article possible) et joint un document : l'EFT les montre."""
		texte = "<p>Contrôle des soudures du réservoir R2, rapport en français, intervention de nuit possible.</p>"
		o = self.opportunite(self.parcours_standard(), lsi_demande_client=texte)
		o.append("items", dict(item_name="Contrôle à préciser", description="Soudures du réservoir R2", qty=1, rate=0))
		o.save()
		frappe.get_doc(dict(doctype="File", file_name="cdc-client.pdf", file_url="https://example.com/cdc-client.pdf",
			attached_to_doctype="Opportunity", attached_to_name=o.name)).insert()
		e = frappe.get_doc("EFT", etude.ouvrir_ou_creer(o.name))
		self.assertEqual(e.demande_client, texte)
		c = frappe.get_doc("Chiffrage", variantes.nouvelle_variante(e.name, "opportunite"))  # la ligne sans article ne bloque pas
		self.assertEqual(len(c.etapes), 1)  # seule la ligne avec un article devient une prestation
		d = etude.demande_opportunite(o.name)
		self.assertIn("Contrôle à préciser", [a["item_name"] for a in d["articles"]])
		self.assertEqual([f["file_name"] for f in d["fichiers"]], ["cdc-client.pdf"])
