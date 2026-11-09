"""Moteur — gammes et modèles (chiffrage/moteur/gammes.py, modeles.py), répartition au prorata."""

import frappe
from frappe.utils import flt

from lsi_inspection.chiffrage import moteur
from lsi_inspection.tests.chiffrage_contexte import article, DESIGNATIONS, ETAPES, lire_projet, TYPES, TestChiffrageBase
from lsi_inspection.tests.contexte import PREFIXE

P = PREFIXE


class TestGammesModeles(TestChiffrageBase):
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
		doc = frappe.get_doc(dict(doctype="Chiffrage", eft=self.etude(), titre=f"{P} gamme", company=self.company, etapes=[dict(prestation=rt, qty=2)])).insert()
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
		doc = frappe.get_doc(dict(doctype="Chiffrage", eft=self.etude(), titre=f"{P} bouton", company=self.company)).insert()
		moteur.ajouter_gamme(doc.name, rt, 1)
		doc = frappe.get_doc("Chiffrage", doc.name)
		principales = [p for p in doc.positions if not p.parente]
		self.assertEqual([p.numero for p in principales], [f"1.{i}" for i in range(1, len(principales) + 1)])  # 1.1 … 1.12
		film = next(p for p in principales if p.item_code == article("Film"))
		sous = [p for p in doc.positions if p.parente == film.numero]
		self.assertEqual([p.numero for p in sous], [f"{film.numero}.{i}" for i in (1, 2, 3)])
		self.assertEqual(film.type_position, TYPES["Prix fixe"])
		self.assertEqual({p.type_position for p in sous}, {TYPES["Article à côut"]})  # déduit du groupe d'articles
		self.assertTrue(all(p.mode == "À coût" for p in sous))  # un type « à coût » sous un prix fixe = sous-position
		self.assertAlmostEqual(film.cout_total, sum(p.cout_total for p in sous), 3)

	def test_modele_sans_couts_et_chargement(self):
		doc = self.eft_exemple()
		m = frappe.get_doc("Modele Chiffrage", moteur.enregistrer_modele(doc.name, f"{P} modèle"))
		self.assertEqual(len(m.positions), 33)
		self.assertFalse(any(flt(p.cout_unitaire) or flt(p.prix_unitaire) or p.ressource for p in m.positions))
		cible = frappe.get_doc(dict(doctype="Chiffrage", eft=self.etude(), titre=f"{P} cible", company=self.company)).insert()
		moteur.charger_modele(cible.name, m.name)
		cible = frappe.get_doc("Chiffrage", cible.name)
		self.assertEqual(len(cible.positions), 33)
		self.assertEqual(self.pos(cible, "1.1").cout_unitaire, max(DESIGNATIONS["Inspecteur RT niveau II"]))  # recalcul immédiat

	def test_repartir_au_prorata(self):
		doc = self.eft_exemple()
		self.pos(doc, "1.17").qty = 6
		doc.save()
		moteur.repartir_prorata(doc.name, "1.17")
		doc = frappe.get_doc("Chiffrage", doc.name)
		self.assertEqual([self.pos(doc, n).qty for n in ("1.17.1", "1.17.2", "1.17.3")], [2, 2, 2])
