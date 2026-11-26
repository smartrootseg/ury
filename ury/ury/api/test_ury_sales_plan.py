import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ury.ury.tests.factories import make_branch, make_item
from ury.ury.api.ury_sales_plan import (
    _guard_backward_transition,
    _validate_plan_scope,
    freeze_approval_snapshot,
    populate_item_production_context,
    validate_no_overlapping_plan_scope,
    validate_plan_has_demand,
    validate_plan_items,
    validate_items_on_active_menu,
    flag_stale_bom_revisions,
)


class TestURYSalesPlanContract(FrappeTestCase):
    """Scope checking, item validation, snapshot freezing, and audit logging
    run inside URYSalesPlan.validate() (ury/ury/doctype/ury_sales_plan/
    ury_sales_plan.py) on every status-changing save, including a real
    Workflow-engine-driven transition. Those guardrails are exercised here as
    direct unit tests of the still-standalone helper functions.

    transition_sales_plan() itself is no longer testable against a bare
    frappe._dict: it now routes through frappe.model.workflow.get_transitions()
    / apply_workflow(), which require a real, persisted "URY Sales Plan" doc
    and an active Workflow. See TestSalesPlanWorkflowTransitions below for
    those end-to-end tests.
    """

    def _doc(self, **values):
        doc = frappe._dict({"status": "Submitted for Approval", "branch": "Branch A", "company": "Company A", "plan_date": "2026-09-12", "items": [{"item_code": "MTPL", "qty": 2, "production_policy": "PRE_PRODUCED", "bom": "BOM-1"}], "insight_snapshot": {"source": "history"}})
        doc.update(values)
        return doc

    def test_validate_plan_scope_fails_closed_on_mismatch(self):
        with patch("ury.ury.api.ury_sales_plan.frappe.db.get_value", return_value="Other Company"):
            with self.assertRaises(frappe.ValidationError):
                _validate_plan_scope(self._doc())

    def test_validate_plan_items_runs_production_configuration_check(self):
        doc = self._doc()
        with patch(
            "ury.ury.api.ury_sales_plan.validate_item_production_configuration"
        ) as validate:
            validate_plan_items(doc)
        validate.assert_called_once_with("MTPL", "Branch A")

    def test_validate_plan_items_fails_closed_on_bad_mapping(self):
        doc = self._doc()
        with patch(
            "ury.ury.api.ury_sales_plan.validate_item_production_configuration",
            side_effect=frappe.ValidationError("invalid mapping"),
        ):
            with self.assertRaises(frappe.ValidationError):
                validate_plan_items(doc)
        self.assertFalse(doc.get("approval_snapshot"))

    def test_validate_plan_items_skips_untouched_zero_qty_rows(self):
        """A history-suggested row nobody actually planned (qty still 0) must
        never gate approval on its own production configuration -- see
        feedback_history_is_suggestion_not_precondition. Only a row with a
        real qty is actually part of the plan."""
        doc = self._doc(
            items=[
                {"item_code": "MTPL", "qty": 2, "production_policy": "PRE_PRODUCED", "bom": "BOM-1"},
                {"item_code": "UNCONFIGURED-ITEM", "qty": 0, "production_policy": "PRE_PRODUCED"},
            ]
        )
        with patch(
            "ury.ury.api.ury_sales_plan.validate_item_production_configuration"
        ) as validate:
            validate_plan_items(doc)
        validate.assert_called_once_with("MTPL", "Branch A")

    def test_plan_with_no_rows_cannot_leave_draft(self):
        """The complement to the test above: skipping qty-0 rows one by one
        left nothing checking that the plan as a whole plans SOMETHING, so an
        empty plan walked the entire path to Locked for Production."""
        with self.assertRaises(frappe.ValidationError):
            validate_plan_has_demand(self._doc(items=[]))

    def test_plan_with_only_zero_qty_rows_cannot_leave_draft(self):
        """A plan carrying the full history-suggested catalog, every row still
        at its default qty 0, plans exactly as much as an empty one."""
        doc = self._doc(
            items=[
                {"item_code": "MTPL", "qty": 0},
                {"item_code": "OTHER", "qty": 0},
            ]
        )
        with self.assertRaises(frappe.ValidationError):
            validate_plan_has_demand(doc)

    def test_plan_with_one_nonzero_row_can_leave_draft(self):
        doc = self._doc(
            items=[
                {"item_code": "MTPL", "qty": 0},
                {"item_code": "OTHER", "qty": 3},
            ]
        )
        validate_plan_has_demand(doc)

    def test_snapshot_is_immutable_once_created(self):
        doc = self._doc()
        # build_demand_vector() BOM-explodes each item against real BOM data
        # (compile_bom_vector -> frappe.db/frappe.get_all) -- irrelevant to
        # what this test actually checks (hash/JSON immutability), so it's
        # stubbed to a fixed value here rather than standing up a real BOM.
        with patch(
            "ury.ury.api.ury_sales_plan.build_demand_vector",
            return_value=[{"component_item": "FLOUR", "required_qty": 2}],
        ):
            first = freeze_approval_snapshot(doc)
            # doc is a frappe._dict (a dict subclass), so "doc.items" resolves to
            # the built-in dict.items() bound method rather than the "items"
            # field -- use item access to reach the actual field instead.
            doc["items"][0]["qty"] = 99
            self.assertEqual(freeze_approval_snapshot(doc), first)

    def test_freeze_approval_snapshot_populates_demand_vector(self):
        """The actual bug this task fixes: approval_snapshot["demand_vector"]
        must be populated at approval time, not left absent -- absence is
        exactly what made frozen_component_demand() in
        ury_issue_authorization.py fail closed for every real approval."""
        doc = self._doc(
            items=[
                {
                    "item_code": "MTPL",
                    "qty": 2,
                    "department": "Kitchen",
                    "production_unit": "…85025 tokens truncated…    @patch("ury.ury.services.production_unit_department_migration.frappe.get_all")
    @patch("ury.ury.services.production_unit_department_migration.frappe.db.exists")
    @patch("ury.ury.services.production_unit_department_migration.frappe.db.set_value")
    def test_apply_skips_when_company_is_missing_or_ambiguous(
        self, mock_set_value, mock_exists, mock_get_all, mock_get_doc
    ):
        def exists_side_effect(doctype, filters=None):
            if doctype == "DocType":
                return True
            if doctype == "URY Production Department":
                return False
            return True

        mock_exists.side_effect = exists_side_effect
        mock_get_all.return_value = [
            {
                "name": "Biryani",
                "production": "Biryani",
                "pos_profile": "POS-001",
                "branch": "Kozhikode",
                "warehouse": "Main Store - K",
                "department": None,
            }
        ]

        def get_value_side_effect(doctype, filters, fieldname, **kwargs):
            if doctype == "Warehouse" and filters == "Main Store - K":
                return None
            if doctype == "Branch" and filters == "Kozhikode":
                return None
            if doctype == "POS Profile" and filters == "POS-001":
                return None
            return None

        mock_get_doc.side_effect = AssertionError("No department should be created")
        with patch(
            "ury.ury.services.production_unit_department_migration.frappe.db.get_value",
            side_effect=get_value_side_effect,
        ):
            plan = apply_production_department_migration(dry_run=False)

        self.assertTrue(plan["applied"])
        self.assertEqual(plan["created"], [])
        self.assertEqual(plan["skipped"], ["Biryani"])
        mock_get_doc.assert_not_called()
        mock_set_value.assert_not_called()

    def test_kot_routing_still_reads_printers_from_production_unit(self):
        # frappe.model.document.Document.__init__ requires a doctype dict (or
        # a doctype/name pair to load from the DB) -- a bare call isn't a
        # valid constructor signature. Pass a minimal in-memory dict so no DB
        # lookup happens for this unit test.
        kot = URYKOT({"doctype": "URY KOT"})
        kot.name = "KOT-0001"
        kot.pos_profile = "POS-001"
        kot.production = "Biryani"
        kot.restaurant_table = None
        kot.table_takeaway = 0
        kot.invoice = "INV-0001"
        kot.owner = "Administrator"

        production_unit_printer_rows = [
            frappe._dict(
                {"printer": "Kitchen Printer", "custom_kot_print_format": "KOT", "custom_kot_print": 1}
            )
        ]

        def get_all_side_effect(doctype, filters=None, **kwargs):
            # multi_print_kot's frappe.db.get_all(...) call for the POS
            # Profile printers is implemented as a thin wrapper around this
            # same frappe.get_all, so patching it unconditionally would also
            # feed the mocked rows into that unrelated lookup and double the
            # print. Only return rows for the "URY Production Unit" lookup
            # this test is actually about.
            if filters and filters.get("parenttype") == "URY Production Unit":
                return production_unit_printer_rows
            return []

        with patch(
            "ury.ury.doctype.ury_kot.ury_kot.frappe.get_all",
            # multi_print_kot accesses attributes like
            # printer.custom_block_takeaway_kot on each row, matching how a
            # real frappe.get_all(...) call returns frappe._dict rows -- a
            # plain dict here would raise AttributeError.
            side_effect=get_all_side_effect,
        ) as mock_get_all, patch(
            "ury.ury.doctype.ury_kot.ury_kot.frappe.get_doc"
        ) as mock_get_printer:
            kot.multi_print_kot()

        mock_get_all.assert_any_call(
            "URY Printer Settings",
            fields=["printer", "custom_kot_print_format", "custom_kot_print", "custom_block_takeaway_kot"],
            filters={"parent": "Biryani", "custom_kot_print": 1, "parenttype": "URY Production Unit"},
            order_by="idx",
        )
        mock_get_printer.assert_called_once_with("Network Printer Settings", "Kitchen Printer")
        mock_get_printer.return_value.print_doc.assert_called_once_with(
            doctype="URY KOT", name="KOT-0001", print_format="KOT", job_type="KOT",
            extra_metadata={"invoice": "INV-0001", "restaurant_table": None,
                            "production": "Biryani", "job_owner": "Administrator"},
        )

    @patch("ury.ury.services.production_unit_department_migration.frappe.get_doc")
    @patch("ury.ury.services.production_unit_department_migration.frappe.get_all")
    @patch("ury.ury.services.production_unit_department_migration.frappe.db.exists")
    @patch("ury.ury.services.production_unit_department_migration.frappe.db.get_value")
    @patch("ury.ury.services.production_unit_department_migration.frappe.db.set_value")
    def test_apply_skips_when_cost_center_is_missing_or_ambiguous(
        self, mock_set_value, mock_get_value, mock_exists, mock_get_all, mock_get_doc
    ):
        def exists_side_effect(doctype, filters=None):
            if doctype == "DocType":
                return True
            if doctype == "URY Production Department":
                return False
            return True

        mock_exists.side_effect = exists_side_effect
        mock_get_all.side_effect = [
            [
                {
                    "name": "Biryani",
                    "production": "Biryani",
                    "pos_profile": "POS-001",
                    "branch": "Kozhikode",
                    "warehouse": "Main Store - K",
                    "department": None,
                }
            ],
            ["CC-1", "CC-2"],
        ]
        mock_get_value.side_effect = lambda doctype, filters, fieldname, **kwargs: (
            "Tridz Technologies Pvt. Ltd." if doctype in {"Warehouse", "Branch", "POS Profile"} else None
        )

        plan = apply_production_department_migration(dry_run=False)

        self.assertTrue(plan["applied"])
        self.assertEqual(plan["created"], [])
        self.assertEqual(plan["skipped"], ["Biryani"])
        mock_get_doc.assert_not_called()
        mock_set_value.assert_not_called()
