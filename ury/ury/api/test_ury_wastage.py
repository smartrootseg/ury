import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ury.ury.api.ury_wastage import (
    approve_wastage,
    capture_wastage,
    compute_wastage_valuation,
    held_quantity,
    list_wastage,
    reject_wastage,
)


MODULE = "ury.ury.api.ury_wastage"


def _auth_doc(**values):
    doc = frappe._dict(
        {
            "name": "AUTH-1",
            "plan": "PLAN-1",
            "branch": "Branch A",
            "company": "Company A",
            "department": "DEPT-1",
            "production_unit": None,
            "component_item": "COMP-1",
            "stock_uom": "Nos",
            "status": "Authorized",
            "authorized_qty": 10,
        }
    )
    doc.update(values)
    return doc


def _new_doc_recorder():
    created = {}

    def _get_doc(*args, **kwargs):
        arg = args[0] if args else kwargs.get("arg1")
        if isinstance(arg, dict):
            doc = frappe._dict(arg)
            doc["items"] = [frappe._dict(item) for item in arg.get("items", [])]
            doc.insert = MagicMock()
            doc.save = MagicMock()
            created["doc"] = doc
            return doc
        raise AssertionError("other lookups should be mocked separately")

    return _get_doc, created


class TestCaptureWastage(FrappeTestCase):
    def setUp(self):
        # capture_wastage() calls frappe.utils.now(), which otherwise
        # chains into get_system_settings() -> get_cached_doc("System
        # Settings") -- a real DB/cache path these unit tests do not
        # stub. Fix the clock instead of routing that lookup through
        # the get_doc mocks below.
        now_patcher = patch(f"{MODULE}.frappe.utils.now", return_value="2024-01-01 00:00:00")
        now_patcher.start()
        self.addCleanup(now_patcher.stop)
        quantity_patcher = patch(f"{MODULE}.sum_authorized_wastage", return_value=0)
        quantity_patcher.start()
        self.addCleanup(quantity_patcher.stop)

    def test_capture_succeeds_within_held_qty(self):
        auth_doc = _auth_doc()
        new_doc_side_effect, created = _new_doc_recorder()

        def get_doc_dispatch(*args, **kwargs):
            if args and args[0] == "URY Issue Authorization":
                return auth_doc
            return new_doc_side_effect(*args, **kwargs)

        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", side_effect=get_doc_dispatch), patch(
            f"{MODULE}.frappe.db.get_value", return_value="Company A"
        ), patch(
            f"{MODULE}.frappe.get_all", return_value=[]
        ), patch(
            f"{MODULE}.frappe.db.exists", return_value=False
        ):
            result = capture_wastage(
                issue_authorization="AUTH-1",
                wasted_qty=3,
                reason_category="Spoilage",
                branch="Branch A",
                company="Company A",
            )

        self.assertEqual(result.status, "Draft")
        self.assertEqual(result.get("items")[0].qty, 3)
        self.assertEqual(result.get("items")[0].item_code, "COMP-1")
        audit = json.loads(result.audit_log)
        self.assertEqual(audit[0]["event"], "captured")
        self.assertEqual(audit[0]["held_qty_before"], 10)
        self.assertEqual(audit[0]["wasted_qty"], 3)
        result.insert.assert_called_once()

    def test_capture_rejected_when_exceeding_held_qty(self):
        # authorized_qty=10, 8 already approved-wasted -> held=2, request 3 fails.
        auth_doc = _auth_doc()
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", return_value=auth_doc), patch(
            f"{MODULE}.frappe.db.get_value", return_value="Company A"
        ), patch(
            f"{MODULE}.sum_authorized_wastage", return_value=8,
        ), patch(
            f"{MODULE}.frappe.db.exists", return_value=False
        ):
            with self.assertRaises(frappe.ValidationError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=3,
                    reason_category="Spoilage",
                    branch="Branch A",
                    company="Company A",
                )

    def test_capture_rejected_when_yield_check_already_exists(self):
        """Mirror of `URYYieldCheck.validate_no_duplicate_wastage`, in the
        reverse order: once a Yield Check already exists for this
        authorization, capturing wastage against it must fail closed too --
        otherwise the same shortfall gets double-counted regardless of which
        record was created first."""
        auth_doc = _auth_doc()

        def get_all_dispatch(doctype, *args, **kwargs):
            if doctype == "URY Yield Check":
                return [{"name": "YC-1"}]
            return []

        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", return_value=auth_doc), patch(
            f"{MODULE}.frappe.db.get_value", return_value="Company A"
        ), patch(
            f"{MODULE}.frappe.get_all", side_effect=get_all_dispatch
        ):
            with self.assertRaises(frappe.ValidationError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=1,
                    reason_category="Spoilage",
                    branch="Branch A",
                    company="Company A",
                )

    def test_branch_mismatch_fails_closed(self):
        auth_doc = _auth_doc()
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", return_value=auth_doc):
            with self.assertRaises(frappe.ValidationError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=1,
                    reason_category="Spoilage",
                    branch="Branch B",
                    company="Company A",
                )

    def test_company_scope_ambiguity_fails_closed(self):
        auth_doc = _auth_doc()
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", return_value=auth_doc), patch(
            f"{MODULE}.frappe.db.get_value", return_value="Other Company"
        ):
            with self.assertRaises(frappe.ValidationError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=1,
                    reason_category="Spoilage",
                    branch="Branch A",
                    company="Company A",
                )

    def test_unauthorized_actor_rejected_role_check(self):
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Stock User"]):
            with self.assertRaises(frappe.PermissionError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=1,
                    reason_category="Spoilage",
                    branch="Branch A",
                    company="Company A",
                )

    def test_unauthorized_actor_rejected_has_permission_false(self):
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=False
        ):
            with self.assertRaises(frappe.PermissionError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=1,
                    reason_category="Spoilage",
                    branch="Branch A",
                    company="Company A",
                )

    def test_capture_rejects_unauthorized_issue_authorization_status(self):
        auth_doc = _auth_doc(status="Rejected")
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", return_value=auth_doc):
            with self.assertRaises(frappe.ValidationError):
                capture_wastage(
                    issue_authorization="AUTH-1",
                    wasted_qty=1,
                    reason_category="Spoilage",
                    branch="Branch A",
                    company="Company A",
                )


class TestApproveWastage(FrappeTestCase):
    def setUp(self):
        # capture_wastage() calls frappe.utils.now(), which otherwise
        # chains into get_system_settings() -> get_cached_doc("System
        # Settings") -- a real DB/cache path these unit tests do not
        # stub. Fix the clock instead of routing that lookup through
        # the get_doc mocks below.
        now_patcher = patch(f"{MODULE}.frappe.utils.now", return_value="2024-01-01 00:00:00")
        now_patcher.start()
        self.addCleanup(now_patcher.stop)
        quantity_patcher = patch(f"{MODULE}.sum_authorized_wastage", return_value=0)
        quantity_patcher.start()
        self.addCleanup(quantity_patcher.stop)

    def _draft_doc(self, **values):
        doc = frappe._dict(
            {
                "name": "W-1",
                "issue_authorization": "AUTH-1",
                "plan": "PLAN-1",
                "branch": "Branch A",
                "company": "Company A",
                "department": "DEPT-1",
                "component_item": "COMP-1",
                "status": "Draft",
                "wasted_qty": 3,
                "items": [frappe._dict(item_code="COMP-1", qty=3, rate=0)],
                "audit_log": None,
            }
        )
        doc.update(values)
        doc.save = MagicMock()
        doc.submit = MagicMock()
        return doc

    def test_held_quantity_scopes_wastage_to_authorization_and_component(self):
        auth_doc = _auth_doc()
        with patch(f"{MODULE}.sum_authorized_wastage", return_value=0) as sum_wastage, patch(
            f"{MODULE}.frappe.db.exists", return_value=False
        ):
            result = held_quantity(auth_doc)
        self.assertEqual(result, 10)
        sum_wastage.assert_called_once_with(
            {"issue_authorization": "AUTH-1", "component_item": "COMP-1"}, exclude_name=None
        )

    def test_approval_requires_correct_permission(self):
        draft = self._draft_doc()
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Production Manager"]):
            with self.assertRaises(frappe.PermissionError):
                approve_wastage("W-1", actor="line-cook@example.com")

    def test_approval_succeeds_with_authorized_role_and_flips_status(self):
        draft = self._draft_doc()
        auth_doc = _auth_doc()

        def get_doc_dispatch(*args, **kwargs):
            if args and args[0] == "URY Wastage":
                return draft
            if args and args[0] == "URY Issue Authorization":
                return auth_doc
            raise AssertionError("unexpected get_doc call")

        with patch(f"{MODULE}.frappe.get_roles", return_value=["Stock Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", side_effect=get_doc_dispatch), patch(
            f"{MODULE}.frappe.get_all", return_value=[]
        ), patch(
            f"{MODULE}.frappe.db.exists", return_value=False
        ):
            result = approve_wastage("W-1", actor="stock-mgr@example.com")

        self.assertEqual(result.status, "Authorized")
        self.assertEqual(result.get("items")[0].amount, 0)
        result.submit.assert_called_once()
        result.save.assert_not_called()

    def test_reject_wastage_leaves_status_rejected(self):
        draft = self._draft_doc()
        with patch(f"{MODULE}.frappe.get_roles", return_value=["Stock Manager"]), patch(
            f"{MODULE}.frappe.has_permission", return_value=True
        ), patch(f"{MODULE}.frappe.get_doc", return_value=draft):
            result = reject_wastage("W-1", actor="stock-mgr@example.com")

        self.assertEqual(result.status, "Rejected")


class TestValuationHook(FrappeTestCase):
    def setUp(self):
        # capture_wastage() calls frappe.utils.now(), which otherwise
        # chains into get_system_settings() -> get_cached_doc("System
        # Settings") -- a real DB/cache path these unit tests do not
        # stub. Fix the clock instead of routing that lookup through
        # the get_doc mocks below.
        now_patcher = patch(f"{MODULE}.frappe.utils.now", return_value="2024-01-01 00:00:00")
        now_patcher.start()
        self.addCleanup(now_patcher.stop)

    def test_valuation_hook_computes_qty_times_rate(self):
        doc = frappe._dict(items=[frappe._dict(item_code="COMP-1", qty=4, rate=None)])
        amount = compute_wastage_valuation(doc, valuation_rate=2.5)
        self.assertEqual(amount, 10.0)
        self.assertEqual(doc.get("items")[0].rate, 2.5)
        self.assertEqual(doc.get("items")[0].amount, 10.0)

    def test_valuation_hook_uses_rate_already_on_doc_when_not_passed(self):
        doc = frappe._dict(items=[frappe._dict(item_code="COMP-1", qty=2, rate=5)])
        amount = compute_wastage_valuation(doc)
        self.assertEqual(amount, 10)


class TestListWastage(FrappeTestCase):
    def setUp(self):
        # capture_wastage() calls frappe.utils.now(), which otherwise
        # chains into get_system_settings() -> get_cached_doc("System
        # Settings") -- a real DB/cache path these unit tests do not
        # stub. Fix the clock instead of routing that lookup through
        # the get_doc mocks below.
        now_patcher = patch(f"{MODULE}.frappe.utils.now", return_value="2024-01-01 00:00:00")
        now_patcher.start()
        self.addCleanup(now_patcher.stop)

    def test_list_scoped_by_branch_succeeds(self):
        rows = [
            {
                "name": "W-1",
                "component_item": "COMP-1",
                "wasted_qty": 3,
                "status": "Authorized",
                "department": "DEPT-1",
                "branch": "Branch A",
                "company": "Company A",
                "valuation_rate": 2.5,
                "valuation_amount": 7.5,
            }
        ]
        with patch(f"{MODULE}.frappe.has_permission", return_value=True), patch(
            f"{MODULE}.frappe.db.sql", return_value=rows
        ) as mocked_sql:
            result = list_wastage(branch="Branch A")

        self.assertEqual(result, rows)
        query, values = mocked_sql.call_args.args
        self.assertIn("LEFT JOIN `tabWastage Item`", query)
        self.assertIn("w.`branch` = %(branch)s", query)
        self.assertEqual(values, {"branch": "Branch A"})
        self.assertTrue(mocked_sql.call_args.kwargs["as_dict"])

    def test_list_fails_closed_when_branch_missing(self):
        with self.assertRaises(frappe.ValidationError):
            list_wastage(branch=None)

    def test_list_narrowed_by_department_and_date_filters(self):
        with patch(f"{MODULE}.frappe.has_permission", return_value=True), patch(
            f"{MODULE}.frappe.db.sql", return_value=[]
        ) as mocked_sql:
            list_wastage(
                branch="Branch A",
                department="DEPT-1",
                from_date="2026-01-01",
                to_date="2026-01-31",
            )

        query, values = mocked_sql.call_args.args
        self.assertIn("w.creation BETWEEN %(from_date)s AND %(to_date)s", query)
        self.assertIn("w.`department` = %(department)s", query)
        self.assertEqual(values, {"branch": "Branch A", "department": "DEPT-1",
                                  "from_date": "2026-01-01", "to_date": "2026-01-31 23:59:59.999999"})


class TestAuthorizedWastageQuantities(FrappeTestCase):
    """Real database coverage for the child-item aggregation contract.

    Insert fixture rows directly: this tests the read query, independently of
    warehouse posting, approval permissions and unrelated link fixtures.
    """

    def _scope(self):
        return {"plan": frappe.generate_hash(length=20), "department": "Quantity Test Dept",
                "branch": "Quantity Test Branch", "company": "Quantity Test Company",
                "component_item": "COMP-1"}

    def _seed(self, scope, qty, status="Authorized", docstatus=1, item_code="COMP-1"):
        name = frappe.generate_hash(length=20)
        frappe.get_doc({"doctype": "URY Wastage", "name": name,
            **{key: value for key, value in scope.items() if key != "component_item"},
            "issue_authorization": scope["plan"], "status": status, "docstatus": docstatus,
        }).db_insert()
        frappe.get_doc({"doctype": "Wastage Item", "name": frappe.generate_hash(length=20),
            "parent": name, "parenttype": "URY Wastage", "parentfield": "items", "idx": 1,
            "docstatus": docstatus, "item_code": item_code, "qty": qty,
        }).db_insert()
        return name

    def test_only_submitted_authorized_component_rows_reduce_entitlement(self):
        from ury.ury.api.ury_issue_authorization import prior_quantities
        from ury.ury.api.ury_wastage_quantities import sum_authorized_wastage

        scope = self._scope()
        self._seed(scope, 3)
        self._seed(scope, 100, status="Draft", docstatus=0)
        self._seed(scope, 100, status="Rejected", docstatus=0)
        self._seed(scope, 100, docstatus=2)
        self._seed(scope, 100, item_code="COMP-2")
        other_scope = {**scope, "branch": "Another Branch"}
        self._seed(other_scope, 100)

        self.assertEqual(sum_authorized_wastage(scope), 3)
        self.assertEqual(prior_quantities(**scope)["wasted_qty"], 3)

    def test_held_quantity_excludes_the_document_being_approved(self):
        from ury.ury.api.ury_wastage_quantities import sum_authorized_wastage

        scope = self._scope()
        first = self._seed(scope, 3)
        self._seed(scope, 2)
        self.assertEqual(sum_authorized_wastage(scope, exclude_name=first), 2)
        auth = frappe._dict(name=scope["plan"], authorized_qty=10, component_item="COMP-1")
        self.assertEqual(held_quantity(auth), 5)
        self.assertEqual(held_quantity(auth, exclude_wastage=first), 8)
