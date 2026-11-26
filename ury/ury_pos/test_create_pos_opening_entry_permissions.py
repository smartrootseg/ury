"""Negative-permission tests for `create_pos_opening_entry()` in
`ury/ury_pos/api.py` -- this whitelisted function had zero test coverage
before this file (see TRACK.md Phase 2 priority-3 audit, sa-comprehensive-
test-strategy). Mock-based, matching the established pattern in this
package (`test_api.py`'s other `TestURYPosAPI`-style tests): the behaviour
under test is authorization control flow, not a real DB round-trip.

Three distinct gates are pinned here, each one confirmed real by reading
the actual source (not assumed):
  1. `frappe.has_permission("POS Opening Entry", "create")`
  2. `frappe.has_permission("POS Opening Entry", "submit")`
  3. `frappe.has_permission("POS Profile", "read", doc=pos_profile_doc)`
     (checked only after the POS Profile doc is loaded and its
     branch/restaurant/company fields are validated as present)
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from ury.ury_pos import api as pos_api

MODULE = "ury.ury_pos.api"


def _make_pos_profile():
    doc = MagicMock()
    doc.branch = "Test Branch"
    doc.restaurant = "Test Restaurant"
    doc.company = "Test Company"
    return doc


class TestCreatePosOpeningEntryPermissions(FrappeTestCase):
    def test_rejected_when_create_permission_missing(self):
        with patch(f"{MODULE}.frappe.has_permission", return_value=False) as mock_perm:
            with self.assertRaises(Exception) as ctx:
                pos_api.create_pos_opening_entry("Test Profile")
        # frappe.throw with frappe.PermissionError raises that exact class.
        import frappe
        self.assertIsInstance(ctx.exception, frappe.PermissionError)
        mock_perm.assert_called_once_with("POS Opening Entry", "create")

    def test_rejected_when_submit_permission_missing(self):
        # create=True, submit=False -- has_permission is called twice with
        # different args, so side_effect must distinguish them positionally.
        def has_permission_side_effect(doctype, perm_type=None, doc=None):
            if doctype == "POS Opening Entry" and perm_type == "create":
                return True
            if doctype == "POS Opening Entry" and perm_type == "submit":
                return False
            return True

        with patch(f"{MODULE}.frappe.has_permission", side_effect=has_permission_side_effect):
            import frappe
            with self.assertRaises(frappe.PermissionError):
                pos_api.create_pos_opening_entry("Test Profile")

    def test_rejected_when_pos_profile_read_permission_missing(self):
        pos_profile_doc = _make_pos_profile()

        def has_permission_side_effect(doctype, perm_type=None, doc=None):
            if doctype == "POS Opening Entry":
                return True
            if doctype == "POS Profile" and perm_type == "read":
                return False
            return True

        with patch(f"{MODULE}.frappe.has_permission", side_effect=has_permission_side_effect), \
            patch(f"{MODULE}.frappe.get_doc", return_value=pos_profile_doc):
            import frappe
            with self.assertRaises(frappe.PermissionError):
                pos_api.create_pos_opening_entry("Test Profile")

    def test_allowed_through_when_all_permissions_present(self):
        pos_profile_doc = _make_pos_profile()
        opening_doc = MagicMock()
        opening_doc.as_dict.return_value = {"name": "POS-OPN-0001"}

        def get_doc_side_effect(arg, *a, **k):
            if arg == "POS Profile":
                return pos_profile_doc
            return opening_doc

        with patch(f"{MODULE}.frappe.has_permission", return_value=True), \
            patch(f"{MODULE}.frappe.get_doc", side_effect=get_doc_side_effect), \
            patch(f"{MODULE}.frappe.session") as mock_session, \
            patch(f"{MODULE}.frappe.utils.get_datetime", return_value="2026-01-01 00:00:00"), \
            patch(f"{MODULE}.frappe.utils.getdate", return_value="2026-01-01"):
            mock_session.user = "manager@ury.test"
            result = pos_api.create_pos_opening_entry("Test Profile")

        self.assertEqual(result["name"], "POS-OPN-0001")
        opening_doc.submit.assert_called_once()

class TestMainCashierStatus(FrappeTestCase):
    def test_identifies_main_cashier_without_requiring_existing_session(self):
        profile = MagicMock()
        profile.custom_enable_multiple_cashier = 1
        row = MagicMock()
        row.custom_main_cashier = 1
        row.user = "main@ury.test"
        profile.applicable_for_users = [row]
        for session_user, expected in [("main@ury.test", True), ("second@ury.test", False)]:
            with self.subTest(user=session_user), \
                patch(f"{MODULE}.frappe.get_doc", return_value=profile), \
                patch(f"{MODULE}.frappe.db.exists", return_value=False), \
                patch(f"{MODULE}.frappe.session") as session:
                session.user = session_user
                result = pos_api._get_main_cashier_status("Test Profile")
            self.assertEqual(result["is_main_cashier"], expected)
            self.assertFalse(result["main_cashier_open"])
