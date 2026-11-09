// EFT — boutons du chiffrage (moteur générique lsi_inspection.chiffrage.moteur). Aucun calcul ici : le serveur recalcule à
// l'enregistrement (brouillon). L'affichage ne modifie jamais le document.
const M = "lsi_inspection.chiffrage.moteur";

frappe.ui.form.on("EFT", {
	setup(frm) {
		// colonne « Prestation » : seulement les prestations (étapes) de l'EFT
		frm.set_query("etape", "positions", () => ({ filters: { name: ["in", (frm.doc.etapes || []).map((e) => e.prestation).filter((x) => x)] } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Ajouter depuis une gamme"), () => lsi_eft.ajouter_gamme(frm)).addClass("btn-primary");
			const P = __("Positions");
			frm.add_custom_button(__("Voir les ressources"), () => lsi_eft.ressources(frm), P);
			frm.add_custom_button(__("Historique d'achat"), () => lsi_eft.historique(frm), P);
			frm.add_custom_button(__("Demander un prix"), () => lsi_eft.demander_prix(frm), P);
			frm.add_custom_button(__("Répartir au prorata"), () => lsi_eft.prorata(frm), P);
			frm.add_custom_button(__("Partager un groupe"), () => lsi_eft.partager(frm), P);
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

lsi_eft.partager = function (frm) {
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
			frappe.call({ method: `${M}.partager_groupe`, args: { eft: frm.doc.name, groupe: v.groupe, etapes: v.etapes }, freeze: true })
				.then(() => { d.hide(); frm.reload_doc(); });
		},
	});
	d.show();
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

// ------------------------------------------------------------------ temps réel, couleurs, synthèse (comme tic_demo)
// Le calcul est fait par le MÊME moteur que l'enregistrement (méthode « apercu », sans enregistrer) : pools, conversions, stock.
const LSI_COULEURS = ["#2563eb", "#16a34a", "#9333ea", "#ea580c", "#db2777", "#0891b2", "#ca8a04", "#4b5563"];
const LSI_CHAMPS_POSITION = ["etape", "item_code", "type_position", "qty", "uom", "prix_unitaire", "cout_unitaire", "cout_manuel", "parente", "groupe", "numero"];

lsi_eft.couleur_etape = function (frm, etape) {
	const i = (frm.doc.etapes || []).findIndex((e) => e.prestation === etape);
	return i < 0 ? null : LSI_COULEURS[i % LSI_COULEURS.length];
};

lsi_eft.etape_de = function (frm, p) {
	// étape principale d'une position (même règle que le serveur) : parente → répartition de la position, puis du groupe, sinon étape unique
	if (p.__etape) return p.__etape;
	const par_num = Object.fromEntries((frm.doc.positions || []).map((x) => [x.numero, x]));
	if (p.parente && par_num[p.parente]) return lsi_eft.etape_de(frm, par_num[p.parente]);
	for (const cible of [p.numero, p.groupe]) {
		const r = (frm.doc.repartitions || []).find((x) => String(x.cible) === String(cible) && x.etape);
		if (r) return r.etape;
	}
	return (frm.doc.etapes || []).length === 1 ? frm.doc.etapes[0].prestation : null;
};

lsi_eft.colorer = function (frm) {
	if (!document.getElementById("lsi-eft-style")) {
		$(`<style id="lsi-eft-style">
			.grid-row.lsi-manquant > .data-row { background: var(--bg-orange, #fff1e7); }
			.grid-row.lsi-perte > .data-row { background: var(--bg-red, #fde8e8); }
			.grid-row.lsi-tarif > .data-row { color: var(--text-muted); font-style: italic; }
			.grid-row.lsi-sous > .data-row .static-area { opacity: .85; }
			.lsi-synth td, .lsi-synth th { padding: 4px 8px; font-size: 12px; }
			.lsi-synth .manquant { color: #c2410c; font-weight: 600; } .lsi-synth .perte { color: #b91c1c; font-weight: 600; }
		</style>`).appendTo("head");
	}
	const peindre = (champ, couleur_de, classes_de) => {
		const grid = frm.fields_dict[champ] && frm.fields_dict[champ].grid;
		(grid ? grid.grid_rows : []).forEach((r) => {
			const c = couleur_de(r.doc);
			$(r.wrapper).find("> .data-row").css("border-left", c ? `5px solid ${c}` : "");
			const cl = classes_de ? classes_de(r.doc) : {};
			Object.entries(cl).forEach(([k, v]) => $(r.wrapper).toggleClass(k, !!v));
		});
	};
	peindre("etapes", (e) => lsi_eft.couleur_etape(frm, e.prestation));
	peindre("groupes", (g) => lsi_eft.couleur_etape(frm, lsi_eft.etape_de(frm, { numero: null, groupe: g.numero })));
	peindre("positions", (p) => lsi_eft.couleur_etape(frm, lsi_eft.etape_de(frm, p)), (p) => ({
		"lsi-manquant": p.cout_manquant || p.cout_en_attente,
		"lsi-perte": !p.parente && flt(p.prix_total) > 0 && flt(p.marge) < 0,
		"lsi-tarif": p.tarif,
		"lsi-sous": !!p.parente,
	}));
	lsi_eft.synthese(frm);
};

lsi_eft.synthese = function (frm) {
	// comme tic_demo : synthèse par type de position, par prestation (+ total), puis besoins en quantités par prestation
	const f = frm.get_field("synthese_html");
	if (!f) return;
	const esc = frappe.utils.escape_html, m = (v) => format_currency(v, frappe.defaults.get_default("currency"));
	const positions = frm.doc.positions || [];
	const vendues = positions.filter((p) => !p.parente && p.item_code);
	if (!vendues.length) {
		f.$wrapper.html("");  // le message d'accueil est affiché par le tableau de chiffrage
		return;
	}
	const qtes = (lignes) => {
		const par_uom = {};
		lignes.forEach((p) => { if (flt(p.qty)) par_uom[p.uom || ""] = (par_uom[p.uom || ""] || 0) + flt(p.qty); });
		return Object.entries(par_uom).map(([u, q]) => `${format_number(q, null, 2)} ${esc(__(u))}`).join(", ");
	};
	const etape_de = (p) => p.etape || lsi_eft.etape_de(frm, p);
	const libelle = (e) => ((frm.doc.etapes || []).find((x) => x.prestation === e) || {}).libelle || e || __("(sans prestation)");
	const ligne = (titre, q, c, pr, opts = {}) => {
		const pb = flt(pr) - flt(c), taux = flt(pr) ? (pb / flt(pr)) * 100 : 0;
		return `<tr style="${opts.gras ? "font-weight:700;" : ""}${opts.couleur ? `border-left:5px solid ${opts.couleur}` : ""}">
			<td>${titre}</td><td>${q || ""}</td>
			<td class="text-right ${opts.manquant ? "manquant" : ""}">${m(c)}${opts.manquant ? " ⚠" : ""}</td>
			<td class="text-right">${m(pr)}</td><td class="text-right ${pb < 0 ? "perte" : ""}">${m(pb)}</td>
			<td class="text-right ${pb < 0 ? "perte" : ""}">${format_number(taux, null, 1)} %</td></tr>`;
	};
	const entete = (premier) => `<thead><tr><th>${premier}</th><th>${__("Quantités")}</th><th class="text-right">${__("Coût")}</th>
		<th class="text-right">${__("Prix")}</th><th class="text-right">${__("Produit brut")}</th>
		<th class="text-right">${__("Marge sur prix de vente (%)")}</th></tr></thead>`;
	const manquant = (lignes) => lignes.some((p) => p.cout_manquant || p.cout_en_attente);

	// 1. par type de position (lignes vendues)
	const types = [...new Set(vendues.map((p) => p.type_position || ""))];
	const t1 = types.map((t) => {
		const l = vendues.filter((p) => (p.type_position || "") === t);
		return ligne(esc(t), qtes(l), l.reduce((s, p) => s + flt(p.cout_total), 0), l.reduce((s, p) => s + flt(p.prix_total), 0), { manquant: manquant(l) });
	}).join("");

	// 2. par prestation (coût et prix répartis : totaux par étape) + total
	const t2 = (frm.doc.totaux_etapes || []).map((t) => {
		const l = vendues.filter((p) => etape_de(p) === t.etape);
		return ligne(esc(libelle(t.etape)), qtes(l), t.cout_total, t.prix_total, { manquant: manquant(l), couleur: lsi_eft.couleur_etape(frm, t.etape) });
	}).join("") + ligne(__("Total de l'EFT"), "", frm.doc.total_cout, frm.doc.total_prix, { gras: true, manquant: frm.doc.cout_incomplet });

	// 3. besoins (quantités) par prestation : ressources réelles = lignes à coût vendues et sous-positions (pas les prix fixes)
	const besoins = positions.filter((p) => p.item_code && flt(p.qty) && p.mode !== "Prix fixe");
	const etapes = [...new Set(besoins.map((p) => etape_de(p)))];
	const t3 = etapes.map((e) => {
		const cumul = {};
		besoins.filter((p) => etape_de(p) === e).forEach((p) => {
			const k = [p.type_position || "", p.item_code, p.uom || ""].join("|");
			cumul[k] = (cumul[k] || 0) + flt(p.qty);
		});
		const rows = Object.entries(cumul).map(([k, q]) => {
			const [t, a, u] = k.split("|");
			return `<tr><td>${esc(t)}</td><td>${esc(a)}</td><td class="text-right">${format_number(q, null, 2)}</td><td>${esc(__(u))}</td></tr>`;
		}).join("");
		const nb = besoins.filter((p) => etape_de(p) === e).length;
		return `<p style="margin:12px 0 4px; font-weight:600; border-left:5px solid ${lsi_eft.couleur_etape(frm, e) || "transparent"}; padding-left:6px">
			${esc(libelle(e))} — ${nb} ${__("position(s)")}</p>
			<table class="table table-bordered lsi-synth"><thead><tr><th>${__("Type")}</th><th>${__("Article")}</th>
			<th class="text-right">${__("Quantité")}</th><th>${__("Unité")}</th></tr></thead><tbody>${rows}</tbody></table>`;
	}).join("");

	const taux = flt(frm.doc.total_prix) ? (flt(frm.doc.total_marge) / flt(frm.doc.total_prix)) * 100 : 0;
	f.$wrapper.html(`
		<table class="table table-bordered lsi-synth">${entete(__("Type de position"))}<tbody>${t1}</tbody></table>
		<table class="table table-bordered lsi-synth">${entete(__("Prestation"))}<tbody>${t2}</tbody></table>
		<p class="text-muted small">${__("Taux de marge de l'EFT : {0} % (marge sur prix de vente : produit brut ÷ prix).", [format_number(taux, null, 2)])}
		${__("Lignes : orange = coût manquant ou en attente ; rouge = vendue à perte ; gris = tarif à quantité 0. Bande de couleur = prestation.")}</p>
		<h5 style="margin-top:18px">${__("Synthèse des besoins (quantités)")}</h5>${t3}`);
};

lsi_eft.apercu = frappe.utils.debounce(function (frm) {
	if (frm.doc.docstatus !== 0) return;
	frappe.call({ method: `${M}.apercu`, args: { doc: frm.doc }, type: "POST" }).then((r) => {
		const d = r.message || {};
		if (d.erreur) {
			frappe.show_alert({ message: d.erreur, indicator: "orange" }, 6);
			return;
		}
		(frm.doc.positions || []).forEach((p) => {
			const v = (d.positions || {})[p.name];
			if (v) { Object.assign(p, v); p.__etape = v.etape_principale; }
		});
		(frm.doc.groupes || []).forEach((g) => Object.assign(g, (d.groupes || {})[g.name] || {}));
		frm.doc.totaux_etapes = (d.totaux_etapes || []).map((t, i) => Object.assign({ doctype: "EFT Total Etape", idx: i + 1, parentfield: "totaux_etapes" }, t));
		["total_cout", "total_prix", "total_marge", "taux_marge", "cout_incomplet"].forEach((c) => (frm.doc[c] = d[c]));
		["positions", "groupes", "totaux_etapes", "total_cout", "total_prix", "total_marge", "taux_marge", "cout_incomplet"].forEach((c) => frm.refresh_field(c));
		lsi_eft.colorer(frm);
		lsi_eft.tableau(frm);
	});
}, 400);

frappe.ui.form.on("EFT", {
	refresh(frm) { setTimeout(() => lsi_eft.colorer(frm), 300); },
	positions_on_form_rendered(frm) { lsi_eft.colorer(frm); },
});
frappe.ui.form.on("EFT Position", Object.assign(
	Object.fromEntries(LSI_CHAMPS_POSITION.map((c) => [c, (frm) => lsi_eft.apercu(frm)])),
	{ positions_remove: (frm) => lsi_eft.apercu(frm) }
));
frappe.ui.form.on("EFT Repartition", { cible: (frm) => lsi_eft.apercu(frm), etape: (frm) => lsi_eft.apercu(frm), part: (frm) => lsi_eft.apercu(frm),
	repartitions_remove: (frm) => lsi_eft.apercu(frm) });

// ------------------------------------------------------------------ tableau hiérarchique (comme l'Excel de TIC / MARI)
// Groupe (en-tête coloré) → positions vendues → sous-positions (décalées, repliables) → sous-total ; total de l'EFT.
// Quantité et prix modifiables directement ; « + ligne » par groupe ; icônes modifier / sous-position / supprimer. Le calcul reste celui du serveur.
lsi_eft.replies = new Set();
lsi_eft.vue = (() => { try { return localStorage.getItem("lsi_eft_vue") || "toutes"; } catch (e) { return "toutes"; } })();
lsi_eft.cle = (n) => String(n || "~").split(".").map((x) => (isNaN(x) ? x : String(x).padStart(4, "0"))).join(".");

// Colonnes : TOUS les champs d'EFT Position (définition du doctype), les principaux d'abord ; un champ ajouté plus tard apparaît seul.
// Chaque colonne suit les permissions natives du champ (permlevel) : masquée, lecture seule ou modifiable.
const LSI_PRINCIPALES = ["type_position", "qty", "uom", "cout_unitaire", "cout_total", "prix_unitaire", "prix_total", "marge", "taux_marge", "stock_disponible"];
const LSI_HORS_COLONNES = ["numero", "item_code", "designation", "designation_2", "groupe", "parente"];  // affichés par la structure (N°, Article, hiérarchie)
const LSI_SAISIE = ["Float", "Currency", "Int", "Percent", "Data", "Check"];
const LSI_TOTAUX = ["cout_total", "prix_total", "marge", "taux_marge"];

lsi_eft.colonnes = function (frm) {
	const meta = frappe.get_meta("EFT Position");
	const champs = meta.fields.filter((df) => !frappe.model.layout_fields.includes(df.fieldtype) && !LSI_HORS_COLONNES.includes(df.fieldname));
	const ordre = (df) => { const i = LSI_PRINCIPALES.indexOf(df.fieldname); return i < 0 ? 100 + champs.indexOf(df) : i; };
	let cols = champs.slice().sort((a, b) => ordre(a) - ordre(b))
		.filter((df) => frappe.perm.get_field_display_status(df, null, frm.perm) !== "None");
	if (lsi_eft.vue === "essentielles") cols = cols.filter((df) => LSI_PRINCIPALES.includes(df.fieldname));
	return cols;
};

lsi_eft.cellule = function (frm, df, p, sous, ed) {
	const esc = frappe.utils.escape_html;
	const v = p[df.fieldname];
	const c = df.fieldname;
	if (sous && ["prix_unitaire", "prix_total", "marge", "taux_marge", "prix_conseille"].includes(c)) return `<td class="text-right text-muted">—</td>`;
	const droit = frappe.perm.get_field_display_status(df, p, frm.perm);
	const modifiable = ed && droit === "Write" && !cint(df.read_only) && LSI_SAISIE.includes(df.fieldtype);
	const calcule = c === "cout_unitaire" && !cint(p.cout_manuel);  // coût calculé : modifiable seulement en « Coût manuel »
	const num = ["Float", "Currency", "Int", "Percent"].includes(df.fieldtype);
	let html;
	if (modifiable && !calcule && df.fieldtype === "Check") {
		html = `<input type="checkbox" class="lsi-chk" data-name="${p.name}" data-champ="${c}" ${cint(v) ? "checked" : ""}>`;
	} else if (modifiable && !calcule) {
		html = `<input class="form-control input-xs lsi-in ${num ? "lsi-num" : ""}" data-name="${p.name}" data-champ="${c}" data-type="${df.fieldtype}" value="${num ? flt(v) : esc(v || "")}">`;
	} else if (df.fieldtype === "Check") {
		html = cint(v) ? "✓" : "";
	} else if (df.fieldtype === "Currency") {
		html = format_number(v, null, 3);
	} else if (df.fieldtype === "Percent") {
		html = sous || (c === "taux_marge" && !flt(p.prix_total)) ? "" : format_number(v, null, 1) + " %";
	} else if (num) {
		html = c === "stock_disponible" && !flt(v) ? "" : format_number(v, null, df.fieldtype === "Int" || c === "stock_disponible" ? 0 : 2);
	} else {
		html = `<span class="lsi-texte">${esc(__(v || ""))}</span>`;
	}
	if (c === "cout_unitaire") {
		html += p.cout_manquant ? " ⚠" : "";
		html += p.cout_en_attente ? ` <span class="text-muted small">(attente)</span>` : "";
	}
	if (c === "qty" && p.tarif) html += `<div class="text-muted small">${__("tarif")}</div>`;
	const classes = [num ? "text-right" : "", c === "cout_total" && p.mode === "Prix fixe" ? "lsi-fort" : "",
		c === "taux_marge" && !sous && flt(p.prix_total) > 0 && flt(p.marge) < 0 ? "lsi-rouge" : ""].join(" ");
	const titre = ["cout_unitaire", "cout_total"].includes(c) ? ` title="${esc(p.source_cout || "")}"` : "";
	return `<td class="${classes}"${titre}>${html}</td>`;
};

lsi_eft.tableau = function (frm) {
	const f = frm.get_field("tableau_html");
	if (!f) return;
	const ed = frm.doc.docstatus === 0;
	const esc = frappe.utils.escape_html;
	const money = (v) => format_number(v, null, 3);
	const pos = frm.doc.positions || [];
	const enfants = {};
	pos.filter((p) => p.parente).forEach((p) => (enfants[p.parente] = enfants[p.parente] || []).push(p));
	const tri = (a, b) => (lsi_eft.cle(a.numero) < lsi_eft.cle(b.numero) ? -1 : 1);
	const groupes = (frm.doc.groupes || []).slice().sort((a, b) => flt(a.numero) - flt(b.numero));
	const cols = lsi_eft.colonnes(frm);
	const NB = cols.length + 3;

	const ligne = (p, sous) => {
		const kids = (enfants[p.numero] || []).sort(tri);
		const replie = lsi_eft.replies.has(p.name);
		const perte = !sous && flt(p.prix_total) > 0 && flt(p.marge) < 0;
		const classe = [p.cout_manquant || p.cout_en_attente ? "lsi-l-manquant" : "", perte ? "lsi-l-perte" : "", p.tarif ? "lsi-l-tarif" : "",
			sous ? "lsi-l-sous" : "", p.mode === "Prix fixe" ? "lsi-l-fixe" : ""].join(" ");
		const bascule = kids.length ? `<a class="lsi-toggle" data-name="${p.name}">${replie ? "▸" : "▾"}</a> ` : "";
		const actions = ed ? `<a class="lsi-edit" data-name="${p.name}" title="${__("Modifier")}">${frappe.utils.icon("edit", "xs")}</a>
			${p.mode === "Prix fixe" ? `<a class="lsi-sous" data-name="${p.name}" title="${__("Ajouter une sous-position")}">${frappe.utils.icon("add", "xs")}</a>` : ""}
			<a class="lsi-del" data-name="${p.name}" title="${__("Supprimer")}">${frappe.utils.icon("delete", "xs")}</a>` : "";
		let html = `<tr class="${classe}">
			<td class="lsi-fixe1">${bascule}${esc(p.numero || __("(nouveau)"))}</td>
			<td class="lsi-fixe2" style="${sous ? "padding-left:28px" : ""}">${sous ? "↳ " : ""}<b>${esc(p.designation || p.item_code || __("(article à choisir)"))}</b>
				${p.designation_2 ? `<div class="text-muted small">${esc(p.designation_2)}</div>` : ""}</td>
			${cols.map((df) => lsi_eft.cellule(frm, df, p, sous, ed)).join("")}
			<td class="lsi-actions">${actions}</td></tr>`;
		if (!replie) kids.forEach((k) => (html += ligne(k, true)));
		return html;
	};
	const ligne_total = (classe, style, libelle, valeurs) => {
		const cellules = cols.map((df) => {
			if (!LSI_TOTAUX.includes(df.fieldname)) return "<td></td>";
			const v = valeurs[df.fieldname];
			const rouge = df.fieldname === "taux_marge" && flt(valeurs.marge) < 0 ? "lsi-rouge" : "";
			return `<td class="text-right ${rouge}">${df.fieldtype === "Percent" ? format_number(v, null, 1) + " %" : money(v)}</td>`;
		}).join("");
		return `<tr class="${classe}" style="${style}"><td class="lsi-fixe1"></td><td class="lsi-fixe2">${libelle}</td>${cellules}<td></td></tr>`;
	};

	let corps = "";
	groupes.forEach((g) => {
		const etape = lsi_eft.etape_de(frm, { numero: null, groupe: g.numero });
		const coul = lsi_eft.couleur_etape(frm, etape) || "#888";
		const lignes = pos.filter((p) => !p.parente && String(p.groupe) === String(g.numero)).sort(tri);
		corps += `<tr class="lsi-g"><td colspan="${NB}" style="border-left:6px solid ${coul}"><span class="lsi-colle"><b>${esc(g.numero)} — ${esc(g.titre || "")}</b>
			<span class="text-muted small"> · ${esc(g.etapes || "")}</span></span></td></tr>`;
		lignes.forEach((p) => (corps += ligne(p, false)));
		if (ed) corps += `<tr><td colspan="${NB}"><a class="lsi-add lsi-colle" data-groupe="${esc(g.numero)}">+ ${__("ligne")}</a></td></tr>`;
		const taux = flt(g.prix_total) ? (flt(g.marge) / flt(g.prix_total)) * 100 : 0;
		corps += ligne_total("lsi-st", `border-left:6px solid ${coul}`, `${__("Sous-total")} ${esc(g.numero)}`,
			{ cout_total: g.cout_total, prix_total: g.prix_total, marge: g.marge, taux_marge: taux });
	});
	const orphelines = pos.filter((p) => !p.parente && !groupes.some((g) => String(g.numero) === String(p.groupe)));
	if (orphelines.length) {
		corps += `<tr class="lsi-g"><td colspan="${NB}"><b class="lsi-colle">${__("Lignes à rattacher (choisir la prestation)")}</b></td></tr>`;
		orphelines.forEach((p) => (corps += ligne(p, false)));
	}
	corps += ligne_total("lsi-tot", "", `${__("Total de l'EFT")}${frm.doc.cout_incomplet ? " ⚠" : ""}`,
		{ cout_total: frm.doc.total_cout, prix_total: frm.doc.total_prix, marge: frm.doc.total_marge, taux_marge: frm.doc.taux_marge });

	const devise = esc(frappe.defaults.get_default("currency") || "");
	const entetes = cols.map((df) => `<th class="${["Float", "Currency", "Int", "Percent"].includes(df.fieldtype) ? "text-right" : ""}"
		title="${esc(__(df.description || ""))}">${esc(__(df.label))}${df.fieldtype === "Currency" ? ` <span class="text-muted">(${devise})</span>` : ""}</th>`).join("");
	const bascule_vue = `<a class="lsi-vue">${lsi_eft.vue === "essentielles" ? __("Afficher toutes les colonnes") : __("Colonnes essentielles seulement")}</a>`;
	f.$wrapper.html(groupes.length || pos.length ? `<div class="text-right small" style="margin-bottom:4px">${bascule_vue}</div>
		<div class="lsi-tab-wrap"><table class="table table-bordered lsi-tab"><thead><tr>
		<th class="lsi-fixe1">${__("N°")}</th><th class="lsi-fixe2">${__("Article")}</th>${entetes}<th></th>
		</tr></thead><tbody>${corps}</tbody></table></div>
		<p class="text-muted small">${__("Faites défiler horizontalement pour voir toutes les colonnes (N° et Article restent visibles). ⚠ coût manquant · (attente) en attente d'une offre fournisseur · survol du coût : sa source. Prix fixe : coût total = somme de ses sous-positions.")}
		<a class="lsi-grille">${__("Afficher / masquer la grille détaillée")}</a></p>`
		: `<p class="text-muted">${__("Ajoutez une prestation (bouton « Ajouter depuis une gamme ») pour commencer le chiffrage.")}</p>`);

	const w = f.$wrapper;
	w.find(".lsi-in").on("change", function () {
		const num = ["Float", "Currency", "Int", "Percent"].includes($(this).data("type"));
		frappe.model.set_value("EFT Position", $(this).data("name"), $(this).data("champ"), num ? flt($(this).val()) : $(this).val());
	});
	w.find(".lsi-chk").on("change", function () {
		frappe.model.set_value("EFT Position", $(this).data("name"), $(this).data("champ"), this.checked ? 1 : 0);
	});
	w.find(".lsi-vue").on("click", () => {
		lsi_eft.vue = lsi_eft.vue === "essentielles" ? "toutes" : "essentielles";
		try { localStorage.setItem("lsi_eft_vue", lsi_eft.vue); } catch (e) { /* préférence locale facultative */ }
		lsi_eft.tableau(frm);
	});
	w.find(".lsi-toggle").on("click", function () {
		const n = $(this).data("name");
		lsi_eft.replies.has(n) ? lsi_eft.replies.delete(n) : lsi_eft.replies.add(n);
		lsi_eft.tableau(frm);
	});
	w.find(".lsi-edit").on("click", function () { lsi_eft.modifier_ligne(frm, $(this).data("name")); });
	w.find(".lsi-del").on("click", function () { lsi_eft.supprimer_ligne(frm, $(this).data("name")); });
	w.find(".lsi-add").on("click", function () { lsi_eft.ajouter_ligne(frm, String($(this).data("groupe")), null); });
	w.find(".lsi-sous").on("click", function () {
		const p = locals["EFT Position"][$(this).data("name")];
		lsi_eft.ajouter_ligne(frm, String(p.groupe), p.numero);
	});
	w.find(".lsi-grille").on("click", () => {
		const cache = frm.get_field("positions").df.hidden;
		frm.toggle_display(["positions", "groupes"], !!cache);
	});
};

lsi_eft.ajouter_ligne = function (frm, groupe, parente) {
	const d = new frappe.ui.Dialog({
		title: parente ? __("Sous-position de la ligne {0}", [parente]) : __("Nouvelle ligne — groupe {0}", [groupe]),
		fields: [
			{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: __("Article"), reqd: 1 },
			{ fieldname: "designation_2", fieldtype: "Data", label: __("Désignation 2") },
			{ fieldname: "qty", fieldtype: "Float", label: __("Quantité"), default: 1 },
			{ fieldname: "uom", fieldtype: "Link", options: "UOM", label: __("Unité"), description: __("Vide : unité de l'article") },
			{ fieldname: "type_position", fieldtype: "Link", options: "Type Position", label: __("Type de position"),
				description: __("Vide : type de l'article ou de son groupe") },
			{ fieldname: "prix_unitaire", fieldtype: "Currency", label: __("Prix unitaire"), hidden: parente ? 1 : 0 },
		],
		primary_action_label: __("Ajouter"),
		primary_action(v) {
			frappe.db.get_value("Item", v.item_code, "stock_uom").then((r) => {
				const row = frappe.model.add_child(frm.doc, "EFT Position", "positions");
				const g = (frm.doc.groupes || []).find((x) => String(x.numero) === groupe);
				Object.assign(row, { groupe, parente: parente || null, item_code: v.item_code, designation_2: v.designation_2, qty: flt(v.qty),
					uom: v.uom || (r.message || {}).stock_uom, type_position: v.type_position, prix_unitaire: parente ? 0 : flt(v.prix_unitaire),
					etape: lsi_eft.etape_de(frm, { numero: null, groupe }) || null });
				frm.refresh_field("positions");
				frm.dirty();
				d.hide();
				lsi_eft.apercu(frm);
			});
		},
	});
	d.show();
};

lsi_eft.modifier_ligne = function (frm, name) {
	const p = locals["EFT Position"][name];
	const champs = ["item_code", "designation_2", "type_position", "qty", "uom", "cout_manuel", "cout_unitaire", "prix_unitaire"];
	const d = new frappe.ui.Dialog({
		title: __("Ligne {0}", [p.numero || ""]),
		fields: [
			{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: __("Article"), reqd: 1, default: p.item_code },
			{ fieldname: "designation_2", fieldtype: "Data", label: __("Désignation 2"), default: p.designation_2 },
			{ fieldname: "type_position", fieldtype: "Link", options: "Type Position", label: __("Type de position"), default: p.type_position },
			{ fieldname: "qty", fieldtype: "Float", label: __("Quantité"), default: p.qty },
			{ fieldname: "uom", fieldtype: "Link", options: "UOM", label: __("Unité"), default: p.uom },
			{ fieldname: "cout_manuel", fieldtype: "Check", label: __("Coût saisi à la main"), default: p.cout_manuel },
			{ fieldname: "cout_unitaire", fieldtype: "Currency", label: __("Coût unitaire"), default: p.cout_unitaire, depends_on: "cout_manuel",
				description: esc_source(p.source_cout) },
			{ fieldname: "prix_unitaire", fieldtype: "Currency", label: __("Prix unitaire"), default: p.prix_unitaire, hidden: p.parente ? 1 : 0 },
		],
		primary_action_label: __("Appliquer"),
		primary_action(v) {
			champs.forEach((c) => { if (v[c] !== undefined && v[c] !== p[c]) frappe.model.set_value("EFT Position", name, c, v[c]); });
			d.hide();
		},
	});
	d.show();
};
const esc_source = (s) => (s ? __("Coût calculé : {0}", [frappe.utils.escape_html(s)]) : "");

lsi_eft.supprimer_ligne = function (frm, name) {
	const p = locals["EFT Position"][name];
	const kids = (frm.doc.positions || []).filter((x) => p.numero && x.parente === p.numero);
	frappe.confirm(kids.length ? __("Supprimer la ligne {0} et ses {1} sous-position(s) ?", [p.numero, kids.length]) : __("Supprimer la ligne {0} ?", [p.numero || ""]), () => {
		const a_retirer = new Set([name, ...kids.map((k) => k.name)]);
		frm.doc.positions = (frm.doc.positions || []).filter((x) => !a_retirer.has(x.name));
		frm.doc.positions.forEach((x, i) => (x.idx = i + 1));
		frm.refresh_field("positions");
		frm.dirty();
		lsi_eft.apercu(frm);
	});
};

frappe.ui.form.on("EFT", {
	refresh(frm) {
		if (!document.getElementById("lsi-tab-style")) {
			$(`<style id="lsi-tab-style">
				.lsi-tab td, .lsi-tab th { padding: 4px 6px !important; font-size: 12px; vertical-align: middle !important; }
				.lsi-tab td.text-right, .lsi-tab th, .lsi-tab .lsi-actions { white-space: nowrap; }
				.lsi-tab .lsi-g td { background: var(--subtle-fg, #f4f5f6); font-size: 13px; }
				.lsi-tab .lsi-st td { font-weight: 600; background: var(--subtle-accent, #fafafa); }
				.lsi-tab .lsi-tot td { font-weight: 700; font-size: 13px; border-top: 2px solid var(--border-color, #ccc); }
				.lsi-tab .lsi-l-sous td { color: var(--text-muted); }
				.lsi-tab .lsi-l-fixe td { font-weight: 500; }
				.lsi-tab .lsi-l-tarif td { font-style: italic; color: var(--text-muted); }
				.lsi-tab .lsi-l-manquant td { background: var(--bg-orange, #fff1e7); }
				.lsi-tab .lsi-l-perte td { background: var(--bg-red, #fde8e8); }
				.lsi-tab .lsi-rouge { color: #b91c1c; font-weight: 600; } .lsi-tab .lsi-fort { font-weight: 700; }
				.lsi-tab .lsi-in { width: 120px; display: inline-block; height: 24px; } .lsi-tab .lsi-in.lsi-num { width: 80px; text-align: right; }
				.lsi-tab-wrap { max-height: 75vh; overflow: auto; }
				.lsi-tab { width: max-content; min-width: 100%; }
				.lsi-tab thead th { position: sticky; top: 0; z-index: 3; background: var(--fg-color, #fff); }
				.lsi-tab .lsi-fixe1, .lsi-tab .lsi-fixe2 { position: sticky; z-index: 2; background: var(--fg-color, #fff); }
				.lsi-tab thead .lsi-fixe1, .lsi-tab thead .lsi-fixe2 { z-index: 4; }
				.lsi-tab .lsi-fixe1 { left: 0; min-width: 70px; } .lsi-tab .lsi-fixe2 { left: 70px; min-width: 240px; max-width: 280px; white-space: normal !important; }
				.lsi-tab .lsi-colle { position: sticky; left: 8px; }
				.lsi-tab .lsi-texte { white-space: normal; display: inline-block; max-width: 260px; }
				.lsi-tab .lsi-actions a, .lsi-tab .lsi-toggle, .lsi-tab .lsi-add { cursor: pointer; margin-right: 6px; }
			</style>`).appendTo("head");
		}
		frm.toggle_display(["positions", "groupes"], false);  // la saisie se fait dans le tableau (grille accessible par le lien)
		lsi_eft.tableau(frm);
	},
});
