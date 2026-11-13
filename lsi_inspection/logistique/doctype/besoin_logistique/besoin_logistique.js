// Besoin Logistique : planification des prestations et affectations nominatives, boutons du circuit logistique.
// Aucun contrôle métier ici : tout est vérifié à l'enregistrement côté serveur (logistique/controles.py) ;
// l'écran propose seulement les bonnes valeurs (n° de ligne, prestations de la ligne, ressources du pool).
const LOG = "lsi_inspection.logistique";
const STATUTS_FIGES = ["Annulé"];

frappe.ui.form.on("Besoin Logistique", {
	setup(frm) {
		// Prestation d'une affectation : celle de sa ligne prévue, ou une des prestations d'une ligne partagée
		frm.set_query("prestation", "affectations", (doc, cdt, cdn) => {
			const a = locals[cdt][cdn];
			return { filters: { name: ["in", prestations_de_ligne(frm, a.ligne_ressource)] } };
		});
		// Ressource : filtrée sur le pool de la ligne (mêmes filtres que le chiffrage, fournis par le serveur)
		frm.set_query("ressource", "affectations", (doc, cdt, cdn) => {
			const f = (frm.__filtres_pool || {})[locals[cdt][cdn].ligne_ressource];
			return f ? { filters: f.filters } : { filters: { name: ["in", []] } };
		});
	},

	refresh(frm) {
		// les prestations viennent de l'extraction de la commande : ni ajout ni suppression de ligne
		frm.set_df_property("prestations", "cannot_add_rows", true);
		frm.set_df_property("prestations", "cannot_delete_rows", true);
		options_lignes(frm);
		charger_filtres_pool(frm);
		if (frm.is_new()) return;
		const statut = frm.doc.statut;
		frm.set_intro(statut === "Annulé" ? __("Besoin annulé : non modifiable.") : "", "orange");
		if (!STATUTS_FIGES.includes(statut)) {
			frm.add_custom_button(__("Préparer les affectations"), () => appeler(frm, "planification.preparer_affectations",
				(n) => __("{0} affectation(s) ajoutée(s) : choisissez les ressources.", [n])));
			if (["Planifié", "OM générés"].includes(statut)) {
				frm.add_custom_button(__("Générer les OM"), () => appeler(frm, "om.generer_om",
					(r) => __("{0} OM et {1} tâche(s).", [r.om.length, r.taches])), __("Actions")).addClass("btn-primary");
			}
			frm.add_custom_button(__("Annuler le besoin"), () => frappe.confirm(
				__("Annuler ce besoin ? Ses OM passent « Annulé » et leurs tâches « Cancelled »."),
				() => appeler(frm, "om.annuler_besoin", () => __("Besoin annulé."))), __("Actions"));
		}
		if (frm.doc.project) frm.add_custom_button(__("Projet"), () => frappe.set_route("Form", "Project", frm.doc.project), __("Voir"));
		frm.add_custom_button(__("Ordres de mission"), () => frappe.set_route("List", "Ordre de Mission", { besoin_logistique: frm.doc.name }), __("Voir"));
		frm.add_custom_button(__("Commande client"), () => frappe.set_route("Form", "Sales Order", frm.doc.sales_order), __("Voir"));
	},
});

frappe.ui.form.on("Besoin Logistique Affectation", {
	affectations_add(frm) { options_lignes(frm); },

	// Ligne choisie : doctype de la ressource (lien dynamique), type, prestation (ligne simple), quantité, dates de la prestation
	ligne_ressource(frm, cdt, cdn) {
		const a = locals[cdt][cdn];
		const r = (frm.doc.ressources || []).find((x) => x.numero === a.ligne_ressource);
		if (!r) return;
		frappe.model.set_value(cdt, cdn, { ressource_doctype: r.ressource_doctype, type_ressource: r.type_ressource, ressource: null,
			prestation: r.partagee ? null : r.prestation, qty: r.qty });
		dates_prestation(frm, cdt, cdn);
	},

	prestation(frm, cdt, cdn) { dates_prestation(frm, cdt, cdn); },
});

// ------------------------------------------------------------------ utilitaires de l'écran
function options_lignes(frm) {
	// n° des lignes prévues proposés dans « Ligne (n°) » (le serveur refuse un n° inconnu)
	const options = [""].concat((frm.doc.ressources || []).map((r) => r.numero));
	frm.fields_dict.affectations.grid.update_docfield_property("ligne_ressource", "options", options.join("\n"));
}

function prestations_de_ligne(frm, numero) {
	const r = (frm.doc.ressources || []).find((x) => x.numero === numero);
	if (!r) return (frm.doc.prestations || []).map((p) => p.prestation);
	if (!r.partagee) return [r.prestation];
	return (frm.doc.repartitions || []).filter((x) => x.numero === numero).map((x) => x.prestation);
}

function charger_filtres_pool(frm) {
	// une requête par ligne prévue : {numero: {doctype, filters}} gardé sur le formulaire pour set_query
	frm.__filtres_pool = {};
	(frm.doc.ressources || []).forEach((r) => {
		frappe.xcall(`${LOG}.pools.ressources_du_pool`, { type_position: r.type_position, pool: r.pool })
			.then((f) => { frm.__filtres_pool[r.numero] = f; });
	});
}

function dates_prestation(frm, cdt, cdn) {
	const a = locals[cdt][cdn];
	const p = (frm.doc.prestations || []).find((x) => x.prestation === a.prestation);
	if (p) frappe.model.set_value(cdt, cdn, { date_debut: a.date_debut || p.date_debut, date_fin: a.date_fin || p.date_fin });
}

function appeler(frm, methode, message) {
	const lancer = () => frappe.xcall(`${LOG}.${methode}`, { besoin: frm.doc.name }).then((r) => {
		frappe.show_alert({ message: message(r), indicator: "green" });
		frm.reload_doc();
	});
	// enregistrer d'abord les saisies en cours : le serveur travaille sur le document enregistré
	if (frm.is_dirty()) frm.save().then(lancer); else lancer();
}
