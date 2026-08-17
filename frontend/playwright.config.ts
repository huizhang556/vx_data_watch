import { defineConfig, devices } from '@playwright/test'

const runId = `${Date.now()}`

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{
    name: 'chrome',
    use: {
      ...devices['Desktop Chrome'],
      launchOptions: { executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' },
    },
  }],
  webServer: {
    command: '..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir ..\\backend --host 127.0.0.1 --port 8765',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      VX_DATA_DIR: `../data/e2e-${runId}`,
      VX_DATABASE_URL: `sqlite:///../data/e2e-${runId}/test.db`,
      VX_COOKIE_SECURE: 'false',
    },
  },
})
