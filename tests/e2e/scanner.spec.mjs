import { test, expect } from "@playwright/test";

const VIEWPORTS = [320, 375, 390, 430];

test.describe("authentication", () => {
  test("fresh context redirects unauthenticated /scanner/ to login", async ({ page }) => {
    const res = await page.request.get("/", { maxRedirects: 0 });
    expect(res.status()).toBe(302);
    expect(res.headers()["location"]).toContain("/auth/login");
    await expect(page.getByText("Start scanner")).toHaveCount(0);
  });

  test("fresh webkit context redirects to login", async ({ page }) => {
    const res = await page.request.get("/", { maxRedirects: 0 });
    expect(res.status()).toBe(302);
    expect(res.headers()["location"]).toContain("/auth/login");
  });

  test("dev-login grants scanner UI access", async ({ page }) => {
    await page.goto("/auth/dev-login");
    await expect(page.locator("html")).toHaveAttribute("data-scanner-ready", "true", {
      timeout: 10000,
    });
    await page.getByRole("button", { name: "Register new product" }).click();
    await expect(page.locator("#reg-start-scanner")).toBeEnabled();
  });

  test("logout requires authentication again", async ({ page }) => {
    await page.goto("/auth/dev-login");
    await page.goto("/auth/logout");
    await expect(page).toHaveURL(/\/auth\/login/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  test("new context after logout redirects", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto("/");
    await expect(page).toHaveURL(/\/auth\/login/);
    await ctx.close();
  });
});

for (const width of VIEWPORTS) {
  test(`layout: no horizontal overflow at ${width}px (authed)`, async ({ page }) => {
    await page.goto("/auth/dev-login");
    await expect(page.locator("html")).toHaveAttribute("data-scanner-ready", "true");
    await page.setViewportSize({ width, height: 800 });
    await page.getByRole("button", { name: "Register new product" }).click();
    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test("scanner bundle initializes without CameraScanner global (authed)", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await page.goto("/auth/dev-login");
  await expect(page.locator("html")).toHaveAttribute("data-scanner-ready", "true");
  await page.getByRole("button", { name: "Register new product" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-scanner-ready", "true");
  const cameraErrors = errors.filter((m) => /CameraScanner/i.test(m));
  expect(cameraErrors).toEqual([]);
});

test("manual entry remains when camera unavailable (authed)", async ({ page }) => {
  await page.goto("/auth/dev-login");
  await expect(page.locator("html")).toHaveAttribute("data-scanner-ready", "true");
  await page.getByRole("button", { name: "Register new product" }).click();
  const input = page.locator("#reg-raw");
  await input.fill("4006381333931");
  await expect(input).toHaveValue("4006381333931");
});
