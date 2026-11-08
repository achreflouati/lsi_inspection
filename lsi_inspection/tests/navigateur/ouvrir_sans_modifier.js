// Ouvre un document enregistré et vérifie que l'affichage ne le modifie pas (frm.is_dirty() == false).
const { chromium } = require("playwright-core");
const [, , chrome, sid, doctype, name] = process.argv;
(async () => {
	const browser = await chromium.launch({ executablePath: chrome, args: ["--no-sandbox", "--disable-gpu"] });
	const ctx = await browser.newContext();
	await ctx.addCookies([{ name: "sid", value: sid, domain: "tic.erpsys.ovh", path: "/", secure: true }]);
	const page = await ctx.newPage();
	const logs = [];
	page.on("console", (m) => m.type() === "error" && logs.push(m.text()));
	await page.goto(`https://tic.erpsys.ovh/app/${doctype.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(name)}`, { waitUntil: "networkidle", timeout: 90000 });
	await page.waitForFunction((n) => window.cur_frm && cur_frm.docname === n && cur_frm.layout, name, { timeout: 60000 });
	await page.waitForTimeout(4000); // appels asynchrones du rafraîchissement (phases, contacts…)
	const r = await page.evaluate(async ([dt, n]) => {
		const serveur = (await frappe.call({ method: "frappe.client.get", args: { doctype: dt, name: n } })).message;
		const local = cur_frm.doc;
		const diff = [];
		const cmp = (a, b, chemin) => {
			for (const k of Object.keys(a)) {
				if (k.startsWith("__") || ["modified", "_seen", "_liked_by", "_comments", "_assign", "_user_tags"].includes(k)) continue;
				const va = a[k], vb = b ? b[k] : undefined;
				if (Array.isArray(va)) { va.forEach((row, i) => cmp(row, (vb || [])[i], `${chemin}${k}[${i}].`)); continue; }
				const norm = (v) => (v === null || v === undefined || v === "" ? "" : String(v));
				if (norm(va) !== norm(vb)) diff.push(`${chemin}${k}: serveur=${JSON.stringify(vb)} navigateur=${JSON.stringify(va)}`);
			}
		};
		cmp(local, serveur, "");
		return { dirty: cur_frm.is_dirty(), unsaved: local.__unsaved || 0, diff };
	}, [doctype, name]);
	console.log(JSON.stringify({ ...r, erreurs_console: logs.slice(0, 5) }, null, 1));
	await browser.close();
	process.exit(r.dirty ? 1 : 0);
})().catch((e) => { console.error("ERREUR", e.message); process.exit(2); });
