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
	def _gamme_rt(self, avec_numeros=True, avec_types=True):
		rt = ETAPES["Contrôle par Radiographie (RT)"]
		lignes = [l for l in lire_projet() if l["pos"].startswith("1.")]
		idx = {l["pos"]: i for i, l in enumerate(lignes, 1)}
		frappe.get_doc(dict(doctype="Gamme", prestation=rt, titre_groupe="Contrôle par Radiographie (Vacation)", actif=1, lignes=[
			dict(numero=l["pos"][2:] if avec_numeros else None, type_position=TYPES[l["type"]] if avec_types else None, item_code=article(l["d1"]),
				parente_ligne=idx[l["pos"].rsplit(".", 1)[0]] if l["pos"].count(".") == 2 else None, qty=l["qty"], uom=l["uom"])
			for l in lignes])).insert()
		return rt, lignes

	def test_gamme_fois_quantite(self):
		rt, lignes = self._gamme_rt()
		doc = frappe.get_doc(dict(doctype="EFT", titre=f"{P} gamme", company=self.company, etapes=[dict(prestation=rt, qty=2)])).insert()
		self.assertEqual([g.titre for g in doc.groupes], ["Contrôle par Radiographie (Vacation)"])
		self.assertEqual([p.numero for p in doc.positions], [l["pos"] for l in lignes])
		self.assertEqual(self.pos(doc, "1.17").qty, 6)  # 3 × 2
		self.assertEqual((self.pos(doc, "1.17.1").qty, self.pos(doc, "1.17.1").parente), (2, "1.17"))
		self.assertEqual(self.pos(doc, "1.2").qty, 0)  # tarif : reste à 0
		self.assertTrue(doc.etapes[0].gamme_appliquee)
		doc.save()
		self.assertEqual(len(doc.groupes), 1)  # la gamme ne s'applique qu'une fois

	def test_ajouter_depuis_une_gamme_numeros_et_types_automatiques(self):
		frappe.db.set_value("Item Group", self.groupe, "lsi_type_position", TYPES["Article à côut"])
		for l in lire_projet():  # type par défaut sur l'article (exception au groupe) pour les services, équipements, prix fixe
			if l["type"] not in ("En-tête groupe", "Article à côut", "Article de la position à prix fixe"):
				frappe.db.set_value("Item", article(l["d1"]), "lsi_type_position", TYPES[l["type"]])
		rt, lignes = self._gamme_rt(avec_numeros=False, avec_types=False)
		doc = frappe.get_doc(dict(doctype="EFT", titre=f"{P} bouton", company=self.company)).insert()
		moteur.ajouter_gamme(doc.name, rt, 1)
		doc = frappe.get_doc("EFT", doc.name)
		principales = [p for p in doc.positions if not p.parente]
		self.assertEqual([p.numero for p in principales], [f"1.{i}" for i in range(1, len(principales) + 1)])  # 1.1 … 1.12
		film = next(p for p in principales if p.item_code == article("Film"))
		sous = [p for p in doc.positions if p.parente == film.numero]
		self.assertEqual([p.numero for p in sous], [f"{film.numero}.{i}" for i in (1, 2, 3)])
		self.assertEqual(film.type_position, TYPES["Prix fixe"])
		self.assertEqual({p.type_position for p in sous}, {TYPES["Article à côut"]})  # déduit du groupe d'articles
		self.assertTrue(all(p.mode == "À coût" for p in sous))  # un type « à coût » sous un prix fixe = sous-position
		self.assertAlmostEqual(film.cout_total, sum(p.cout_total for p in sous), 3)

	def test_position_sans_type_ni_defaut_cout_manquant(self):
		"""Sans type (ni ligne, ni article, ni groupe) : l'EFT s'enregistre, la ligne est en coût manquant (étape 8)."""
		doc = self.eft_exemple()
		self.pos(doc, "1.18").type_position = None
		doc.save()
		p = self.pos(doc, "1.18")
		self.assertTrue(p.cout_manquant)
		self.assertTrue(doc.cout_incomplet)

	def test_valorisation_du_stock_et_stock_disponible(self):
		code = article("FILM MX125 RECHARGEABLE 10/40")
		frappe.db.set_value("Item", code, {"is_stock_item": 1, "lsi_source_cout": "Valorisation"})
		entrepot = frappe.get_all("Warehouse", filters={"company": self.company, "is_group": 0}, pluck="name", limit=1)[0]
		for qty, prix in ((10, 12), (30, 16)):  # moyenne pondérée : (120 + 480) / 40 = 15
			se = frappe.get_doc(dict(doctype="Stock Entry", stock_entry_type="Material Receipt", purpose="Material Receipt", company=self.company,
				items=[dict(item_code=code, qty=qty, basic_rate=prix, t_warehouse=entrepot, uom="Unité", conversion_factor=1)]))
			se.insert()
			se.submit()
		doc = self.eft_exemple()
		p = self.pos(doc, "1.17.1")
		self.assertAlmostEqual(p.cout_unitaire, 15, 3)
		self.assertEqual(p.stock_disponible, 40)
		self.assertEqual(p.source_cout, "Valorisation")

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

	# ------------------------------------------------------------------ calcul en temps réel (aperçu sans enregistrer)
	def test_apercu_identique_a_l_enregistrement(self):
		doc = self.eft_exemple()
		brouillon = doc.as_dict()
		ligne = next(p for p in brouillon["positions"] if p["numero"] == "1.1")
		ligne["qty"] = 3
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertEqual(r["positions"][ligne["name"]]["cout_total"], 3 * max(DESIGNATIONS["Inspecteur RT niveau II"]))
		self.assertEqual(r["positions"][ligne["name"]]["etape_principale"], ETAPES["Contrôle par Radiographie (RT)"])
		self.assertEqual(frappe.db.get_value("EFT Position", ligne["name"], "qty"), 1)  # rien d'enregistré
		self.pos(doc, "1.1").qty = 3
		doc.save()
		self.assertAlmostEqual(r["total_cout"], doc.total_cout, 3)
		self.assertAlmostEqual(r["total_prix"], doc.total_prix, 3)
		self.assertEqual([round(t["cout_total"], 3) for t in r["totaux_etapes"]], [round(t.cout_total, 3) for t in doc.totaux_etapes])

	def test_apercu_erreur_de_structure_sans_planter(self):
		brouillon = self.eft_exemple().as_dict()
		next(p for p in brouillon["positions"] if p["numero"] == "1.18")["parente"] = "1.1"
		self.assertIn("1.18", moteur.apercu(frappe.as_json(brouillon))["erreur"])

	def test_apercu_ligne_a_perte_et_cout_manquant(self):
		brouillon = self.eft_exemple().as_dict()
		ligne = next(p for p in brouillon["positions"] if p["numero"] == "1.1")
		ligne["prix_unitaire"] = 10  # vendu sous le coût
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertLess(r["positions"][ligne["name"]]["marge"], 0)
		essai = next(p for p in brouillon["positions"] if p["numero"] == "3.2")
		self.assertTrue(r["positions"][essai["name"]]["cout_manquant"])

	def test_apercu_ligne_en_cours_de_saisie(self):
		"""Ligne ajoutée sans article (type seul) : l'aperçu ne plante pas, la ligne est en coût manquant."""
		brouillon = self.eft_exemple().as_dict()
		brouillon["positions"].append(dict(doctype="EFT Position", name="new-eft-position-1", __islocal=1, numero=None, groupe="1",
			type_position=TYPES["Article à côut"], parenttype="EFT", parentfield="positions"))
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertNotIn("erreur", r)
		self.assertTrue(r["positions"]["new-eft-position-1"]["cout_manquant"])
		self.assertEqual(r["positions"]["new-eft-position-1"]["source_cout"], "article à choisir")

	# ------------------------------------------------------------------ simplification : on travaille par prestation
	def test_ligne_saisie_par_prestation_groupe_et_numero_automatiques(self):
		doc = self.eft_exemple()
		self.assertEqual(self.pos(doc, "2.1").etape, ETAPES["Approbation d'un DMOS"])  # prestation remplie d'après le groupe
		doc.append("positions", dict(etape=ETAPES["Approbation d'un DMOS"], item_code=article("Expert en soudage"), type_position=TYPES["Service à côut"],
			qty=1, uom="Jour"))
		doc.save()
		nouvelle = doc.positions[-1] if doc.positions[-1].numero == "2.2" else self.pos(doc, "2.2")
		self.assertEqual((nouvelle.groupe, nouvelle.numero, nouvelle.etape), ("2", "2.2", ETAPES["Approbation d'un DMOS"]))
		self.assertEqual(nouvelle.cout_unitaire, max(DESIGNATIONS["Expert en soudage"]))

	def test_sous_position_suit_sa_parente(self):
		doc = self.eft_exemple()
		doc.append("positions", dict(parente="1.17", item_code=article("CASSETTE FILM 10/40"), type_position=TYPES["Article à côut"], qty=1, uom="Unité"))
		doc.save()
		p = self.pos(doc, "1.17.4")
		self.assertEqual((p.groupe, p.etape), ("1", ETAPES["Contrôle par Radiographie (RT)"]))

	def test_prestation_sans_gamme_cree_son_groupe(self):
		rt = ETAPES["Contrôle par Radiographie (RT)"]
		doc = frappe.get_doc(dict(doctype="EFT", titre=f"{P} sans gamme", company=self.company, etapes=[dict(prestation=rt, qty=1)])).insert()
		self.assertEqual([(g.numero, g.titre) for g in doc.groupes], [("1", rt)])
		doc.append("positions", dict(item_code=article("PROJECTEUR GAMMA"), type_position=TYPES["Durée de l'équipement à coût"], qty=2, uom="Jour"))
		doc.save()  # une seule prestation : la ligne y est rattachée
		self.assertEqual((doc.positions[0].numero, doc.positions[0].etape), ("1.1", rt))
		self.assertEqual(doc.totaux_etapes[0].cout_total, 2 * max(CATEGORIES["PROJECTEUR GAMMA"]))

	def test_partager_un_groupe(self):
		doc = self.eft_exemple()
		rt, dmos = ETAPES["Contrôle par Radiographie (RT)"], ETAPES["Approbation d'un DMOS"]
		moteur.partager_groupe(doc.name, "4", frappe.as_json([rt, dmos]))
		doc = frappe.get_doc("EFT", doc.name)
		self.assertEqual(sorted(r.etape for r in doc.repartitions if r.cible == "4"), sorted([rt, dmos]))
		g4 = next(g for g in doc.groupes if g.numero == "4")
		t = {x.etape: x.cout_total for x in doc.totaux_etapes}
		g2 = next(g for g in doc.groupes if g.numero == "2")
		self.assertAlmostEqual(t[dmos], g2.cout_total + g4.cout_total / 2, 3)

	# ------------------------------------------------------------------ BU et Service : opportunité → EFT → devis
	def test_bu_et_service_recopies(self):
		bu = frappe.get_doc(dict(doctype="Branch", branch=f"{P} BU")).insert().name
		service = self.departement(f"{P} SERVICE")
		o = self.opportunite(self.parcours_standard(), lsi_bu=bu, lsi_service=service)
		e = frappe.get_doc("EFT", moteur.make_eft(o.name))
		self.assertEqual((e.bu, e.service), (bu, service))
		doc = self.eft_exemple(bu=bu, service=service)
		doc = self._valider(doc)
		q = frappe.get_doc("Quotation", moteur.creer_devis(doc.name))
		self.assertEqual((q.lsi_bu, q.lsi_service), (bu, service))

	# ------------------------------------------------------------------ consommable chiffré par un pool (groupe d'articles)
	def test_consommable_pool_groupe_d_articles(self):
		"""Ligne facturée « Film » : pool = groupe d'articles « Films » ; coût = dernier prix d'achat le plus élevé du groupe."""
		racine = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("in", ["", None])})
		films = frappe.get_doc(dict(doctype="Item Group", item_group_name=f"{P} Films", parent_item_group=racine, is_group=0)).insert().name
		typ = frappe.get_doc(dict(doctype="Type Position", libelle=f"{P} Consommable pool", actif=1, mode="À coût", source_cout="Pool de ressources",
			pool_doctype="Item Group", ressource_doctype="Item", champ_appartenance="item_group", champ_cout="last_purchase_rate",
			filtres_ressources='{"disabled": 0}', regle="Plus élevé")).insert().name
		ressources = []
		for i, prix in enumerate([10, 15, 20], 1):
			code = f"{P} Film {i}"
			frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=films, stock_uom="Unité", is_stock_item=1,
				include_item_in_manufacturing=0)).insert()
			frappe.db.set_value("Item", code, "last_purchase_rate", prix)  # (normalement mis à jour par les achats)
			ressources.append(code)
		self.item(f"{P} Film RTX", "Unité", lsi_pool_doctype="Item Group", lsi_pool=films)
		doc = frappe.new_doc("EFT")
		doc.update(dict(titre=f"{P} film", company=self.company, customer=self.client()))
		doc.append("etapes", dict(prestation=ETAPES["Contrôle par Radiographie (RT)"], qty=1))
		doc.append("positions", dict(etape=ETAPES["Contrôle par Radiographie (RT)"], item_code=f"{P} Film RTX", type_position=typ, qty=3, uom="Unité",
			prix_unitaire=25))
		doc.insert()
		p = doc.positions[0]
		self.assertEqual((p.cout_unitaire, p.cout_total, p.cout_manquant), (20, 60, 0))
		self.assertIn("Plus élevé", p.source_cout)
		self.assertEqual(sorted(r["name"] for r in moteur.voir_ressources(doc.name, p.numero)["ressources"]), ressources)
		moteur.choisir_ressource(doc.name, p.numero, ressources[0])  # le chiffreur peut retenir un film précis
		self.assertEqual(frappe.get_doc("EFT", doc.name).positions[0].cout_unitaire, 10)

	def test_sous_position_consommable_pool_dans_prix_fixe(self):
		"""Prix fixe = somme ; sa sous-ligne « Film » prend le film le plus cher du groupe, ou celui choisi par l'utilisateur."""
		racine = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("in", ["", None])})
		films = frappe.get_doc(dict(doctype="Item Group", item_group_name=f"{P} Films SP", parent_item_group=racine, is_group=0)).insert().name
		typ = frappe.get_doc(dict(doctype="Type Position", libelle=f"{P} Consommable sous-position pool", actif=1, mode="Sous-position",
			source_cout="Pool de ressources", pool_doctype="Item Group", ressource_doctype="Item", champ_appartenance="item_group",
			champ_cout="last_purchase_rate", filtres_ressources='{"disabled": 0}', regle="Plus élevé")).insert().name
		codes = []
		for i, prix in enumerate([10, 15, 20], 1):
			code = f"{P} Film SP {i}"
			frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=films, stock_uom="Unité", is_stock_item=1,
				include_item_in_manufacturing=0)).insert()
			frappe.db.set_value("Item", code, "last_purchase_rate", prix)
			codes.append(code)
		self.item(f"{P} Film RTX SP", "Unité", lsi_pool_doctype="Item Group", lsi_pool=films)
		doc = self.eft_exemple()
		avant = self.pos(doc, "5.1").cout_total
		doc.append("positions", dict(parente="5.1", item_code=f"{P} Film RTX SP", type_position=typ, qty=2, uom="Unité"))
		doc.save()
		film = next(p for p in doc.positions if p.item_code == f"{P} Film RTX SP")
		self.assertEqual((film.cout_unitaire, film.cout_total), (20, 40))  # le plus élevé par défaut
		self.assertEqual(self.pos(doc, "5.1").cout_total, avant + 40)  # le prix fixe fait toujours la somme
		moteur.choisir_ressource(doc.name, film.numero, codes[0])  # l'utilisateur choisit un autre film
		doc = frappe.get_doc("EFT", doc.name)
		self.assertEqual((self.pos(doc, film.numero).cout_unitaire, self.pos(doc, "5.1").cout_total), (10, avant + 20))

	# ------------------------------------------------------------------ étape 8 : jamais d'exception dans le chiffrage
	def _ligne_seule(self, item_code, type_position, qty=1):
		doc = frappe.new_doc("EFT")
		doc.update(dict(titre=f"{P} robustesse", company=self.company, customer=self.client()))
		doc.append("etapes", dict(prestation=ETAPES["Contrôle par Radiographie (RT)"], qty=1))
		doc.append("positions", dict(etape=ETAPES["Contrôle par Radiographie (RT)"], item_code=item_code, type_position=type_position, qty=qty,
			uom="Unité", prix_unitaire=10))
		return doc

	def _manquant(self, doc, motif):
		r = moteur.apercu(frappe.as_json(doc.as_dict()))
		self.assertNotIn("erreur", r)
		v = next(iter(r["positions"].values()))
		self.assertTrue(v["cout_manquant"])
		self.assertIn(motif, v["source_cout"])
		self.assertTrue(r["cout_incomplet"])

	def test_article_absent_cout_manquant(self):
		"""Cause de l'Error Log du 09/11 00:16 : ligne dont l'article n'existe pas (saisie en cours) → coût manquant."""
		self._manquant(self._ligne_seule(f"{P} article inexistant", TYPES["Article à côut"]), "introuvable")

	def test_article_sans_prix_cout_manquant(self):
		code = self.item(f"{P} Sans prix", "Unité")
		doc = self._ligne_seule(code, TYPES["Article à côut"])
		self._manquant(doc, "aucun coût")
		doc.insert()  # l'enregistrement passe aussi
		self.assertTrue(doc.positions[0].cout_manquant)

	def test_pool_vide_cout_manquant(self):
		frappe.get_doc(dict(doctype="Designation", designation_name=f"{P} Personne")).insert()
		code = self.item(f"{P} Sans ressource", "Jour", lsi_pool_doctype="Designation", lsi_pool=f"{P} Personne")
		self._manquant(self._ligne_seule(code, TYPES["Service à côut"]), "aucune ressource")

	def test_pool_mal_parametre_cout_manquant(self):
		typ = frappe.get_doc(dict(doctype="Type Position", libelle=f"{P} Pool faux", actif=1, mode="À coût", source_cout="Pool de ressources",
			pool_doctype="Designation", ressource_doctype="Employee", champ_appartenance="designation", champ_cout="champ_inexistant",
			regle="Plus élevé")).insert().name
		code = self.item(f"{P} Pool faux", "Jour", lsi_pool_doctype="Designation", lsi_pool=f"{P} Inspecteur RT niveau II")
		self._manquant(self._ligne_seule(code, typ), "non calculable")

	def test_type_absent_cout_manquant(self):
		code = self.item(f"{P} Sans type", "Unité")
		frappe.db.set_value("Item Group", self.groupe, "lsi_type_position", None)
		doc = self._ligne_seule(code, None)
		self._manquant(doc, "type de position à choisir")
		doc.insert()
		self.assertTrue(doc.positions[0].cout_manquant)

	def test_pool_d_articles_source_du_cout_de_chaque_article(self):
		"""Pool d'articles sans champ de coût : chaque film est chiffré selon la source de son groupe (liste de prix d'achat),
		sans achat ni stock ; la ligne prend le plus élevé."""
		racine = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("in", ["", None])})
		films = frappe.get_doc(dict(doctype="Item Group", item_group_name=f"{P} Films LP", parent_item_group=racine, is_group=0,
			lsi_source_cout="Liste de prix d'achat")).insert().name
		typ = frappe.get_doc(dict(doctype="Type Position", libelle=f"{P} Consommable pool LP", actif=1, mode="À coût", source_cout="Pool de ressources",
			pool_doctype="Item Group", ressource_doctype="Item", champ_appartenance="item_group", filtres_ressources='{"disabled": 0}',
			regle="Plus élevé")).insert().name
		for i, prix in enumerate([12, 15, 10], 1):
			code = f"{P} Film LP {i}"
			frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=films, stock_uom="Unité", is_stock_item=1,
				include_item_in_manufacturing=0)).insert()
			frappe.get_doc(dict(doctype="Item Price", item_code=code, price_list=self.liste, price_list_rate=prix, uom="Unité")).insert()
		self.item(f"{P} Film LP", "Unité", lsi_pool_doctype="Item Group", lsi_pool=films)
		doc = self._ligne_seule(f"{P} Film LP", typ, qty=3)
		doc.insert()
		p = doc.positions[0]
		self.assertEqual((p.cout_unitaire, p.cout_total, p.cout_manquant), (15, 45, 0))
		self.assertFalse(frappe.db.exists("Bin", {"item_code": f"{P} Film LP 2"}))  # aucun stock créé
		r = moteur.voir_ressources(doc.name, p.numero)
		self.assertEqual(sorted(x["cout"] for x in r["ressources"]), [10, 12, 15])
