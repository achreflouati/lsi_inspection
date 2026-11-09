// Chiffrage — tableau hiérarchique : groupes, lignes vendues, sous-lignes, sous-totaux ; colonnes = champs de Chiffrage Position (droits natifs).
frappe.provide("lsi_chiffrage");

// ------------------------------------------------------------------ tableau hiérarchique (comme l'Excel de TIC / MARI)
// Groupe (en-tête coloré) → positions vendues → sous-positions (décalées, repliables) → sous-total ; total de l'EFT.
// Quantité et prix modifiables directement ; « + ligne » par groupe ; icônes modifier / sous-position / supprimer. Le calcul reste celui du serveur.
lsi_chiffrage.replies = new Set();
lsi_chiffrage.vue = (() => { try { return localStorage.getItem("lsi_chiffrage_vue") || "toutes"; } catch (e) { return "toutes"; } })();
lsi_chiffrage.cle = (n) => String(n || "~").split(".").map((x) => (isNaN(x) ? x : String(x).padStart(4, "0"))).join(".");

// Colonnes : TOUS les champs d'EFT Position (définition du doctype), les principaux d'abord ; un champ ajouté plus tard apparaît seul.
// Chaque colonne suit les permissions natives du champ (permlevel) : masquée, lecture seule ou modifiable.
const LSI_PRINCIPALES = ["type_position", "qty", "uom", "cout_unitaire", "cout_total", "prix_unitaire", "prix_total", "marge", "taux_marge", "stock_disponible"];
const LSI_HORS_COLONNES = ["numero", "item_code", "designation", "designation_2", "groupe", "parente"];  // affichés par la structure (N°, Article, hiérarchie)
const LSI_SAISIE = ["Float", "Currency", "Int", "Percent", "Data", "Check"];
const LSI_TOTAUX = ["cout_total", "prix_total", "marge", "taux_marge"];

lsi_chiffrage.colonnes = function (frm) {
	const meta = frappe.get_meta("Chiffrage Position");
	const champs = meta.fields.filter((df) => !frappe.model.layout_fields.includes(df.fieldtype) && !LSI_HORS_COLONNES.includes(df.fieldname));
	const ordre = (df) => { const i = LSI_PRINCIPALES.indexOf(df.fieldname); return i < 0 ? 100 + champs.indexOf(df) : i; };
	let cols = champs.slice().sort((a, b) => ordre(a) - ordre(b))
		.filter((df) => frappe.perm.get_field_display_status(df, null, frm.perm) !== "None");
	if (lsi_chiffrage.vue === "essentielles") cols = cols.filter((df) => LSI_PRINCIPALES.includes(df.fieldname));
	return cols;
};

lsi_chiffrage.cellule = function (frm, df, p, sous, ed) {
	const esc = frappe.utils.escape_html;
	const v = p[df.fieldname];
	const c = df.fieldname;
	if (sous && ["prix_unitaire", "prix_total", "marge", "taux_marge", "prix_conseille"].includes(c)) return `<td class="text-right text-muted">—</td>`;
	if (c === "retenue" && !sous) return "<td></td>";  // choix d'une sous-position (prix fixe « le plus élevé »)
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

lsi_chiffrage.tableau = function (frm) {
	const f = frm.get_field("tableau_html");
	if (!f) return;
	const ed = frm.doc.docstatus === 0;
	const esc = frappe.utils.escape_html;
	const money = (v) => format_number(v, null, 3);
	const pos = frm.doc.positions || [];
	const enfants = {};
	pos.filter((p) => p.parente).forEach((p) => (enfants[p.parente] = enfants[p.parente] || []).push(p));
	const tri = (a, b) => (lsi_chiffrage.cle(a.numero) < lsi_chiffrage.cle(b.numero) ? -1 : 1);
	const groupes = (frm.doc.groupes || []).slice().sort((a, b) => flt(a.numero) - flt(b.numero));
	const cols = lsi_chiffrage.colonnes(frm);
	const NB = cols.length + 3;

	const ligne = (p, sous) => {
		const kids = (enfants[p.numero] || []).sort(tri);
		const replie = lsi_chiffrage.replies.has(p.name);
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
			${cols.map((df) => lsi_chiffrage.cellule(frm, df, p, sous, ed)).join("")}
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
		const etape = lsi_chiffrage.etape_de(frm, { numero: null, groupe: g.numero });
		const coul = lsi_chiffrage.couleur_etape(frm, etape) || "#888";
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
	const bascule_vue = `<a class="lsi-vue">${lsi_chiffrage.vue === "essentielles" ? __("Afficher toutes les colonnes") : __("Colonnes essentielles seulement")}</a>`;
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
		frappe.model.set_value("Chiffrage Position", $(this).data("name"), $(this).data("champ"), num ? flt($(this).val()) : $(this).val());
	});
	w.find(".lsi-chk").on("change", function () {
		frappe.model.set_value("Chiffrage Position", $(this).data("name"), $(this).data("champ"), this.checked ? 1 : 0);
	});
	w.find(".lsi-vue").on("click", () => {
		lsi_chiffrage.vue = lsi_chiffrage.vue === "essentielles" ? "toutes" : "essentielles";
		try { localStorage.setItem("lsi_chiffrage_vue", lsi_chiffrage.vue); } catch (e) { /* préférence locale facultative */ }
		lsi_chiffrage.tableau(frm);
	});
	w.find(".lsi-toggle").on("click", function () {
		const n = $(this).data("name");
		lsi_chiffrage.replies.has(n) ? lsi_chiffrage.replies.delete(n) : lsi_chiffrage.replies.add(n);
		lsi_chiffrage.tableau(frm);
	});
	w.find(".lsi-edit").on("click", function () { lsi_chiffrage.modifier_ligne(frm, $(this).data("name")); });
	w.find(".lsi-del").on("click", function () { lsi_chiffrage.supprimer_ligne(frm, $(this).data("name")); });
	w.find(".lsi-add").on("click", function () { lsi_chiffrage.ajouter_ligne(frm, String($(this).data("groupe")), null); });
	w.find(".lsi-sous").on("click", function () {
		const p = locals["Chiffrage Position"][$(this).data("name")];
		lsi_chiffrage.ajouter_ligne(frm, String(p.groupe), p.name);  // la parente est identifiée par sa ligne : son n° peut arriver pendant la saisie
	});
	w.find(".lsi-grille").on("click", () => {
		const cache = frm.get_field("positions").df.hidden;
		frm.toggle_display(["positions", "groupes"], !!cache);
	});
};

lsi_chiffrage.ajouter_ligne = function (frm, groupe, ligne_parente) {
	const num_parente = () => (ligne_parente ? (locals["Chiffrage Position"][ligne_parente] || {}).numero : null);
	const parente = ligne_parente ? num_parente() || __("(en cours de numérotation)") : null;
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
			const parente = ligne_parente ? num_parente() : null;
			if (ligne_parente && !parente) {
				frappe.show_alert({ message: __("La ligne parente est en cours de numérotation : réessayez dans un instant."), indicator: "orange" });
				lsi_chiffrage.apercu(frm);
				return;
			}
			frappe.db.get_value("Item", v.item_code, "stock_uom").then((r) => {
				const row = frappe.model.add_child(frm.doc, "Chiffrage Position", "positions");
				const g = (frm.doc.groupes || []).find((x) => String(x.numero) === groupe);
				Object.assign(row, { groupe, parente: parente || null, item_code: v.item_code, designation_2: v.designation_2, qty: flt(v.qty),
					uom: v.uom || (r.message || {}).stock_uom, type_position: v.type_position, prix_unitaire: parente ? 0 : flt(v.prix_unitaire),
					etape: lsi_chiffrage.etape_de(frm, { numero: null, groupe }) || null });
				frm.refresh_field("positions");
				frm.dirty();
				d.hide();
				lsi_chiffrage.apercu(frm);
			});
		},
	});
	d.show();
};

lsi_chiffrage.modifier_ligne = function (frm, name) {
	const p = locals["Chiffrage Position"][name];
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
			champs.forEach((c) => { if (v[c] !== undefined && v[c] !== p[c]) frappe.model.set_value("Chiffrage Position", name, c, v[c]); });
			d.hide();
		},
	});
	d.show();
};
const esc_source = (s) => (s ? __("Coût calculé : {0}", [frappe.utils.escape_html(s)]) : "");

lsi_chiffrage.supprimer_ligne = function (frm, name) {
	const p = locals["Chiffrage Position"][name];
	const kids = (frm.doc.positions || []).filter((x) => p.numero && x.parente === p.numero);
	frappe.confirm(kids.length ? __("Supprimer la ligne {0} et ses {1} sous-position(s) ?", [p.numero, kids.length]) : __("Supprimer la ligne {0} ?", [p.numero || ""]), () => {
		const a_retirer = new Set([name, ...kids.map((k) => k.name)]);
		frm.doc.positions = (frm.doc.positions || []).filter((x) => !a_retirer.has(x.name));
		frm.doc.positions.forEach((x, i) => (x.idx = i + 1));
		frm.refresh_field("positions");
		frm.dirty();
		lsi_chiffrage.apercu(frm);
	});
};

frappe.ui.form.on("Chiffrage", {
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
		lsi_chiffrage.tableau(frm);
	},
});

