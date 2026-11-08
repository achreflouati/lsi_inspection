"""Lot 3 — chiffrage : reproduction de l'exemple TIC (docs/references/exemple_projet.csv) et règles du moteur."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import flt

from lsi_inspection.chiffrage import moteur
from lsi_inspection.tests.chiffrage_contexte import (
	CATEGORIES, DESIGNATIONS, ETAPES, PRIX, TYPES, TestChiffrageBase, article, lire_projet,
)
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestChiffrage(TestChiffrageBase):
	# ------------------------------------------------------------------ reproduction de l'exemple complet
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

	# ------------------------------------------------------------------ pool
	def test_pool_cout_le_plus_eleve(self):
		doc = self.eft_exemple()
		p = self.pos(doc, "1.1")
		self.assertEqual(p.cout_unitaire, max(DESIGNATIONS["Inspecteur RT niveau II"]))
		self.assertIn("Plus élevé", p.source_cout)
		self.assertEqual(self.pos(doc, "1.9").cout_unitaire, max(CATEGORIES["PROJECTEUR GAMMA"]))

	def test_choix_d_une_autre_ressource(self):
		doc = self.eft_exemple()
		moins_cher = self.employes["Inspecteur RT niveau II"][0]
		moteur.choisir_ressource(doc.name, "1.1", moins_cher)
		p = self.pos(frappe.get_doc("EFT", doc.name), "1.1")
		self.assertEqual((p.cout_unitaire, p.ressource), (DESIGNATIONS["Inspecteur RT niveau II"][0], moins_cher))
		self.assertIn(moins_cher, p.source_cout)
		moteur.choisir_ressource(doc.name, "1.1", None)  # retour à la règle du pool
		self.assertEqual(self.pos(frappe.get_doc("EFT", doc.name), "1.1").cout_unitaire, max(DESIGNATIONS["Inspecteur RT niveau II"]))

	def test_regle_moyenne_type_ajoute_a_l_ecran_sans_code(self):
		self.utilisateur(f"param.{P.lower()}@example.com", ["Paramétreur chiffrage"])
		frappe.set_user(f"param.{P.lower()}@example.com")
		t = frappe.get_doc("Type Position", TYPES["Service à côut"]).as_dict()
		for k in ("name", "creation", "modified", "owner", "modified_by"):
			t.pop(k, None)
		t.update(libelle=f"{P} Service moyenne", regle="Moyenne")
		frappe.get_doc(dict(t, doctype="Type Position")).insert()
		frappe.set_user("Administrator")
		doc = self.eft_exemple()
		self.pos(doc, "1.1").type_position = f"{P} Service moyenne"
		doc.save()
		couts = DESIGNATIONS["Inspecteur RT niveau II"]
		self.assertAlmostEqual(self.pos(doc, "1.1").cout_unitaire, sum(couts) / len(couts), 3)

	def test_conversion_jour_heure(self):
		doc = self.eft_exemple()
		p = self.pos(doc, "5.1.1")  # 6 heures d'inspecteur agréé B2
		self.assertEqual(p.uom, "Heure")
		self.assertAlmostEqual(p.cout_unitaire, max(DESIGNATIONS["Inspecteur agréé B2"]) / 8, 3)
		self.assertAlmostEqual(p.cout_total, 6 * max(DESIGNATIONS["Inspecteur agréé B2"]) / 8, 3)
		self.assertIn("÷ 8", p.source_cout)

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

	# ------------------------------------------------------------------ coût manquant / en attente
	def test_cout_manquant_jamais_zero_silencieux(self):
		doc = self.eft_exemple()
		frappe.db.set_value("Employee", {"designation": f"{P} Expert en soudage"}, "lsi_cout_journalier", 0)
		doc.save()
		self.assertTrue(self.pos(doc, "2.1.1").cout_manquant)
		self.assertTrue(self.pos(doc, "2.1").cout_manquant)  # remonte au prix fixe
		self.assertTrue(doc.cout_incomplet)

	def test_cout_en_attente_puis_offre_fournisseur(self):
		from erpnext.buying.doctype.request_for_quotation.request_for_quotation import make_supplier_quotation_from_rfq

		doc = self.eft_exemple()
		rfq_name = moteur.demander_prix(doc.name, "3.2", frappe.as_json([self.fournisseurs[2]]))
		p = self.pos(frappe.get_doc("EFT", doc.name), "3.2")
		self.assertEqual((p.demande_prix, p.cout_en_attente, p.cout_manquant), (rfq_name, 1, 0))
		rfq = frappe.get_doc("Request for Quotation", rfq_name)
		self.assertEqual(rfq.lsi_eft, doc.name)
		for s in rfq.suppliers:
			s.send_email = 0
		rfq.save()
		rfq.submit()
		sq = make_supplier_quotation_from_rfq(rfq_name, for_supplier=self.fournisseurs[2])
		for it in sq.items:
			it.rate = 75
		sq.insert()
		sq.submit()  # hook : l'EFT (brouillon) est recalculée
		p = self.pos(frappe.get_doc("EFT", doc.name), "3.2")
		self.assertEqual((p.cout_unitaire, p.cout_en_attente, p.cout_manquant), (75, 0, 0))

	# ------------------------------------------------------------------ fraîcheur
	def _valider(self, doc):
		doc = apply_workflow(frappe.get_doc("EFT", doc.name), "Chiffrer")
		return apply_workflow(frappe.get_doc("EFT", doc.name), "Valider")

	def test_recalcul_en_brouillon_sauf_cout_manuel(self):
		doc = self.eft_exemple()
		frappe.db.set_value("Asset", {"asset_name": f"{P} PROJECTEUR GAMMA 2"}, "lsi_cout_journalier", 130)
		self.pos(doc, "1.5").cout_manuel = 1
		self.pos(doc, "1.5").cout_unitaire = 99
		doc.save()
		self.assertEqual(self.pos(doc, "1.9").cout_unitaire, 130)
		self.assertEqual(self.pos(doc, "1.5").cout_unitaire, 99)

	def test_couts_figes_apres_validation(self):
		doc = self._valider(self.eft_exemple())
		self.assertEqual((doc.docstatus, doc.workflow_state), (1, "Validée"))
		frappe.db.set_value("Asset", {"asset_name": f"{P} PROJECTEUR GAMMA 2"}, "lsi_cout_journalier", 130)
		doc = frappe.get_doc("EFT", doc.name)
		self.assertEqual(self.pos(doc, "1.9").cout_unitaire, max(CATEGORIES["PROJECTEUR GAMMA"]))

	def test_dupliquer_et_amend_recalculent(self):
		doc = self._valider(self.eft_exemple())
		frappe.db.set_value("Asset", {"asset_name": f"{P} PROJECTEUR GAMMA 2"}, "lsi_cout_journalier", 130)
		copie = frappe.copy_doc(doc, ignore_no_copy=False)  # comme « Dupliquer » dans l'interface (brouillon, sans les champs non copiés)
		copie.docstatus = 0
		copie.insert()
		self.assertEqual(self.pos(copie, "1.9").cout_unitaire, 130)
		doc = apply_workflow(frappe.get_doc("EFT", doc.name), "Annuler")
		amende = frappe.copy_doc(doc, ignore_no_copy=False)  # comme « Amender » dans l'interface
		amende.docstatus = 0
		amende.amended_from = doc.name
		amende.insert()
		self.assertEqual(frappe.db.get_value("EFT", amende.name, "amended_from"), doc.name)  # version d'origine tracée
		self.assertEqual(self.pos(amende, "1.9").cout_unitaire, 130)

	# ------------------------------------------------------------------ gammes, modèles, prorata
	def test_gamme_fois_quantite(self):
		rt = ETAPES["Contrôle par Radiographie (RT)"]
		lignes = [l for l in lire_projet() if l["pos"].startswith("1.")]
		frappe.get_doc(dict(doctype="Gamme", prestation=rt, titre_groupe="Contrôle par Radiographie (Vacation)", actif=1, lignes=[
			dict(numero=l["pos"][2:], parente=l["pos"][2:].rsplit(".", 1)[0] if l["pos"].count(".") == 2 else None, type_position=TYPES[l["type"]],
				item_code=article(l["d1"]), qty=l["qty"], uom=l["uom"]) for l in lignes])).insert()
		doc = frappe.get_doc(dict(doctype="EFT", titre=f"{P} gamme", company=self.company, etapes=[dict(prestation=rt, qty=2)])).insert()
		self.assertEqual([g.titre for g in doc.groupes], ["Contrôle par Radiographie (Vacation)"])
		self.assertEqual([p.numero for p in doc.positions], [l["pos"] for l in lignes])
		self.assertEqual(self.pos(doc, "1.17").qty, 6)  # 3 × 2
		self.assertEqual(self.pos(doc, "1.17.1").qty, 2)
		self.assertEqual(self.pos(doc, "1.2").qty, 0)  # tarif : reste à 0
		self.assertTrue(doc.etapes[0].gamme_appliquee)
		doc.save()
		self.assertEqual(len(doc.groupes), 1)  # la gamme ne s'applique qu'une fois

	def test_modele_sans_couts_et_chargement(self):
		doc = self.eft_exemple()
		m = frappe.get_doc("Modele EFT", moteur.enregistrer_modele(doc.name, f"{P} modèle"))
		self.assertEqual(len(m.positions), 33)
		self.assertFalse(any(flt(p.cout_unitaire) or flt(p.prix_unitaire) or p.ressource for p in m.positions))
		cible = frappe.get_doc(dict(doctype="EFT", titre=f"{P} cible", company=self.company)).insert()
		moteur.charger_modele(cible.name, m.name)
		cible = frappe.get_doc("EFT", cible.name)
		self.assertEqual(len(cible.positions), 33)
		self.assertEqual(self.pos(cible, "1.1").cout_unitaire, max(DESIGNATIONS["Inspecteur RT niveau II"]))  # recalcul immédiat

	def test_repartir_au_prorata(self):
		doc = self.eft_exemple()
		self.pos(doc, "1.17").qty = 6
		doc.save()
		moteur.repartir_prorata(doc.name, "1.17")
		doc = frappe.get_doc("EFT", doc.name)
		self.assertEqual([self.pos(doc, n).qty for n in ("1.17.1", "1.17.2", "1.17.3")], [2, 2, 2])

	def test_structure_invalide(self):
		doc = self.eft_exemple()
		self.pos(doc, "1.18").parente = "1.1"  # parente non prix fixe
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	# ------------------------------------------------------------------ devis
	def test_devis_positions_vendues_seulement(self):
		doc = self._valider(self.eft_exemple())
		q = frappe.get_doc("Quotation", moteur.creer_devis(doc.name))
		vendues = [p for p in doc.positions if not p.parente]
		self.assertEqual([i.lsi_numero_position for i in q.items], [p.numero for p in vendues])
		self.assertFalse([i for i in q.items if i.lsi_numero_position.count(".") == 2])  # aucune sous-position
		self.assertEqual(q.lsi_eft, doc.name)
		tarif = next(i for i in q.items if i.lsi_numero_position == "1.2")
		self.assertEqual((tarif.qty, tarif.rate, tarif.amount, tarif.lsi_tarif), (0, PRIX["1.2"], 0, 1))
		self.assertAlmostEqual(q.net_total, doc.total_prix, 2)
		self.assertEqual(next(i for i in q.items if i.lsi_numero_position == "4.1").lsi_groupe_titre, "Transport & Indemnité")
		html = frappe.get_print("Quotation", q.name, print_format="Devis groupe", doc=q)
		self.assertIn("Transport &amp; Indemnité", html.replace("Transport & Indemnité", "Transport &amp; Indemnité"))
		self.assertIn("Sous-total", html)
		self.assertNotIn("FILM MX125", html)

	def test_devis_refuse_si_quantite_zero_non_autorisee(self):
		doc = self._valider(self.eft_exemple())
		frappe.db.set_single_value("Selling Settings", "allow_zero_qty_in_quotation", 0)
		with self.assertRaises(frappe.ValidationError):
			moteur.creer_devis(doc.name)

	# ------------------------------------------------------------------ droits, rapport, événements
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
		from lsi_inspection.chiffrage.report.besoins_eft.besoins_eft import besoins

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
		eft = moteur.make_eft(o.name)
		o = self.recharger(o)
		self.assertEqual(o.sales_stage, "T Chiffrage")
		self.assertEqual(o.lsi_historique_phases[-1].document_name, eft)
