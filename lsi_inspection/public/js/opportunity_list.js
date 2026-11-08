// Liste des opportunités : filtres « Département concerné » et « Pilote » (table enfant Departement Concerne).
// Filtres standard dont df.doctype est la table enfant : la liste les envoie tels quels ([table, champ, "=", valeur]).
// Le onload d'ERPNext (menus « Set as Open / Closed ») est conservé et appelé en premier.
(() => {
	const settings = (frappe.listview_settings["Opportunity"] = frappe.listview_settings["Opportunity"] || {});
	const onload_erpnext = settings.onload;
	settings.onload = function (listview) {
		if (onload_erpnext) onload_erpnext.call(this, listview);
		const zone = listview.filter_area && listview.filter_area.standard_filters_wrapper;
		[
			{ fieldname: "departement", label: __("Département concerné"), options: "Department" },
			{ fieldname: "pilote", label: __("Pilote"), options: "Employee" },
		].forEach((df) => {
			if (listview.page.fields_dict[df.fieldname]) return;
			listview.page.add_field(
				{
					...df,
					fieldtype: "Link",
					doctype: "Departement Concerne",
					condition: "=",
					is_filter: 1,
					onchange: () => listview.refresh(),
				},
				zone
			);
		});
	};
})();
