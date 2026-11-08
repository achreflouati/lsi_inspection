// Besoins de l'EFT (calculés à partir des positions et sous-positions)
frappe.query_reports["Besoins EFT"] = {
	filters: [{ fieldname: "eft", label: __("EFT"), fieldtype: "Link", options: "EFT", reqd: 1 }],
};
