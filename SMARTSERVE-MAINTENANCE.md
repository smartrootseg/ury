# Smartserve URY customization

The Smartserve POS course buttons allow multiline labels while keeping item-count badges separate.

## Deployment source

- Upstream: https://github.com/ury-erp/ury, version-16
- Starting revision: 5262bbedb129806489930b63709e4cc14f943d6b
- Maintained owner: smartrootseg
- Intended deployment branch: smartserve-version-16
- Source change: pos/src/components/Sidebar.tsx

Frappe Cloud must deploy URY from this maintained fork and branch. Do not switch its URY source back to the upstream repository when updating.

## Updating URY

Merge upstream version-16 into smartserve-version-16. Resolve any conflicts in Sidebar.tsx while retaining natural button height, multiline labels, a shrinking label group, and nonshrinking count badges. Review and test before deploying the merged branch. Never force-reset the maintained branch to upstream.

Run the existing Sidebar tests and the POS production build. Verify on the deployed POS that long course names remain inside their buttons, the badges remain separate, and selecting a course displays the expected products. A CSS or component redesign upstream requires a fresh layout check; a fork preserves the committed change but cannot guarantee compatibility with arbitrary future redesigns.

Use the ordinary repository build scripts during Cloud deployment. Generated frontend assets are build output and should not be edited manually. The temporary SSH build used a separate assets/course-wrap directory to avoid a cached missing-asset response; permanent deployments can use the normal build output.

The original source fix is saved separately as ury-pos-course-wrap.patch. No private SSH key, certificate or site data belongs in the repository.

