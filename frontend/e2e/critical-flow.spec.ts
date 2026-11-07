import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

const PASSWORD = "Student1234!";

test("yeni öğrenci kayıt olur", async ({ page }) => {
  const email = `e2e-${Date.now()}@medspaced.local`;
  await page.goto("/register");
  await page.getByLabel("Ad soyad").fill("E2E Öğrenci");
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola (en az 8 karakter)").fill(PASSWORD);
  await page.getByRole("button", { name: "Hesap oluştur" }).click();
  await expect(page.getByRole("heading", { name: /Merhaba/ })).toBeVisible();
});

test("reviewer içerik yükler, soru üretir ve onaylar", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("E-posta").fill("reviewer@medspaced.local");
  await page.getByLabel("Parola").fill("Reviewer1234!");
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page.getByRole("heading", { name: /Merhaba/ })).toBeVisible();

  await page.goto("/content");
  await page.locator("#file").setInputFiles({
    name: "e2e-anestezi.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# E2E Anestezi\n\nPropofol indüksiyon dozu 1.5-2.5 mg/kg IV'dir.\n"),
  });
  await page.getByRole("button", { name: "Yükle ve işle" }).click();
  await expect(page.getByText(/yüklendi ve \d+ chunk/)).toBeVisible({ timeout: 30_000 });

  const sourceValue = await page
    .locator("#sourceFile option")
    .filter({ hasText: "e2e-anestezi.md" })
    .getAttribute("value");
  expect(sourceValue).toBeTruthy();
  await page.locator("#sourceFile").selectOption(sourceValue!);
  await page.locator("#maxChunks").fill("1");
  await page.getByRole("button", { name: "Üret" }).click();
  await expect(page.getByText(/soru üretildi/)).toBeVisible({ timeout: 30_000 });

  await page.goto("/review");
  await page.getByRole("button", { name: "İncelemede" }).click();
  const approve = page.getByRole("button", { name: "Onayla" });
  await expect(approve.first()).toBeVisible();
  const before = await approve.count();
  await approve.first().click();
  await expect(approve).toHaveCount(Math.max(0, before - 1));
});

test("öğrenci tekrar kartı görür", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("E-posta").fill("student@medspaced.local");
  await page.getByLabel("Parola").fill("Student1234!");
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page.getByRole("heading", { name: /Merhaba/ })).toBeVisible();

  await page.getByRole("link", { name: "Çalışmaya başla" }).click();
  await expect(page).toHaveURL(/\/study$/);
  await expect(page.locator(".study-shell")).toBeVisible();
  await expect(page.getByText(/Kart 1 \//)).toBeVisible();
  await expect(page.getByRole("button", { name: "Cevabı kontrol et" })).toBeVisible();
});

test("öğrenci sınav başlatır ve bitirir", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("E-posta").fill("student@medspaced.local");
  await page.getByLabel("Parola").fill("Student1234!");
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page.getByRole("heading", { name: /Merhaba/ })).toBeVisible();

  await page.goto("/exam");
  await page.locator('input[type="number"]').first().fill("3");
  await page.getByRole("button", { name: "Sınavı başlat" }).click();
  await expect(page.getByText("3 soru")).toBeVisible();

  const cards = page.locator(".review-list .card");
  const count = await cards.count();
  for (let index = 0; index < count; index += 1) {
    const card = cards.nth(index);
    const option = card.locator("button.option").first();
    if (await option.count()) {
      await option.click();
      continue;
    }
    const select = card.locator("select").first();
    if (await select.count()) {
      await select.selectOption({ index: 1 });
      continue;
    }
    const textarea = card.locator("textarea").first();
    if (await textarea.count()) {
      await textarea.fill("E2E klinik karar ve gerekçe.");
      continue;
    }
    const input = card.locator('input[type="text"], input:not([type])').first();
    if (await input.count()) await input.fill("E2E cevap");
  }

  await page.getByRole("button", { name: "Sınavı bitir" }).click();
  await expect(page.getByRole("heading", { name: "Sınav sonucu" })).toBeVisible();
});
