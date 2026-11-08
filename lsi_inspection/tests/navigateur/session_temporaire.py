# Session Administrator temporaire pour le test navigateur (créée puis supprimée par verifier_ouverture.sh).
import os, sys, frappe
os.chdir("/home/frappe/frappe-bench/sites"); frappe.init(site="tic.erpsys.ovh", sites_path="."); frappe.connect()
from frappe.sessions import Session, delete_session
if sys.argv[1] == "ouvrir":
    frappe.local.request_ip = "127.0.0.1"; frappe.local.form_dict = frappe._dict(sid="Guest")
    s = Session(user="Administrator", resume=False, full_name="Administrator", user_type="System User")
    frappe.db.commit(); print(s.sid)
else:
    delete_session(sys.argv[2], reason="test navigateur termine"); frappe.db.commit(); print("session supprimée")
