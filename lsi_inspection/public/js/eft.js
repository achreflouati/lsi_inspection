// EFT — boutons du chiffrage (moteur générique lsi_inspection.chiffrage.moteur). Aucun calcul ici : le serveur recalcule à
// l'enregistrement (brouillon). L'affichage ne modifie jamais le document.
const M = "lsi_inspection.chiffrage.moteur";

frappe.ui.form.on("EFT", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Ajouter depuis une gamme"), () => lsi_eft.ajouter_gamme(frm)).addClass("btn-primary");
			const P = __("Positions");
			frm.add_custom_button(__("Voir les ressources"), () => lsi_eft.ressources(frm), P);
			frm.add_custom_button(__("Historique d'achat"), () => lsi_eft.historique(frm), P);
			frm.add_custom_button(__("Demander un prix"), () => lsi_eft.demander_prix(frm), P);
			frm.add_custom_button(__("Répartir au prorata"), () => lsi_eft.prorata(frm), P);
			frm.add_custom_button(__("Charger un modèle"), () => lsi_eft.charger_modele(frm), __("Modèle"));
		}
		frm.add_custom_button(__("Enregistrer comme modèle"), () => lsi_eft.enregistrer_modele(frm), __("Modèle"));
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Créer le devis"), () =>
				frappe.call({ method: `${M}.creer_devis`, args: { eft: frm.doc.name }, freeze: true }).then((r) =>
					frappe.set_route("Form", "Quotation", r.message)
				), __("Créer"));
		}
		if (frm.doc.cout_incomplet) {
			frm.dashboard.set_headline(`<span class="text-danger">${__("Coût incomplet : au moins une position a un coût manquant ou en attente.")}</span>`);
		}
	},
});

frappe.provide("lsi_eft");

lsi_eft.choisir_position = function (frm, filtre, titre, suite) {
	const options = (frm.doc.positions || []).filter(filtre).map((p) => ({
		value: p.numero,
		label: `${p.numero} — ${p.designation || p.item_code}${p.designation_2 ? " (" + p.designation_2 + ")" : ""}`,
	}));
	if (!options.length) return frappe.msgprint(__("Aucune position concernée."));
	frappe.prompt([{ fieldname: "numero", fieldtype: "Select", label: __("Position"), options, reqd: 1 }], (v) => suite(v.numero), titre);
};

lsi_eft.ajouter_gamme = function (frm) {
	frappe.prompt(
		[
			{ fieldname: "gamme", fieldtype: "Link", options: "Gamme", label: __("Gamme (prestation)"), reqd: 1,
				get_query: () => ({ filters: { actif: 1 } }) },
			{ fieldname: "qty", fieldtype: "Float", label: __("Quantité"), default: 1, reqd: 1 },
		],
		(v) => frappe.call({ method: `${M}.ajouter_gamme`, args: { eft: frm.doc.name, prestation: v.gamme, qty: v.qty }, freeze: true })
			.then(() => frm.reload_doc()),
		__("Ajouter depuis une gamme"), __("Ajouter")
	);
};

lsi_eft.ressources = function (frm) {
	lsi_eft.choisir_position(frm, (p) => p.ressource_doctype || (p.source_cout || "").includes("pool"), __("Voir les ressources"), (numero) =>
		frappe.call({ method: `${M}.voir_ressources`, args: { eft: frm.doc.name, numero } }).then((r) => {
			const d = r.message;
			const esc = frappe.utils.escape_html;
			const options = [{ value: "", label: __("Règle du pool ({0})", [__(d.regle || "Plus élevé")]) }].concat(
				d.ressources.map((x) => ({
					value: x.name,
					label: `${x.titre}${d.voit_couts ? " — " + format_currency(x.cout) + " / " + __(d.uom_cout || "") : ""}`,
				}))
			);
			const dlg = new frappe.ui.Dialog({
				title: __("Ressources du pool {0}", [esc(d.pool || "")]),
				fields: [
					{ fieldtype: "HTML", options: `<p>${__("Coût retenu")} : <b>${format_currency(d.cout_retenu)}</b>${
						d.voit_couts ? "" : " — <span class='text-muted'>" + __("coûts individuels non visibles pour votre rôle") + "</span>"}</p>` },
					{ fieldname: "ressource", fieldtype: "Select", label: __("Ressource"), options, default: d.choisie || "" },
				],
				primary_action_label: __("Appliquer"),
				primary_action(v) {
					frappe.call({ method: `${M}.choisir_ressource`, args: { eft: frm.doc.name, numero, ressource: v.ressource || null }, freeze: true })
						.then(() => { dlg.hide(); frm.reload_doc(); });
				},
			});
			dlg.show();
		})
	);
};

lsi_eft.historique = function (frm) {
	lsi_eft.choisir_position(frm, () => true, __("Historique d'achat"), (numero) => {
		const p = frm.doc.positions.find((x) => x.numero === numero);
		frappe.call({ method: `${M}.historique_achat`, args: { item_code: p.item_code } }).then((r) => {
			const lignes = (r.message || []).map((x) =>
				`<tr><td>${__(x.doctype)}</td><td>${x.name}</td><td>${frappe.utils.escape_html(x.supplier || "")}</td>
				<td>${frappe.datetime.str_to_user(x.date)}</td><td>${format_currency(x.rate)}</td><td>${x.qty} ${x.uom || ""}</td></tr>`).join("");
			frappe.msgprint({ title: __("Historique d'achat : {0}", [p.item_code]), wide: true,
				message: lignes ? `<table class="table table-bordered table-sm"><tr><th>${__("Document")}</th><th></th><th>${__("Fournisseur")}</th>
				<th>${__("Date")}</th><th>${__("Prix")}</th><th>${__("Quantité")}</th></tr>${lignes}</table>` : __("Aucun achat.") });
		});
	});
};

lsi_eft.demander_prix = function (frm) {
	lsi_eft.choisir_position(frm, (p) => !p.cout_manuel, __("Demander un prix"), (numero) => {
		const dlg = new frappe.ui.Dialog({
			title: __("Demande de prix — position {0}", [numero]),
			fields: [{ fieldname: "fournisseurs", fieldtype: "Table MultiSelect", label: __("Fournisseurs"), options: "Request for Quotation Supplier",
				reqd: 1 }],
			primary_action_label: __("Créer la demande de prix"),
			primary_action(v) {
				const fournisseurs = (v.fournisseurs || []).map((x) => x.supplier);
				frappe.call({ method: `${M}.demander_prix`, args: { eft: frm.doc.name, numero, fournisseurs }, freeze: true }).then((r) => {
					dlg.hide();
					frappe.show_alert({ message: __("Demande de prix {0} créée (brouillon)", [r.message]), indicator: "green" });
					frm.reload_doc();
				});
			},
		});
		dlg.show();
	});
};

lsi_eft.prorata = function (frm) {
	lsi_eft.choisir_position(frm, (p) => p.mode === "Prix fixe", __("Répartir au prorata"), (numero) =>
		frappe.call({ method: `${M}.repartir_prorata`, args: { eft: frm.doc.name, numero }, freeze: true }).then(() => frm.reload_doc())
	);
};

lsi_eft.enregistrer_modele = function (frm) {
	frappe.prompt([{ fieldname: "titre", fieldtype: "Data", label: __("Titre du modèle"), reqd: 1 }], (v) =>
		frappe.call({ method: `${M}.enregistrer_modele`, args: { eft: frm.doc.name, titre: v.titre }, freeze: true }).then((r) =>
			frappe.show_alert({ message: __("Modèle {0} enregistré (sans coûts)", [r.message]), indicator: "green" })
		), __("Enregistrer comme modèle"));
};

lsi_eft.charger_modele = function (frm) {
	frappe.prompt([{ fieldname: "modele", fieldtype: "Link", options: "Modele EFT", label: __("Modèle"), reqd: 1 }], (v) =>
		frappe.call({ method: `${M}.charger_modele`, args: { eft: frm.doc.name, modele: v.modele }, freeze: true }).then(() => frm.reload_doc()),
		__("Charger un modèle"));
};
