# Knowledge and Grounding UI QA — 2026-08-09

## Scope

- Branch: `codex/legal-agent-reliability-knowledge`
- Routes: `/library`, `/reviews`
- Runtime: real Vite/FastAPI against an isolated PostgreSQL integration database
- Viewports: 1440×900, 1024×768, 390×844

## Interactions verified

- Opened a PostgreSQL-backed KnowledgeDocument from the directory.
- Inspected and edited the deterministic authority metadata form; authority role is read-only and derived from type.
- Opened Chunk and retrieval-hit tabs and verified locator, Token and budget audit content.
- Opened a grounded ReviewPackage, inspected fact/risk/strategy/action source refs, and opened the original-source detail modal.
- Confirmed the page and modal do not expose the local absolute source path.

## Finding and resolution

`QA-KNOW-001` — At 390px the initial table kept all desktop columns and clipped the status column. The directory now uses Ant Design responsive columns, retains material/status on mobile, and resets the title cell minimum width. Final measurements: body scroll width 390px, table client/scroll width 308px, no horizontal page overflow. The details drawer is 390px wide and the Review modal is 374px wide.

No blocking, high, or medium visual findings remain in the changed surfaces. The only console error is the repository's existing missing `/favicon.ico` 404 and does not affect the workflow.

## Evidence

- `artifacts/ui-review/after-knowledge-library-1440.png`
- `artifacts/ui-review/after-knowledge-library-1024.png`
- `artifacts/ui-review/after-knowledge-library-390.png`
- `artifacts/ui-review/after-knowledge-drawer-1440.png`
- `artifacts/ui-review/after-knowledge-drawer-390.png`
- `artifacts/ui-review/after-review-grounding-1440.png`
- `artifacts/ui-review/after-review-grounding-390.png`
- `artifacts/ui-review/after-review-grounding-citations-390.png`
