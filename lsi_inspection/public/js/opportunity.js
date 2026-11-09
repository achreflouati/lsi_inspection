// Opportunité — onglet « Suivi commercial » (moteur générique lsi_inspection.commercial.phases).
// Phases, responsables et événements se règlent sur le type d'opportunité : rien de métier ici.
frappe.provide("lsi.phases");

// départements concernés : une seule ligne principale (l'ancienne se décoche ; le serveur contrôle aussi)
frappe.ui.form.on("Departement Concerne", {
	principal(frm, cdt, cdn) {
		if (!locals[cdt][cdn].principal) return;
		(frm.doc.lsi_departements || []).forEach((r) => {
			if (r.name !== cdn && r.principal) frappe.model.set_value(r.doctype, r.name, "principal", 0);
		});
	},
});

frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		lsi.phases.durees(frm);
		lsi.devis_hors_eft(frm);
		if (!frm.is_new() && frappe.model.can_create("EFT")) {
			frm.add_custom_button(__("EFT"), () =>
				frappe.call({ method: "lsi_inspection.chiffrage.moteur.make_eft", args: { opportunity: frm.doc.name }, freeze: true })
					.then((r) => frappe.set_route("Form", "EFT", r.message)), __("Create"));
		}
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
					frm.add_custom_button(__("Terminer ma phase"), () => lsi.phases.terminer(frm, info)).addClass("btn-primary");
				}
			});
	},
});

lsi.phases.terminer = function (frm, info) {
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
			{ fieldname: "commentaire", fieldtype: "Small Text", label: __("Commentaire (facultatif)") },
		],
		primary_action_label: __("Terminer et passer la main"),
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
};

// ------------------------------------------------------------------ tableau « Durée par phase commerciale »
// Lu depuis le document (lsi_phases, lsi_historique_phases) : aucune requête, aucune valeur métier.
const COULEURS = {
	"Terminée": "green",
	"En cours": "orange",
	"À venir": "gray",
	"Sautée": "yellow",
	"Sautée (auto)": "yellow",
	"Annulée": "gray",
};

lsi.phases.heures = function (debut, fin) {
	if (!debut) return null;
	const a = frappe.datetime.str_to_obj(debut);
	const b = fin ? frappe.datetime.str_to_obj(fin) : new Date();
	return Math.max(0, (b - a) / 3600000);
};

lsi.phases.format_duree = function (h) {
	if (h === null || h === undefined) return "";
	return `${format_number(h, null, 1)} h · ${format_number(h / 24, null, 2)} j`;
};

lsi.phases.durees = function (frm) {
	const f = frm.get_field("lsi_durees_html");
	if (!f) return;
	const lignes = (frm.doc.lsi_phases || []).slice().sort((a, b) => (a.ordre || 0) - (b.ordre || 0));
	if (frm.is_new() || !lignes.length) {
		f.$wrapper.html(`<p class="text-muted">${__("Les phases commerciales démarrent à l'enregistrement de l'opportunité.")}</p>`);
		return;
	}
	const esc = frappe.utils.escape_html;
	const dt = (v) => (v ? frappe.datetime.str_to_user(v) : "");
	const histo = frm.doc.lsi_historique_phases || [];
	const maintenant = new Date();
	const termine_par = (l) => {
		if (!l.fin) return "";
		const h = histo.find((x) => x.date && x.date.slice(0, 19) === String(l.fin).slice(0, 19));
		return h && h.par ? frappe.user.full_name(h.par) : "";
	};
	const responsables = (l) =>
		(l.responsables || "")
			.split(", ")
			.filter((u) => u)
			.map((u) => frappe.user.full_name(u))
			.join(", ");
	const en_cours = lignes.find((l) => l.statut === "En cours");
	const corps = lignes
		.map((l) => {
			const retard = l.statut === "En cours" && l.echeance && frappe.datetime.str_to_obj(l.echeance) < maintenant;
			const pastille = retard ? "red" : COULEURS[l.statut] || "gray";
			const bulle = l.commentaire ? ` title="${esc(l.commentaire)}"` : "";
			return `<tr${en_cours && l.name === en_cours.name ? ' style="font-weight:600"' : ""}>
				<td>${esc(__(l.phase))}${l.obligatoire ? " *" : ""}${
				l.hors_parcours ? ` <span class="text-muted">(${__("retirée du parcours")})</span>` : ""
			}</td>
				<td><span class="indicator-pill ${pastille}"${bulle}>${esc(__(l.statut))}${retard ? " — " + __("en retard") : ""}</span></td>
				<td>${dt(l.debut)}</td><td>${dt(l.fin)}</td>
				<td>${lsi.phases.format_duree(lsi.phases.heures(l.debut, l.fin))}${
				l.statut === "En cours" ? ` <span class="text-muted">(${__("jusqu'à maintenant")})</span>` : ""
			}</td>
				<td>${l.duree_cible ? l.duree_cible + " j" : ""}</td><td>${dt(l.echeance)}</td>
				<td>${esc(l.evenement_fin || "")}</td><td>${esc(responsables(l))}</td><td>${esc(termine_par(l))}</td></tr>`;
		})
		.join("");
	const fins = lignes.filter((l) => l.fin).map((l) => l.fin).sort();
	const fin_totale = en_cours || !fins.length ? null : fins[fins.length - 1];
	const total = lsi.phases.heures(frm.doc.creation, fin_totale);
	f.$wrapper.html(`<p class="text-muted" style="margin-bottom:4px">${__("Parcours du type « {0} »", [
		esc(frm.doc.opportunity_type || "—"),
	])}</p>
		<table class="table table-bordered table-sm" style="font-size:12px">
		<thead><tr><th>${__("Phase commerciale")}</th><th>${__("Statut")}</th><th>${__("Début")}</th><th>${__("Fin")}</th>
		<th>${__("Durée")}</th><th>${__("Cible")}</th><th>${__("Échéance")}</th><th>${__("Fin sur")}</th><th>${__("Responsable")}</th>
		<th>${__("Terminé par")}</th></tr></thead><tbody>${corps}
		<tr style="font-weight:700"><td colspan="4">${__("Durée totale depuis la création")}</td>
		<td>${lsi.phases.format_duree(total)}</td><td colspan="5"></td></tr></tbody></table>
		<p class="text-muted small">${__(
			"* phase obligatoire (ne peut pas être sautée à la main). Survol d'une phase sautée : le document qui a provoqué le saut."
		)}</p>`);
};

// Le devis se crée depuis l'EFT (« Créer le devis »). Le bouton natif Créer > Devis de l'opportunité (et le « + » Devis des
// connexions) ne sont visibles qu'avec le rôle « Devis hors EFT » : réactivable en donnant ce rôle, sans toucher au code.
lsi.devis_hors_eft = function (frm) {
	if (frappe.user.has_role("Devis hors EFT")) return;
	frm.remove_custom_button(__("Quotation"), __("Create"));
	setTimeout(() => $(frm.wrapper).find('.document-link[data-doctype="Quotation"] .btn-new').hide(), 500);
};
