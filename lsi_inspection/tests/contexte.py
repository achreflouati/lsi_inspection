"""Contexte des tests du lot 2 : chaque test tourne dans une transaction annulée (savepoint) et construit SA configuration
(étapes, type, parcours, événements, modèles) : aucune dépendance aux valeurs du profil TIC."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

from lsi_inspection.commercial import phases
from lsi_inspection.tests.compat import IntegrationTestCase

PREFIXE = "LSI-T"


class TestLot2(IntegrationTestCase):
	def setUp(self):
		# frappe.log_error écrit hors de la transaction de test : remplacé pendant les tests (aucun journal laissé sur le site)
		self._log_error = patch("frappe.log_error")
		self.log_error = self._log_error.start()
		self.addCleanup(self._log_error.stop)
		# aucun e-mail réellement envoyé (le site a un compte sortant réel) : un envoi immédiat valide aussi la transaction
		envoi = patch("frappe.email.doctype.email_queue.email_queue.EmailQueue.send")
		envoi.start()
		self.addCleanup(envoi.stop)
		# garde-fou : aucun commit pendant un test (sinon les données de test resteraient sur le site)
		garde = patch.object(frappe.db, "commit", side_effect=AssertionError("commit interdit pendant un test"))
		garde.start()
		self.addCleanup(garde.stop)
		frappe.set_user("Administrator")
		self._temoin = self.etat_site()
		frappe.db.savepoint("lsi_test")
		frappe.local.lsi_evenements_differes = {}
		phases.vider_cache_evenements()
		self.company = frappe.defaults.get_global_default("company")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="lsi_test")
		frappe.local.lsi_evenements_differes = {}
		phases.vider_cache_evenements()
		frappe.cache.hdel("notifications", "Opportunity")  # notifications natives créées par le test
		frappe.clear_cache(doctype="Opportunity")
		# contrôle automatique : utilisateurs temporaires supprimés, aucun e-mail ni notification laissés sur le site
		self.assertEqual(self.etat_site(), self._temoin, "le test a laissé des données sur le site")

	@staticmethod
	def etat_site():
		return dict(utilisateurs=frappe.db.count("User"), email_queue=frappe.db.count("Email Queue"),
			notification_log=frappe.db.count("Notification Log"), opportunites=frappe.db.count("Opportunity"))

	# ------------------------------------------------------------------ référentiels
	def etape(self, nom):
		if not frappe.db.exists("Sales Stage", nom):
			frappe.get_doc(dict(doctype="Sales Stage", stage_name=nom)).insert(ignore_permissions=True)
		return nom

	def evenement(self, libelle, declencheur="Manuel", **kw):
		if not frappe.db.exists("Evenement Phase", libelle):
			frappe.get_doc(dict(doctype="Evenement Phase", libelle=libelle, declencheur=declencheur, actif=1, **kw)).insert(ignore_permissions=True)
		phases.vider_cache_evenements()
		return libelle

	def modele(self, nom, sujet="{{ doc.name }} — {{ phase }}", corps="<p>{{ moment }} : {{ phase }} ({{ doc.name }})</p>"):
		if not frappe.db.exists("Email Template", nom):
			frappe.get_doc(dict(doctype="Email Template", name=nom, subject=sujet, use_html=1, response_html=corps)).insert(
				ignore_permissions=True, set_name=nom)
		return nom

	def type_parcours(self, nom, lignes, defaut=0):
		"""lignes : (ordre, phase, responsable, événement, options) ; responsable = Commercial / Rôle:<rôle> / Utilisateur:<user>."""
		doc = frappe.get_doc("Opportunity Type", nom) if frappe.db.exists("Opportunity Type", nom) else frappe.new_doc("Opportunity Type")
		doc.name = nom
		doc.set("lsi_parcours", [])
		for ordre, phase, resp, evt, *opt in lignes:
			r = dict(ordre=ordre, phase=self.etape(phase), evenement_fin=evt)
			r.update(opt[0] if opt else {})
			typ, _, val = resp.partition(":")
			r["type_responsable"] = typ
			if typ == "Rôle":
				r["role"] = val
			elif typ == "Utilisateur":
				r["utilisateur"] = val
			doc.append("lsi_parcours", r)
		doc.lsi_parcours_defaut = defaut
		if doc.is_new():
			doc.insert(ignore_permissions=True, set_name=nom)
		else:
			doc.save(ignore_permissions=True)
		return nom

	def parcours_standard(self, nom=f"{PREFIXE} Parcours", options=None, annulation=True):
		"""Parcours de test : 5 phases dans la séquence + Gagnée (finale) + Perdue (hors séquence)."""
		o = options or {}
		self.evenement("Manuel")
		return self.type_parcours(nom, [
			(10, "T Création", "Commercial", "Manuel", o.get("T Création", {})),
			(20, "T Étude", "Commercial", "Manuel", o.get("T Étude", {})),
			(30, "T Chiffrage", "Commercial", "Manuel", o.get("T Chiffrage", {})),
			(40, "T Validation", "Commercial", self.evenement("Devis validé", "Validation", document_type="Quotation")),
			(50, "T Offre", "Commercial", "Manuel"),
			(60, "T Gagnée", "Commercial", self.evenement("Opportunité convertie", "Changement de statut", document_type="Opportunity",
				champ_statut="status", valeur="Converted"), {"phase_finale": "Gagnée"}),
			(99, "T Perdue", "Commercial", self.evenement("Opportunité perdue", "Changement de statut", document_type="Opportunity",
				champ_statut="status", valeur="Lost"), {"phase_finale": "Perdue", "evenement_annulation": self.evenement("Opportunité rouverte",
				"Changement de statut", document_type="Opportunity", champ_statut="status", valeur="Lost", sens="Quitte la valeur")
				if annulation else None}),
		])

	# ------------------------------------------------------------------ données
	def utilisateur(self, email, roles):
		if not frappe.db.exists("User", email):
			u = frappe.get_doc(dict(doctype="User", email=email, first_name=email.split("@")[0], send_welcome_email=0, user_type="System User"))
			u.flags.no_welcome_mail = True
			u.insert(ignore_permissions=True)
		u = frappe.get_doc("User", email)
		u.add_roles(*roles)
		return email

	def departement(self, nom, responsable=None):
		name = frappe.db.get_value("Department", {"department_name": nom, "company": self.company})
		if not name:
			d = frappe.get_doc(dict(doctype="Department", department_name=nom, company=self.company,
				parent_department=frappe.db.get_value("Department", {"is_group": 1, "parent_department": ("in", ["", None])})))
			d.insert(ignore_permissions=True)
			name = d.name
		if responsable:
			frappe.db.set_value("Department", name, "lsi_responsable", responsable)
		return name

	def employe(self, prenom, departement, user=None):
		e = frappe.get_doc(dict(doctype="Employee", first_name=prenom, gender=frappe.get_all("Gender", pluck="name")[0], date_of_birth="1990-01-01",
			date_of_joining="2020-01-01", company=self.company, department=departement, user_id=user, status="Active"))
		e.insert(ignore_permissions=True)
		return e.name

	def client(self):
		nom = f"{PREFIXE} Client"
		if not frappe.db.exists("Customer", nom):
			frappe.get_doc(dict(doctype="Customer", customer_name=nom, customer_type="Company",
				customer_group=frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name")[0],
				territory=frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")[0])).insert(ignore_permissions=True)
		return nom

	def article(self):
		code = f"{PREFIXE}-PREST"
		if not frappe.db.exists("Item", code):
			frappe.get_doc(dict(doctype="Item", item_code=code, item_name="Prestation de test", is_stock_item=0, include_item_in_manufacturing=0,
				item_group=frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0],
				stock_uom=frappe.get_all("UOM", pluck="name", limit=1, filters={"enabled": 1})[0])).insert(ignore_permissions=True)
		return code

	def opportunite(self, type_, **kw):
		o = frappe.get_doc(dict(doctype="Opportunity", opportunity_from="Customer", party_name=self.client(), opportunity_type=type_,
			company=self.company, items=[dict(item_code=self.article(), qty=1, rate=100)], **kw))
		o.insert()
		return o

	def devis(self, opp, soumettre=True):
		from erpnext.crm.doctype.opportunity.opportunity import make_quotation

		q = make_quotation(opp.name)
		q.valid_till = add_days(nowdate(), 30)
		for it in q.items:
			it.rate = 100
		q.insert()
		if soumettre:
			q.submit()
		return q

	def commande(self, devis):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		so = make_sales_order(devis.name)
		so.delivery_date = add_days(nowdate(), 10)
		for it in so.items:
			it.delivery_date = so.delivery_date
		so.insert()
		so.submit()
		return so

	def recharger(self, opp):
		return frappe.get_doc("Opportunity", opp.name if hasattr(opp, "name") else opp)

	@staticmethod
	def statuts(opp):
		return {r.phase: r.statut for r in opp.lsi_phases}

	def erreurs(self, reference_name):
		"""Erreurs journalisées (frappe.log_error remplacé) pour ce document."""
		return [c for c in self.log_error.call_args_list if c.kwargs.get("reference_name") == reference_name]

	@staticmethod
	def commit_simule():
		"""Les tests ne valident jamais la transaction : on exécute le traitement « avant commit » des événements de valeur."""
		phases.traiter_differes()
