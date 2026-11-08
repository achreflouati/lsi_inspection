"""DÉMO lot 3 — reproduit l'exemple de projet TIC (docs/references/exemple_projet.csv) de bout en bout.

Données de démonstration (hors profil) : articles aux noms de l'exemple, désignations, salariés « DÉMO » (sans compte
utilisateur ni adresse), actifs, fournisseurs et prix, client et opportunité « DÉMO », puis l'EFT avec ses 5 groupes.
Coûts et prix : valeurs DÉMO, en attendant les coûts réels de TIC.

Charger : bench --site tic.erpsys.ovh execute lsi_inspection.demo.lot3.run
Annuler : bench --site tic.erpsys.ovh execute lsi_inspection.demo.lot3.annuler
Chaque création est consignée dans un registre (fichier privé du site) que « annuler » relit dans l'ordre inverse.
"""

import json
import os

import frappe
from frappe.utils import add_days, nowdate

DEMO = "DÉMO lot 3"
MARQUE = f"[{DEMO}]"
ACHAT = "DÉMO Achats chiffrage"
GROUPE = "DÉMO Chiffrage"

# coûts journaliers DÉMO par désignation / catégorie d'actif : deux ressources quand l'exemple doit montrer la règle « plus élevé »
DESIGNATIONS = {"Inspecteur RT niveau II": [200, 250], "Assistant RT": [120, 150], "Expert en soudage": [400], "Inspecteur agréé B2": [320, 360]}
CATEGORIES = {"Projecteur gamma": [80, 100], "Véhicule": [60], "Carte carburant": [40], "Appareil photo": [10],
	"Contrôleur d'installation électrique": [25]}
PRESTATIONS = ["Contrôle par Radiographie (RT)", "Approbation d'un DMOS", "Découpages et Essais Mécaniques",
	"Contrôle réglementaire des installations électriques Sfax"]
# articles vendus au coût d'un pool : (article, unité, doctype du pool, pool)
SERVICES = [
	("Inspecteur RT niveau II", "Jour", "Designation", "Inspecteur RT niveau II"),
	("Inspecteur RT niveau II - Travaux de nuit", "Jour", "Designation", "Inspecteur RT niveau II"),
	("Inspecteur RT niveau II - Dimanche & jour férié", "Jour", "Designation", "Inspecteur RT niveau II"),
	("Assistant RT", "Jour", "Designation", "Assistant RT"),
	("Assistant RT - Travaux de nuit", "Jour", "Designation", "Assistant RT"),
	("Assistant RT - Dimanche & jour férié", "Jour", "Designation", "Assistant RT"),
	("Expert en soudage", "Jour", "Designation", "Expert en soudage"),
	("Inspecteur agréé B2", "Jour", "Designation", "Inspecteur agréé B2"),
	("Rédaction rapport", "Jour", "Designation", "Inspecteur agréé B2"),
	("PROJECTEUR GAMMA", "Jour", "Asset Category", "Projecteur gamma"),
	("VEHICULE", "Jour", "Asset Category", "Véhicule"),
	("CARTE CARBURANT", "Jour", "Asset Category", "Carte carburant"),
	("APPAREIL PHOTO", "Jour", "Asset Category", "Appareil photo"),
	("CONTRÔLEUR D'INSTALLATION ÉLECTRIQUE", "Jour", "Asset Category", "Contrôleur d'installation électrique"),
]
# articles au coût de la liste de prix d'achat : (article, unité, prix d'achat DÉMO)
ARTICLES = [("Heure supplémentaire Inspecteur", "Unité", 30), ("Heure supplémentaire Assistant", "Unité", 20),
	("FILM MX125 RECHARGEABLE 10/40", "Unité", 12), ("FILM FUJIFILM RECHARGEABLE IX100 10/40", "Unité", 15),
	("FILM FUJIFILM STANDARD IX100 10/40", "Unité", 10), ("EMBOUT TEST/MDS TIF/TSI", "Unité", 5), ("CASSETTE FILM 10/40", "Unité", 8),
	("Indemnité d'hébergement", "Unité", 60), ("Indemnité de Repas", "Unité", 15), ("Frais kilométriques", "Kilometer", 0.5),
	("Frais de Péage", "Unité", 4), ("Indemnités kilométriques", "Kilometer", 0.5)]
PRIX_FIXE = [("Film", "Unité"), ("Forfait /DMOS", "Unité"), ("Inspecteur agréé B2 + Transport", "Jour")]
SOUS_TRAITANCE = {"Usinage de traction": [("DÉMO Atelier mécanique A", 90), ("DÉMO Atelier mécanique B", 110)],
	"Essai De Traction": []}  # sans prix : « Demander un prix » (T3.7)
# prix de vente DÉMO (saisis par le commercial dans l'EFT)
PRIX = {"1.1": 450, "1.2": 520, "1.3": 560, "1.4": 45, "1.5": 250, "1.6": 300, "1.7": 320, "1.8": 30, "1.9": 180, "1.17": 25,
	"1.18": 10, "1.19": 14, "2.1": 1500, "3.1": 160, "3.2": 140, "4.1": 110, "4.2": 70, "4.3": 90, "4.4": 25, "4.5": 0.9, "4.6": 6,
	"5.1": 900, "5.2": 30, "5.3": 60}


# ------------------------------------------------------------------ registre
def _registre_chemin():
	return frappe.get_site_path("private", "lsi_demo_lot3.json")


def _registre():
	if os.path.exists(_registre_chemin()):
		with open(_registre_chemin()) as f:
			return json.load(f)
	return []


def _noter(dt, name):
	r = _registre()
	if [dt, name] not in r:
		r.append([dt, name])
		with open(_registre_chemin(), "w") as f:
			json.dump(r, f, ensure_ascii=False, indent=0)


def _creer(dt, name, valeurs, champ_nom=None):
	"""Crée le document s'il n'existe pas (et le consigne) ; sinon le laisse tel quel."""
	if name and frappe.db.exists(dt, name):
		return name
	doc = frappe.get_doc(dict(doctype=dt, **valeurs))
	doc.flags.ignore_permissions = True
	doc.insert(set_name=name) if name and not champ_nom else doc.insert()
	_noter(dt, doc.name)
	return doc.name


# ------------------------------------------------------------------ données de base
def _base():
	company = frappe.defaults.get_global_default("company")
	compte = frappe.get_all("Account", filters={"account_type": "Fixed Asset", "is_group": 0, "company": company}, pluck="name", limit=1)
	racine = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("in", ["", None])})
	_creer("Item Group", GROUPE, dict(item_group_name=GROUPE, parent_item_group=racine, is_group=0, lsi_source_cout="Liste de prix d'achat",
		lsi_marge_cible=30))
	if not frappe.db.get_single_value("Buying Settings", "buying_price_list"):  # liste d'achat par défaut : réglage natif
		_creer("Price List", ACHAT, dict(price_list_name=ACHAT, buying=1, selling=0, currency=frappe.db.get_value("Company", company, "default_currency")))
		frappe.db.set_single_value("Buying Settings", "buying_price_list", ACHAT)
	liste = frappe.db.get_single_value("Buying Settings", "buying_price_list")
	location = _creer("Location", "DÉMO Dépôt", dict(location_name="DÉMO Dépôt"))
	genre = frappe.get_all("Gender", pluck="name", limit=1)[0]

	for d, couts in DESIGNATIONS.items():
		_creer("Designation", d, dict(designation_name=d, description=MARQUE))
		for i, cout in enumerate(couts, 1):
			nom = f"DÉMO {d} {i}"
			if not frappe.db.exists("Employee", {"employee_name": nom}):
				e = frappe.get_doc(dict(doctype="Employee", first_name="DÉMO", last_name=f"{d} {i}", gender=genre, date_of_birth="1985-01-01",
					date_of_joining="2020-01-01", company=company, designation=d, status="Active", lsi_cout_journalier=cout))
				e.flags.ignore_permissions = True
				e.insert()
				_noter("Employee", e.name)
	for cat, couts in CATEGORIES.items():
		_creer("Asset Category", cat, dict(asset_category_name=cat, accounts=[dict(company_name=company, fixed_asset_account=compte[0])]))
		materiel = f"DÉMO Matériel {cat}"
		_creer("Item", materiel, dict(item_code=materiel, item_name=materiel, item_group=GROUPE, stock_uom="Unité", is_stock_item=0,
			is_fixed_asset=1, asset_category=cat, description=MARQUE))
		for i, cout in enumerate(couts, 1):
			nom = f"DÉMO {cat} {i}"
			if not frappe.db.exists("Asset", {"asset_name": nom}):
				a = frappe.get_doc(dict(doctype="Asset", asset_name=nom, item_code=materiel, asset_category=cat, company=company, location=location,
					purchase_date="2024-01-01", available_for_use_date="2024-01-01", gross_purchase_amount=1000, is_existing_asset=1,
					calculate_depreciation=0, lsi_cout_journalier=cout))
				a.flags.ignore_permissions = True
				a.insert()
				_noter("Asset", a.name)

	def article(code, uom, **kw):
		return _creer("Item", code, dict(item_code=code, item_name=code, item_group=GROUPE, stock_uom=uom, is_stock_item=0,
			include_item_in_manufacturing=0, description=MARQUE, **kw))

	for p in PRESTATIONS:
		article(p, "Unité")
	for code, uom, pool_dt, pool in SERVICES:
		article(code, uom, lsi_pool_doctype=pool_dt, lsi_pool=pool)
	for code, uom in PRIX_FIXE:
		article(code, uom)
	for code, uom, prix in ARTICLES:
		article(code, uom)
		if not frappe.db.exists("Item Price", {"item_code": code, "price_list": liste}):
			_creer("Item Price", None, dict(item_code=code, price_list=liste, price_list_rate=prix, uom=uom), champ_nom=True)
	for code, prix_fournisseurs in SOUS_TRAITANCE.items():
		article(code, "Unité")
		for fournisseur, prix in prix_fournisseurs:
			_creer("Supplier", fournisseur, dict(supplier_name=fournisseur, supplier_group=frappe.get_all("Supplier Group", pluck="name", limit=1)[0]))
			if not frappe.db.exists("Item Price", {"item_code": code, "supplier": fournisseur}):
				_creer("Item Price", None, dict(item_code=code, price_list=liste, supplier=fournisseur, price_list_rate=prix, uom="Unité"), champ_nom=True)
	for fournisseur in ("DÉMO Laboratoire d'essais",):  # pour la demande de prix (T3.7)
		_creer("Supplier", fournisseur, dict(supplier_name=fournisseur, supplier_group=frappe.get_all("Supplier Group", pluck="name", limit=1)[0]))
	return company


# ------------------------------------------------------------------ scénario
def run():
	frappe.flags.mute_emails = True
	company = _base()
	from lsi_inspection import config

	config.charger()  # les gammes en attente (articles absents) sont maintenant insérées
	client = _creer("Customer", "DÉMO Client lot 3", dict(customer_name="DÉMO Client lot 3", customer_type="Company",
		customer_group=frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name")[0],
		territory=frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")[0]))
	opp = frappe.db.get_value("Opportunity", {"party_name": client, "title": DEMO})
	if not opp:
		o = frappe.get_doc(dict(doctype="Opportunity", opportunity_from="Customer", party_name=client, title=DEMO, company=company,
			opportunity_type=frappe.db.get_value("Opportunity Type", {"lsi_parcours_defaut": 1}),
			items=[dict(item_code=p, qty=1, rate=0) for p in PRESTATIONS]))
		o.flags.ignore_permissions = True
		o.insert()
		_noter("Opportunity", o.name)
		opp = o.name
	eft = frappe.db.get_value("EFT", {"opportunity": opp, "docstatus": ("<", 2)})
	if not eft:
		from lsi_inspection.chiffrage import moteur

		# ordre de l'exemple : groupes 1-3 (gammes), 4 = Transport & Indemnité (modèle, partagé RT + Découpage), 5 = Électricité Sfax
		e = frappe.get_doc(dict(doctype="EFT", titre=f"{DEMO} — exemple de projet TIC", opportunity=opp, customer=client, company=company,
			etapes=[dict(prestation=p, qty=1) for p in PRESTATIONS[:3]]))
		e.flags.ignore_permissions = True
		e.insert()
		_noter("EFT", e.name)
		moteur.charger_modele(e.name, "Transport & Indemnité")
		e = frappe.get_doc("EFT", e.name)
		e.append("etapes", dict(prestation=PRESTATIONS[3], qty=1))
		for r in [r for r in e.repartitions if r.cible == "4"]:
			e.remove(r)
		e.append("repartitions", dict(cible="4", etape=PRESTATIONS[0]))
		e.append("repartitions", dict(cible="4", etape=PRESTATIONS[2]))
		e.save(ignore_permissions=True)
		for p in e.positions:
			if not p.parente and p.numero in PRIX:
				p.prix_unitaire = PRIX[p.numero]
		e.save(ignore_permissions=True)
		eft = e.name
	frappe.db.commit()
	e = frappe.get_doc("EFT", eft)
	print(f"{DEMO} : opportunité {opp}, EFT {eft} — {len(e.groupes)} groupes, {len(e.positions)} positions ; "
		f"coût {e.total_cout:.3f}, prix {e.total_prix:.3f}, marge {e.taux_marge:.1f} %, coût incomplet : {e.cout_incomplet}")
	for t in e.totaux_etapes:
		print(f"  étape {t.etape} : coût {t.cout_total:.3f}, prix {t.prix_total:.3f}")
	return eft


def annuler():
	"""Supprime tout ce que la démo a créé (registre, ordre inverse), avec les documents qui en dépendent (EFT, devis, demandes de prix)."""
	frappe.flags.mute_emails = True
	reg = _registre()
	efts = [n for dt, n in reg if dt == "EFT"]
	opps = [n for dt, n in reg if dt == "Opportunity"]
	efts += frappe.get_all("EFT", filters={"opportunity": ("in", opps or [""])}, pluck="name")
	dependants = []
	for dt, champ, valeurs in (("Quotation", "lsi_eft", efts), ("Quotation", "opportunity", opps), ("Request for Quotation", "lsi_eft", efts)):
		dependants += [(dt, n) for n in frappe.get_all(dt, filters={champ: ("in", valeurs or [""])}, pluck="name")]
	for rfq in [n for dt, n in dependants if dt == "Request for Quotation"]:
		dependants += [("Supplier Quotation", n) for n in frappe.get_all("Supplier Quotation Item", filters={"request_for_quotation": rfq},
			pluck="parent", distinct=True)]
	dependants += [("Modele EFT", n) for n in frappe.get_all("Modele EFT", filters={"titre": ("like", f"{DEMO}%")}, pluck="name")]
	articles = [n for dt, n in reg if dt == "Item"]
	gammes = [("Gamme", n) for n in frappe.get_all("Gamme", filters={"prestation": ("in", articles or [""])}, pluck="name")]
	n = 0
	for dt, name in list(dict.fromkeys(dependants)) + [("EFT", x) for x in sorted(set(efts), reverse=True)] + gammes + list(reversed(reg)):
		if not frappe.db.exists(dt, name):
			continue
		doc = frappe.get_doc(dt, name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
		n += 1
	if os.path.exists(_registre_chemin()):
		os.remove(_registre_chemin())
	frappe.db.commit()
	print(f"« {DEMO} » retirée : {n} document(s) supprimé(s)")
	return n
