"""Lot 2 — écran Opportunité aligné sur tidemo : disposition (Détails 100 % natif, onglet « Suivi commercial »), champs calculés
de l'avancement, Dossier AO (visibilité par le type), valeurs par défaut du référentiel, alertes de remise, liste."""

import frappe
from frappe.utils import add_days, now_datetime

from lsi_inspection import outils
from lsi_inspection.commercial import phases
from lsi_inspection.tests.contexte import PREFIXE, TestLot2

SECTIONS_SUIVI = ["Suivi commercial", "Demande d'offre", "Départements concernés", "Avancement de l'opportunité",
	"Durée par phase commerciale", None, "Dossier AO", None, "Résultat de l'AO"]


class TestEcran(TestLot2):
	# ------------------------------------------------------------------ disposition
	def test_details_reste_natif(self):
		meta = frappe.get_meta("Opportunity")
		natifs = [f.fieldname for f in frappe.get_meta("Opportunity", cached=False).fields if not f.get("is_custom_field")]
		standard = [f.fieldname for f in frappe.get_doc("DocType", "Opportunity").fields]
		self.assertEqual(natifs, standard, "ordre des champs natifs modifié")
		noms = [f.fieldname for f in meta.fields]
		self.assertFalse([n for n in noms[: noms.index("lsi_tab_suivi")] if n.startswith("lsi_")], "champ lsi dans l'onglet Détails")

	def test_onglet_suivi_apres_details_dans_l_ordre(self):
		meta = frappe.get_meta("Opportunity")
		noms = [f.fieldname for f in meta.fields]
		i = noms.index("lsi_tab_suivi")
		self.assertEqual(noms[i - 1], "competitors")  # dernier champ de Détails
		bloc = [f for f in meta.fields[i:] if f.fieldname.startswith("lsi_")]
		bloc = bloc[: [f.fieldname for f in bloc].index("lsi_ao_concurrents") + 1]
		self.assertEqual(noms[noms.index("lsi_ao_concurrents") + 1], "contact_info")
		self.assertEqual([f.label or None for f in bloc if f.fieldtype in ("Tab Break", "Section Break")], SECTIONS_SUIVI)
		for fn in ("lsi_sb_ao", "lsi_sb_ao_tables", "lsi_sb_ao_resultat"):
			self.assertEqual(meta.get_field(fn).depends_on, "eval:doc.lsi_dossier_ao")

	def test_libelles_comme_tidemo(self):
		meta = frappe.get_meta("Opportunity")
		attendus = {"lsi_canal_demande": "Type de consultation", "lsi_origine_demande": "Personnel à l'origine de la consultation",
			"lsi_statut_validation": "Statut de validation", "lsi_date_limite": "Date limite de réponse",
			"lsi_phase_depuis": "Phase commerciale en cours depuis", "lsi_responsables_phase": "Responsables de la phase en cours",
			"lsi_historique_phases": "Historique des phases commerciales"}
		self.assertEqual({k: meta.get_field(k).label for k in attendus}, attendus)
		self.assertEqual(meta.get_field("lsi_durees_html").fieldtype, "HTML")

	def test_liste_colonnes_et_filtres(self):
		meta = frappe.get_meta("Opportunity")
		self.assertTrue(meta.get_field("lsi_statut_validation").in_list_view)
		self.assertTrue(meta.get_field("lsi_ao_date_limite_remise").in_list_view)
		self.assertTrue(meta.get_field("lsi_ao_reference").in_standard_filter)

	# ------------------------------------------------------------------ avancement
	def test_avancement_calcule(self):
		self.utilisateur(f"etude.{PREFIXE.lower()}@example.com", ["Sales User"])
		o = self.opportunite(self.parcours_standard())
		cur = phases.courante(o)
		self.assertEqual(str(o.lsi_phase_depuis), str(cur.debut))
		self.assertEqual(o.lsi_responsables_phase, frappe.utils.get_fullname("Administrator"))
		q = self.devis(o)
		o = self.recharger(o)
		etude = next(r for r in o.lsi_phases if r.phase == "T Étude")
		self.assertEqual(etude.commentaire, f"Devis validé : Quotation {q.name}")  # bulle de la phase sautée
		phases.terminer_phase(o.name, vers="T Gagnée")
		o = self.recharger(o)
		self.assertIn("Sautée par", next(r for r in o.lsi_phases if r.phase == "T Offre").commentaire or "Sautée par")

	# ------------------------------------------------------------------ dossier AO
	def _type_ao(self, ao=1):
		t = self.parcours_standard(f"{PREFIXE} {'AO' if ao else 'Spot'}")
		frappe.db.set_value("Opportunity Type", t, "lsi_dossier_ao", ao)
		return t

	def test_dossier_ao_visible_selon_le_type(self):
		self.assertEqual(self.opportunite(self._type_ao(1)).lsi_dossier_ao, 1)
		self.assertEqual(self.opportunite(self._type_ao(0)).lsi_dossier_ao, 0)

	def test_dossier_ao_tables(self):
		concurrent = f"{PREFIXE} Concurrent"
		if not frappe.db.exists("Competitor", concurrent):
			frappe.get_doc(dict(doctype="Competitor", competitor_name=concurrent)).insert()
		o = self.opportunite(self._type_ao(1), lsi_ao_reference="AO-T-1", lsi_ao_lots=[dict(numero="1", intitule="Lot 1", on_repond=1)],
			lsi_ao_exigences=[dict(exigence="Exigence 1", lot="1")], lsi_ao_concurrents=[dict(competitor=concurrent, montant=1000, rang=2)])
		o = self.recharger(o)
		self.assertEqual((len(o.lsi_ao_lots), len(o.lsi_ao_exigences), len(o.lsi_ao_concurrents)), (1, 1, 1))
		self.assertIn("CONFORMITE_CDC", frappe.get_meta("Exigence CDC").get_field("conformite").link_filters)

	def test_alertes_remise_days_before(self):
		ao = self.opportunite(self._type_ao(1), lsi_ao_date_limite_remise=add_days(now_datetime(), 3))
		spot = self.opportunite(self._type_ao(0), lsi_ao_date_limite_remise=add_days(now_datetime(), 3))
		n = frappe.get_doc("Notification", "Remise AO J-3")
		docs = [d.name for d in n.get_documents_for_today()]
		self.assertIn(ao.name, docs)
		from frappe.email.doctype.notification.notification import get_context

		self.assertTrue(frappe.safe_eval(n.condition, None, get_context(ao)))
		self.assertFalse(frappe.safe_eval(n.condition, None, get_context(spot)))
		self.assertEqual(sorted(frappe.get_all("Notification", filters={"name": ("like", "Remise AO J-%")}, pluck="days_in_advance")), [1, 3, 7])

	# ------------------------------------------------------------------ valeurs par défaut du référentiel
	def _defaut(self, famille, code):
		frappe.db.set_value("Type Metier", {"famille": famille}, "par_defaut", 0)
		if not frappe.db.exists("Famille de Type", famille):
			frappe.get_doc(dict(doctype="Famille de Type", code=famille, libelle=famille)).insert()
		return frappe.get_doc(dict(doctype="Type Metier", famille=famille, code=code, libelle=code, par_defaut=1)).insert().name

	def test_defaut_rempli_si_vide_et_affiche(self):
		conformite = self._defaut("CONFORMITE_CDC", f"{PREFIXE}_ANALYSE")
		resultat = self._defaut("RESULTAT_AO", f"{PREFIXE}_ATTENTE")
		ao = self.opportunite(self._type_ao(1), lsi_ao_exigences=[dict(exigence="E1")])
		self.assertEqual((ao.lsi_ao_attribue, ao.lsi_ao_exigences[0].conformite), (resultat, conformite))
		spot = self.opportunite(self._type_ao(0))
		self.assertFalse(spot.lsi_ao_attribue)  # section Dossier AO masquée : pas de valeur posée

	def test_valeur_saisie_conservee(self):
		self._defaut("CONFORMITE_CDC", f"{PREFIXE}_ANALYSE")
		autre = frappe.get_doc(dict(doctype="Type Metier", famille="CONFORMITE_CDC", code=f"{PREFIXE}_OK", libelle="OK")).insert().name
		o = self.opportunite(self._type_ao(1), lsi_ao_exigences=[dict(exigence="E1", conformite=autre)])
		self.assertEqual(o.lsi_ao_exigences[0].conformite, autre)

	def test_un_seul_defaut_par_famille(self):
		self._defaut("CONFORMITE_CDC", f"{PREFIXE}_A")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(dict(doctype="Type Metier", famille="CONFORMITE_CDC", code=f"{PREFIXE}_B", libelle="B", par_defaut=1)).insert()

	def test_famille_lue_dans_les_link_filters(self):
		df = frappe.get_meta("Opportunity").get_field("lsi_ao_portee")
		self.assertEqual(outils._famille(df), "PORTEE_AO")

	# ------------------------------------------------------------------ défauts : nouveau document / nouvelle ligne seulement
	def test_defaut_jamais_sur_un_document_enregistre(self):
		resultat = self._defaut("RESULTAT_AO", f"{PREFIXE}_ATTENTE")
		o = self.opportunite(self._type_ao(1))
		self.assertEqual(o.lsi_ao_attribue, resultat)  # nouveau document : défaut posé
		o.lsi_ao_attribue = None
		o.save()
		self.assertFalse(self.recharger(o).lsi_ao_attribue)  # vidé à la main : reste vide
		avant = self.recharger(o).modified
		o = self.recharger(o)
		o.save()
		self.assertFalse(o.lsi_ao_attribue)  # ré-enregistré sans changement : rien n'est ajouté
		self.assertNotEqual(avant, None)

	def test_defaut_sur_nouvelle_ligne_seulement(self):
		conformite = self._defaut("CONFORMITE_CDC", f"{PREFIXE}_ANALYSE")
		o = self.opportunite(self._type_ao(1), lsi_ao_exigences=[dict(exigence="E1")])
		self.assertEqual(o.lsi_ao_exigences[0].conformite, conformite)
		o.lsi_ao_exigences[0].conformite = None  # ligne existante vidée à la main
		o.append("lsi_ao_exigences", dict(exigence="E2"))  # nouvelle ligne
		o.save()
		o = self.recharger(o)
		self.assertEqual([r.conformite for r in o.lsi_ao_exigences], [None, conformite])

	def test_document_existant_sans_defaut_n_est_pas_complete(self):
		o = self.opportunite(self._type_ao(1))
		frappe.db.set_value("Opportunity", o.name, "lsi_ao_attribue", None)  # document antérieur à la valeur par défaut
		self._defaut("RESULTAT_AO", f"{PREFIXE}_ATTENTE")
		o = self.recharger(o)
		o.save()
		self.assertFalse(self.recharger(o).lsi_ao_attribue)
