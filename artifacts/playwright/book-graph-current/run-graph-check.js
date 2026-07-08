async page => {
  const outDir = 'Q:/Hackathons/QWENHack/artifacts/playwright/book-graph-current';
  const repoUrl = 'https://github.com/Lsdaer-1/Intelligent-Book-Management-System';
  const logPath = 'Q:/Hackathons/QWENHack/tests/fixtures/incident_logs/ibm/book-query-sql-error.log';
  const repoId = `ibm-book-ui-${Date.now()}`;
  const result = {
    repoId,
    repoUrl,
    logPath,
    screenshots: [],
    console: [],
    pageErrors: [],
    failedResponses: [],
    graph: {},
    steps: {},
    buttons: [],
  };
  const shot = async (name) => {
    const path = `${outDir}/${name}.png`;
    await page.screenshot({ path, fullPage: true });
    result.screenshots.push(path);
  };

  page.on('console', msg => {
    if (['error', 'warning'].includes(msg.type())) {
      result.console.push({ type: msg.type(), text: msg.text().slice(0, 500) });
    }
  });
  page.on('pageerror', err => result.pageErrors.push(String(err).slice(0, 800)));
  page.on('response', resp => {
    const status = resp.status();
    const url = resp.url();
    if (status >= 400 && url.includes('127.0.0.1')) {
      result.failedResponses.push({ status, url });
    }
  });

  await page.goto('http://127.0.0.1:8080/', { waitUntil: 'domcontentloaded' });
  await page.getByText('legacy-pilot-interface-contract-middleware').waitFor({ timeout: 30000 });
  result.buttons.push('page loaded + health visible');
  await shot('01-loaded');

  await page.getByRole('button', { name: 'Settings' }).click();
  await page.getByTestId('settings-modal').waitFor({ timeout: 10000 });
  result.buttons.push('Settings opens');
  await page.keyboard.press('Escape').catch(() => {});
  if (await page.getByTestId('settings-modal').isVisible().catch(() => false)) {
    await page.getByTestId('settings-modal').getByRole('button', { name: /^Close$/i }).click().catch(async () => {
      await page.getByRole('button', { name: /^Close$/i }).click();
    });
  }
  result.buttons.push('Settings closes');

  await page.getByRole('button', { name: 'Health' }).click();
  await page.getByText(/passed/).first().waitFor({ timeout: 30000 });
  result.buttons.push('Health button works');

  await page.getByLabel('Repo ID').fill(repoId);
  await page.getByTestId('repo-uri-input').fill(repoUrl);
  await page.getByLabel('Language').fill('java');
  await page.getByLabel('Parser profile').fill('spring-boot');
  await page.getByRole('button', { name: /^Index repo$/i }).click();
  result.buttons.push('Index repo clicked');

  await page.getByTestId('snapshot-summary').getByText(/GraphSnapshot/).waitFor({ timeout: 240000 });
  await page.waitForFunction(() => document.querySelectorAll('.graph-node').length > 0, null, { timeout: 60000 });
  await page.waitForFunction(() => document.querySelectorAll('.graph-edge').length > 0, null, { timeout: 60000 });
  await shot('02-after-index-graph');

  const graphStatsBefore = await page.evaluate(() => {
    const svg = document.querySelector('[data-testid="graph-canvas"]');
    const group = svg?.querySelector('g');
    const firstNode = document.querySelector('.graph-node');
    return {
      nodes: document.querySelectorAll('.graph-node').length,
      edges: document.querySelectorAll('.graph-edge').length,
      transform: group?.getAttribute('transform') || null,
      firstNodeTransform: firstNode?.getAttribute('transform') || null,
      statsText: document.querySelector('.graph-stats')?.textContent || '',
    };
  });
  result.graph.before = graphStatsBefore;

  for (const testId of ['graph-layer-raw', 'graph-layer-evidence', 'graph-layer-paths', 'graph-layer-overview']) {
    await page.getByTestId(testId).click();
    await page.waitForTimeout(250);
    const pressed = await page.getByTestId(testId).getAttribute('aria-pressed');
    result.buttons.push(`${testId} pressed=${pressed}`);
  }

  const canvas = page.getByTestId('graph-canvas');
  const box = await canvas.boundingBox();
  if (!box) throw new Error('graph canvas missing bounding box');
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.55);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.55 + 90, box.y + box.height * 0.55 + 55, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  result.graph.panTransform = await page.evaluate(() => document.querySelector('[data-testid="graph-canvas"] g')?.getAttribute('transform') || null);

  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.wheel(0, -650);
  await page.waitForTimeout(300);
  result.graph.zoomTransform = await page.evaluate(() => document.querySelector('[data-testid="graph-canvas"] g')?.getAttribute('transform') || null);

  const nodeBox = await page.locator('.graph-node').first().boundingBox();
  if (!nodeBox) throw new Error('first graph node missing bounding box');
  const nodeBefore = await page.locator('.graph-node').first().evaluate(el => el.getAttribute('transform'));
  await page.mouse.move(nodeBox.x + nodeBox.width / 2, nodeBox.y + nodeBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(nodeBox.x + nodeBox.width / 2 + 70, nodeBox.y + nodeBox.height / 2 + 35, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  const nodeAfter = await page.locator('.graph-node').first().evaluate(el => el.getAttribute('transform'));
  result.graph.nodeDrag = { before: nodeBefore, after: nodeAfter };

  await page.getByRole('button', { name: 'Fit' }).click();
  await page.waitForTimeout(300);
  result.buttons.push('Fit clicked');
  await shot('03-after-graph-interactions');

  await page.getByRole('button', { name: 'Import local log' }).click();
  await page.setInputFiles('[data-testid="local-log-file-input"]', logPath);
  await page.waitForFunction(() => document.querySelector('[data-testid="raw-log-input"]')?.value?.includes('BookMapper.selectAvailableBooks'), null, { timeout: 10000 });
  result.buttons.push('Import local log works');
  result.importedAlertId = await page.getByLabel('Alert ID').inputValue();
  result.importedSource = await page.getByLabel('Source').inputValue();
  await shot('04-after-import-log');

  await page.getByRole('button', { name: /^Run full pipeline$/i }).click();
  result.buttons.push('Run full pipeline clicked');
  await page.getByTestId('incident-query-summary').getByText(/IncidentQuery/).waitFor({ timeout: 90000 });
  result.steps.submit = 'passed';
  await page.getByTestId('evidence-bundle').getByText(/EvidenceBundle/).waitFor({ timeout: 180000 });
  result.steps.evidence = 'passed';
  await shot('05-after-evidence');

  await page.getByTestId('graph-layer-evidence').click();
  await page.waitForTimeout(500);
  result.graph.evidence = await page.evaluate(() => ({
    nodes: document.querySelectorAll('.graph-node').length,
    edges: document.querySelectorAll('.graph-edge').length,
    focusNodes: document.querySelectorAll('.graph-node.focus').length,
    focusEdges: document.querySelectorAll('.graph-edge.focus').length,
    statsText: document.querySelector('.graph-stats')?.textContent || '',
  }));
  await shot('06-evidence-focus-graph');

  await page.getByTestId('rca-report').getByText(/Selected root cause|RCAReport/).waitFor({ timeout: 240000 });
  result.steps.generate = 'passed';
  await page.getByTestId('reviewed-report').getByText(/ReviewedRCAReport/).waitFor({ timeout: 90000 });
  result.steps.review = 'passed';
  await shot('07-after-rca-review');

  await page.getByTestId('user-confirmation-checkbox').check();
  await page.getByLabel('Fix outcome').fill('playwright verified graph and imported IBM incident log');
  await page.getByLabel('Retention policy').fill('ui-graph-e2e');
  await page.getByTestId('save-incident-button').click();
  await page.getByTestId('incident-record').getByText(/INC-/).waitFor({ timeout: 90000 });
  result.steps.save = 'passed';
  await page.getByTestId('incident-readback').getByText(/INC-/).waitFor({ timeout: 90000 });
  result.steps.readback = 'passed';
  result.buttons.push('Save incident works');
  await shot('08-after-save-readback');

  await page.getByRole('button', { name: 'Contract debug' }).click();
  await page.getByText('Request/Response Debug').waitFor({ timeout: 10000 });
  result.buttons.push('Contract debug opens');
  await shot('09-contract-debug');
  await page.getByRole('button', { name: /^Close$/ }).click();
  result.buttons.push('Contract debug closes');

  result.final = await page.evaluate(() => ({
    url: location.href,
    pipelineText: Array.from(document.querySelectorAll('[aria-label="Pipeline status"] *')).map(el => el.textContent).join(' ').slice(0, 1000),
    graphStats: document.querySelector('.graph-stats')?.textContent || '',
  }));
  return result;
}
