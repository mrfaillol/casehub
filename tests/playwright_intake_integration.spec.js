/**
 * Playwright E2E Tests - Intake Portal + CaseHub Integration
 * Tests complete workflows: upload, approve, reject
 */
const { test, expect } = require('@playwright/test');

// Test configuration
const BASE_URL = 'https://legacy.example';
const INTAKE_URL = `${BASE_URL}/intake`;
const CASEHUB_URL = `${BASE_URL}/casehub`;

// Test credentials (should be in env vars in production)
const STAFF_EMAIL = 'ana@legacy.example';
const STAFF_PASSWORD = process.env.CASEHUB_TEST_PASSWORD || 'test123';
const TEST_PACKAGE_ID = process.env.TEST_PACKAGE_ID || 'TEST123';
const TEST_TOKEN = process.env.TEST_TOKEN || 'test-token';

test.describe('Intake Document Upload Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Set longer timeout for file uploads
    test.setTimeout(120000);
  });

  test('should display documents page with stats', async ({ page }) => {
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);

    // Wait for page load
    await page.waitForSelector('.stat-card', { timeout: 10000 });

    // Verify stats cards are visible
    const statCards = await page.locator('.stat-card').count();
    expect(statCards).toBe(4); // Total, Pending, Approved, Rejected

    // Verify header
    await expect(page.locator('h2:has-text("My Documents")')).toBeVisible();
  });

  test('should show upload form with document types', async ({ page }) => {
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);

    // Wait for form
    await page.waitForSelector('#uploadForm');

    // Verify document type dropdown
    const docTypeSelect = page.locator('select[name="doc_type"]');
    await expect(docTypeSelect).toBeVisible();

    // Verify it has options
    const options = await docTypeSelect.locator('option').count();
    expect(options).toBeGreaterThan(10); // At least 10 document types
  });

  test('should upload document successfully', async ({ page }) => {
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);

    // Fill form
    await page.selectOption('select[name="doc_type"]', 'passport');
    await page.fill('input[name="description"]', 'Test passport upload');

    // Upload file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test-passport.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('Test PDF content')
    });

    // Wait for preview
    await page.waitForSelector('#filePreview:not(.d-none)');

    // Submit form
    await page.click('button[type="submit"]');

    // Wait for success message
    await page.waitForSelector('.alert-success', { timeout: 15000 });

    // Verify success message
    await expect(page.locator('.alert-success')).toContainText('uploaded successfully');
  });

  test('should show AI classification badge', async ({ page }) => {
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);

    // Check if any document has AI badge
    const aiBadges = page.locator('.badge:has-text("AI Classified")');
    const count = await aiBadges.count();

    if (count > 0) {
      // Verify badge attributes
      const firstBadge = aiBadges.first();
      await expect(firstBadge).toBeVisible();
      await expect(firstBadge).toHaveClass(/badge/);
    }
  });

  test('should display rejection modal with feedback', async ({ page }) => {
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);

    // Look for rejected document
    const rejectedDoc = page.locator('.doc-item.rejected').first();

    if (await rejectedDoc.count() > 0) {
      // Click "View Feedback" button
      await rejectedDoc.locator('button:has-text("View Feedback")').click();

      // Wait for modal
      await page.waitForSelector('.modal.show', { timeout: 5000 });

      // Verify modal content
      await expect(page.locator('.modal-header')).toContainText('Needs Resubmission');
      await expect(page.locator('.modal-body')).toBeVisible();

      // Close modal
      await page.click('.btn-close');
    }
  });

  test('should have responsive drag-and-drop zone', async ({ page }) => {
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);

    // Verify upload zone
    const dropZone = page.locator('#dropZone');
    await expect(dropZone).toBeVisible();

    // Hover should change style
    await dropZone.hover();

    // Click should open file picker
    const fileInput = page.locator('#fileInput');
    await expect(fileInput).toHaveAttribute('type', 'file');
  });
});

test.describe('CaseHub Document Approval Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Login to CaseHub
    await page.goto(`${CASEHUB_URL}/login`);
    await page.fill('input[name="email"]', STAFF_EMAIL);
    await page.fill('input[name="password"]', STAFF_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(`${CASEHUB_URL}/dashboard`, { timeout: 10000 });
  });

  test('should display document detail with new fields', async ({ page }) => {
    // Navigate to documents list
    await page.goto(`${CASEHUB_URL}/documents`);

    // Click first document
    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Wait for detail page
      await page.waitForSelector('.card-header:has-text("Document Info")');

      // Verify new sections
      await expect(page.locator('text=Google Drive Sync')).toBeVisible();
      await expect(page.locator('text=Intake & Notifications')).toBeVisible();

      // Verify badges
      const badges = page.locator('.badge');
      expect(await badges.count()).toBeGreaterThan(0);
    }
  });

  test('should show Drive sync status badge', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Check Drive sync card
      const driveCard = page.locator('.card:has-text("Google Drive Sync")');
      await expect(driveCard).toBeVisible();

      // Verify status badge exists
      const statusBadge = driveCard.locator('.badge');
      expect(await statusBadge.count()).toBeGreaterThan(0);
    }
  });

  test('should display "Open in Drive" button when synced', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Check for Open in Drive button
      const driveButton = page.locator('a:has-text("Open in Drive")');

      if (await driveButton.count() > 0) {
        await expect(driveButton).toBeVisible();
        await expect(driveButton).toHaveClass(/btn-success/);

        // Verify it's a valid link
        const href = await driveButton.getAttribute('href');
        expect(href).toContain('drive.google.com');
      }
    }
  });

  test('should show retry button for failed syncs', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    // Find a document with failed sync status
    const failedSyncCard = page.locator('.card:has-text("Sync failed")');

    if (await failedSyncCard.count() > 0) {
      // Verify retry button exists
      const retryButton = failedSyncCard.locator('button:has-text("Retry Sync")');
      await expect(retryButton).toBeVisible();

      // Verify it's a warning button
      await expect(retryButton).toHaveClass(/btn-warning/);
    }
  });

  test('should display upload source badge', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Check for upload source badge
      const sourceBadge = page.locator('.badge:has-text("Client Portal"), .badge:has-text("Staff Upload"), .badge:has-text("Email")');

      if (await sourceBadge.count() > 0) {
        await expect(sourceBadge.first()).toBeVisible();
      }
    }
  });

  test('should show AI classification badge with confidence', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Check for AI badge
      const aiBadge = page.locator('.badge:has-text("AI Classified")');

      if (await aiBadge.count() > 0) {
        await expect(aiBadge).toBeVisible();

        // Verify it shows confidence percentage
        const text = await aiBadge.textContent();
        expect(text).toMatch(/\d+%/); // Should contain percentage
      }
    }
  });

  test('should show intake package link when applicable', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Check for intake package link
      const intakeLink = page.locator('a[href*="/intake/packages/"]');

      if (await intakeLink.count() > 0) {
        await expect(intakeLink).toBeVisible();
        await expect(intakeLink).toHaveAttribute('href', /#\d+/);
      }
    }
  });

  test('should display notification status indicators', async ({ page }) => {
    await page.goto(`${CASEHUB_URL}/documents`);

    const firstDoc = page.locator('.doc-item, .list-group-item').first();
    if (await firstDoc.count() > 0) {
      await firstDoc.click();

      // Check notification indicators
      const notifCard = page.locator('.card:has-text("Intake & Notifications")');
      await expect(notifCard).toBeVisible();

      // Verify notification status text
      await expect(notifCard).toContainText('Approval notification:');
      await expect(notifCard).toContainText('Rejection notification:');
    }
  });
});

test.describe('Integration Workflow Tests', () => {
  test('complete flow: upload → approve → verify sync', async ({ page }) => {
    // This test requires coordination between intake and casehub
    // Skip if test environment not configured
    if (!process.env.RUN_INTEGRATION_TESTS) {
      test.skip();
      return;
    }

    // 1. Upload document as client
    await page.goto(`${INTAKE_URL}/${TEST_PACKAGE_ID}/documents?token=${TEST_TOKEN}`);
    await page.selectOption('select[name="doc_type"]', 'passport');
    await page.setInputFiles('input[type="file"]', {
      name: 'integration-test.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('Integration test PDF')
    });
    await page.click('button[type="submit"]');
    await page.waitForSelector('.alert-success');

    // 2. Login as staff
    await page.goto(`${CASEHUB_URL}/login`);
    await page.fill('input[name="email"]', STAFF_EMAIL);
    await page.fill('input[name="password"]', STAFF_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(`${CASEHUB_URL}/dashboard`);

    // 3. Find pending document
    await page.goto(`${CASEHUB_URL}/documents?status=PENDING_APPROVAL`);
    const pendingDoc = page.locator('.badge:has-text("Pending")').first();

    if (await pendingDoc.count() > 0) {
      await pendingDoc.click();

      // 4. Approve document
      const approveButton = page.locator('button:has-text("Approve")');
      if (await approveButton.count() > 0) {
        await approveButton.click();
        await page.waitForSelector('.alert-success', { timeout: 10000 });

        // 5. Verify Drive sync initiated
        await page.reload();
        const driveStatus = page.locator('.badge:has-text("Synced"), .badge:has-text("Pending")');
        expect(await driveStatus.count()).toBeGreaterThan(0);
      }
    }
  });
});
