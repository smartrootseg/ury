# Smartserve update and release process

## What runs automatically

`Smartserve upstream updates` checks `ury-erp/ury:version-16` every Monday at 04:17 UTC and can also be run from Actions at any time. This tracks the ERPNext 16 compatible upstream branch, including fixes between tagged releases; it never changes major branches automatically.

New upstream commits are merged into `updates/ury-version-16`, retaining our customization commits. An existing update branch is extended with ordinary merges, never force-reset. A conflict fails the update and reports the affected paths in the Actions summary; the deployment branch remains unchanged. Resolve conflicts manually without discarding customizations.

The candidate is tested through a reusable workflow even when GitHub suppresses push-triggered runs made by its own token. Tests run with read-only repository access, no site credentials and no production data. Only the preparation job can push the candidate branch; only the review job can create/update its pull request. Neither can deploy a site. Failed candidates become draft pull requests. Existing drafts require a maintainer to mark them ready after reviewing results.

## Validation

- All POS unit tests and management-frontend unit tests.
- The normal production build for every URY frontend.
- Chromium layout regression using the real Sidebar component, Button, Badge and Tailwind styles; only data, translations, dialog and icon selection are fixtures. Tests cover long English/Arabic labels, LTR and RTL, four-digit counts, long unbroken words, category selection and two viewport widths.
- The upstream v16 backend suite on four disposable Frappe 16 test-site shards. Its documented upstream exclusions remain visible in `smartserve-backend.yml`; passing CI does not replace business acceptance testing. Backend failures are blocking rather than ignored.
- `Smartserve validation` is the combined pass/fail result. Never treat a skipped, cancelled or failed result as approval.

See the Actions run linked in each update PR for exact candidate SHA and results. Automated PRs may require **Approve workflows to run** before GitHub starts their PR checks. Rerun checks after any new commits or conflict resolutions; require an up-to-date passing PR check before merging.

## Promotion — human controlled

1. Review the upstream changes, any dependency changes and the test results for the exact candidate. Ensure our menu-course wrapping remains intact. Never use Sync fork's destructive reset on `smartserve-version-16`.
2. For operational changes, create a disposable copy of Smartserve on a testing bench running the candidate. Take a fresh database/files backup before any production update. Do not test migrations or submit test transactions on the prospect demo itself.
3. On the copy, verify all three branch menus, standard and lounge pricing, addons, unavailable-item blocking, product-bundle raw-material consumption, and food/drinks/sweets KDS routing. Verify one full order/payment/cancellation flow and the accounting/stock impact. Record the candidate SHA, results and any exclusions in the PR.
4. Merge only a passing, reviewed update PR into `smartserve-version-16`. Frappe Cloud continues to use this maintained branch. No workflow has deployment credentials, a deploy webhook or an automatic merge step.
5. In Frappe Cloud, fetch the branch update and deploy at a chosen time. Verify the live POS and branch/KDS configuration after deployment. Keep the pre-update backup and previous deployed revision until accepted.
6. If rollback is necessary, redeploy the previous app revision; if migrations changed data, restore the matching database and files backup using Frappe Cloud's restore flow. A code rollback alone is not a database rollback.

## Repository configuration

Use `smartserve-version-16` as the default branch so the weekly schedule and manual workflows are discoverable. Enable the three Smartserve workflows. Leave the inherited upstream deployment workflows disabled; they target upstream infrastructure and are not part of this process. No SSH key, site password or Frappe Cloud token is needed by these workflows.

Keep default workflow permissions read-only. GitHub's repository setting **Allow GitHub Actions to create and approve pull requests** must be enabled to let the review job open PRs; GitHub combines those capabilities in one setting, but our workflow never submits approvals. Protect `smartserve-version-16` by requiring a pull request, an up-to-date passing `Smartserve validation` check, and disallowing force pushes and branch deletion.

GitHub disables scheduled workflows in inactive public repositories after 60 days. Check Actions if weekly checks stop; re-enable the schedule if GitHub disables it. Follow failed-run notifications in GitHub and investigate rather than bypassing a red validation gate.
