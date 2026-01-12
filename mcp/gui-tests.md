# Auto-generated GUI intent spec for MCP Playwright

- Generated: (auto)
- Base URL: https://zeda.video
- Routes file: mcp/gui-routes.json

## Scenarios

### Scenario 1: Login screen
- Route: /auth/login
- URL: https://zeda.video/auth/login
- Goal: Load the auth login page, exercise primary controls (inputs, sign-in buttons, forgot password, Google, create account) and wait for UI responses.
- Steps:
  1. Start a fresh browser session (clear cookies/localStorage).
  2. Navigate to the route URL.
  3. Systematically interact with visible inputs using placeholder text.
  4. Click each prominent button/CTA once; after every click, wait ~3s to observe the UI.
  5. If a modal or secondary flow appears, interact once then return to the primary page.
- Failure conditions:
  - UI becomes unresponsive longer than the wait window.
  - Navigation errors (blank pages, 404, crash screens).
  - Required interactive controls are missing or disabled.
  - Obvious error modals or crash overlays.
