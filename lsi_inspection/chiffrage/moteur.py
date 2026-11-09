"""Moteur générique de chiffrage de l'EFT. Aucune valeur métier : tout vient de la configuration et des fiches natives.

- Type Position (configuration) : mode (À coût / Prix fixe / Sous-position) et source du coût :
  * Pool de ressources : l'article vendu porte son pool (Item.lsi_pool_doctype / lsi_pool) ; ressources = doctype configuré
    (ex. Employee, Asset) appartenant au pool par le champ configuré, filtrées ; coût = champ configuré, règle du type
    (Plus élevé / Moins élevé / Moyenne) ou ressource choisie ; conversion d'unité par UOM Conversion Factor (natif) ;
  * Article : dernier prix d'achat, valorisation ou liste de prix d'achat (Buying Settings) — choisi sur l'article ou son groupe ;
  * Prix fournisseur : prix d'achat par fournisseur (Item Price) et offres fournisseurs validées ; sinon « coût en attente » si
    une demande de prix existe ;
  * Somme des sous-positions (prix fixe) ; Manuel.
- Position vendue = sans parente ; sous-position = parente (position à prix fixe) : coût seulement, jamais vendue.
- Ligne à quantité 0 = tarif annoncé : prix unitaire affiché, total 0, hors totaux.
- Brouillon : recalcul à chaque enregistrement (sauf coût manuel) ; soumise : coûts figés ; amend / dupliquer : recalcul.
- Totaux par groupe, par étape (répartition : parts indiquées, sinon parts égales) et pour l'EFT. « Coût manquant » si aucun
  coût n'est trouvé : jamais compté silencieusement à 0.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate

A_COUT, PRIX_FIXE, SOUS_POSITION = "À coût", "Prix fixe", "Sous-position"
POOL, ARTICLE, FOURNISSEUR, SOMME, MANUEL = "Pool de ressources", "Article", "Prix fournisseur", "Somme des sous-positions", "Manuel"
DERNIER_PRIX, VALORISATION, LISTE_PRIX = "Dernier prix d'achat", "Valorisation", "Liste de prix d'achat"
CHAMPS_COUT = ("cout_unitaire", "cout_total", "source_cout", "ressource", "ressource_doctype", "cout_manquant", "cout_en_attente",
	"demande_prix", "cout_manuel", "prix_unitaire", "prix_total", "prix_conseille", "marge", "taux_marge")


# ------------------------------------------------------------------ outils
def cle_numero(numero):
	"""« 1.17.1 » → ((0, 1), (0, 17), (0, 1)) : ordre naturel ; une ligne sans numéro (en cours de saisie) va à la fin."""
	texte = cstr(numero).replace(" ", "")
	if not texte:
		return ((2, ""),)
	return tuple((0, int(x)) if x.isdigit() else (1, x) for x in texte.split("."))


def _regle(valeurs, regle):
	if not valeurs:
		return None
	if regle == "Moins élevé":
		return min(valeurs)
	if regle == "Moyenne":
		return sum(valeurs) / len(valeurs)
	return max(valeurs)


def facteur_uom(de, vers):
	"""Nombre d'unités « vers » dans une unité « de » (UOM Conversion Factor natif, dans un sens ou dans l'autre)."""
	if not de or not vers or de == vers:
		return 1
	v = frappe.db.get_value("UOM Conversion Factor", {"from_uom": de, "to_uom": vers}, "value")
	if flt(v):
		return flt(v)
	v = frappe.db.get_value("UOM Conversion Factor", {"from_uom": vers, "to_uom": de}, "value")
	return 1 / flt(v) if flt(v) else None


def _valeur_groupe(item_code, champ):
	"""Valeur sur l'article, sinon sur son groupe d'articles puis les groupes parents."""
	valeur, groupe = frappe.db.get_value("Item", item_code, [champ, "item_group"]) or (None, None)
	while not valeur and groupe:
		valeur, groupe = frappe.db.get_value("Item Group", groupe, [champ, "parent_item_group"]) or (None, None)
	return valeur


def type_par_defaut(item_code):
	"""Type de position par défaut : celui de l'article, sinon de son groupe d'articles (puis groupes parents)."""
	return _valeur_groupe(item_code, "lsi_type_position") if item_code else None


def _types(doc):
	for p in doc.get("positions") or []:
		if not p.type_position and p.item_code:  # ligne en cours de saisie (sans article) : ignorée ici
			p.type_position = type_par_defaut(p.item_code)  # vide si ni l'article ni son groupe n'en ont : coût manquant
	noms = {p.type_position for p in doc.get("positions") or [] if p.type_position and frappe.db.exists("Type Position", p.type_position)}
	return {n: frappe.get_doc("Type Position", n) for n in noms}


def valorisation(item_code):
	"""Valorisation du stock : moyenne pondérée des entrepôts (Bin natif) ; à défaut, valorisation de la fiche article."""
	r = frappe.db.sql("""select sum(stock_value), sum(actual_qty) from `tabBin` where item_code = %s and actual_qty > 0""", item_code)
	valeur, qty = r[0] if r else (0, 0)
	return flt(valeur) / flt(qty) if flt(qty) else flt(frappe.db.get_value("Item", item_code, "valuation_rate"))


def stock_disponible(item_code):
	return flt(frappe.db.sql("select sum(actual_qty) from `tabBin` where item_code = %s", item_code)[0][0])


# ------------------------------------------------------------------ hooks
def eft_validate(doc, method=None):
	if doc.docstatus != 0:
		return  # soumise : coûts figés
	appliquer_gammes(doc)
	organiser(doc)
	calculer(doc)


# ------------------------------------------------------------------ organisation automatique : prestation → groupe, n° automatiques
def etapes_du_groupe(doc, numero):
	return [r.etape for r in doc.get("repartitions") or [] if cstr(r.cible) == cstr(numero) and r.etape]


def groupe_de_etape(doc, etape):
	return next((cstr(g.numero) for g in doc.get("groupes") or [] if etape in etapes_du_groupe(doc, g.numero)), None)


def _creer_groupe(doc, etape):
	n = cstr(_prochain_groupe(doc))
	libelle = next((e.libelle for e in doc.get("etapes") or [] if e.prestation == etape and e.libelle), None)
	doc.append("groupes", dict(numero=n, titre=libelle or frappe.db.get_value("Item", etape, "item_name") or etape))
	doc.append("repartitions", dict(cible=n, etape=etape))
	return n


def _suivant(prefixe, numeros):
	"""Prochain n° « <prefixe>.<k> » libre."""
	ks = [int(x.rsplit(".", 1)[1]) for x in numeros if x.startswith(f"{prefixe}.") and x.count(".") == prefixe.count(".") + 1
		and x.rsplit(".", 1)[1].isdigit()]
	return f"{prefixe}.{max(ks, default=0) + 1}"


def organiser(doc, numeroter=True):
	"""L'utilisateur ne travaille que sur les prestations (étapes) : les groupes, la répartition et les n° suivent.
	- une prestation sans groupe (sans gamme) reçoit un groupe vide ;
	- une position reçoit le groupe de sa prestation (ou la prestation de son groupe) ; une sous-position suit sa parente ;
	- une position sans n° reçoit le suivant de son groupe (ou de sa parente)."""
	presentes = [e.prestation for e in doc.get("etapes") or [] if e.prestation]
	for p in doc.get("positions") or []:  # prestation choisie sur une ligne mais absente des étapes : ajoutée
		if p.etape and p.etape not in presentes and not p.parente:
			doc.append("etapes", dict(prestation=p.etape, qty=1, gamme_appliquee=1))
			presentes.append(p.etape)
	for e in doc.get("etapes") or []:
		if e.prestation and not groupe_de_etape(doc, e.prestation):
			if cint(e.gamme_appliquee) or not frappe.db.exists("Gamme", {"prestation": e.prestation, "actif": 1}):
				_creer_groupe(doc, e.prestation)
	positions = doc.get("positions") or []
	par_num = {p.numero: p for p in positions if p.numero}
	for p in sorted(positions, key=lambda x: bool(x.parente)):  # positions principales d'abord
		if p.parente and p.parente in par_num:
			parent = par_num[p.parente]
			p.groupe, p.etape = parent.groupe, parent.etape or p.etape
			continue
		if p.etape and (not p.groupe or p.etape not in etapes_du_groupe(doc, p.groupe)):
			p.groupe = groupe_de_etape(doc, p.etape) or _creer_groupe(doc, p.etape)
		elif not p.etape and p.groupe:
			p.etape = (etapes_du_groupe(doc, p.groupe) or [None])[0]
		elif not p.etape and not p.groupe and len(presentes) == 1:
			p.etape = presentes[0]
			p.groupe = groupe_de_etape(doc, p.etape) or _creer_groupe(doc, p.etape)
	if not numeroter:
		return  # aperçu : les n° ne sont donnés qu'à l'enregistrement (la ligne parente peut encore être choisie)
	numeros = {p.numero for p in positions if p.numero}
	for p in positions:
		if not p.numero and (p.parente or p.groupe):
			p.numero = _suivant(cstr(p.parente or p.groupe), numeros)
			numeros.add(p.numero)


@frappe.whitelist(methods=["POST"])
def partager_groupe(eft, groupe, etapes):
	"""Un groupe partagé entre plusieurs prestations (parts égales) : cocher les prestations concernées."""
	doc = _eft_brouillon(eft)
	etapes = frappe.parse_json(etapes) or []
	if not etapes:
		frappe.throw(_("Cochez au moins une prestation."))
	if not any(cstr(g.numero) == cstr(groupe) for g in doc.groupes):
		frappe.throw(_("Groupe {0} introuvable.").format(groupe))
	for r in [r for r in doc.repartitions if cstr(r.cible) == cstr(groupe)]:
		doc.remove(r)
	for e in etapes:
		doc.append("repartitions", dict(cible=cstr(groupe), etape=e))
	for p in doc.positions:
		if cstr(p.groupe) == cstr(groupe) and p.etape not in etapes:
			p.etape = etapes[0]
	doc.save()
	return doc.name


def modele_validate(doc, method=None):
	"""Un modèle d'EFT ne garde jamais de coût ni de prix."""
	for p in doc.get("positions") or []:
		for c in CHAMPS_COUT:
			p.set(c, None if c in ("source_cout", "ressource", "ressource_doctype", "demande_prix") else 0)
	for g in doc.get("groupes") or []:
		g.cout_total = g.prix_total = g.marge = g.taux_marge = 0
	for e in doc.get("etapes") or []:
		e.gamme_appliquee = 1


# ------------------------------------------------------------------ gammes
def _prochain_groupe(doc):
	nums = [int(g.numero) for g in doc.get("groupes") or [] if cstr(g.numero).isdigit()]
	return max(nums, default=0) + 1


def numeros_gamme(lignes):
	"""N° relatif de chaque ligne : n° imposé, sinon automatique (lignes principales 1, 2, 3… ; sous-lignes <parente>.1, .2…)."""
	nums, imposes = {}, {cstr(l.numero) for l in lignes if l.numero}
	compteur, sous = 0, {}
	for l in sorted(lignes, key=lambda x: x.idx):
		if cint(l.get("parente_ligne")):
			parent = nums.get(cint(l.parente_ligne))
			if not parent:
				frappe.throw(_("Gamme, ligne {0} : la ligne parente n° {1} doit précéder la sous-ligne.").format(l.idx, l.parente_ligne))
			if l.numero:
				nums[l.idx] = cstr(l.numero)
			else:
				sous[parent] = sous.get(parent, 0) + 1
				nums[l.idx] = f"{parent}.{sous[parent]}"
		elif l.numero:
			nums[l.idx] = cstr(l.numero)
		else:
			compteur += 1
			while str(compteur) in imposes:
				compteur += 1
			nums[l.idx] = str(compteur)
	return nums


def appliquer_gamme(doc, etape):
	"""La gamme de la prestation crée le groupe et préremplit positions et sous-positions (× quantité de l'étape)."""
	nom = frappe.db.get_value("Gamme", {"prestation": etape.prestation, "actif": 1})
	if not nom:
		return False
	gamme = frappe.get_doc("Gamme", nom)
	n = cstr(_prochain_groupe(doc))
	nums = numeros_gamme(gamme.lignes)
	doc.append("groupes", dict(numero=n, titre=gamme.titre_groupe))
	for l in gamme.lignes:
		parent = nums.get(cint(l.get("parente_ligne"))) if cint(l.get("parente_ligne")) else None
		doc.append("positions", dict(numero=f"{n}.{nums[l.idx]}", groupe=n, etape=etape.prestation, parente=f"{n}.{parent}" if parent else None,
			type_position=l.type_position or type_par_defaut(l.item_code), item_code=l.item_code, designation_2=l.designation_2,
			qty=flt(l.qty) * flt(etape.qty or 1), uom=l.uom))
	doc.append("repartitions", dict(cible=n, etape=etape.prestation))
	etape.gamme_appliquee = 1
	return True


def appliquer_gammes(doc):
	"""Étape (prestation) ajoutée : sa gamme est appliquée une seule fois."""
	for e in doc.get("etapes") or []:
		if not cint(e.gamme_appliquee) and e.prestation:
			appliquer_gamme(doc, e)


# ------------------------------------------------------------------ coûts
def _ressources(t, pool, titre=None):
	"""Ressources du pool avec leur coût. Pool d'articles sans champ de coût : coût de chaque article selon sa propre
	« Source du coût » (article, sinon groupe : dernier prix d'achat, valorisation ou liste de prix d'achat)."""
	filtres = {t.champ_appartenance: pool}
	filtres.update(json.loads(t.filtres_ressources or "{}") or {})
	champs = ["name"] + ([f"{titre} as titre"] if titre else [])
	if t.ressource_doctype == "Item" and not t.champ_cout:
		lignes = frappe.get_all("Item", filters=filtres, fields=champs)
		for r in lignes:
			r.cout = (_cout_article(frappe._dict(item_code=r.name, uom=None))[0]) or 0
		return lignes
	return frappe.get_all(t.ressource_doctype, filters=filtres, fields=champs + [f"{t.champ_cout} as cout"])


def _cout_pool(p, t):
	pool_dt, pool = frappe.db.get_value("Item", p.item_code, ["lsi_pool_doctype", "lsi_pool"]) or (None, None)
	if pool_dt != t.pool_doctype or not pool:
		return None, _("article sans pool {0}").format(_(t.pool_doctype))
	ressources = [r for r in _ressources(t, pool) if flt(r.cout) > 0]
	p.ressource_doctype = t.ressource_doctype
	choisie = next((r for r in ressources if p.ressource and r.name == p.ressource), None)
	if choisie:
		cout, trace = flt(choisie.cout), _("ressource choisie : {0}").format(p.ressource)
	else:
		p.ressource = None
		cout = _regle([flt(r.cout) for r in ressources], t.regle)
		trace = _("règle du pool : {0} ({1} ressource(s) de {2})").format(_(t.regle or "Plus élevé"), len(ressources), pool)
	if cout is None:
		return None, _("aucune ressource avec un coût dans le pool {0}").format(pool)
	f = facteur_uom(t.uom_cout or p.uom, p.uom)
	if not f:
		return None, _("conversion {0} → {1} absente (UOM Conversion Factor)").format(t.uom_cout, p.uom)
	if f != 1:
		trace += _(" ; converti {0} → {1} (÷ {2})").format(t.uom_cout, p.uom, f)
	return cout / f, trace


def _cout_article(p):
	source = _valeur_groupe(p.item_code, "lsi_source_cout") or DERNIER_PRIX
	item = frappe.db.get_value("Item", p.item_code, ["last_purchase_rate", "valuation_rate", "stock_uom"], as_dict=True)
	if not item:
		return None, _("article introuvable")
	if source == VALORISATION:
		cout = valorisation(p.item_code)
	elif source == LISTE_PRIX:
		liste = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		cout = flt(frappe.db.get_value("Item Price", {"item_code": p.item_code, "price_list": liste, "buying": 1}, "price_list_rate"))
		source = f"{source} ({liste})"
	else:
		cout = flt(item.last_purchase_rate)
	if not cout:
		return None, _("{0} : aucun coût").format(source)
	if p.uom and item.stock_uom and p.uom != item.stock_uom:
		cf = flt(frappe.db.get_value("UOM Conversion Detail", {"parent": p.item_code, "uom": p.uom}, "conversion_factor"))
		if not cf:
			return None, _("unité {0} non définie sur l'article (conversions)").format(p.uom)
		cout *= cf
	return cout, source


def prix_fournisseurs(item_code):
	prix = [dict(fournisseur=r.supplier, prix=flt(r.price_list_rate), origine=_("Prix d'achat"), reference=r.name)
		for r in frappe.get_all("Item Price", filters={"item_code": item_code, "buying": 1, "supplier": ("is", "set")},
			fields=["name", "supplier", "price_list_rate"])]
	for r in frappe.db.sql("""select sq.name, sq.supplier, sqi.rate from `tabSupplier Quotation Item` sqi
			join `tabSupplier Quotation` sq on sq.name = sqi.parent
			where sqi.item_code = %s and sq.docstatus = 1 and (sq.valid_till is null or sq.valid_till >= %s)""",
			(item_code, nowdate()), as_dict=True):
		prix.append(dict(fournisseur=r.supplier, prix=flt(r.rate), origine=_("Offre fournisseur"), reference=r.name))
	return [x for x in prix if x["prix"] > 0]


def _cout_fournisseur(p, t):
	prix = prix_fournisseurs(p.item_code)
	if not prix:
		if p.demande_prix:
			p.cout_en_attente = 1
			return None, _("coût en attente : demande de prix {0}").format(p.demande_prix)
		return None, _("aucun prix fournisseur")
	cout = _regle([x["prix"] for x in prix], t.regle)
	return cout, _("prix fournisseurs : {0} ({1} prix)").format(_(t.regle or "Plus élevé"), len(prix))


def _cout_securise(p, t):
	"""Le coût d'une ligne ne bloque jamais le chiffrage : article absent, sans prix, pool vide ou mal paramétré → coût manquant,
	avec la raison dans « Source du coût »."""
	if not frappe.db.exists("Item", p.item_code):
		p.cout_unitaire, p.cout_manquant, p.cout_en_attente = 0, 1, 0
		p.source_cout = _("article introuvable : {0}").format(p.item_code)
		return
	frappe.db.savepoint("lsi_cout")
	try:
		_cout_position(p, t)
	except Exception as e:  # paramétrage incohérent (ex. champ de coût inexistant) : signalé sur la ligne, jamais une erreur
		frappe.db.rollback(save_point="lsi_cout")
		frappe.clear_messages()
		p.cout_unitaire, p.cout_manquant, p.cout_en_attente = 0, 1, 0
		p.source_cout = _("coût non calculable ({0}) : vérifier le type de position {1}").format(cstr(e)[:140], t.name)


def _cout_position(p, t):
	p.cout_manquant = p.cout_en_attente = 0
	if cint(p.cout_manuel) or t.source_cout == MANUEL:
		p.source_cout = _("coût saisi")
		return
	if t.source_cout == POOL:
		cout, trace = _cout_pool(p, t)
	elif t.source_cout == ARTICLE:
		cout, trace = _cout_article(p)
	elif t.source_cout == FOURNISSEUR:
		cout, trace = _cout_fournisseur(p, t)
	else:
		cout, trace = None, _("source {0} : réservée aux positions à prix fixe").format(t.source_cout)
	p.source_cout = trace
	if cout is None:
		p.cout_unitaire = 0
		p.cout_manquant = 0 if p.cout_en_attente else 1
	else:
		p.cout_unitaire = cout


# ------------------------------------------------------------------ calcul complet
def _etapes_de(doc, p, par_num):
	"""[(étape, fraction)] : répartition de la position, sinon de son groupe, sinon l'étape unique de l'EFT."""
	if p.parente and p.parente in par_num:
		return _etapes_de(doc, par_num[p.parente], par_num)
	for cible in (p.numero, p.groupe):
		lignes = [r for r in doc.get("repartitions") or [] if cstr(r.cible) == cstr(cible) and r.etape]
		if lignes:
			total = sum(flt(r.part) for r in lignes)
			if total:
				return [(r.etape, flt(r.part) / total) for r in lignes]
			return [(r.etape, 1 / len(lignes)) for r in lignes]
	etapes = [e.prestation for e in doc.get("etapes") or [] if e.prestation]
	return [(etapes[0], 1)] if len(etapes) == 1 else []


def calculer(doc):
	positions = doc.get("positions") or []
	types = _types(doc)
	par_num = {}
	for p in positions:
		if not p.numero:
			continue  # ligne en cours de saisie (le n° est obligatoire à l'enregistrement)
		if p.numero in par_num:
			frappe.throw(_("Position {0} en double.").format(p.numero))
		par_num[p.numero] = p
	enfants = defaultdict(list)
	for p in positions:
		t = types.get(p.type_position)
		p.mode = t.mode if t else None
		if p.parente:
			parent = par_num.get(p.parente)
			if not parent or (types.get(parent.type_position) and types[parent.type_position].mode != PRIX_FIXE):
				frappe.throw(_("Position {0} : la parente {1} doit être une position à prix fixe.").format(p.numero, p.parente))
			if p.mode == PRIX_FIXE:
				frappe.throw(_("Position {0} : une sous-position ne peut pas être à prix fixe.").format(p.numero))
			enfants[p.parente].append(p)
			p.groupe = p.groupe or parent.groupe
		elif p.mode == SOUS_POSITION:
			frappe.throw(_("Position {0} : le type {1} ne s'emploie que sous une position à prix fixe.").format(p.numero, p.type_position))
		p.tarif = 1 if not p.parente and flt(p.qty) == 0 else 0
		p.stock_disponible = stock_disponible(p.item_code) if frappe.db.get_value("Item", p.item_code, "is_stock_item") else 0

	for p in positions:  # coûts unitaires (hors prix fixe)
		if not p.item_code:  # ligne en cours de saisie : pas encore d'article
			p.cout_unitaire, p.cout_total, p.cout_manquant, p.source_cout = 0, 0, 1, _("article à choisir")
			continue
		if p.mode != PRIX_FIXE and p.type_position in types:
			_cout_securise(p, types[p.type_position])
			p.cout_total = flt(p.cout_unitaire) * flt(p.qty)
		elif p.mode != PRIX_FIXE:
			p.cout_unitaire, p.cout_total, p.cout_manquant = 0, 0, 1
			p.source_cout = _("type de position à choisir (ni sur la ligne, ni sur l'article, ni sur son groupe)")
	for p in positions:  # prix fixe = somme des sous-positions
		if p.mode == PRIX_FIXE:
			if not flt(p.qty_base):
				p.qty_base = p.qty
			kids = enfants.get(p.numero, [])
			p.cout_manquant = p.cout_en_attente = 0
			if cint(p.cout_manuel):
				p.source_cout = _("coût saisi")
				p.cout_total = flt(p.cout_unitaire) * flt(p.qty)
			else:
				p.cout_total = sum(flt(k.cout_total) for k in kids)
				p.cout_unitaire = p.cout_total / flt(p.qty) if flt(p.qty) else p.cout_total
				p.cout_manquant = 1 if not kids or any(cint(k.cout_manquant) for k in kids) else 0
				p.cout_en_attente = 1 if any(cint(k.cout_en_attente) for k in kids) else 0
				p.source_cout = _("somme de {0} sous-position(s)").format(len(kids)) if kids else _("aucune sous-position")
	for p in positions:  # prix et marges
		if p.parente:
			p.prix_unitaire = p.prix_total = p.marge = p.taux_marge = p.prix_conseille = 0
			continue
		p.prix_total = flt(p.prix_unitaire) * flt(p.qty)
		p.marge = p.prix_total - flt(p.cout_total)
		p.taux_marge = p.marge / p.prix_total * 100 if p.prix_total else 0
		cible = flt(_valeur_groupe(p.item_code, "lsi_marge_cible"))
		p.prix_conseille = flt(p.cout_unitaire) / (1 - cible / 100) if cible and cible < 100 and flt(p.cout_unitaire) else 0

	libelles = {e.prestation: e.libelle or e.prestation for e in doc.get("etapes") or []}
	vendues = [p for p in positions if not p.parente]
	for p in positions:
		parts = _etapes_de(doc, p, par_num)
		p.etapes = ", ".join(f"{libelles.get(e, e)}" + (f" ({round(f * 100)} %)" if len(parts) > 1 else "") for e, f in parts) or None
	for g in doc.get("groupes") or []:
		lignes = [p for p in vendues if cstr(p.groupe) == cstr(g.numero)]
		g.cout_total = sum(flt(p.cout_total) for p in lignes)
		g.prix_total = sum(flt(p.prix_total) for p in lignes)
		g.marge = g.prix_total - g.cout_total
		g.taux_marge = g.marge / g.prix_total * 100 if g.prix_total else 0
		parts = _etapes_de(doc, frappe._dict(numero=None, groupe=g.numero, parente=None), par_num)
		g.etapes = ", ".join(libelles.get(e, e) for e, _f in parts) or None

	totaux = defaultdict(lambda: [0.0, 0.0])
	for p in vendues:
		for e, f in _etapes_de(doc, p, par_num):
			totaux[e][0] += flt(p.cout_total) * f
			totaux[e][1] += flt(p.prix_total) * f
	doc.set("totaux_etapes", [])
	ordre = [e.prestation for e in doc.get("etapes") or []] + [e for e in totaux if e not in libelles]
	for e in dict.fromkeys(ordre):
		cout, prix = totaux.get(e, (0, 0))
		doc.append("totaux_etapes", dict(etape=e, cout_total=cout, prix_total=prix, marge=prix - cout,
			taux_marge=(prix - cout) / prix * 100 if prix else 0))
	doc.total_cout = sum(flt(p.cout_total) for p in vendues)
	doc.total_prix = sum(flt(p.prix_total) for p in vendues)
	doc.total_marge = doc.total_prix - doc.total_cout
	doc.taux_marge = doc.total_marge / doc.total_prix * 100 if doc.total_prix else 0
	doc.cout_incomplet = 1 if any(cint(p.cout_manquant) or cint(p.cout_en_attente) for p in vendues) else 0
	doc.set("positions", sorted(positions, key=lambda p: cle_numero(p.numero)))
	for i, p in enumerate(doc.positions, 1):
		p.idx = i


# ------------------------------------------------------------------ actions (boutons)
def _eft_brouillon(eft):
	doc = frappe.get_doc("EFT", eft)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("L'EFT {0} n'est plus en brouillon.").format(eft))
	return doc


def _position(doc, numero):
	p = next((x for x in doc.positions if x.numero == numero), None)
	if not p:
		frappe.throw(_("Position {0} introuvable.").format(numero))
	return p


@frappe.whitelist()
def make_eft(opportunity):
	"""Opportunité → EFT : étapes = articles de l'opportunité (leurs gammes s'appliquent à l'enregistrement)."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("read")
	doc = frappe.new_doc("EFT")
	doc.update(dict(titre=opp.get("title") or opp.name, opportunity=opp.name, company=opp.company, bu=opp.get("lsi_bu"),
		service=opp.get("lsi_service"),
		customer=opp.party_name if opp.opportunity_from == "Customer" else None))
	for it in opp.get("items") or []:
		doc.append("etapes", dict(prestation=it.item_code, qty=flt(it.qty) or 1, uom=it.uom))
	doc.insert()
	return doc.name


CHAMPS_APERCU_POSITION = ("numero", "groupe", "etape", "type_position", "mode", "tarif", "stock_disponible", "etapes", "cout_unitaire", "cout_total", "source_cout",
	"ressource", "ressource_doctype", "cout_manquant", "cout_en_attente", "prix_unitaire", "prix_total", "prix_conseille", "marge", "taux_marge")


@frappe.whitelist(methods=["POST"])
def apercu(doc):
	"""Calcul en temps réel (sans enregistrer) : même moteur qu'à l'enregistrement. Renvoie les valeurs calculées par ligne,
	l'étape principale de chaque position (couleurs) et les totaux. Une erreur de structure est renvoyée comme message."""
	d = frappe.get_doc(frappe.parse_json(doc))
	if not frappe.has_permission("EFT", "write") and not frappe.has_permission("EFT", "create"):
		frappe.throw(_("Pas de droit sur l'EFT."), frappe.PermissionError)
	if d.docstatus != 0:
		return {}
	try:
		organiser(d, numeroter=False)
		calculer(d)
	except frappe.ValidationError as e:
		frappe.clear_messages()
		return dict(erreur=cstr(e))
	par_num = {p.numero: p for p in d.positions}
	return dict(
		positions={p.name: dict({c: p.get(c) for c in CHAMPS_APERCU_POSITION}, etape_principale=(_etapes_de(d, p, par_num) or [(None, 0)])[0][0])
			for p in d.positions},
		groupes={g.name: dict(cout_total=g.cout_total, prix_total=g.prix_total, marge=g.marge, taux_marge=g.taux_marge, etapes=g.etapes)
			for g in d.groupes},
		totaux_etapes=[dict(etape=t.etape, cout_total=t.cout_total, prix_total=t.prix_total, marge=t.marge, taux_marge=t.taux_marge)
			for t in d.totaux_etapes],
		total_cout=d.total_cout, total_prix=d.total_prix, total_marge=d.total_marge, taux_marge=d.taux_marge, cout_incomplet=d.cout_incomplet,
	)


@frappe.whitelist(methods=["POST"])
def ajouter_gamme(eft, prestation, qty=1):
	"""Bouton « Ajouter depuis une gamme » : ajoute la prestation (étape) et applique sa gamme immédiatement."""
	doc = _eft_brouillon(eft)
	if not frappe.db.exists("Gamme", {"prestation": prestation, "actif": 1}):
		frappe.throw(_("Aucune gamme active pour la prestation {0}.").format(prestation))
	etape = next((e for e in doc.etapes if e.prestation == prestation and not cint(e.gamme_appliquee)), None)
	if not etape:
		etape = doc.append("etapes", dict(prestation=prestation, qty=flt(qty) or 1))
	else:
		etape.qty = flt(qty) or etape.qty
	appliquer_gamme(doc, etape)
	doc.save()
	return doc.name


@frappe.whitelist()
def voir_ressources(eft, numero):
	"""Ressources du pool de la position. Les coûts individuels ne sont renvoyés qu'aux rôles qui ont le droit de lire le champ de coût."""
	doc = frappe.get_doc("EFT", eft)
	doc.check_permission("read")
	p = _position(doc, numero)
	t = frappe.get_doc("Type Position", p.type_position)
	if t.source_cout != POOL:
		frappe.throw(_("La position {0} n'est pas chiffrée par un pool de ressources.").format(numero))
	pool = frappe.db.get_value("Item", p.item_code, "lsi_pool")
	meta = frappe.get_meta(t.ressource_doctype)
	df = meta.get_field(t.champ_cout) if t.champ_cout else None
	voit = (df.permlevel if df else 0) in meta.get_permlevel_access("read")
	titre = meta.get_title_field()
	lignes = _ressources(t, pool, titre)
	return dict(pool=pool, regle=t.regle, choisie=p.ressource, voit_couts=voit, cout_retenu=p.cout_unitaire, uom_cout=t.uom_cout,
		ressources=[dict(name=r.name, titre=r.titre or r.name, cout=flt(r.cout) if voit else None) for r in lignes])


@frappe.whitelist(methods=["POST"])
def choisir_ressource(eft, numero, ressource=None):
	doc = _eft_brouillon(eft)
	p = _position(doc, numero)
	p.ressource = ressource or None
	doc.save()
	return p.source_cout


@frappe.whitelist()
def historique_achat(item_code, limite=10):
	"""Derniers achats (factures et commandes validées) et offres fournisseurs de l'article."""
	frappe.has_permission("Item", "read", throw=True)
	out = []
	for dt, champ_date in (("Purchase Invoice", "posting_date"), ("Purchase Order", "transaction_date"), ("Supplier Quotation", "transaction_date")):
		out += frappe.db.sql(f"""select '{dt}' as doctype, p.name, p.supplier, p.{champ_date} as date, i.rate, i.uom, i.qty
			from `tab{dt} Item` i join `tab{dt}` p on p.name = i.parent
			where i.item_code = %s and p.docstatus = 1 order by p.{champ_date} desc limit %s""", (item_code, cint(limite)), as_dict=True)
	return sorted(out, key=lambda r: getdate(r.date), reverse=True)[: cint(limite)]


@frappe.whitelist(methods=["POST"])
def demander_prix(eft, numero, fournisseurs):
	"""Demande de prix native (Request for Quotation, brouillon) ; la position passe « coût en attente » jusqu'à l'offre."""
	doc = _eft_brouillon(eft)
	p = _position(doc, numero)
	fournisseurs = frappe.parse_json(fournisseurs) or []
	if not fournisseurs:
		frappe.throw(_("Choisissez au moins un fournisseur."))
	rfq = frappe.new_doc("Request for Quotation")
	rfq.update(dict(company=doc.company, transaction_date=nowdate(), lsi_eft=doc.name,
		message_for_supplier=_("Merci de nous adresser votre meilleure offre.")))
	for f in fournisseurs:
		rfq.append("suppliers", dict(supplier=f))
	stock_uom = frappe.db.get_value("Item", p.item_code, "stock_uom")
	rfq.append("items", dict(item_code=p.item_code, qty=flt(p.qty) or 1, uom=p.uom or stock_uom, stock_uom=stock_uom, conversion_factor=1,
		schedule_date=add_days(nowdate(), 7), description=p.designation or p.item_code))
	rfq.flags.ignore_permissions = True
	rfq.insert()
	p.demande_prix = rfq.name
	doc.save()
	return rfq.name


def offre_fournisseur(doc, method=None):
	"""Supplier Quotation validée en réponse à une demande de prix d'une EFT : l'EFT (brouillon) est recalculée."""
	for rfq in {i.request_for_quotation for i in doc.items if i.get("request_for_quotation")}:
		eft = frappe.db.get_value("Request for Quotation", rfq, "lsi_eft")
		if eft and frappe.db.get_value("EFT", eft, "docstatus") == 0:
			e = frappe.get_doc("EFT", eft)
			e.flags.ignore_permissions = True
			e.save()


@frappe.whitelist(methods=["POST"])
def repartir_prorata(eft, numero):
	"""Position à prix fixe dont la quantité a changé : ses sous-positions sont mises à l'échelle (nouvelle / ancienne quantité)."""
	doc = _eft_brouillon(eft)
	p = _position(doc, numero)
	if p.mode != PRIX_FIXE:
		frappe.throw(_("La position {0} n'est pas à prix fixe.").format(numero))
	base = flt(p.qty_base)
	if not base or base == flt(p.qty):
		frappe.throw(_("Aucun changement de quantité à répartir sur la position {0}.").format(numero))
	ratio = flt(p.qty) / base
	for k in doc.positions:
		if k.parente == numero:
			k.qty = flt(k.qty) * ratio
	p.qty_base = p.qty
	doc.save()
	return ratio


@frappe.whitelist(methods=["POST"])
def enregistrer_modele(eft, titre):
	doc = frappe.get_doc("EFT", eft)
	doc.check_permission("read")
	m = frappe.new_doc("Modele EFT")
	m.titre = titre
	for champ in ("etapes", "groupes", "positions", "repartitions"):
		for r in doc.get(champ) or []:
			d = r.as_dict()
			for k in ("name", "parent", "parentfield", "parenttype", "idx", "creation", "modified", "owner", "modified_by", "docstatus"):
				d.pop(k, None)
			m.append(champ, d)
	m.insert()
	return m.name


@frappe.whitelist(methods=["POST"])
def charger_modele(eft, modele):
	"""Ajoute la structure du modèle (groupes renumérotés après les groupes existants) ; coûts recalculés immédiatement."""
	doc = _eft_brouillon(eft)
	m = frappe.get_doc("Modele EFT", modele)
	decalage, correspondance = _prochain_groupe(doc) - 1, {}
	for g in m.groupes:
		nouveau = cstr(int(g.numero) + decalage) if cstr(g.numero).isdigit() else g.numero
		correspondance[cstr(g.numero)] = nouveau
		doc.append("groupes", dict(numero=nouveau, titre=g.titre))

	def renum(numero):
		if not numero:
			return numero
		tete, _sep, reste = cstr(numero).partition(".")
		return correspondance.get(tete, tete) + (f".{reste}" if reste else "")

	presentes = {e.prestation for e in doc.etapes}
	for e in m.etapes:
		if e.prestation not in presentes:
			doc.append("etapes", dict(prestation=e.prestation, libelle=e.libelle, qty=e.qty, uom=e.uom, gamme_appliquee=1))
	for p in m.positions:
		doc.append("positions", dict(numero=renum(p.numero), groupe=renum(p.groupe), etape=p.etape, parente=renum(p.parente), type_position=p.type_position,
			item_code=p.item_code, designation_2=p.designation_2, qty=p.qty, uom=p.uom))
	for r in m.repartitions:
		doc.append("repartitions", dict(cible=renum(r.cible), etape=r.etape, part=r.part))
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def creer_devis(eft):
	"""Un seul chemin : chaque POSITION VENDUE (sans parente) = une ligne de devis natif ; jamais les sous-positions."""
	doc = frappe.get_doc("EFT", eft)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("L'EFT doit être validée avant de créer le devis."))
	vendues = [p for p in doc.positions if not p.parente]
	if any(cint(p.tarif) for p in vendues) and not cint(frappe.db.get_single_value("Selling Settings", "allow_zero_qty_in_quotation")):
		frappe.throw(_("Des lignes tarif (quantité 0) existent : activez « Allow Quotation with Zero Quantity » dans les paramètres de vente."))
	if not doc.customer:
		frappe.throw(_("Renseignez le client de l'EFT."))
	titres = {cstr(g.numero): g.titre for g in doc.groupes}
	q = frappe.new_doc("Quotation")
	q.update(dict(quotation_to="Customer", party_name=doc.customer, company=doc.company, transaction_date=nowdate(),
		valid_till=add_days(nowdate(), 30), opportunity=doc.opportunity, lsi_eft=doc.name, lsi_bu=doc.bu, lsi_service=doc.service,
		ignore_pricing_rule=1))
	for p in vendues:
		q.append("items", dict(item_code=p.item_code, qty=flt(p.qty), uom=p.uom, conversion_factor=1, rate=flt(p.prix_unitaire),
			description=" — ".join(x for x in (p.designation or p.item_code, p.designation_2) if x),
			lsi_groupe_numero=p.groupe, lsi_groupe_titre=titres.get(cstr(p.groupe)), lsi_numero_position=p.numero,
			lsi_designation_2=p.designation_2, lsi_etapes=p.etapes, lsi_tarif=p.tarif, lsi_eft_position=p.name))
	q.insert()
	return q.name
