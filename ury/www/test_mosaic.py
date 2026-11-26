import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.sessions import get_csrf_token
from ury.www.mosaic import get_context


class TestMosaicSessionContext(FrappeTestCase):
	def test_context_initializes_current_session_csrf_and_disables_caching(self):
		context = frappe._dict()
		get_context(context)
		self.assertTrue(context.csrf_token)
		self.assertEqual(context.csrf_token, get_csrf_token())
		self.assertEqual(context.csrf_token, frappe.session.data.csrf_token)
		self.assertEqual(context.no_cache, 1)
