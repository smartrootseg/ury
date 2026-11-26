import { test, expect } from '@playwright/test';
for (const dir of ['ltr', 'rtl']) {
  for (const width of [1024, 1280]) {
    test(`course labels stay separate from counts (${dir}, ${width})`, async ({page}) => {
      await page.setViewportSize({width,height:1000});
      await page.goto(`/tests/layout/index.html?dir=${dir}`);
      const course = page.getByRole('button', {name:'Fresh Juices and Smoothies 1000',exact:true});
      await expect(course).toBeVisible();
      const results = await page.locator('nav button').evaluateAll(buttons => buttons.map(button => {
        const label = button.querySelector('span')!;
        const badge = button.lastElementChild!;
        const b=button.getBoundingClientRect(),l=label.getBoundingClientRect(),c=badge.getBoundingClientRect();
        const rtl=getComputedStyle(button).direction==='rtl';
        return {label:label.textContent,contained:l.left>=b.left && l.right<=b.right && c.left>=b.left && c.right<=b.right,
          gap:rtl ? l.left-c.right : c.left-l.right,
          noOverflow:label.scrollWidth<=label.clientWidth+1,
          height:l.height,lineHeight:parseFloat(getComputedStyle(label).lineHeight)};
      }));
      expect(results).toHaveLength(6);
      for (const result of results) {
        expect(result.contained,result.label!).toBeTruthy();
        expect(result.gap,result.label!).toBeGreaterThanOrEqual(7);
        expect(result.noOverflow,result.label!).toBeTruthy();
      }
      expect(results[1].height).toBeGreaterThan(results[1].lineHeight);
      await course.click();
      await expect(course).toHaveClass(/bg-white/);
    });
  }
}
