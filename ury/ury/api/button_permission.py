import frappe


@frappe.whitelist()
def cancel_check():
    if frappe.permissions.has_permission(
        "POS Invoice", "cancel", print_logs=False
    ):
        permission = True
    else:
        permission = False
    return permission
