import json
MODULE = frappe.db.get_value("Workspace", "Inspection", "module")

def carte(nom, dt, filtres=None, dyn=None, couleur="#4F46E5"):
    d = frappe.get_doc("Number Card", nom) if frappe.db.exists("Number Card", nom) else frappe.new_doc("Number Card")
    d.update({"label": nom, "type": "Document Type", "document_type": dt,
              "function": "Count", "is_public": 1, "show_percentage_stats": 0,
              "filters_json": json.dumps(filtres or []), "dynamic_filters_json": json.dumps(dyn or []),
              "color": couleur, "is_standard": 1, "module": MODULE})
    if d.is_new():
        d.insert(ignore_permissions=True, set_name=nom)
    else:
        d.save(ignore_permissions=True)
    return nom

cartes = [
    carte("Opportunités ouvertes", "Opportunity", [["Opportunity", "status", "=", "Open"]], couleur="#2563EB"),
    carte("EFT en cours", "EFT", [["EFT", "docstatus", "=", 0]], couleur="#EA580C"),
    carte("Chiffrages en brouillon", "Chiffrage", [["Chiffrage", "docstatus", "=", 0]], couleur="#7C3AED"),
    carte("Devis en attente", "Quotation", [["Quotation", "status", "=", "Open"], ["Quotation", "docstatus", "=", 1]], couleur="#16A34A"),
    carte("Phases en retard", "Opportunity", [["Opportunity", "status", "=", "Open"]],
          dyn=[["Opportunity", "lsi_echeance_phase", "<", "frappe.datetime.now_date()"]], couleur="#DC2626"),
    carte("Retours de test ouverts", "Issue", [["Issue", "status", "=", "Open"]], couleur="#CA8A04"),
]

g = "Chiffrages par mois"
dc = frappe.get_doc("Dashboard Chart", g) if frappe.db.exists("Dashboard Chart", g) else frappe.new_doc("Dashboard Chart")
dc.update({"chart_name": g, "chart_type": "Count", "document_type": "Chiffrage", "based_on": "creation",
           "timeseries": 1, "time_interval": "Monthly", "timespan": "Last Year", "type": "Bar",
           "filters_json": "[]", "is_public": 1, "is_standard": 1, "module": MODULE})
if dc.is_new():
    dc.insert(ignore_permissions=True)
else:
    dc.save(ignore_permissions=True)

ws = frappe.get_doc("Workspace", "Inspection")
if not ws.get("type"):
    options = (ws.meta.get_field("type").options or "").split("\n")
    ws.type = "Workspace" if "Workspace" in options else options[0]
    print("type =", ws.type, "options :", options)
for l in ws.links:
    if l.type == "Link" and l.link_to == "Lead Source" and not frappe.db.exists("DocType", "Lead Source"):
        l.link_to = "UTM Source"
for c in cartes:
    if not any(n.number_card_name == c for n in ws.number_cards):
        ws.append("number_cards", {"number_card_name": c, "label": c})
if not any(ch.chart_name == g for ch in ws.charts):
    ws.append("charts", {"chart_name": g, "label": g})

actions = [("Nouvelle opportunité", "/desk/opportunity/new"), ("Nouvelle EFT", "/desk/eft/new"),
           ("Mes chiffrages", "/desk/chiffrage")]
noms_actions = [a for a, _ in actions]
for label, url in actions:
    if not any(s.label == label for s in ws.shortcuts):
        ws.append("shortcuts", {"type": "URL", "label": label, "url": url, "color": "Blue"})

def bloc(t, data):
    return {"id": frappe.generate_hash(length=10), "type": t, "data": data}

anciens = json.loads(ws.content)
cartes_liens = [b for b in anciens if b["type"] == "card"]     # gardées pour la v15
graph_existants = [b for b in anciens if b["type"] == "chart"]
contenu = [bloc("header", {"text": '<span class="h4"><b>Tableau de bord</b></span>', "col": 12})]
contenu += [bloc("number_card", {"number_card_name": c, "col": 4}) for c in cartes]
contenu += [bloc("header", {"text": '<span class="h4"><b>Actions</b></span>', "col": 12})]
contenu += [bloc("shortcut", {"shortcut_name": l, "col": 3}) for l in noms_actions]
contenu += [bloc("shortcut", {"shortcut_name": s.label, "col": 3}) for s in ws.shortcuts if s.label not in noms_actions]
contenu += graph_existants + [bloc("chart", {"chart_name": g, "col": 6})]
contenu += cartes_liens
ws.content = json.dumps(contenu)
ws.save(ignore_permissions=True)
frappe.db.commit()
print("OK :", len(cartes), "compteurs,", len(ws.shortcuts), "raccourcis, graphiques :", [c.chart_name for c in ws.charts])
