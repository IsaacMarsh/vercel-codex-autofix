# MCP Playwright assets

This folder is the **template** copied into each target repo under `<repo>/vercel_codex_autofix/mcp` the first time the loop runs. Inside the runtime copy you’ll find:

- `playwright.config.json` – headless Chromium config shared by every run (CI-friendly viewport/timeouts).
- `gui-routes.json` – the only file you edit manually. List each route (and optional name/description) you want the MCP agent to explore.
- `gui-tests.md` – auto-generated intent spec derived from `gui-routes.json`. The loop rewrites it before every MCP run, so do not edit manually.
- `gui-plan.generated.json` – machine-readable summary of the scenarios, also regenerated automatically for other tooling.
- `run-gui-check.sh` – a thin wrapper around `npx @playwright/mcp@latest` that executes the spec above, saves traces/videos to `logs/gui/`, and prints a concise PASS/FAIL summary.

## How it works

1. In your target repo, edit `vercel_codex_autofix/mcp/gui-routes.json` to list the routes you want to probe (just one line per route if you like).
2. The autofix loop regenerates `gui-tests.md` and `gui-plan.generated.json` automatically before launching each MCP run.
3. `bash vercel_codex_autofix/mcp/run-gui-check.sh <deployment-url>` starts the Playwright MCP tool, which reads the freshly-generated intent spec and drives the browser locally.
4. Playwright MCP emits text output, plus trace/video artifacts whenever it discovers a problem; the loop copies the textual report into `vercel_codex_autofix/.autofix/gui_report.md` so Codex can fix the issue.

> **Which LLM does this use?**  
> Whatever LLM your MCP environment is configured for. The script itself doesn’t hardcode a model; it simply shells out to `@playwright/mcp`, which negotiates with your configured MCP/LLM stack.

Customize `gui-tests.md` as your product evolves—no code changes required. If you need to skip GUI checks entirely (e.g., while stabilizing flows), export `RUN_MCP_GUI=0` before launching the loop.
