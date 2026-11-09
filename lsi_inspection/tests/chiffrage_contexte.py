"""Contexte des tests du chiffrage : configuration et données propres aux tests (transaction annulée), construites à partir de la
référence métier docs/references/exemple_projet.csv (feuille Projet). Aucune dépendance au profil TIC ni au jeu DÉMO."""

import os

import frappe
from frappe.utils import flt

from lsi_inspection.tests.contexte import PREFIXE, TestLot2

P = PREFIXE
CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "docs", "references", "exemple_projet.csv")

# types de position de l'exemple → types de test
TYPES = {
	"Service à côut": f"{P} Service à coût", "Article à côut": f"{P} Article à coût",
	"Durée de l'équipement à coût": f"{P} Équipement à coût", "Sous-traitance à coût": f"{P} Sous-traitance à coût",
	"Prix fixe": f"{P} Prix fixe", "Article de la position à prix fixe": f"{P} Article de la position",
	"Service de la position à prix fixe": f"{P} Service de la position",
}
ETAPES = {"Contrôle par Radiographie (RT)": f"{P} RT", "Approbation d'un DMOS": f"{P} DMOS",
	"Découpages et Essais Mécaniques": f"{P} Découpage", "Contrôle réglementaire des installations électriques Sfax": f"{P} Électricité"}
PARTAGE = ["Contrôle par Radiographie (RT)", "Découpages et Essais Mécaniques"]  # « 2 sélectionné » (en attendant TIC)
UNITES = {"Jour": "Jour", "Jours": "Jour", "jour": "Jour", "Heure": "Heure", "Unité": "Unité", "Kilomètre": "Kilometer"}
# pools : désignation / catégorie d'actif → coûts journaliers posés par le test
DESIGNATIONS = {"Inspecteur RT niveau II": [200, 250], "Assistant RT": [120, 150], "Expert en soudage": [400], "Inspecteur agréé B2": [320, 360]}
CATEGORIES = {"PROJECTEUR GAMMA": [80, 100], "VEHICULE": [60], "CARTE CARBURANT": [40], "APPAREIL PHOTO": [10],
	"CONTRÔLEUR D'INSTALLATION ÉLECTRIQUE": [25]}
POOL_DESIGNATION = {"Rédaction rapport": "Inspecteur agréé B2"}  # 5.1.2 : pool Inspecteur agréé B2
ARTICLES = {"Heure supplémentaire Inspecteur": 30, "Heure supplémentaire Assistant": 20, "FILM MX125 RECHARGEABLE 10/40": 12,
	"FILM FUJIFILM RECHARGEABLE IX100 10/40": 15, "FILM FUJIFILM STANDARD IX100 10/40": 10, "EMBOUT TEST/MDS TIF/TSI": 5, "CASSETTE FILM 10/40": 8,
	"Indemnité d'hébergement": 60, "Indemnité de Repas": 15, "Frais kilométriques": 0.5, "Frais de Péage": 4, "Indemnités kilométriques": 0.5}
SOUS_TRAITANCE = {"Usinage de traction": [90, 110], "Essai De Traction": []}
PRIX = {"1.1": 450, "1.2": 520, "1.3": 560, "1.4": 45, "1.5": 250, "1.6": 300, "1.7": 320, "1.8": 30, "1.9": 180, "1.17": 25,
	"1.18": 10, "1.19": 14, "2.1": 1500, "3.1": 160, "3.2": 140, "4.1": 110, "4.2": 70, "4.3": 90, "4.4": 25, "4.5": 0.9, "4.6": 6,
	"5.1": 900, "5.2": 30, "5.3": 60}


def lire_projet():
	"""Lignes de la feuille Projet : dict(pos, type, d1, d2, qty, uom, etape) ; en-têtes de groupe avec type « En-tête groupe »."""
	lignes, dans = [], False
	with open(CSV, encoding="utf-8") as f:
		for brut in f:
			brut = brut.rstrip("\n")
			if brut.startswith("###"):
				dans = brut.strip() == "### Projet"
				continue
			if not dans or not brut or brut.startswith("Pos;"):
				continue
			c = (brut.split(";") + [""] * 10)[:10]
			if c[1] == "Sous-total groupe":
				continue
			lignes.append(dict(pos=c[0].strip(), type=c[1].strip(), d1=c[2].strip(), d2=c[3].strip(), qty=flt(c[4]) if c[4] else 0,
				uom=UNITES.get(c[5].strip(), c[5].strip()), etape=c[9].strip()))
	return lignes


def article(d1):
	return f"{P} {d1}"


class TestChiffrageBase(TestLot2):
	def setUp(self):
		super().setUp()
		self.construire()

	# ------------------------------------------------------------------ configuration et données de test
	def construire(self):
		"""Configuration et données du test : types de position, groupe et liste d'achat, ressources (employés, immobilisations),
		fournisseurs, articles de l'exemple."""
		self._types_de_test()
		self._groupe_et_liste()
		self._ressources()
		self._articles_exemple()

	def _types_de_test(self):
		frappe.db.set_single_value("Selling Settings", "allow_zero_qty_in_quotation", 1)
		if not frappe.db.exists("UOM Conversion Factor", {"from_uom": "Jour", "to_uom": "Heure"}):
			frappe.get_doc(dict(doctype="UOM Conversion Factor", category="Temps", from_uom="Jour", to_uom="Heure", value=8)).insert()
		pool_emp = dict(source_cout="Pool de ressources", pool_doctype="Designation", ressource_doctype="Employee",
			champ_appartenance="designation", champ_cout="lsi_cout_journalier", uom_cout="Jour", filtres_ressources='{"status": "Active"}')
		pool_actif = dict(source_cout="Pool de ressources", pool_doctype="Asset Category", ressource_doctype="Asset",
			champ_appartenance="asset_category", champ_cout="lsi_cout_journalier", uom_cout="Jour", filtres_ressources='{"docstatus": ["<", 2]}')
		for cle, nom in TYPES.items():
			v = dict(mode="À coût", source_cout="Article", regle="Plus élevé")
			if cle.startswith("Service"):
				v.update(pool_emp)
			if cle.startswith("Durée"):
				v.update(pool_actif)
			if cle.startswith("Sous-traitance"):
				v["source_cout"] = "Prix fournisseur"
			if cle == "Prix fixe":
				v.update(mode="Prix fixe", source_cout="Somme des sous-positions")
			if "de la position" in cle:
				v["mode"] = "Sous-position"
			frappe.get_doc(dict(doctype="Type Position", libelle=nom, actif=1, **v)).insert()

	def _groupe_et_liste(self):
		racine = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("in", ["", None])})
		self.groupe = frappe.get_doc(dict(doctype="Item Group", item_group_name=f"{P} Groupe", parent_item_group=racine, is_group=0,
			lsi_source_cout="Liste de prix d'achat", lsi_marge_cible=30)).insert().name
		self.liste = frappe.db.get_single_value("Buying Settings", "buying_price_list")

	def _ressources(self):
		company = self.company
		self.employes, self.actifs = {}, {}
		genre = frappe.get_all("Gender", pluck="name", limit=1)[0]
		for d, couts in DESIGNATIONS.items():
			nom = f"{P} {d}"
			frappe.get_doc(dict(doctype="Designation", designation_name=nom)).insert()
			for i, cout in enumerate(couts, 1):
				e = frappe.get_doc(dict(doctype="Employee", first_name=P, last_name=f"{d} {i}", gender=genre, date_of_birth="1985-01-01",
					date_of_joining="2020-01-01", company=company, designation=nom, status="Active", lsi_cout_journalier=cout)).insert()
				self.employes.setdefault(d, []).append(e.name)
		compte = frappe.get_all("Account", filters={"account_type": "Fixed Asset", "is_group": 0, "company": company}, pluck="name", limit=1)[0]
		lieu = frappe.get_doc(dict(doctype="Location", location_name=f"{P} Dépôt")).insert().name
		for cat, couts in CATEGORIES.items():
			nom = f"{P} {cat}"
			frappe.get_doc(dict(doctype="Asset Category", asset_category_name=nom, accounts=[dict(company_name=company, fixed_asset_account=compte)])).insert()
			mat = self.item(f"{P} Matériel {cat}", "Unité", is_fixed_asset=1, asset_category=nom)
			for i, cout in enumerate(couts, 1):
				a = frappe.get_doc(dict(doctype="Asset", asset_name=f"{nom} {i}", item_code=mat, asset_category=nom, company=company, location=lieu,
					purchase_date="2024-01-01", available_for_use_date="2024-01-01", gross_purchase_amount=1000, is_existing_asset=1,
					calculate_depreciation=0, lsi_cout_journalier=cout)).insert()
				self.actifs.setdefault(cat, []).append(a.name)

	def _articles_exemple(self):
		groupe_fournisseurs = frappe.get_all("Supplier Group", pluck="name", limit=1)[0]
		self.fournisseurs = []
		for i in range(1, 4):
			self.fournisseurs.append(frappe.get_doc(dict(doctype="Supplier", supplier_name=f"{P} Fournisseur {i}",
				supplier_group=groupe_fournisseurs)).insert().name)
		for e in ETAPES.values():
			self.item(e, "Unité")
		for l in lire_projet():
			if l["type"] == "En-tête groupe" or frappe.db.exists("Item", article(l["d1"])):
				continue
			d1 = l["d1"]
			if l["type"].startswith("Service"):
				pool = POOL_DESIGNATION.get(d1) or next(k for k in DESIGNATIONS if d1.startswith(k))
				self.item(article(d1), "Jour", lsi_pool_doctype="Designation", lsi_pool=f"{P} {pool}")
			elif l["type"].startswith("Durée"):
				self.item(article(d1), "Jour", lsi_pool_doctype="Asset Category", lsi_pool=f"{P} {d1}")
			elif d1 in ARTICLES:
				self.item(article(d1), l["uom"] or "Unité")
				frappe.get_doc(dict(doctype="Item Price", item_code=article(d1), price_list=self.liste, price_list_rate=ARTICLES[d1],
					uom=l["uom"] or "Unité")).insert()
			elif d1 in SOUS_TRAITANCE:
				self.item(article(d1), "Unité")
				for f, prix in zip(self.fournisseurs, SOUS_TRAITANCE[d1]):
					frappe.get_doc(dict(doctype="Item Price", item_code=article(d1), price_list=self.liste, supplier=f, price_list_rate=prix,
						uom="Unité")).insert()
			else:
				self.item(article(d1), l["uom"] or "Unité")  # article à prix fixe (ligne de facturation)

	def etude(self):
		"""EFT (étude technique) du test : une opportunité minimale et son EFT, créées une fois par test."""
		if not getattr(self, "_etude", None):
			opp = frappe.get_doc(dict(doctype="Opportunity", opportunity_from="Customer", party_name=self.client(), company=self.company)).insert()
			self._etude = frappe.get_doc(dict(doctype="EFT", opportunity=opp.name, company=self.company, customer=self.client())).insert().name
		return self._etude

	def valider_chiffrage(self, doc):
		"""Brouillon → Chiffrée → Validée (workflow natif)."""
		from frappe.model.workflow import apply_workflow

		apply_workflow(frappe.get_doc("Chiffrage", doc.name), "Chiffrer")
		return apply_workflow(frappe.get_doc("Chiffrage", doc.name), "Valider")

	def nouveau_chiffrage(self):
		"""Chiffrage (variante) vide rattaché à l'EFT du test."""
		doc = frappe.new_doc("Chiffrage")
		doc.eft = self.etude()
		return doc

	def item(self, code, uom, **kw):
		if not frappe.db.exists("Item", code):
			frappe.get_doc(dict(doctype="Item", item_code=code, item_name=code, item_group=self.groupe, stock_uom=uom, is_stock_item=0,
				include_item_in_manufacturing=0, **kw)).insert()
		return code

	# ------------------------------------------------------------------ EFT de l'exemple (directement depuis la feuille Projet)
	def eft_exemple(self, prix=True, **kw):
		doc = self.nouveau_chiffrage()
		doc.update(dict(titre=f"{P} exemple", company=self.company, customer=self.client(), **kw))
		for e in ETAPES.values():
			doc.append("etapes", dict(prestation=e, qty=1, gamme_appliquee=1))
		groupe = None
		for l in lire_projet():
			if l["type"] == "En-tête groupe":
				groupe = l["pos"]
				doc.append("groupes", dict(numero=groupe, titre=l["d1"]))
				continue
			parente = l["pos"].rsplit(".", 1)[0] if l["pos"].count(".") == 2 else None
			doc.append("positions", dict(numero=l["pos"], groupe=groupe, parente=parente, type_position=TYPES[l["type"]], item_code=article(l["d1"]),
				designation_2=l["d2"] if l["d2"] not in ("ligne de facturation", "sous position") else None, qty=l["qty"], uom=l["uom"],
				prix_unitaire=PRIX.get(l["pos"], 0) if prix and not parente else 0))
			cibles = PARTAGE if l["etape"] == "2 sélectionné" else [l["etape"]]
			for c in cibles:
				if not any(r.cible == groupe and r.etape == ETAPES[c] for r in doc.repartitions):
					doc.append("repartitions", dict(cible=groupe, etape=ETAPES[c]))
		doc.insert()
		return doc

	# ------------------------------------------------------------------ calcul attendu, indépendant du moteur
	def cout_attendu(self, l):
		d1, uom = l["d1"], l["uom"]
		if l["type"].startswith("Service"):
			pool = POOL_DESIGNATION.get(d1) or next(k for k in DESIGNATIONS if d1.startswith(k))
			jour = max(DESIGNATIONS[pool])
			return jour / 8 if uom == "Heure" else jour
		if l["type"].startswith("Durée"):
			return max(CATEGORIES[d1])
		if d1 in ARTICLES:
			return ARTICLES[d1]
		if d1 in SOUS_TRAITANCE:
			return max(SOUS_TRAITANCE[d1]) if SOUS_TRAITANCE[d1] else 0
		return None  # prix fixe : somme des sous-positions

	def attendus(self):
		"""{pos: (coût total, prix total)}, {groupe: (coût, prix)}, {étape: (coût, prix)} recalculés à partir du CSV."""
		lignes = [l for l in lire_projet() if l["type"] != "En-tête groupe"]
		cout = {}
		for l in lignes:
			cu = self.cout_attendu(l)
			if cu is not None:
				cout[l["pos"]] = cu * l["qty"]
		for l in lignes:
			if l["type"] == "Prix fixe":
				cout[l["pos"]] = sum(v for k, v in cout.items() if k.startswith(l["pos"] + "."))
		positions, groupes, etapes = {}, {}, {}
		for l in lignes:
			if l["pos"].count(".") == 2:
				continue  # sous-position
			ct, pt = cout[l["pos"]], PRIX.get(l["pos"], 0) * l["qty"]
			positions[l["pos"]] = (ct, pt)
			g = l["pos"].split(".")[0]
			gc, gp = groupes.get(g, (0, 0))
			groupes[g] = (gc + ct, gp + pt)
			cibles = PARTAGE if l["etape"] == "2 sélectionné" else [l["etape"]]
			for c in cibles:
				ec, ep = etapes.get(ETAPES[c], (0, 0))
				etapes[ETAPES[c]] = (ec + ct / len(cibles), ep + pt / len(cibles))
		return positions, groupes, etapes

	@staticmethod
	def pos(doc, numero):
		return next(p for p in doc.positions if p.numero == numero)
