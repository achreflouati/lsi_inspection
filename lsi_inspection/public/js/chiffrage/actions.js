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


lsi_chiffrage.planifier_position = function (frm) {
	// 1. Utiliser la fonction existante pour choisir la position
	lsi_chiffrage.choisir_position(frm, (p) => true, __("Planifier une position"), (numero) => {
		
		// 2. Ouvrir un dialogue pour saisir les détails de la planification
		const d = new frappe.ui.Dialog({
			title: __("Planifier la position {0}", [numero]),
			fields: [
				{ fieldname: "date_debut", fieldtype: "Date", label: __("Date de début prévue"), reqd: 1 },
				{ fieldname: "date_fin", fieldtype: "Date", label: __("Date de fin prévue"), reqd: 1 },
				{ fieldname: "responsable", fieldtype: "Link", options: "User", label: __("Responsable / Intervenant") },
				{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes ou instructions particulières") }
			],
			primary_action_label: __("Planifier"),
			primary_action(v) {
				// 3. Appeler la méthode côté serveur pour enregistrer
				frappe.call({
					method: `${lsi_chiffrage.M}.planifier_position`,
					args: {
						chiffrage: frm.doc.name,
						numero: numero,
						date_debut: v.date_debut,
						date_fin: v.date_fin,
						responsable: v.responsable || null,
						notes: v.notes || null
					},
					freeze: true,
					freeze_message: __("Planification en cours...")
				}).then((r) => {
					d.hide();
					frappe.show_alert({
						message: __("Position {0} planifiée avec succès.", [numero]),
						indicator: "green"
					});
					frm.reload_doc(); // Recharge le document pour afficher les mises à jour
				}).catch((err) => {
					frappe.msgprint({
						title: __("Erreur"),
						message: __("Impossible de planifier la position : ") + (err.message || err),
						indicator: "red"
					});
				});
			}
		});
		d.show();
	});
};

// =========================================================================
// PLANIFICATION GLOBALE (Tableau)
// =========================================================================
lsi_chiffrage.planning_global = function (frm) {
	const esc = frappe.utils.escape_html;
	const positions = (frm.doc.positions || []).filter((p) => p.item_code && !p.parente);
	
	if (!positions.length) {
		return frappe.msgprint(__("Aucune position à planifier."));
	}

	const d = new frappe.ui.Dialog({
		title: __("📋 Planning Prévisionnel - {0}", [frm.doc.name]),
		size: "extra-large",
		fields: [
			{ fieldname: "planning_html", fieldtype: "HTML", options: `<div id="planning-table-container"></div>` }
		],
		primary_action_label: __("💾 Enregistrer le planning"),
		primary_action(v) {
			const lignes = [];
			d.$wrapper.find(".planning-row").each(function() {
				const row = $(this);
				const date_debut = row.find(`[data-field="date_debut"]`).val();
				if (date_debut) {
					lignes.push({
						numero: row.data("numero"),
						type_planif: row.data("type-planif"),
						date_debut: date_debut,
						date_fin: row.find(`[data-field="date_fin"]`).val(),
						responsable: row.find(`[data-field="responsable"]`).val(),
						asset_specifique: row.find(`[data-field="asset"]`).val(),
						qty_commande: row.find(`[data-field="qty_commande"]`).val(),
						notes: row.find(`[data-field="notes"]`).val()
					});
				}
			});
			
			if (!lignes.length) return frappe.msgprint(__("Veuillez remplir au moins une date de début."));
			
			frappe.call({
				method: `${lsi_chiffrage.M}.planifier_positions_globales`,
				args: { eft: frm.doc.name, positions: JSON.stringify(lignes) },
				freeze: true,
				freeze_message: __("Enregistrement du planning...")
			}).then((r) => {
				d.hide();
				frappe.show_alert({ message: r.message, indicator: "green" });
				frm.reload_doc();
			}).catch((err) => {
				frappe.msgprint({ title: __("Erreur"), message: err.message, indicator: "red" });
			});
		}
	});

	d.show();

	// Construction asynchrone du tableau avec détection des types
	const construire_tableau = async () => {
		let html = `<div style="max-height: 60vh; overflow-y: auto;">
			<table class="table table-bordered table-sm">
				<thead class="sticky-top" style="background: #f5f7fa; z-index: 10;">
					<tr>
						<th style="width: 7%;">N°</th>
						<th style="width: 20%;">Désignation</th>
						<th style="width: 12%;">Type</th>
						<th style="width: 10%;">Date début</th>
						<th style="width: 10%;">Date fin</th>
						<th style="width: 12%;">Responsable</th>
						<th style="width: 10%;">Asset / Qté</th>
						<th style="width: 19%;">Notes</th>
					</tr>
				</thead>
				<tbody id="planning-tbody"><tr><td colspan="8" class="text-center text-muted">⏳ Chargement...</td></tr></tbody>
			</table></div>
			<p class="text-muted small mt-2">💡 Les champs s'adaptent automatiquement (Équipement 🚜, Stock 📦, Consommable 🧰, Activité 👷).</p>`;

		d.fields_dict.planning_html.$wrapper.html(html);

		const item_codes = positions.map(p => p.item_code);
		const items_info = {};
		await Promise.all(item_codes.map(async (item_code) => {
			const r = await frappe.db.get_value("Item", item_code, ["is_stock_item", "is_fixed_asset"]);
			items_info[item_code] = r.message;
		}));

		let tbody_html = "";
		positions.forEach((p) => {
			const info = items_info[p.item_code] || {};
			const type_label = p.type_position || "Non défini";
			
			let type_planif, badge_color, icon, champ_asset_qty = "", date_fin_hidden = 0, responsable_hidden = 0;
			
			if (info.is_fixed_asset) {
				type_planif = "equipement"; badge_color = "warning"; icon = "🚜";
				champ_asset_qty = `<input type="text" class="form-control form-control-sm" data-field="asset" placeholder="Asset spécifique">`;
			} else if (info.is_stock_item) {
				const est_consommable = type_label.toLowerCase().includes("consommable");
				if (est_consommable) {
					type_planif = "consommable"; badge_color = "secondary"; icon = "🧰";
					responsable_hidden = 1; date_fin_hidden = 1;
				} else {
					type_planif = "stock"; badge_color = "primary"; icon = "📦";
					date_fin_hidden = 1;
				}
				champ_asset_qty = `<input type="number" class="form-control form-control-sm" data-field="qty_commande" value="${p.qty || 1}" step="0.01">`;
			} else {
				type_planif = "activite"; badge_color = "success"; icon = "👷";
				champ_asset_qty = `<span class="text-muted">-</span>`;
			}

			tbody_html += `<tr class="planning-row" data-numero="${esc(p.numero)}" data-type-planif="${type_planif}">
				<td><b>${esc(p.numero)}</b></td>
				<td>${esc(p.designation || p.item_code)}</td>
				<td><span class="badge badge-${badge_color}">${icon} ${esc(type_label)}</span></td>
				<td><input type="date" class="form-control form-control-sm" data-field="date_debut" value="${p.date_debut_prevue || ''}"></td>
				<td ${date_fin_hidden ? 'style="opacity:0.3"' : ''}><input type="date" class="form-control form-control-sm" data-field="date_fin" value="${p.date_fin_prevue || ''}" ${date_fin_hidden ? 'disabled' : ''}></td>
				<td ${responsable_hidden ? 'style="opacity:0.3"' : ''}><input type="text" class="form-control form-control-sm" data-field="responsable" value="${esc(p.responsable || '')}" ${responsable_hidden ? 'disabled' : ''} placeholder="${responsable_hidden ? 'N/A' : 'Intervenant'}"></td>
				<td>${champ_asset_qty}</td>
				<td><input type="text" class="form-control form-control-sm" data-field="notes" value="${esc(p.notes_planification || '')}" placeholder="Instructions..."></td>
			</tr>`;
		});
		d.$wrapper.find("#planning-tbody").html(tbody_html);
	};
	construire_tableau();
};

// =========================================================================
// VUE GANTT PRÉVISIONNELLE (via Gantt natif ERPNext)
// =========================================================================
lsi_chiffrage.vue_gantt = function (frm) {
	const positions = (frm.doc.positions || []).filter((p) => p.date_debut_prevue && !p.parente);
	
	if (!positions.length) {
		return frappe.msgprint(__("Aucune position planifiée. Utilisez 'Planning global' d'abord."));
	}

	// Fonction pour ouvrir le Gantt
	const ouvrir_gantt = (project_name) => {
		frappe.set_route("List", "Task", "Gantt", {
			project: project_name
		});
	};

	// Chercher un projet existant lié à cet EFT (par le nom)
	const nom_projet_pattern = `%${frm.doc.name}%`;
	frappe.db.get_list("Project", {
		filters: { project_name: ["like", nom_projet_pattern] },
		fields: ["name", "project_name"],
		limit: 1
	}).then((projets) => {
		if (projets.length > 0) {
			// Un projet existe déjà
			const projet_existant = projets[0];
			frappe.show_alert({
				message: __("Projet trouvé : {0}", [projet_existant.project_name]),
				indicator: "blue"
			});
			ouvrir_gantt(projet_existant.name);
		} else {
			// Aucun projet, en créer un
			const nom_unique = `EFT ${frm.doc.name} - ${frm.doc.titre || 'Planning'}`;
			frappe.confirm(
				__("Créer le projet \"{0}\" pour afficher le Gantt ?", [nom_unique]),
				() => {
					frappe.call({
						method: "frappe.client.insert",
						args: {
							doc: {
								doctype: "Project",
								project_name: nom_unique,
								expected_start_date: positions[0].date_debut_prevue,
								expected_end_date: positions[positions.length - 1].date_fin_prevue || positions[positions.length - 1].date_debut_prevue,
								company: frm.doc.company,
								status: "Open",
								// Stocker la référence à l'EFT dans la description
								notes: `Lié à l'EFT ${frm.doc.name}`
							}
						},
						freeze: true,
						freeze_message: __("Création du projet..."),
						callback: (r) => {
							if (r.message) {
								frappe.show_alert({
									message: __("Projet créé : {0}", [r.message.name]),
									indicator: "green"
								});
								ouvrir_gantt(r.message.name);
							}
						}
					});
				},
				() => {
					// Refus : afficher un tableau
					frappe.msgprint({
						title: __("Planning prévisionnel"),
						message: positions.map(p => 
							`<b>${p.numero}</b> - ${p.designation || p.item_code}<br>
							 📅 ${frappe.datetime.str_to_user(p.date_debut_prevue)} → ${p.date_fin_prevue ? frappe.datetime.str_to_user(p.date_fin_prevue) : frappe.datetime.str_to_user(p.date_debut_prevue)}
							 ${p.responsable ? '<br>👷 ' + p.responsable : ''}`
						).join("<hr>"),
						wide: true
					});
				}
			);
		}
	});
};


// =========================================================================
// CRÉER L'OFFRE CLIENT (DEVIS)
// =========================================================================
// =========================================================================
// CRÉER L'OFFRE CLIENT (DEVIS) - VERSION ORIGINALE FONCTIONNELLE
// =========================================================================
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
			
			// APPEL ORIGINAL VERS devis.creer_devis (et non moteur.creer_devis)
			frappe.call({ 
				method: "lsi_inspection.chiffrage.devis.creer_devis", 
				args: { chiffrage: frm.doc.name, lignes: lignes, remise: v.remise || 0 }, 
				freeze: true 
			}).then((r) => {
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