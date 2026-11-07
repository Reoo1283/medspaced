import { expect, test } from "@playwright/test";

test("öğrenci giriş yapar ve tekrar kartı görür", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("E-posta").fill("student@medspaced.local");
  await page.getByLabel("Parola").fill("Student1234!");
  await page.getByRole("button", { name: "Giriş yap" }).click();

  await expect(page.getByRole("heading", { name: /Merhaba/ })).toBeVisible();
  await expect(page.getByText("Bugün tekrar")).toBeVisible();

  await page.getByRole("link", { name: "Çalışmaya başla" }).click();
  await expect(page).toHaveURL(/\/study$/);
  await expect(page.getByRole("heading", { name: "Tekrar" })).toBeVisible();
  await expect(page.locator(".study-shell")).toBeVisible();
  await expect(page.getByText(/Kart 1 \//)).toBeVisible();
  await expect(page.getByRole("button", { name: "Cevabı kontrol et" })).toBeVisible();
});
