import { existsSync } from "node:fs";
import { test, expect } from "@playwright/test";

test("empty state preserves unknown inventory, material separation and responsive navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A clearer view of your stock." }),
  ).toBeVisible();
  await expect(
    page.getByText("Missing branch data is never counted as zero inventory."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Natural diamonds", exact: true })
    .click();
  await expect(
    page.getByText(
      "Natural diamonds · values are kept separate from other materials",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Data & imports", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reconciliation gate", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Planning rules", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Margins & stone economics" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Activate approved rule" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Stock overview", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Inventory command" })
    .fill("show old gold at NV");
  await page.getByRole("button", { name: "Interpret command" }).click();
  await expect(
    page.getByRole("heading", { name: "Label ageing register" }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Branch filter" }),
  ).toHaveValue("NV");
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Data & imports", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Import an Ornate workbook" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("real Ornate export previews exact label totals and does not confirm assumptions automatically", async ({
  page,
}) => {
  const stockExport = process.env.RG_TEST_STOCK_FILE ||
    "/workspace/attachments/0ae7ea1d-ce39-43b8-ae6d-cac6b66be35c/ALLSTOCK1410.xls";
  test.skip(!existsSync(stockExport), "Supply RG_TEST_STOCK_FILE for the private real-export check");
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Operator identity" })
    .fill("Browser verification");
  await page
    .getByRole("button", { name: "Data & imports", exact: true })
    .click();
  await page
    .getByLabel("Excel workbook")
    .setInputFiles(stockExport);
  await expect(page.getByText("Verified Ornate report layout")).toBeVisible();
  await expect(page.getByText(/14151 labels/)).toBeVisible();
  await expect(
    page.getByLabel("Closing Value is confirmed full landed buying cost."),
  ).not.toBeChecked();
  await expect(
    page.getByLabel("Days is confirmed original label age."),
  ).not.toBeChecked();
  await page
    .getByRole("button", { name: "Validate Ornate report", exact: true })
    .click();
  await expect(page.getByText("14151 rows", { exact: true })).toBeVisible();
  await expect(
    page.getByText("0 errors · 5 warnings", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "IK coverage", exact: true }),
  ).toHaveValue("missing");
  await expect(
    page.getByRole("button", { name: "Confirm reconciled snapshot" }),
  ).toBeDisabled();
});
