"""Actions de l'écran de chiffrage (menu Positions) : ressources, historique d'achat, demande de prix, prorata, partage."""

import frappe
from frappe.query_builder import Order
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate

from lsi_inspection.constants import POOL, PRIX_FIXE
from lsi_inspection.chiffrage.moteur.couts import _ressources


def _chiffrage_brouillon(chiffrage):
	doc = frappe.get_doc("Chiffrage", chiffrage)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Le chiffrage {0} n'est plus en brouillon.").format(chiffrage))
	return doc


def _eft_brouillon(eft):
	"""Récupère un EFT en brouillon avec vérification des droits."""
	doc = frappe.get_doc("Chiffrage", eft)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("L'EFT {0} n'est plus en brouillon.").format(eft))
	return doc


def _position(doc, numero):
	p = next((x for x in doc.positions if x.numero == numero), None)
	if not p:
		frappe.throw(_("Position {0} introuvable.").format(numero))
	return p


@frappe.whitelist(methods=["POST"])
def partager_groupe(chiffrage, groupe, etapes=None):
	if not etapes or len(frappe.parse_json(etapes)) < 2:
		frappe.throw(_("Ajoutez au moins 2 prestations au chiffrage pour partager un groupe entre elles."))
	"""Un groupe partagé entre plusieurs prestations (parts égales) : cocher les prestations concernées."""
	doc = _chiffrage_brouillon(chiffrage)
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


@frappe.whitelist()
def voir_ressources(chiffrage, numero):
	"""Ressources du pool de la position. Les coûts individuels ne sont renvoyés qu'aux rôles qui ont le droit de lire le champ de coût."""
	doc = frappe.get_doc("Chiffrage", chiffrage)
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
def choisir_ressource(chiffrage, numero, ressource=None):
	doc = _chiffrage_brouillon(chiffrage)
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
		doc, ligne = frappe.qb.DocType(dt), frappe.qb.DocType(f"{dt} Item")
		lignes = (frappe.qb.from_(ligne).join(doc).on(doc.name == ligne.parent)
			.select(doc.name, doc.supplier, doc[champ_date].as_("date"), ligne.rate, ligne.uom, ligne.qty)
			.where((ligne.item_code == item_code) & (doc.docstatus == 1)).orderby(doc[champ_date], order=Order.desc).limit(cint(limite))
			).run(as_dict=True)
		out += [frappe._dict(r, doctype=dt) for r in lignes]
	return sorted(out, key=lambda r: getdate(r.date), reverse=True)[: cint(limite)]


@frappe.whitelist(methods=["POST"])
def demander_prix(chiffrage, numero, fournisseurs):
	"""Demande de prix native (Request for Quotation, brouillon) ; la position passe « coût en attente » jusqu'à l'offre."""
	doc = _chiffrage_brouillon(chiffrage)
	p = _position(doc, numero)
	fournisseurs = frappe.parse_json(fournisseurs) or []
	if not fournisseurs:
		frappe.throw(_("Choisissez au moins un fournisseur."))
	rfq = frappe.new_doc("Request for Quotation")
	rfq.update(dict(company=doc.company, transaction_date=nowdate(), lsi_chiffrage=doc.name,
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
	"""Supplier Quotation validée en réponse à une demande de prix d'un chiffrage : le chiffrage (brouillon) est recalculée."""
	for rfq in {i.request_for_quotation for i in doc.items if i.get("request_for_quotation")}:
		chiffrage = frappe.db.get_value("Request for Quotation", rfq, "lsi_chiffrage")
		if chiffrage and frappe.db.get_value("Chiffrage", chiffrage, "docstatus") == 0:
			e = frappe.get_doc("Chiffrage", chiffrage)
			e.flags.ignore_permissions = True
			e.save()


@frappe.whitelist(methods=["POST"])
def repartir_prorata(chiffrage, numero):
	"""Position à prix fixe dont la quantité a changé : ses sous-positions sont mises à l'échelle (nouvelle / ancienne quantité)."""
	doc = _chiffrage_brouillon(chiffrage)
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
def planifier_positions_globales(eft, positions):
	"""
	Planification globale intelligente selon le type :
	- Équipement ➔ Task de réservation d'asset
	- Stock ➔ Material Request
	- Consommable ➔ Material Request (sans responsable)
	- Activité ➔ Task assignée
	"""
	doc = _eft_brouillon(eft)
	positions_data = frappe.parse_json(positions)
	
	if not positions_data:
		frappe.throw(_("Aucune position à planifier."))
	
	par_num = {p.numero: p for p in doc.positions}
	nb_planifie = 0
	messages = []
	
	for ligne in positions_data:
		numero = ligne.get("numero")
		# Gérer le cas où le numéro est un float (1.1) ou string ("1.1")
		p = par_num.get(str(numero)) or par_num.get(numero) or par_num.get(float(numero))
		if not p or not ligne.get("date_debut"):
			continue
		
		type_planif = ligne.get("type_planif")
		date_debut = getdate(ligne.get("date_debut"))
		date_fin = getdate(ligne.get("date_fin")) if ligne.get("date_fin") else date_debut
		responsable = ligne.get("responsable")
		asset = ligne.get("asset_specifique")
		qty_commande = ligne.get("qty_commande") or flt(p.qty) or 1
		notes = ligne.get("notes")
		
		# Enregistrement des dates sur la position
		p.db_set("date_debut_prevue", date_debut, update_modified=False)
		p.db_set("date_fin_prevue", date_fin, update_modified=False)
		p.db_set("responsable", responsable, update_modified=False)
		p.db_set("notes_planification", notes, update_modified=False)
		p.db_set("statut_planification", "Planifié", update_modified=False)
		
		# --- ACTION SELON LE TYPE ---
		if type_planif == "equipement":
			subject = f"[ÉQUIPEMENT] {p.numero} - {p.designation or p.item_code}"
			if asset:
				subject += f" ({asset})"
			task = frappe.get_doc({
				"doctype": "Task",
				"subject": subject,
				"description": notes or f"Réservation équipement depuis EFT {eft}",
				"exp_start_date": date_debut,
				"exp_end_date": date_fin,
				"assigned_to": responsable,
				"status": "Open",
				"priority": "High"
			})
			task.insert(ignore_permissions=True)
			messages.append(f"🚜 {p.numero} : Task {task.name}")
			
		elif type_planif in ("stock", "consommable"):
			mr = frappe.new_doc("Material Request")
			mr.material_request_type = "Purchase"
			mr.schedule_date = date_debut
			mr.company = doc.company
			mr.append("items", {
				"item_code": p.item_code,
				"qty": flt(qty_commande),
				"schedule_date": date_debut,
				"description": f"{p.designation or ''} (Pos: {p.numero})"
			})
			mr.insert(ignore_permissions=True)
			messages.append(f"📦 {p.numero} : Demande {mr.name}")
			
		else:  # activite
			task = frappe.get_doc({
				"doctype": "Task",
				"subject": f"[ACTIVITÉ] {p.numero} - {p.designation or p.item_code}",
				"description": notes or f"Intervention planifiée depuis EFT {eft}",
				"project": doc.get("project"),
				"exp_start_date": date_debut,
				"exp_end_date": date_fin,
				"assigned_to": responsable,
				"status": "Open"
			})
			task.insert(ignore_permissions=True)
			messages.append(f"👷 {p.numero} : Task {task.name}")
		
		nb_planifie += 1
	
	doc.save()
	
	recap = "\n".join(messages) if messages else ""
	return _("✅ {0} position(s) planifiée(s).\n\n{1}").format(nb_planifie, recap)