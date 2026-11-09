// Chiffrage — calcul en temps réel (même moteur que l'enregistrement), couleurs des prestations, synthèse.
frappe.provide("lsi_chiffrage");

// ------------------------------------------------------------------ temps réel, couleurs, synthèse (comme tic_demo)
// Le calcul est fait par le MÊME moteur que l'enregistrement (méthode « apercu », sans enregistrer) : pools, conversions, stock.
const LSI_COULEURS = ["#2563eb", "#16a34a", "#9333ea", "#ea580c", "#db2777", "#0891b2", "#ca8a04", "#4b5563"];
const LSI_CHAMPS_POSITION = ["etape", "item_code", "type_position", "qty", "uom", "prix_unitaire", "cout_unitaire", "cout_manuel", "parente", "groupe", "numero", "retenue"];

lsi_chiffrage.couleur_etape = function (frm, etape) {
	const i = (frm.doc.etapes || []).findIndex((e) => e.prestation === etape);
	return i < 0 ? null : LSI_COULEURS[i % LSI_COULEURS.length];
};

lsi_chiffrage.etape_de = function (frm, p) {
	// étape principale d'une position (même règle que le serveur) : parente → répartition de la position, puis du groupe, sinon étape unique
	if (p.__etape) return p.__etape;
	const par_num = Object.fromEntries((frm.doc.positions || []).map((x) => [x.numero, x]));
	if (p.parente && par_num[p.parente]) return lsi_chiffrage.etape_de(frm, par_num[p.parente]);
	for (const cible of [p.numero, p.groupe]) {
		const r = (frm.doc.repartitions || []).find((x) => String(x.cible) === String(cible) && x.etape);
		if (r) return r.etape;
	}
	return (frm.doc.etapes || []).length === 1 ? frm.doc.etapes[0].prestation : null;
};

lsi_chiffrage.colorer = function (frm) {
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
	peindre("etapes", (e) => lsi_chiffrage.couleur_etape(frm, e.prestation));
	peindre("groupes", (g) => lsi_chiffrage.couleur_etape(frm, lsi_chiffrage.etape_de(frm, { numero: null, groupe: g.numero })));
	peindre("positions", (p) => lsi_chiffrage.couleur_etape(frm, lsi_chiffrage.etape_de(frm, p)), (p) => ({
		"lsi-manquant": p.cout_manquant || p.cout_en_attente,
		"lsi-perte": !p.parente && flt(p.prix_total) > 0 && flt(p.marge) < 0,
		"lsi-tarif": p.tarif,
		"lsi-sous": !!p.parente,
	}));
	lsi_chiffrage.synthese(frm);
};

lsi_chiffrage.synthese = function (frm) {
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
	const etape_de = (p) => p.etape || lsi_chiffrage.etape_de(frm, p);
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
		return ligne(esc(libelle(t.etape)), qtes(l), t.cout_total, t.prix_total, { manquant: manquant(l), couleur: lsi_chiffrage.couleur_etape(frm, t.etape) });
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
		return `<p style="margin:12px 0 4px; font-weight:600; border-left:5px solid ${lsi_chiffrage.couleur_etape(frm, e) || "transparent"}; padding-left:6px">
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

lsi_chiffrage.apercu = frappe.utils.debounce(function (frm) {
	if (frm.doc.docstatus !== 0) return;
	frappe.call({ method: `${lsi_chiffrage.M}.apercu`, args: { doc: frm.doc }, type: "POST" }).then((r) => {
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
		lsi_chiffrage.colorer(frm);
		lsi_chiffrage.tableau(frm);
	});
}, 400);

frappe.ui.form.on("Chiffrage", {
	refresh(frm) { setTimeout(() => lsi_chiffrage.colorer(frm), 300); },
	positions_on_form_rendered(frm) { lsi_chiffrage.colorer(frm); },
});
frappe.ui.form.on("Chiffrage Position", Object.assign(
	Object.fromEntries(LSI_CHAMPS_POSITION.map((c) => [c, (frm) => lsi_chiffrage.apercu(frm)])),
	{ positions_remove: (frm) => lsi_chiffrage.apercu(frm) }
));
// prix fixe « le plus élevé » : une seule sous-position retenue par ligne (les autres sont décochées)
frappe.ui.form.on("Chiffrage Position", {
	retenue(frm, cdt, cdn) {
		const p = locals[cdt][cdn];
		if (!p.retenue || !p.parente) return;
		(frm.doc.positions || []).filter((x) => x.parente === p.parente && x.name !== p.name && x.retenue)
			.forEach((x) => frappe.model.set_value(cdt, x.name, "retenue", 0));
	},
});
frappe.ui.form.on("Chiffrage Repartition", { cible: (frm) => lsi_chiffrage.apercu(frm), etape: (frm) => lsi_chiffrage.apercu(frm), part: (frm) => lsi_chiffrage.apercu(frm),
	repartitions_remove: (frm) => lsi_chiffrage.apercu(frm) });
