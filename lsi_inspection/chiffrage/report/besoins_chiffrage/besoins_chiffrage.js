// Besoins de l'EFT (calculés à partir des positions et sous-positions)
frappe.query_reports["Besoins Chiffrage"] = {
	filters: [{ fieldname: "chiffrage", label: __("Chiffrage (variante)"), fieldtype: "Link", options: "Chiffrage", reqd: 1 }],
};
