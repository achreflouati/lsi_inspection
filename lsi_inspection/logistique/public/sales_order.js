// Commande client (Sales Order) : bouton du circuit logistique (lsi_inspection/logistique/extraction.py).
// Commande validée sans besoin : « Créer projet et besoin logistique » ; besoin existant : bouton pour l'ouvrir.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frappe.model.can_read("Besoin Logistique")) return;
		frappe.db.get_value("Besoin Logistique", { sales_order: frm.doc.name }, "name").then(({ message }) => {
			const groupe = __("Logistique");
			if (message && message.name) {
				frm.add_custom_button(__("Ouvrir le besoin logistique"),
					() => frappe.set_route("Form", "Besoin Logistique", message.name), groupe);
				return;
			}
			if (!frappe.model.can_create("Besoin Logistique")) return;
			frm.add_custom_button(__("Créer projet et besoin logistique"), () => {
				frappe.call({
					method: "lsi_inspection.logistique.extraction.creer_projet_et_besoin",
					args: { sales_order: frm.doc.name },
					freeze: true,
					freeze_message: __("Création du projet et extraction du chiffrage…"),
				}).then(({ message: r }) => {
					frappe.show_alert({ message: __("Projet {0} — besoin {1}", [r.project, r.besoin]), indicator: "green" });
					frappe.set_route("Form", "Besoin Logistique", r.besoin);
				});
			}, groupe);
		});
	},
});
