// Liste des ordres de mission : couleur du statut.
frappe.listview_settings["Ordre de Mission"] = {
	add_fields: ["statut"],
	get_indicator(doc) {
		return [__(doc.statut), doc.statut === "Annulé" ? "red" : "green", `statut,=,${doc.statut}`];
	},
};
