---
name: browser-visual-qa
description: Use when reviewing a rendered Legal Workbench page after frontend changes, verifying responsive layouts or interactions, comparing visual fixes, or deciding whether UI work is ready for release.
---

# Browser Visual QA

## Core contract

Use the real rendered application as the source of truth. Source inspection, typecheck, build success, or a single desktop screenshot cannot establish visual completion.

Use Playwright MCP for browser operation and screenshots. If it is unavailable or the application cannot run, report the verification gap and do not approve the page from source code alone.

Remain an independent reviewer. You may start or access the development server, operate non-destructive controls, inspect console/network evidence, capture screenshots under `artifacts/ui-review/`, and write reports under `docs/ui-review/`. Do not edit application source or mutate production/persistent data.

## Preflight

1. Identify the package manager from repository files.
2. Read `package.json` to select the existing development or preview command.
3. Reuse a healthy running server or start one with the documented command.
4. Record the target URL, route, build/commit context, and expected critical flow.
5. Wait for loading to settle; distinguish product failures from unavailable dependencies.

## Required evidence

Inspect and capture every target route at exactly:

- 1440 × 900;
- 1024 × 768;
- 390 × 844.

Use clear route-and-state names, for example:

- `before-inbox-1440.png`;
- `after-inbox-1024.png`;
- `after-inbox-390.png`.

Do not omit a required viewport because another size looks acceptable. Preserve before/after screenshots when verifying a fix.

## Inspection matrix

Check visual behavior:

- hierarchy, title, primary action, navigation, alignment, spacing, typography, density, surfaces, tables, filters, search, status colors, icons, and responsive collapse;
- loading, empty, failure, permission-denied, disabled, selected, hover, focus, modal, and drawer states;
- clipping, unexpected horizontal or vertical overflow, sticky regions, long text, and obscured controls.

Check interactions:

- primary navigation and main action;
- filters, search, tabs, expandable content, dialogs, and drawers;
- keyboard focus on critical controls;
- browser console errors and failed network requests that affect rendering.

Use safe existing data or reversible UI state. Never approve an interaction that would bypass human review or change persistent business state merely to obtain a screenshot.

## Finding contract

For each finding include:

1. ID;
2. severity: `blocker`, `high`, `medium`, or `low`;
3. viewport and route;
4. affected region;
5. screenshot or observed evidence;
6. observed result;
7. expected result;
8. recommended correction.

Use `blocker` for unusable or major layout failure, `high` for material task/comprehension harm, `medium` for a noticeable defect, and `low` for polish.

## Final verification

After fixes, repeat the same viewports and affected interactions, capture after screenshots, and compare against the original evidence. Confirm every blocker, high, and medium finding as resolved or explicitly unresolved.

End with the release recommendation, required fixes, optional polish, screenshots created, and verification gaps. Do not recommend release or claim visual completion while a required viewport, critical interaction, or material finding remains unverified.
