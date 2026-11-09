// Chiffrage — actions des menus (Positions, Modèle) et « Créer l'offre client ».
frappe.provide("lsi_chiffrage");
lsi_chiffrage.M = "lsi_inspection.chiffrage.moteur";  // API publique du moteur (chiffrage/moteur/__init__.py)

lsi_chiffrage.choisir_position = function (frm, filtre, titre, suite) {
	const options = (frm.doc.positions || []).filter(filtre).map((p) => ({
		value: p.numero,
		label: `${p.numero} — ${p.designation || p.item_code}${p.designation_2 ? " (" + p.designation_2 + ")" : ""}`,
	}));
	if (!options.length) return frappe.msgprint(__("Aucune position concernée."));
	frappe.prompt([{ fieldname: "numero", fieldtype: "Select", label: __("Position"), options, reqd: 1 }], (v) => suite(v.numero), titre);
};

lsi_chiffrage.ajouter_gamme = function (frm) {
	frappe.prompt(
		[
			{ fieldname: "gamme", fieldtype: "Link", options: "Gamme", label: __("Gamme (prestation)"), reqd: 1,
				get_query: () => ({ filters: { actif: 1 } }) },
			{ fieldname: "qty", fieldtype: "Float", label: __("Quantité"), default: 1, reqd: 1 },
		],
		(v) => frappe.call({ method: `${lsi_chiffrage.M}.ajouter_gamme`, args: { chiffrage: frm.doc.name, prestation: v.gamme, qty: v.qty }, freeze: true })
			.then(() => frm.reload_doc()),
		__("Ajouter depuis une gamme"), __("Ajouter")
	);
};

lsi_chiffrage.partager = function (frm) {
	const groupes = (frm.doc.groupes || []).map((g) => ({ value: g.numero, label: `${g.numero} — ${g.titre || ""}` }));
	if (!groupes.length) return frappe.msgprint(__("Aucun groupe."));
	const d = new frappe.ui.Dialog({
		title: __("Partager un groupe entre plusieurs prestations"),
		fields: [
			{ fieldname: "groupe", fieldtype: "Select", label: __("Groupe"), options: groupes, reqd: 1 },
			{ fieldname: "etapes", fieldtype: "MultiCheck", label: __("Prestations concernées (parts égales)"),
				options: (frm.doc.etapes || []).filter((e) => e.prestation).map((e) => ({ label: e.libelle || e.prestation, value: e.prestation })) },
		],
		primary_action_label: __("Partager"),
		primary_action(v) {
			frappe.call({ method: `${lsi_chiffrage.M}.partager_groupe`, args: { chiffrage: frm.doc.name, groupe: v.groupe, etapes: v.etapes }, freeze: true })
				.then(() => { d.hide(); frm.reload_doc(); });
		},
	});
	d.show();
};

lsi_chiffrage.ressources = function (frm) {
	lsi_chiffrage.choisir_position(frm, (p) => p.ressource_doctype || (p.source_cout || "").includes("pool"), __("Voir les ressources"), (numero) =>
		frappe.call({ method: `${lsi_chiffrage.M}.voir_ressources`, args: { chiffrage: frm.doc.name, numero } }).then((r) => {
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
					frappe.call({ method: `${lsi_chiffrage.M}.choisir_ressource`, args: { chiffrage: frm.doc.name, numero, ressource: v.ressource || null }, freeze: true })
						.then(() => { dlg.hide(); frm.reload_doc(); });
				},
			});
			dlg.show();
		})
	);
};

lsi_chiffrage.historique = function (frm) {
	lsi_chiffrage.choisir_position(frm, () => true, __("Historique d'achat"), (numero) => {
		const p = frm.doc.positions.find((x) => x.numero === numero);
		frappe.call({ method: `${lsi_chiffrage.M}.historique_achat`, args: { item_code: p.item_code } }).then((r) => {
			const lignes = (r.message || []).map((x) =>
				`<tr><td>${__(x.doctype)}</td><td>${x.name}</td><td>${frappe.utils.escape_html(x.supplier || "")}</td>
				<td>${frappe.datetime.str_to_user(x.date)}</td><td>${format_currency(x.rate)}</td><td>${x.qty} ${x.uom || ""}</td></tr>`).join("");
			frappe.msgprint({ title: __("Historique d'achat : {0}", [p.item_code]), wide: true,
				message: lignes ? `<table class="table table-bordered table-sm"><tr><th>${__("Document")}</th><th></th><th>${__("Fournisseur")}</th>
				<th>${__("Date")}</th><th>${__("Prix")}</th><th>${__("Quantité")}</th></tr>${lignes}</table>` : __("Aucun achat.") });
		});
	});
};

lsi_chiffrage.demander_prix = function (frm) {
	lsi_chiffrage.choisir_position(frm, (p) => !p.cout_manuel, __("Demander un prix"), (numero) => {
		const dlg = new frappe.ui.Dialog({
			title: __("Demande de prix — position {0}", [numero]),
			fields: [{ fieldname: "fournisseurs", fieldtype: "Table MultiSelect", label: __("Fournisseurs"), options: "Request for Quotation Supplier",
				reqd: 1 }],
			primary_action_label: __("Créer la demande de prix"),
			primary_action(v) {
				const fournisseurs = (v.fournisseurs || []).map((x) => x.supplier);
				frappe.call({ method: `${lsi_chiffrage.M}.demander_prix`, args: { chiffrage: frm.doc.name, numero, fournisseurs }, freeze: true }).then((r) => {
					dlg.hide();
					frappe.show_alert({ message: __("Demande de prix {0} créée (brouillon)", [r.message]), indicator: "green" });
					frm.reload_doc();
				});
			},
		});
		dlg.show();
	});
};

lsi_chiffrage.prorata = function (frm) {
	lsi_chiffrage.choisir_position(frm, (p) => p.mode === "Prix fixe", __("Répartir au prorata"), (numero) =>
		frappe.call({ method: `${lsi_chiffrage.M}.repartir_prorata`, args: { chiffrage: frm.doc.name, numero }, freeze: true }).then(() => frm.reload_doc())
	);
};

lsi_chiffrage.enregistrer_modele = function (frm) {
	frappe.prompt([{ fieldname: "titre", fieldtype: "Data", label: __("Titre du modèle"), reqd: 1 }], (v) =>
		frappe.call({ method: `${lsi_chiffrage.M}.enregistrer_modele`, args: { chiffrage: frm.doc.name, titre: v.titre }, freeze: true }).then((r) =>
			frappe.show_alert({ message: __("Modèle {0} enregistré (sans coûts)", [r.message]), indicator: "green" })
		), __("Enregistrer comme modèle"));
};

lsi_chiffrage.charger_modele = function (frm) {
	frappe.prompt([{ fieldname: "modele", fieldtype: "Link", options: "Modele EFT", label: __("Modèle"), reqd: 1 }], (v) =>
		frappe.call({ method: `${lsi_chiffrage.M}.charger_modele`, args: { chiffrage: frm.doc.name, modele: v.modele }, freeze: true }).then(() => frm.reload_doc()),
		__("Charger un modèle"));
};


lsi_chiffrage.offre_client = function (frm) {
	const esc = frappe.utils.escape_html;
	const vendues = (frm.doc.positions || []).filter((p) => !p.parente && p.item_code).sort((a, b) => (lsi_chiffrage.cle(a.numero) < lsi_chiffrage.cle(b.numero) ? -1 : 1));
	const sans_valeur = (p) => !flt(p.prix_unitaire);
	const d = new frappe.ui.Dialog({
		title: __("Créer l'offre client"), size: "extra-large",
		fields: [
			{ fieldname: "remise", fieldtype: "Percent", label: __("Remise (%)"), default: 0, description: __("Remise native du devis, sur le total net.") },
			{ fieldtype: "Column Break" },
			{ fieldname: "sans_valeur", fieldtype: "Check", label: __("Afficher les positions sans valeur"), default: 0 },
			{ fieldtype: "Section Break" },
			{ fieldname: "lignes_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Créer l'offre client"),
		primary_action(v) {
			const lignes = d.$wrapper.find(".lsi-oc:checked").map(function () { return $(this).data("name"); }).get();
			if (!lignes.length) return frappe.msgprint(__("Cochez au moins une ligne."));
			frappe.call({ method: "lsi_inspection.chiffrage.devis.creer_devis", args: { chiffrage: frm.doc.name, lignes, remise: v.remise || 0 }, freeze: true }).then((r) => {
				d.hide();
				frappe.set_route("Form", "Quotation", r.message);
			});
		},
	});
	const rendre = () => {
		const montrer = d.get_value("sans_valeur");
		const coches = new Set(d.$wrapper.find(".lsi-oc:checked").map(function () { return $(this).data("name"); }).get());
		const premier = !d.$wrapper.find(".lsi-oc").length;
		const lignes = vendues.filter((p) => montrer || !sans_valeur(p)).map((p) => {
			const ok = premier ? !sans_valeur(p) : coches.has(p.name);
			return `<tr><td><input type="checkbox" class="lsi-oc" data-name="${p.name}" ${ok ? "checked" : ""}></td>
				<td>${esc(p.numero || "")}</td><td><b>${esc(p.designation || p.item_code)}</b>${p.designation_2 ? `<div class="text-muted small">${esc(p.designation_2)}</div>` : ""}</td>
				<td class="text-right">${p.tarif ? __("tarif") : format_number(p.qty, null, 2)}</td><td>${esc(__(p.uom || ""))}</td>
				<td class="text-right">${format_number(p.prix_unitaire, null, 3)}</td><td class="text-right">${format_number(p.prix_total, null, 3)}</td></tr>`;
		}).join("");
		d.fields_dict.lignes_html.$wrapper.html(`<div style="max-height:55vh;overflow:auto"><table class="table table-bordered table-sm">
			<thead><tr><th><input type="checkbox" class="lsi-oc-tout" checked title="${__("Tout cocher / décocher")}"></th><th>${__("Pos")}</th><th>${__("Désignation")}</th>
			<th class="text-right">${__("Quantité")}</th><th>${__("Unité")}</th><th class="text-right">${__("Prix unitaire")}</th><th class="text-right">${__("Valeur")}</th></tr></thead>
			<tbody>${lignes || `<tr><td colspan="7" class="text-muted">${__("Aucune ligne vendue avec un prix.")}</td></tr>`}</tbody></table></div>
			<p class="text-muted small">${__("Seules les lignes cochées vont dans le devis. Les sous-lignes restent dans le chiffrage.")}</p>`);
		d.$wrapper.find(".lsi-oc-tout").on("change", function () { d.$wrapper.find(".lsi-oc").prop("checked", this.checked); });
	};
	d.fields_dict.sans_valeur.$input.on("change", rendre);
	d.show();
	rendre();
};
