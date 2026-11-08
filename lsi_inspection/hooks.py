app_name = "lsi_inspection"
app_title = "LSI Inspection"
app_publisher = "achref louati"
app_description = "ERP inspection et controle (TIC) sur ERPNext"
app_email = "lsi.louati@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext", "hrms"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "lsi_inspection",
# 		"logo": "/assets/lsi_inspection/logo.png",
# 		"title": "LSI Inspection",
# 		"route": "/lsi_inspection",
# 		"has_permission": "lsi_inspection.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lsi_inspection/css/lsi_inspection.css"
# app_include_js = "/assets/lsi_inspection/js/lsi_inspection.js"

# include js, css files in header of web template
# web_include_css = "/assets/lsi_inspection/css/lsi_inspection.css"
# web_include_js = "/assets/lsi_inspection/js/lsi_inspection.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "lsi_inspection/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "lsi_inspection/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "lsi_inspection.utils.jinja_methods",
# 	"filters": "lsi_inspection.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "lsi_inspection.install.before_install"
# after_install = "lsi_inspection.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "lsi_inspection.uninstall.before_uninstall"
# after_uninstall = "lsi_inspection.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "lsi_inspection.utils.before_app_install"
# after_app_install = "lsi_inspection.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "lsi_inspection.utils.before_app_uninstall"
# after_app_uninstall = "lsi_inspection.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "lsi_inspection.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"lsi_inspection.tasks.all"
# 	],
# 	"daily": [
# 		"lsi_inspection.tasks.daily"
# 	],
# 	"hourly": [
# 		"lsi_inspection.tasks.hourly"
# 	],
# 	"weekly": [
# 		"lsi_inspection.tasks.weekly"
# 	],
# 	"monthly": [
# 		"lsi_inspection.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "lsi_inspection.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "lsi_inspection.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "lsi_inspection.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["lsi_inspection.utils.before_request"]
# after_request = ["lsi_inspection.utils.after_request"]

# Job Events
# ----------
# before_job = ["lsi_inspection.utils.before_job"]
# after_job = ["lsi_inspection.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"lsi_inspection.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# Fixtures
# --------
# Tout le paramétrage est livré ici, TOUJOURS filtré (jamais un doctype entier sans filtre).
# Exemple : {"dt": "Custom Field", "filters": [["module", "=", "LSI Inspection"]]}
fixtures = [
	# lot 2 — structure de l'opportunité (champs, property setters, notifications fixes : module Commercial)
	{"dt": "Custom Field", "filters": [["module", "in", ["Commercial", "Referentiel"]]]},
	{"dt": "Property Setter", "filters": [["module", "in", ["Commercial", "Referentiel"]]]},
	{"dt": "Notification", "filters": [["module", "in", ["Commercial"]]]},
	{"dt": "Role", "filters": [["name", "in", ["Validateur demande d'offre", "Etude technique", "Paramétreur commercial"]]]},
	{"dt": "Workflow", "filters": [["name", "in", ["Validation demande d'offre"]]]},
	{"dt": "Workflow State", "filters": [["name", "in", ["À valider", "Validée", "Non validée", "Clarification"]]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", ["Valider", "Refuser", "Demander clarification", "Remettre à valider"]]]},
	# permissions : toutes les règles (natives recopiées + nos rôles) des doctypes dont on change les droits
	{"dt": "Custom DocPerm", "filters": [["parent", "in", ["Opportunity", "Opportunity Type", "Sales Stage", "Email Template"]]]},
]
