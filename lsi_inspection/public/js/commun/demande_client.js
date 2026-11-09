// Commun EFT / Chiffrage — demande du client de l'opportunité : articles demandés et pièces jointes (champ HTML « demande_html »).
frappe.provide("lsi.demande_client");

lsi.demande_client.afficher = function (frm, opportunite) {
	const f = frm.get_field("demande_html");
	if (!f || !opportunite) return;
	const esc = frappe.utils.escape_html;
	frappe.call({ method: "lsi_inspection.chiffrage.etude.demande_opportunite", args: { opportunity: opportunite } }).then((r) => {
		const d = r.message || {};
		const articles = (d.articles || []).map((a) => `<tr><td>${a.item_code ? `<a href="/app/item/${encodeURIComponent(a.item_code)}">${esc(a.item_code)}</a>`
			: `<span class="text-muted">${__("(sans article)")}</span>`}</td><td>${esc(a.item_name || "")}</td>
			<td class="text-right">${format_number(a.qty, null, 2)} ${esc(__(a.uom || ""))}</td><td>${esc(strip_html(a.description || ""))}</td></tr>`).join("");
		const fichiers = (d.fichiers || []).map((x) => `<li><a href="${encodeURI(x.file_url)}" target="_blank" rel="noopener">${esc(x.file_name || x.file_url)}</a>
			${x.is_private ? `<span class="text-muted small">(${__("privé")})</span>` : ""}</li>`).join("");
		f.$wrapper.html(`
			<p><a href="/app/opportunity/${encodeURIComponent(opportunite)}">${__("Ouvrir l'opportunité {0}", [esc(opportunite)])}</a></p>
			<p class="text-muted small" style="margin:8px 0 4px">${__("Articles demandés par le commercial")}</p>
			${articles ? `<table class="table table-bordered table-sm"><tr><th>${__("Article")}</th><th>${__("Désignation")}</th><th class="text-right">${__("Quantité")}</th><th>${__("Description")}</th></tr>${articles}</table>`
				: `<p class="text-muted">${__("Aucun article : la demande est décrite en texte ci-dessus.")}</p>`}
			<p class="text-muted small" style="margin:8px 0 4px">${__("Pièces jointes de l'opportunité")}</p>
			${fichiers ? `<ul>${fichiers}</ul>` : `<p class="text-muted">${__("Aucune pièce jointe.")}</p>`}
			<p class="text-muted small">${__("Traduisez la demande en prestations ci-dessous (tableau « Étapes » ou bouton « Ajouter depuis une gamme »).")}</p>`);
	});
};

// « Créer l'offre client » (comme MARI) : cocher les lignes vendues qui iront dans le devis, remise sur le total
