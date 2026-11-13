// Liste des besoins logistiques : couleur du statut.
frappe.listview_settings["Besoin Logistique"] = {
	add_fields: ["statut"],
	get_indicator(doc) {
		const couleurs = { Brouillon: "gray", "En planification": "orange", "Planifié": "blue", "OM générés": "green", "Annulé": "red" };
		return [__(doc.statut), couleurs[doc.statut] || "gray", `statut,=,${doc.statut}`];
	},
};
