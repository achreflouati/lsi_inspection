"""Moteur — organisation et aperçu (chiffrage/moteur/organisation.py, apercu.py) : groupes et n° automatiques,
numérotation pendant la saisie, calcul en temps réel identique à l'enregistrement."""

import frappe

from lsi_inspection.chiffrage import moteur
from lsi_inspection.tests.chiffrage_contexte import article, CATEGORIES, DESIGNATIONS, ETAPES, TYPES, TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestOrganisation(TestChiffrageBase):
	def test_apercu_identique_a_l_enregistrement(self):
		doc = self.eft_exemple()
		brouillon = doc.as_dict()
		ligne = next(p for p in brouillon["positions"] if p["numero"] == "1.1")
		ligne["qty"] = 3
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertEqual(r["positions"][ligne["name"]]["cout_total"], 3 * max(DESIGNATIONS["Inspecteur RT niveau II"]))
		self.assertEqual(r["positions"][ligne["name"]]["etape_principale"], ETAPES["Contrôle par Radiographie (RT)"])
		self.assertEqual(frappe.db.get_value("Chiffrage Position", ligne["name"], "qty"), 1)  # rien d'enregistré
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
		brouillon["positions"].append(dict(doctype="Chiffrage Position", name="new-eft-position-1", __islocal=1, numero=None, groupe="1",
			type_position=TYPES["Article à côut"], parenttype="Chiffrage", parentfield="positions"))
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertNotIn("erreur", r)
		self.assertTrue(r["positions"]["new-eft-position-1"]["cout_manquant"])
		self.assertEqual(r["positions"]["new-eft-position-1"]["source_cout"], "article à choisir")

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
		doc = frappe.get_doc(dict(doctype="Chiffrage", eft=self.etude(), titre=f"{P} sans gamme", company=self.company, etapes=[dict(prestation=rt, qty=1)])).insert()
		self.assertEqual([(g.numero, g.titre) for g in doc.groupes], [("1", rt)])
		doc.append("positions", dict(item_code=article("PROJECTEUR GAMMA"), type_position=TYPES["Durée de l'équipement à coût"], qty=2, uom="Jour"))
		doc.save()  # une seule prestation : la ligne y est rattachée
		self.assertEqual((doc.positions[0].numero, doc.positions[0].etape), ("1.1", rt))
		self.assertEqual(doc.totaux_etapes[0].cout_total, 2 * max(CATEGORIES["PROJECTEUR GAMMA"]))

	def test_partager_un_groupe(self):
		doc = self.eft_exemple()
		rt, dmos = ETAPES["Contrôle par Radiographie (RT)"], ETAPES["Approbation d'un DMOS"]
		moteur.partager_groupe(doc.name, "4", frappe.as_json([rt, dmos]))
		doc = frappe.get_doc("Chiffrage", doc.name)
		self.assertEqual(sorted(r.etape for r in doc.repartitions if r.cible == "4"), sorted([rt, dmos]))
		g4 = next(g for g in doc.groupes if g.numero == "4")
		t = {x.etape: x.cout_total for x in doc.totaux_etapes}
		g2 = next(g for g in doc.groupes if g.numero == "2")
		self.assertAlmostEqual(t[dmos], g2.cout_total + g4.cout_total / 2, 3)

	def test_apercu_numerote_les_nouvelles_lignes(self):
		"""Ligne prix fixe ajoutée puis sous-ligne : l'aperçu donne les n° (1.20, puis 1.20.1) sans enregistrer."""
		doc = self.eft_exemple()
		brouillon = doc.as_dict()
		brouillon["positions"].append(dict(doctype="Chiffrage Position", name="new-pf", __islocal=1, groupe="1", item_code=article("Film"),
			type_position=TYPES["Prix fixe"], qty=1, uom="Unité", parenttype="Chiffrage", parentfield="positions"))
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertEqual(r["positions"]["new-pf"]["numero"], "1.20")
		brouillon["positions"][-1]["numero"] = "1.20"
		brouillon["positions"].append(dict(doctype="Chiffrage Position", name="new-sp", __islocal=1, parente="1.20",
			item_code=article("FILM MX125 RECHARGEABLE 10/40"), type_position=TYPES["Article de la position à prix fixe"], qty=1, uom="Unité",
			parenttype="Chiffrage", parentfield="positions"))
		r = moteur.apercu(frappe.as_json(brouillon))
		self.assertEqual(r["positions"]["new-sp"]["numero"], "1.20.1")
		self.assertEqual(r["positions"]["new-pf"]["cout_total"], 12)  # somme calculée en direct

	def test_ligne_renumerotee_quand_rattachee_a_une_parente(self):
		"""Ancien défaut : une ligne numérotée 1.20 puis rattachée à 1.17 devient 1.17.4 (et non « 1.20 sous 1.17 »)."""
		doc = self.eft_exemple()
		doc.append("positions", dict(groupe="1", item_code=article("FILM MX125 RECHARGEABLE 10/40"),
			type_position=TYPES["Article de la position à prix fixe"], qty=1, uom="Unité", numero="1.20", parente="1.17"))
		doc.save()
		nouvelle = next(p for p in doc.positions if p.parente == "1.17" and p.numero not in ("1.17.1", "1.17.2", "1.17.3"))
		self.assertEqual(nouvelle.numero, "1.17.4")
