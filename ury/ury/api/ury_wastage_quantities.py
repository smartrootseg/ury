"""Read approved wastage quantities from the current child-item schema."""

import frappe
from frappe.utils import flt


def sum_authorized_wastage(filters, exclude_name=None):
    """Sum submitted, authorized items within the supplied business scope.

    Draft, rejected and cancelled documents never consume held quantities or
    sales-plan entitlement. Keep this query shared by both calculations.
    """
    conditions = ["w.status = 'Authorized'", "w.docstatus = 1"]
    values = {}
    for field in ("plan", "department", "branch", "company", "issue_authorization"):
        if field in filters:
            conditions.append(f"w.`{field}` = %({field})s")
            values[field] = filters[field]
    if filters.get("component_item"):
        conditions.append("i.item_code = %(component_item)s")
        values["component_item"] = filters["component_item"]
    if exclude_name:
        conditions.append("w.name != %(exclude_name)s")
        values["exclude_name"] = exclude_name

    rows = frappe.db.sql(
        f"""SELECT COALESCE(SUM(i.qty), 0)
        FROM `tabURY Wastage` w
        JOIN `tabWastage Item` i ON i.parent = w.name
            AND i.parenttype = 'URY Wastage' AND i.parentfield = 'items'
        WHERE {' AND '.join(conditions)}""",
        values,
    )
    return flt(rows[0][0]) if rows else 0
