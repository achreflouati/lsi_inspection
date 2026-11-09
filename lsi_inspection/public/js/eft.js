// EFT (étude technique) — une par opportunité : faisabilité, demande du client, variantes de chiffrage et leur comparaison.
// Fichier chargé avant celui-ci (hooks.py, doctype_js) : commun/demande_client.js.
frappe.provide("lsi_eft");
lsi_eft.ETUDE = "lsi_inspection.chiffrage.etude";
lsi_eft.VARIANTES = "lsi_inspection.chiffrage.variantes";

frappe.ui.form.on("EFT", {
	refresh(frm) {
		lsi.demande_client.afficher(frm, frm.doc.opportunity);
		if (frm.is_new()) return;
		lsi_eft.comparaison(frm);
		if (frm.doc.docstatus < 2) {
			frm.add_custom_button(__("Nouvelle variante"), () => lsi_eft.nouvelle_variante(frm)).addClass("btn-primary");
		}
		if (frm.doc.faisabilite === "Non faisable") {
			frm.add_custom_button(__("Déclarer l'opportunité perdue"), () => lsi_eft.declarer_perdue(frm));
		}
	},
});

lsi_eft.nouvelle_variante = function (frm) {
	frappe.call({ method: `${lsi_eft.VARIANTES}.comparaison`, args: { eft: frm.doc.name } }).then((r) => {
		const sources = (r.message || []).filter((v) => v.docstatus < 2).map((v) => ({ value: v.name, label: `${v.variante} — ${v.libelle_variante || ""}` }));
		const d = new frappe.ui.Dialog({
			title: __("Nouvelle variante de chiffrage"),
			fields: [
				{ fieldname: "depart", fieldtype: "Select", label: __("Point de départ"), reqd: 1, default: "opportunite",
					options: [{ value: "vide", label: __("Vide") }, { value: "opportunite", label: __("Prestations de l'opportunité (gammes)") }]
						.concat(sources.length ? [{ value: "copie", label: __("Copie d'une variante") }] : []) },
				{ fieldname: "source", fieldtype: "Select", label: __("Variante à copier"), options: sources, depends_on: "eval:doc.depart==='copie'",
					mandatory_depends_on: "eval:doc.depart==='copie'", description: __("Lignes et prix repris ; coûts recalculés.") },
				{ fieldname: "libelle", fieldtype: "Data", label: __("Libellé"), description: __("Ex. « Avec inspecteur niveau III ». Vide : Variante A, B…") },
			],
			primary_action_label: __("Créer"),
			primary_action(v) {
				frappe.call({ method: `${lsi_eft.VARIANTES}.nouvelle_variante`, freeze: true,
					args: { eft: frm.doc.name, depart: v.depart, source: v.source, libelle: v.libelle } })
					.then((res) => { d.hide(); frappe.set_route("Form", "Chiffrage", res.message); });
			},
		});
		d.show();
	});
};

lsi_eft.comparaison = function (frm) {
	const f = frm.get_field("variantes_html");
	if (!f) return;
	const esc = frappe.utils.escape_html;
	const money = (v) => format_number(v, null, 3);
	frappe.call({ method: `${lsi_eft.VARIANTES}.comparaison`, args: { eft: frm.doc.name } }).then((r) => {
		const lignes = (r.message || []).map((v) => `<tr>
			<td><a href="/app/chiffrage/${encodeURIComponent(v.name)}"><b>${esc(v.variante || "")}</b></a></td><td>${esc(v.libelle_variante || "")}</td>
			<td>${esc(__(v.workflow_state || ""))}</td><td class="text-right">${money(v.total_cout)}</td><td class="text-right">${money(v.total_prix)}</td>
			<td class="text-right">${money(v.total_marge)}</td><td class="text-right">${format_number(v.taux_marge, null, 1)} %</td>
			<td>${(v.devis || []).map((q) => `<a href="/app/quotation/${encodeURIComponent(q.name)}">${esc(q.name)}</a> (${esc(__(q.status))})`).join("<br>")}</td></tr>`).join("");
		f.$wrapper.html(lignes ? `<div style="overflow-x:auto"><table class="table table-bordered table-sm">
			<thead><tr><th>${__("Variante")}</th><th>${__("Libellé")}</th><th>${__("Statut")}</th><th class="text-right">${__("Coût")}</th>
			<th class="text-right">${__("Prix")}</th><th class="text-right">${__("Marge")}</th><th class="text-right">${__("Marge %")}</th><th>${__("Devis")}</th></tr></thead>
			<tbody>${lignes}</tbody></table></div><p class="text-muted small">${__("Dernière version de chaque variante. Une seule variante peut être « Retenue ».")}</p>`
			: `<p class="text-muted">${__("Aucune variante : bouton « Nouvelle variante ».")}</p>`);
	});
};

lsi_eft.declarer_perdue = function (frm) {
	const d = new frappe.ui.Dialog({
		title: __("Déclarer l'opportunité {0} perdue", [frm.doc.opportunity]),
		fields: [
			{ fieldname: "motifs", fieldtype: "Table MultiSelect", label: __("Motifs de perte"), options: "Opportunity Lost Reason Detail", reqd: 1 },
			{ fieldname: "detail", fieldtype: "Small Text", label: __("Détail"), default: frm.doc.commentaire_faisabilite || frm.doc.motif_faisabilite || "" },
		],
		primary_action_label: __("Déclarer perdue"),
		primary_action(v) {
			frappe.call({ method: `${lsi_eft.ETUDE}.declarer_perdue`, freeze: true,
				args: { eft: frm.doc.name, motifs: (v.motifs || []).map((m) => m.lost_reason), detail: v.detail } })
				.then(() => { d.hide(); frappe.show_alert({ message: __("Opportunité déclarée perdue."), indicator: "orange" }); });
		},
	});
	d.show();
};
