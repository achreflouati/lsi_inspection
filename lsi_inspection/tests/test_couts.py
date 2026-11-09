"""Moteur — coûts d'une ligne (chiffrage/moteur/couts.py) : pools, règles, conversions, article, fournisseur, prix fixe
« règle », coût manquant sans exception."""

import frappe

from lsi_inspection.chiffrage import moteur
from lsi_inspection.constants import REGLE_SOUS
from lsi_inspection.tests.chiffrage_contexte import article, CATEGORIES, DESIGNATIONS, ETAPES, TYPES, TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestCouts(TestChiffrageBase):
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
		p = self.pos(frappe.get_doc("Chiffrage", doc.name), "1.1")
		self.assertEqual((p.cout_unitaire, p.ressource), (DESIGNATIONS["Inspecteur RT niveau II"][0], moins_cher))
		self.assertIn(moins_cher, p.source_cout)
		moteur.choisir_ressource(doc.name, "1.1", None)  # retour à la règle du pool
		self.assertEqual(self.pos(frappe.get_doc("Chiffrage", doc.name), "1.1").cout_unitaire, max(DESIGNATIONS["Inspecteur RT niveau II"]))

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

	def test_cout_en_attente_puis_offre_fournisseur(self):
		from erpnext.buying.doctype.request_for_quotation.request_for_quotation import make_supplier_quotation_from_rfq

		doc = self.eft_exemple()
		rfq_name = moteur.demander_prix(doc.name, "3.2", frappe.as_json([self.fournisseurs[2]]))
		p = self.pos(frappe.get_doc("Chiffrage", doc.name), "3.2")
		self.assertEqual((p.demande_prix, p.cout_en_attente, p.cout_manquant), (rfq_name, 1, 0))
		rfq = frappe.get_doc("Request for Quotation", rfq_name)
		self.assertEqual(rfq.lsi_chiffrage, doc.name)
		for s in rfq.suppliers:
			s.send_email = 0
		rfq.save()
		rfq.submit()
		sq = make_supplier_quotation_from_rfq(rfq_name, for_supplier=self.fournisseurs[2])
		for it in sq.items:
			it.rate = 75
		sq.insert()
		sq.submit()  # hook : l'EFT (brouillon) est recalculée
		p = self.pos(frappe.get_doc("Chiffrage", doc.name), "3.2")
		self.assertEqual((p.cout_unitaire, p.cout_en_attente, p.cout_manquant), (75, 0, 0))

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
		doc = self.nouveau_chiffrage()
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
		self.assertEqual(frappe.get_doc("Chiffrage", doc.name).positions[0].cout_unitaire, 10)

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
		doc = frappe.get_doc("Chiffrage", doc.name)
		self.assertEqual((self.pos(doc, film.numero).cout_unitaire, self.pos(doc, "5.1").cout_total), (10, avant + 20))

	def _ligne_seule(self, item_code, type_position, qty=1):
		doc = self.nouveau_chiffrage()
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

	def _film_max(self, regle="Plus élevé"):
		typ = frappe.get_doc(dict(doctype="Type Position", libelle=f"{P} Prix fixe max", actif=1, mode="Prix fixe",
			source_cout=REGLE_SOUS, regle=regle)).insert().name
		doc = self.eft_exemple()
		self.pos(doc, "1.17").type_position = typ  # Film (3) : films 12, 15, 10
		doc.save()
		return doc, typ

	def test_prix_fixe_le_plus_eleve_par_defaut(self):
		doc, _typ = self._film_max()
		film = self.pos(doc, "1.17")
		self.assertEqual((film.cout_unitaire, film.cout_total, film.cout_manquant), (15, 45, 0))
		self.assertEqual([self.pos(doc, n).cout_unitaire for n in ("1.17.1", "1.17.2", "1.17.3")], [12, 15, 10])  # coûts réels gardés
		self.assertIn("Plus élevé", film.source_cout)

	def test_prix_fixe_sous_ligne_retenue(self):
		doc, _typ = self._film_max()
		self.pos(doc, "1.17.1").retenue = 1  # l'utilisateur choisit le film à 12
		doc.save()
		self.assertEqual(self.pos(doc, "1.17").cout_total, 36)
		self.assertIn("retenue", self.pos(doc, "1.17").source_cout)
		self.pos(doc, "1.17.3").retenue = 1  # deux cochées : une seule est gardée
		doc.save()
		self.assertEqual(sum(1 for n in ("1.17.1", "1.17.2", "1.17.3") if self.pos(doc, n).retenue), 1)

	def test_prix_fixe_cout_manuel_et_regle(self):
		doc, typ = self._film_max()
		film = self.pos(doc, "1.17")
		film.cout_manuel, film.cout_unitaire = 1, 20
		doc.save()
		self.assertEqual(self.pos(doc, "1.17").cout_total, 60)
		self.pos(doc, "1.17").cout_manuel = 0
		frappe.db.set_value("Type Position", typ, "regle", "Moins élevé")
		doc.save()
		self.assertEqual(self.pos(doc, "1.17").cout_total, 30)

	def test_prix_fixe_le_plus_eleve_besoins(self):
		from lsi_inspection.chiffrage.report.besoins_chiffrage.besoins_chiffrage import besoins
		doc, _typ = self._film_max()
		films = {l["ressource"]: l["quantite"] for l in besoins(doc) if "FILM" in (l["ressource"] or "") and "CASSETTE" not in l["ressource"]}
		self.assertEqual(films, {article("FILM FUJIFILM RECHARGEABLE IX100 10/40"): 3})  # seul le film retenu, × 3
