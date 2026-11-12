// Chiffrage (variante de l'EFT) — boutons de l'écran. Aucun calcul ici : le serveur recalcule (moteur lsi_inspection.chiffrage.moteur).
// Fichiers chargés avant celui-ci (hooks.py, doctype_js) : commun/demande_client.js, chiffrage/tableau.js, chiffrage/apercu.js, chiffrage/actions.js.
frappe.ui.form.on("Chiffrage", {
	setup(frm) {
		// colonne « Prestation » : seulement les prestations (étapes) de l'EFT
		frm.set_query("etape", "positions", () => ({ filters: { name: ["in", (frm.doc.etapes || []).map((e) => e.prestation).filter((x) => x)] } }));
	},
	refresh(frm) {
		lsi.demande_client.afficher(frm, frm.doc.opportunity);
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Ajouter depuis une gamme"), () => lsi_chiffrage.ajouter_gamme(frm)).addClass("btn-primary");
			const P = __("Positions");
			frm.add_custom_button(__("Voir les ressources"), () => lsi_chiffrage.ressources(frm), P);
			frm.add_custom_button(__("Historique d'achat"), () => lsi_chiffrage.historique(frm), P);
			frm.add_custom_button(__("Demander un prix"), () => lsi_chiffrage.demander_prix(frm), P);
			frm.add_custom_button(__("Répartir au prorata"), () => lsi_chiffrage.prorata(frm), P);
			frm.add_custom_button(__("Partager un groupe"), () => lsi_chiffrage.partager(frm), P);
			frm.add_custom_button(__("Planifier postions"), () => lsi_chiffrage.planifier_position(frm), P);
			frm.add_custom_button(__("📋 Planning global"), () => lsi_chiffrage.planning_global(frm), P);
			frm.add_custom_button(__("dhia non pas comme ca  Vue Gantt prévisionnelle"), () => lsi_chiffrage.vue_gantt(frm), P);
			frm.add_custom_button(__("Charger un modèle"), () => lsi_chiffrage.charger_modele(frm), __("Modèle"));
		}
		frm.add_custom_button(__("Enregistrer comme modèle"), () => lsi_chiffrage.enregistrer_modele(frm), __("Modèle"));
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Créer l'offre client"), () => lsi_chiffrage.offre_client(frm), __("Créer"));
		}
		if (frm.doc.cout_incomplet) {
			frm.dashboard.set_headline(`<span class="text-danger">${__("Coût incomplet : au moins une position a un coût manquant ou en attente.")}</span>`);
		}
	},
});
