"""Classe de base des tests, compatible v15 et v16.

v16 : frappe.tests.IntegrationTestCase ; v15 : frappe.tests.utils.FrappeTestCase.
Les tests de l'app importent toujours `IntegrationTestCase` depuis ce module.
"""

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

__all__ = ["IntegrationTestCase"]
