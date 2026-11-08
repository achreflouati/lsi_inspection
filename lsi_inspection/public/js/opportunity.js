// Opportunité : bouton « Terminer ma phase » (moteur générique lsi_inspection.commercial.phases).
// Les phases, responsables et événements se règlent sur le type d'opportunité : rien de métier ici.
frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		if (frm.is_new() || !(frm.doc.lsi_phases || []).length) return;
		frappe
			.call({ method: "lsi_inspection.commercial.phases.infos_phases", args: { opportunity: frm.doc.name } })
			.then((r) => {
				const info = r.message || {};
				if (!info.courante) return;
				frm.dashboard.set_headline(
					__("Phase en cours : {0}", [`<b>${frappe.utils.escape_html(__(info.courante))}</b>`])
				);
				if (info.peut_terminer) {
					frm.add_custom_button(__("Terminer ma phase"), () => terminer(frm, info)).addClass("btn-primary");
				}
			});
	},
});

function terminer(frm, info) {
	const options = (info.choix || []).map((c) => ({
		value: c.phase,
		label: (c.retour ? "↩ " + __("Retour à") + " " : "") + __(c.phase) + (c.obligatoire ? " *" : ""),
	}));
	const d = new frappe.ui.Dialog({
		title: __("Terminer la phase « {0} »", [__(info.courante)]),
		fields: [
			{
				fieldname: "vers",
				fieldtype: "Select",
				label: __("Phase suivante"),
				options: [{ value: "", label: __("(aucune : fin du parcours)") }].concat(options),
				default: info.suivante || "",
				description: __("* phase obligatoire : elle ne peut pas être sautée."),
			},
			{ fieldname: "commentaire", fieldtype: "Small Text", label: __("Commentaire") },
		],
		primary_action_label: __("Terminer"),
		primary_action(v) {
			frappe
				.call({
					method: "lsi_inspection.commercial.phases.terminer_phase",
					args: { opportunity: frm.doc.name, vers: v.vers || null, commentaire: v.commentaire },
					freeze: true,
				})
				.then(() => {
					d.hide();
					frm.reload_doc();
				});
		},
	});
	d.show();
}
