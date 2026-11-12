"""Configuration initiale : commun (générique) + profil du site (clé site_config « lsi_profil »).

- charger() (after_sync à l'installation, after_migrate) : insère ce qui manque, ne modifie JAMAIS l'existant ;
- exporter_profil(profil) : écrit la configuration du site dans config_initiale/profils/<profil>/ (JSON triés, sans champs
  techniques) ; ne touche jamais commun/.
La liste des doctypes (et leur ordre de chargement, et les filtres d'export) est dans config_initiale/manifeste.json :
configuration, pas code.
Circuit : TIC paramètre à l'écran → export → commit Git → la production l'insère à la migration.
"""

import json
import glob
import os

import frappe
from frappe.utils import cstr
from frappe.model import default_fields, no_value_fields, table_fields

TECHNIQUES = set(default_fields) | {"parent", "parentfield", "parenttype", "amended_from", "_user_tags", "_comments", "_assign",
	"_liked_by", "_seen", "lft", "rgt", "old_parent"}  # lft / rgt / old_parent : arbre recalculé à l'insertion


def racine():
	return frappe.get_app_path("lsi_inspection", "config_initiale")


def manifeste():
	with open(os.path.join(racine(), "manifeste.json")) as f:
		return json.load(f)["doctypes"]


def _fichier(dossier, doctype):
	return os.path.join(dossier, frappe.scrub(doctype) + ".json")


def _lire(dossier, doctype):
	chemin = _fichier(dossier, doctype)
	if not os.path.exists(chemin):
		return []
	with open(chemin) as f:
		return _substituer(json.load(f), _variables())


def dossiers(profil=None):
	profil = profil if profil is not None else frappe.conf.get("lsi_profil")
	out = [os.path.join(racine(), "commun")]
	if profil:
		out.append(os.path.join(racine(), "profils", profil))
	return out


def charger(profil=None):
	"""Insère les éléments absents (commun puis profil) ; renvoie le nombre d'insertions."""
	n = 0
	for dossier in dossiers(profil):
		n += charger_dossier(dossier)
	if n:
		print(f"lsi_inspection : configuration initiale, {n} élément(s) inséré(s)")
	return n


def _charger_reglages(dt, valeurs):
	"""Réglage natif (document unique) : chaque champ n'est renseigné que s'il est encore à sa valeur d'origine (vide, défaut
	du champ, ou racine d'un arbre comme « Tous les groupes clients »). Enregistré par le document natif : ses propres
	règles s'appliquent (ex. Selling Settings recopie groupe client et territoire dans les valeurs par défaut globales)."""
	meta = frappe.get_meta(dt)
	doc = frappe.get_single(dt)
	changes = {}
	for champ, valeur in (valeurs or {}).items():
		df = meta.get_field(champ)
		if not df:
			continue
		actuel = doc.get(champ)
		if cstr(actuel) != cstr(valeur) and (cstr(actuel) in ("", "0", cstr(df.default or "")) or _racine(df, actuel)):
			changes[champ] = valeur
	if changes:
		doc.update(changes)
		doc.flags.ignore_permissions = True
		try:
			doc.save()
		except frappe.LinkValidationError as e:
			print(f"[lsi_inspection] réglage {dt} ignoré : {e}")
			return 0
	return len(changes)


def _racine(df, valeur):
	if df.fieldtype != "Link" or not valeur or not frappe.get_meta(df.options).is_tree:
		return False
	parent = frappe.get_meta(df.options).get("nsm_parent_field") or f"parent_{frappe.scrub(df.options)}"
	return not frappe.db.get_value(df.options, valeur, parent)


def charger_dossier(dossier):
	"""Insère les éléments absents. Un élément dont un lien n'existe pas encore est mis en attente ; tout le manifeste est
	repassé tant que des éléments en attente peuvent être insérés (liens entre fichiers, ex. article → type de position)."""
	total = 0
	while True:
		n, attente = _passe(dossier)
		total += n
		if not attente or not n:
			break
	if attente:
		print(f"lsi_inspection : en attente (lien manquant) : {', '.join(attente)}")
	return total


def _passe(dossier):
	n, attente = 0, []
	frappe.flags.lsi_chargement_config = True
	try:
		_creer_unites(dossier)
		for entree in _substituer(manifeste(), _variables()):
			dt = entree["doctype"]
			if entree.get("single"):
				chemin = _fichier(dossier, dt)
				if os.path.exists(chemin):
					with open(chemin) as f:
						n += _charger_reglages(dt, _substituer(json.load(f), _variables()))
				continue
			restants = [d for d in _lire(dossier, dt) if not frappe.db.exists(dt, d["name"])]
			while restants:  # plusieurs passes : un élément peut citer un autre du même fichier (ex. département parent)
				echecs = []
				for d in restants:
					doc = frappe.get_doc(dict(d, doctype=dt))
					doc.flags.ignore_permissions = True
					frappe.db.savepoint("lsi_config")
					try:
						doc.insert(set_name=d["name"])
						n += 1
					except frappe.LinkValidationError:
						frappe.db.rollback(save_point="lsi_config")
						frappe.clear_messages()
						echecs.append(d)
				if len(echecs) == len(restants):
					attente += [f"{dt} {d['name']}" for d in echecs]
					break
				restants = echecs
	finally:
		frappe.flags.lsi_chargement_config = False
	return n, attente


# ------------------------------------------------------------------ portabilité du profil
# Le profil n'écrit jamais le nom de la société, son abréviation ni les racines des arbres :
# il utilise des variables, remplacées ici par les valeurs du site.
CHAMPS_UNITE = ("uom", "stock_uom", "from_uom", "to_uom")


def _variables():
	"""Valeurs du site : {societe}, {abbr}, {racine_groupe_articles}, {racine_departements}, {categorie_temps}."""
	from frappe.utils.nestedset import get_root_of
	societe = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
	return {
		"societe": societe or "",
		"abbr": (frappe.db.get_value("Company", societe, "abbr") if societe else "") or "",
		"racine_groupe_articles": get_root_of("Item Group") or "",
		"racine_departements": get_root_of("Department") or "",
		"categorie_temps": next((c for c in ("Temps", "Time") if frappe.db.exists("UOM Category", c)), ""),
	}


def _substituer(valeur, variables):
	"""Remplace {variable} par sa valeur ; une variable inconnue (vide) reste telle quelle."""
	if isinstance(valeur, str):
		for cle, val in variables.items():
			if val:
				valeur = valeur.replace("{" + cle + "}", val)
		return valeur
	if isinstance(valeur, list):
		return [_substituer(v, variables) for v in valeur]
	if isinstance(valeur, dict):
		return {k: _substituer(v, variables) for k, v in valeur.items()}
	return valeur


def _variabiliser(valeur, variables):
	"""Inverse de _substituer, pour l'export : remet les variables à la place des valeurs du site."""
	if isinstance(valeur, str):
		abbr = variables.get("abbr")
		if abbr and valeur.endswith(" - " + abbr):
			valeur = valeur[: -len(abbr)] + "{abbr}"
		for cle in ("societe", "racine_groupe_articles", "racine_departements", "categorie_temps"):
			if variables.get(cle) and valeur == variables[cle]:
				return "{" + cle + "}"
		return valeur
	if isinstance(valeur, list):
		return [_variabiliser(v, variables) for v in valeur]
	if isinstance(valeur, dict):
		return {k: _variabiliser(v, variables) for k, v in valeur.items()}
	return valeur


def _creer_unites(dossier):
	"""Crée les unités citées par le profil si le site ne les a pas (ex. « Jour » sur un site en anglais)."""
	noms = set()

	def parcourir(x):
		if isinstance(x, dict):
			for k, v in x.items():
				if k in CHAMPS_UNITE and isinstance(v, str) and v:
					noms.add(v)
				else:
					parcourir(v)
		elif isinstance(x, list):
			for v in x:
				parcourir(v)

	for fichier in glob.glob(os.path.join(dossier, "*.json")):
		with open(fichier, encoding="utf-8") as f:
			parcourir(json.load(f))
	for nom in sorted(noms):
		if not frappe.db.exists("UOM", nom):
			frappe.get_doc({"doctype": "UOM", "uom_name": nom}).insert(ignore_permissions=True)



# ------------------------------------------------------------------ export
def _valeur(v):
	return str(v) if not isinstance(v, (int, float, str, bool)) else v


def _propre(doc):
	out = {"name": doc.name} if not doc.meta.istable else {}
	for df in doc.meta.fields:
		f = df.fieldname
		if f in TECHNIQUES or df.fieldtype in no_value_fields and df.fieldtype not in table_fields:
			continue
		if df.get("fetch_from") and not df.get("fetch_if_empty"):
			continue  # toujours recopié automatiquement : jamais exporté (sinon l'export dépend de l'ordre de chargement)
		if df.fieldtype in table_fields:
			lignes = [_propre(r) for r in doc.get(f) or []]
			if lignes:
				out[f] = lignes
			continue
		v = doc.get(f)
		if v not in (None, ""):
			out[f] = _valeur(v)
	return out


def _references(docs, cible):
	"""Noms de « cible » cités par des champs Link des documents (tables comprises)."""
	noms = set()

	def parcourir(doc):
		for df in doc.meta.get_link_fields():
			if df.options == cible and doc.get(df.fieldname):
				noms.add(doc.get(df.fieldname))
		for tdf in doc.meta.get_table_fields():
			for r in doc.get(tdf.fieldname) or []:
				parcourir(r)

	for d in docs:
		parcourir(d)
	return noms


@frappe.whitelist()
def exporter_profil(profil, dossier=None):
	"""Exporte la configuration du site dans profils/<profil>/ (ou « dossier » pour les tests). Renvoie {doctype: nombre}."""
	frappe.only_for("System Manager")
	if not profil or "/" in profil or profil.startswith("."):
		frappe.throw("Profil invalide")
	cible = dossier or os.path.join(racine(), "profils", profil)
	commun = os.path.join(racine(), "commun")
	if os.path.realpath(cible).startswith(os.path.realpath(commun)):
		frappe.throw("L'export n'écrit jamais dans commun/")
	os.makedirs(cible, exist_ok=True)
	variables = _variables()
	entrees = _substituer(manifeste(), variables)
	docs = {}
	for e in entrees:
		if e.get("export") == "references" or e.get("single"):
			continue
		exclus = {d["name"] for d in _lire(commun, e["doctype"])}
		noms = [n for n in frappe.get_all(e["doctype"], filters=e.get("filtres"), or_filters=e.get("filtres_ou"), pluck="name", order_by="name asc") if n not in exclus]
		docs[e["doctype"]] = [frappe.get_doc(e["doctype"], n) for n in noms]
	tous = [d for liste in docs.values() for d in liste]
	for e in entrees:
		if e.get("export") == "references":
			exclus = {d["name"] for d in _lire(commun, e["doctype"])}
			noms = sorted(n for n in _references(tous, e["doctype"]) if n not in exclus)
			docs[e["doctype"]] = [frappe.get_doc(e["doctype"], n) for n in noms]
	resultat = {}
	for e in entrees:
		dt = e["doctype"]
		if e.get("single"):
			valeurs = {c: frappe.db.get_single_value(dt, c) for c in e.get("champs") or []}
			valeurs = _variabiliser(valeurs, variables)
			with open(_fichier(cible, dt), "w") as f:
				f.write(json.dumps(valeurs, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
			resultat[dt] = len(valeurs)
			continue
		contenu = sorted((_propre(d) for d in docs.get(dt, [])), key=lambda x: x["name"])
		contenu = _variabiliser(contenu, variables)
		chemin = _fichier(cible, dt)
		if contenu:
			with open(chemin, "w") as f:
				f.write(json.dumps(contenu, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
		elif os.path.exists(chemin):
			with open(chemin, "w") as f:
				f.write("[]\n")
		resultat[dt] = len(contenu)
	return resultat
