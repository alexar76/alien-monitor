# SYMMARTYS local monitor rename validation

Recorded for the user-authorized local rename on 2026-10-28. No deployment or publication was performed.

The monitor projects the current product name onto known provider labels and descriptions, including a remote provider still returning its former name. It preserves observed node IDs, operational URLs, metrics, signed nested objects and historical events. Navigation accepts both names and focuses the actual observed node. Same-named providers outside this ecosystem are left unchanged. The registry keeps an explicitly visible local service known without inventing a published repository.

## Backend

Working directory: `/Users/alex/Desktop/ai_tests/aicompany/aicom`.
Interpreter: `.venv/bin/python`, Python 3.12.13. No additional environment settings; tests use fixtures and temporary state.

```bash
.venv/bin/python -m pytest alien-monitor/tests/test_symmartys_display.py alien-monitor/tests/test_ecosystem_registry.py alien-monitor/tests/test_live_graph_answers.py alien-monitor/tests/test_ai_nav_actions.py alien-monitor/tests/test_ai_knows_every_component.py -q
```

Result after the central knowledge sync: **112 passed in 0.56 s**. This includes the central-to-container mirror drift assertions.

## Frontend

Working directory: `/Users/alex/Desktop/ai_tests/aicompany/aicom/alien-monitor/frontend`.
Runtime: Node v22.22.1, npm 10.9.4; installed dependencies used without installation or updates.

```bash
npm test -- src/__tests__/productDisplay.test.tsx src/__tests__/ecoGraphSanitize.test.ts
npm run build
```

Results: **18 passed** in two files; TypeScript and Vite production build succeeded. The display test renders the actual node detail component with the current name from a legacy remote identity. The build regenerated `alien-monitor/frontend/dist/`; its existing warning about chunks larger than 500 kB remains.

The display projection is applied to normal state, lazy neighborhood nodes, and the windowed map. It changes human labels, not wire identity or signed evidence.

Current legacy-name references in monitor implementation are intentional compatibility mappings and regression fixtures. Current knowledge, architecture, whitepapers and glossary use SYMMARTYS. Dated evidence and previously observed or signed data were not rewritten.
