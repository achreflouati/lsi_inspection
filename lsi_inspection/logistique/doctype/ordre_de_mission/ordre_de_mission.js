// Ordre de Mission : généré par le Besoin Logistique (logistique/om.py) ; on le modifie depuis le besoin, puis « Générer les OM ».
frappe.ui.form.on("Ordre de Mission", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.besoin_logistique) {
			frm.set_intro(__("Généré par le besoin logistique {0} : modifiez le besoin puis « Générer les OM ».", [frm.doc.besoin_logistique]), "blue");
			frm.add_custom_button(__("Besoin logistique"), () => frappe.set_route("Form", "Besoin Logistique", frm.doc.besoin_logistique), __("Voir"));
		}
		if (frm.doc.project) {
			frm.add_custom_button(__("Projet"), () => frappe.set_route("Form", "Project", frm.doc.project), __("Voir"));
			frm.add_custom_button(__("Tâches"), () => frappe.set_route("List", "Task", { project: frm.doc.project }), __("Voir"));
		}
	},
});
