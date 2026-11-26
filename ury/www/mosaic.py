"""Session-specific context for the Mosaic kitchen display."""

from frappe.sessions import get_csrf_token

no_cache = 1


def get_context(context):
	# Frappe v16 stores the token inside session.data. Initialize it and
	# render it per session so authenticated KDS POSTs retain CSRF protection.
	context.no_cache = 1
	context.csrf_token = get_csrf_token()
