# Copyright (c) 2026, Tridz Technologies Pvt. Ltd and contributors
# See license.txt
"""Test the current counted-stock model, not obsolete signed adjustment APIs.

Stock Entry persistence is mocked; inspect the receipt/issue documents passed
to ERPNext, alongside invalid-count safeguards and cancellation behavior.
"""
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from ury.ury.doctype.stock_correction.stock_correction import StockCorrection

MODULE = "ury.ury.doctype.stock_correction.stock_correction"


def _row(qty=5, warehouse="WH-1", rate=10, item_code="ITEM-1"):
	row = frappe._dict(item_code=item_code, qty=qty, warehouse=warehouse,
		valuation_rate=rate, current_qty=2, current_valuation_rate=8, uom="Nos", idx=1)
	row.precision = lambda field: 2
	return row


def _new_doc(items=None, **values):
	doc = StockCorrection({"doctype": "Stock Correction", "name": "SC-TEST",
		"company": "Company A", "branch": "Branch A", "cost_center": "CC-1",
		"posting_date": "2026-01-01", "posting_time": "12:00:00",
		"edit_posting_date": 1, "status": "Draft", **values})
	doc.items = items if items is not None else []
	doc.correction_stock_entries = []
	return doc


class TestCountedStockValidation(FrappeTestCase):
	def _validate(self, rows, warehouse_exists=True):
		doc = _new_doc(rows)
		with patch.object(doc, "validate_item"), \
			patch(f"{MODULE}.frappe.db.get_default", return_value="INR"), \
			patch(f"{MODULE}.frappe.db.get_value", return_value="WH-1" if warehouse_exists else None), \
			patch(f"{MODULE}.msgprint"):
			doc.validate_data()

	def test_zero_count_is_valid_and_can_empty_a_warehouse(self):
		self._validate([_row(qty=0)])

	def test_negative_count_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Negative Quantity"):
			self._validate([_row(qty=-1)])

	def test_negative_valuation_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Negative Valuation"):
			self._validate([_row(rate=-1)])

	def test_missing_quantity_and_rate_are_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "specify either Quantity"):
			self._validate([_row(qty=None, rate=None)])

	def test_duplicate_item_and_warehouse_are_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Same item and warehouse"):
			self._validate([_row(), _row()])

	def test_same_item_in_distinct_warehouses_is_valid(self):
		self._validate([_row(), _row(warehouse="WH-2")])

	def test_missing_warehouse_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Warehouse not found"):
			self._validate([_row()], warehouse_exists=False)

	def test_item_validation_errors_are_not_dropped(self):
		doc = _new_doc([_row()])
		doc.validation_messages = []
		with patch(f"{MODULE}.frappe.get_doc", side_effect=frappe.ValidationError("Disabled item")):
			doc.validate_item("ITEM-1", doc.items[0])
		self.assertIn("Disabled item", doc.validation_messages[0])

	def test_quantity_and_valuation_differences_use_counted_stock(self):
		doc = _new_doc([_row()])
		doc.set_total_qty_and_amount()
		self.assertEqual(doc.items[0].amount, 50)
		self.assertEqual(doc.items[0].current_amount, 16)
		self.assertEqual(doc.items[0].quantity_difference, 3)
		self.assertEqual(doc.items[0].amount_difference, 34)

	def test_invalid_data_blocks_calculations(self):
		doc = _new_doc([_row(qty=-1)])
		with patch.object(doc, "validate_data", side_effect=frappe.ValidationError("Invalid count")), \
			patch.object(doc, "set_total_qty_and_amount") as totals:
			with self.assertRaises(frappe.ValidationError):
				doc.validate()
		totals.assert_not_called()


class TestCorrectionStockEntries(FrappeTestCase):
	def _create(self, rows, current_qty=2):
		doc, stored, entries = _new_doc(rows), MagicMock(), []

		def new_entry(doctype):
			self.assertEqual(doctype, "Stock Entry")
			entry = MagicMock()
			entry.name = f"STE-{len(entries) + 1}"
			entries.append(entry)
			return entry

		with ExitStack() as stack:
			stack.enter_context(patch(f"{MODULE}.frappe.get_doc", return_value=stored))
			stack.enter_context(patch(f"{MODULE}.frappe.new_doc", side_effect=new_entry))
			stack.enter_context(patch(f"{MODULE}.get_stock_balance_for", return_value={"qty": current_qty, "rate": 8}))
			stack.enter_context(patch(f"{MODULE}.frappe.db.exists", return_value=None))
			stack.enter_context(patch(f"{MODULE}.frappe.db.get_value", return_value=10))
			# Surface errors instead of entering the controller's retry path.
			stack.enter_context(patch(f"{MODULE}.frappe.db.rollback", side_effect=AssertionError("Stock entry creation failed")))
			doc.create_stock_entries()
		return stored, entries

	def test_increased_count_receives_only_the_difference(self):
		stored, entries = self._create([_row(qty=5)])
		self.assertEqual(len(entries), 1)
		entry = entries[0]
		self.assertEqual(entry.stock_entry_type, "Material Receipt")
		item = entry.append.call_args.args[1]
		self.assertEqual(item["qty"], 3)
		self.assertEqual(item["t_warehouse"], "WH-1")
		self.assertNotIn("s_warehouse", item)
		self.assertEqual(entry.company, "Company A")
		self.assertEqual(entry.branch, "Branch A")
		entry.insert.assert_called_once()
		entry.submit.assert_called_once()
		stored.append.assert_called_once_with("correction_stock_entries", {"item_code": "ITEM-1", "stock_entry": "STE-1"})
		self.assertEqual(stored.status, "Submitted")

	def test_decreased_count_issues_only_the_difference(self):
		_, entries = self._create([_row(qty=1)], current_qty=5)
		self.assertEqual(entries[0].stock_entry_type, "Material Issue")
		item = entries[0].append.call_args.args[1]
		self.assertEqual(item["qty"], 4)
		self.assertEqual(item["s_warehouse"], "WH-1")
		self.assertNotIn("t_warehouse", item)

	def test_zero_count_issues_all_current_stock(self):
		_, entries = self._create([_row(qty=0)], current_qty=5)
		self.assertEqual(entries[0].append.call_args.args[1]["qty"], 5)

	def test_unchanged_count_creates_no_entry(self):
		stored, entries = self._create([_row(qty=2)])
		self.assertEqual(entries, [])
		stored.append.assert_not_called()

	def test_one_correction_can_receive_one_item_and_issue_another(self):
		_, entries = self._create([_row(qty=5), _row(item_code="ITEM-2", qty=1)])
		self.assertEqual([entry.stock_entry_type for entry in entries], ["Material Receipt", "Material Issue"])


class TestCorrectionLifecycle(FrappeTestCase):
	def test_submit_schedules_stock_creation(self):
		doc = _new_doc([_row()])
		with patch.object(doc, "_submit") as submit, patch.object(doc, "enqueue_create_stock_entries") as create:
			doc.submit()
		submit.assert_called_once()
		create.assert_called_once()

	def test_queued_document_does_not_schedule_duplicate_creation(self):
		doc = _new_doc([_row()], status="Queued")
		with patch.object(doc, "_submit"), patch.object(doc, "enqueue_create_stock_entries") as create:
			doc.submit()
		create.assert_not_called()

	def test_cancel_cancels_linked_stock_entries(self):
		doc = _new_doc([_row()])
		with patch.object(doc, "_cancel") as cancel, patch.object(doc, "cancel_stock_entry") as cancel_entries:
			doc.cancel()
		cancel.assert_called_once()
		cancel_entries.assert_called_once()

	def test_no_linked_entries_requires_no_lookup(self):
		with patch(f"{MODULE}.frappe.get_doc") as get_doc:
			_new_doc().cancel_stock_entry()
		get_doc.assert_not_called()

	def test_only_submitted_linked_entries_are_cancelled(self):
		doc = _new_doc()
		doc.correction_stock_entries = [frappe._dict(stock_entry="STE-1"), frappe._dict(stock_entry="STE-2")]
		submitted, cancelled = MagicMock(docstatus=1), MagicMock(docstatus=2)
		with patch(f"{MODULE}.frappe.get_doc", side_effect=[submitted, cancelled]) as get_doc:
			doc.cancel_stock_entry()
		self.assertEqual(get_doc.call_count, 2)
		submitted.cancel.assert_called_once()
		cancelled.cancel.assert_not_called()
