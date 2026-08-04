---
name: legal-workbench-ui
description: Use Figma MCP, Playwright MCP, repository context and human-centered product design principles to audit, redesign, implement and verify the complete Legal Workbench interface. Use for system-wide UI upgrades, page redesigns, workflow improvements, responsive layouts, design-system work, Figma-to-code implementation, accessibility and browser visual QA.
---

# Legal Workbench UI

## 1. Mission

Design and implement a mature enterprise legal operations product.

The interface must feel:

- professional;
- restrained;
- trustworthy;
- calm;
- information-efficient;
- predictable;
- suitable for prolonged daily use;
- designed for legal work rather than technology demonstration.

The product is not a marketing website, AI showcase, generic admin template or decorative dashboard.

The primary user is a corporate legal professional who needs to:

- identify legal work from messages and files;
- triage urgency and risk;
- collect materials;
- assign responsibility;
- review contracts and legal issues;
- manage complaints, disputes and litigation;
- review AI-generated recommendations;
- approve responses;
- follow up deadlines;
- preserve an auditable record.

## 2. Source-of-truth priority

Resolve design decisions in this order:

1. Real legal workflow and user task.
2. Existing business behavior and safety requirements.
3. Approved Figma design and design-system variables.
4. Existing repository components and tokens.
5. Accessibility and responsive requirements.
6. Aesthetic preference.

Never sacrifice workflow clarity or legal safety for decoration.

## 3. Required tools

For substantial UI work, use:

- Figma MCP for design context, frames, components, variables and prototypes;
- Playwright MCP for real browser inspection and functional validation;
- repository inspection for implementation truth;
- existing custom subagents where available.

Do not approve a design based only on source code.

Do not implement a visual redesign before inspecting the rendered product.

## 4. Figma workflow

When Figma write access is available:

1. Open or create one dedicated Figma file.
2. Capture representative current pages from the running application.
3. Create the following Figma pages:

   - `00 Current Audit`
   - `01 Foundations`
   - `02 Components`
   - `03 Desktop Screens`
   - `04 Tablet Screens`
   - `05 Mobile Screens`
   - `06 User Flows`
   - `07 Handoff`

4. Use native Figma frames, components, variants, variables and auto layout.
5. Reuse an existing Figma design system when present.
6. Map Figma components to repository components.
7. Mark final screens ready for development.
8. Record unresolved assumptions in annotations.
9. Preserve before and proposed states for comparison.

When Figma is read-only:

- read design variables and components;
- use existing approved screens as visual authority;
- record proposed design decisions in repository documents;
- do not claim that Figma was modified.

When no Figma file exists:

- capture the current running UI into a new Figma file when supported;
- otherwise create a design specification in the repository and continue with Playwright evidence.

## 5. Product design direction

Use the design direction:

**Quiet legal operations console**

Characteristics:

- actionable work before statistics;
- legal risk and deadline before decorative analytics;
- human review before AI automation;
- transparent data boundaries;
- consistent information architecture;
- low visual noise;
- high scanning efficiency;
- explicit next actions;
- meaningful empty, loading and error states.

AI must appear as an assistant subject to human review, not as the central product identity.

## 6. Aesthetic rules

### Required

- Use a restrained neutral base.
- Use one primary interaction color.
- Use semantic colors only for meaningful states.
- Maintain a clear typography hierarchy.
- Use consistent spacing rhythm.
- Align labels, controls and content precisely.
- Prefer layout and whitespace over excessive borders.
- Use subtle surfaces and shadows.
- Keep information dense enough for professional work.
- Make important actions visible without making every action prominent.
- Use icons only when they improve recognition.
- Preserve clear visual relationships between summary, evidence and action.

### Avoid

Unless already justified by the approved design:

- large gradients;
- glassmorphism;
- neon glow;
- excessive shadows;
- excessive rounded cards;
- nested cards inside cards;
- floating decorative metrics;
- oversized hero sections;
- random illustration;
- decorative charts;
- gratuitous animation;
- emoji as product icons;
- multiple competing accent colors;
- dark AI panels used only to look futuristic;
- simulated online status;
- simulated real-time synchronization;
- meaningless confidence meters;
- fake buttons;
- controls without behavior;
- placeholder content presented as real data.

## 7. Typography

Use a small and deliberate hierarchy.

Recommended starting system:

- page title: 24px, semibold;
- section title: 16px, semibold;
- card or group title: 14px, medium or semibold;
- body: 14px;
- metadata: 12px minimum;
- table content: 13–14px;
- button label: 14px.

Requirements:

- avoid unnecessary font-size variation;
- do not use light font weights for essential information;
- do not use low-contrast gray for important facts;
- support Chinese and English text without layout instability;
- prevent headings from wrapping awkwardly at common widths.

## 8. Color semantics

Default direction:

- primary interaction: existing project blue;
- primary text: dark neutral blue-black;
- secondary text: medium neutral;
- borders: low-contrast cool neutral;
- surfaces: white and lightly tinted neutral;
- red: confirmed severe risk, destructive action or overdue state;
- orange: warning or approaching deadline;
- green: verified success only;
- blue: navigation, selection and informational state;
- muted blue-purple: AI suggestion requiring human review.

Never use green for an unverified connection or synchronization state.

Never imply real-time status without backend evidence.

## 9. Spacing and geometry

Use a consistent spacing scale:

- 4px;
- 8px;
- 12px;
- 16px;
- 24px;
- 32px.

Default radius:

- 6px for normal controls and panels;
- larger radii only when established by the design system.

Requirements:

- controls within one group share alignment;
- related items stay visually close;
- unrelated sections receive clear separation;
- avoid excessive blank space in professional desktop workflows;
- avoid cramped mobile layouts;
- avoid arbitrary one-off spacing values.

## 10. Information hierarchy

Each screen must clearly answer:

1. Where am I?
2. What needs attention?
3. Why does it matter?
4. What is the risk or deadline?
5. Who owns it?
6. What information is missing?
7. What should happen next?
8. What requires human review?
9. What has already happened?
10. How do I return or continue?

A page must not require decorative statistics to explain its purpose.

## 11. Navigation

Navigation must:

- reflect the legal work model;
- use consistent naming;
- show current location;
- preserve browser history;
- avoid dead destinations;
- avoid duplicate routes representing the same concept;
- support deep links;
- work with keyboard navigation;
- remain usable on desktop, tablet and mobile.

Desktop may use a persistent sidebar.

Tablet may use a collapsed navigation rail.

Mobile should use a drawer or equivalent progressive navigation.

Do not compress a desktop sidebar into unreadable mobile content.

## 12. Page and workflow audit

For every existing route inspect:

- page purpose;
- primary user goal;
- navigation entry;
- page title;
- primary action;
- secondary actions;
- search;
- filters;
- sorting;
- tabs;
- tables;
- cards;
- forms;
- drawers;
- dialogs;
- confirmations;
- notifications;
- pagination;
- loading state;
- empty state;
- error state;
- stale-data state;
- permission state;
- mobile behavior;
- keyboard behavior;
- data source;
- API dependency;
- mock/live boundary;
- destructive action safety.

Identify:

- dead controls;
- false filters;
- duplicate actions;
- broken navigation;
- inaccessible actions;
- misleading labels;
- inconsistent state naming;
- actions without feedback;
- pages with no clear next step;
- features that pretend to work;
- business behavior hidden behind visual ambiguity.

## 13. Functional UX rules

### Forms

- Every input has a visible or accessible label.
- Required fields are clear.
- Validation occurs at useful moments.
- Error messages explain how to recover.
- Save, submit and cancel behavior is predictable.
- Unsaved changes receive appropriate protection.
- Destructive actions require intentional confirmation.
- Loading disables duplicate submission.
- Successful actions provide verified feedback.

### Search and filters

- Controls must actually affect the presented data.
- Active filters must be visible.
- Reset behavior must be obvious.
- Empty results must explain why.
- Search must not silently search only an undocumented subset.
- Mobile filters must remain accessible.

### Tables and queues

- Prioritize task identity, risk, deadline, owner and next action.
- Avoid too many columns.
- Keep essential actions reachable at 1024px.
- Use responsive card or list views on mobile when tables become unreadable.
- Preserve sorting and filtering meaning across breakpoints.
- Do not truncate critical legal facts without a reveal mechanism.

### AI content

Clearly distinguish:

- source material;
- extracted fact;
- AI inference;
- AI recommendation;
- human decision;
- confirmed business state.

AI recommendations must show:

- evidence scope;
- uncertainty;
- missing context;
- human-review requirement.

AI must never silently:

- send a message;
- create a binding legal conclusion;
- change a formal task state;
- represent a draft as approved;
- claim that a source was reviewed when it was not.

## 14. Responsive behavior

Validate at least:

- 1440 × 900;
- 1024 × 768;
- 390 × 844.

Also inspect at intermediate widths when layout behavior changes.

### Desktop

- optimize for prolonged professional use;
- preserve high information density;
- keep primary actions reachable;
- use tables where appropriate.

### Tablet

- collapse navigation intentionally;
- reduce secondary metadata;
- avoid clipped actions;
- avoid horizontal page overflow.

### Mobile

- use progressive disclosure;
- use task cards or structured lists instead of unreadable tables;
- preserve risk, deadline, owner and next action;
- use at least 44px touch targets;
- avoid horizontal page overflow;
- avoid relying on hover;
- keep dialogs and drawers within viewport bounds.

## 15. Accessibility

Meet or closely approximate WCAG AA for the modified interface.

Check:

- text contrast;
- interactive-state contrast;
- visible focus;
- keyboard order;
- semantic headings;
- form labels;
- button names;
- link purpose;
- dialog focus trapping;
- status announcements;
- reduced-motion behavior;
- target size;
- color-independent status communication.

Do not use color alone to communicate risk or state.

## 16. Existing-system rule

Before implementation:

1. inspect package.json;
2. identify framework and router;
3. identify styling solution;
4. identify Ant Design version;
5. locate existing theme tokens;
6. locate shared layout components;
7. locate canonical buttons, forms, cards, tables, tags and dialogs;
8. locate state management and API clients;
9. locate existing responsive utilities;
10. locate tests and build commands.

Reuse existing:

- Ant Design components;
- project theme;
- project icons;
- routing;
- state management;
- API patterns;
- common layout;
- status vocabulary.

Do not:

- install another UI framework;
- create a parallel design system;
- replace working business logic for visual convenience;
- rewrite unrelated modules;
- create one-off local components when a shared component should be improved;
- directly paste unreviewed Figma-generated code.

## 17. Figma-to-code rule

Treat Figma as design intent, not infallible generated code.

Before implementation:

- map Figma components to existing repository components;
- map Figma variables to existing tokens;
- identify design/code mismatches;
- preserve business semantics;
- preserve accessibility;
- preserve responsive behavior;
- document necessary deviations.

Implementation order:

1. foundations and theme;
2. application shell;
3. shared components;
4. page templates;
5. page-specific implementation;
6. interaction states;
7. responsive behavior;
8. accessibility;
9. browser verification.

## 18. Playwright baseline

Before modifying a page:

1. start the real application;
2. identify all reachable routes;
3. capture representative before screenshots;
4. exercise the main user path;
5. record console errors;
6. record rendering-related network failures;
7. identify horizontal overflow;
8. identify dead controls;
9. identify broken routes;
10. record existing test results.

Save evidence under:

`artifacts/ui-upgrade/before/`

Do not use destructive production data.

## 19. Playwright final verification

After implementation, repeat the same pages, states and viewports.

Save evidence under:

`artifacts/ui-upgrade/after/`

Verify:

- navigation;
- main actions;
- search;
- filters;
- tabs;
- tables;
- forms;
- dialogs;
- drawers;
- validation;
- loading;
- empty states;
- errors;
- keyboard navigation;
- focus;
- responsive transitions;
- console errors;
- network failures;
- accessibility basics;
- screenshots.

Use stable selectors and role-based locators.

Add or update Playwright tests for critical workflows.

## 20. Visual review rubric

Evaluate each screen from 1 to 5 on:

- hierarchy;
- clarity;
- consistency;
- density;
- alignment;
- typography;
- color discipline;
- action prominence;
- workflow fit;
- responsive quality;
- accessibility;
- professional credibility.

A screen cannot pass solely because it looks attractive.

## 21. Finding severity

- Blocker: prevents completion or causes major layout failure.
- High: materially harms comprehension, safety or task completion.
- Medium: meaningful usability or consistency defect.
- Low: polish improvement without workflow impact.

Every finding must include:

- route;
- viewport;
- affected region;
- evidence;
- expected behavior;
- recommended correction.

## 22. Completion gate

Do not claim completion unless:

- all scoped routes were inventoried;
- Figma design context was used or its unavailability documented;
- the app renders successfully;
- critical user flows work;
- 1440, 1024 and 390 were checked;
- there is no page-level horizontal overflow;
- there are no unresolved blockers;
- there are no unresolved high findings;
- there are no medium findings affecting core workflows;
- browser console contains no serious regression from the work;
- available typecheck, tests and build pass;
- before and after evidence exists;
- mock and live data remain clearly distinguished;
- the final report lists residual limitations honestly.

## 23. Required deliverables

For system-wide work create:

- `docs/ui-upgrade/00-system-inventory.md`
- `docs/ui-upgrade/01-current-state-audit.md`
- `docs/ui-upgrade/02-information-architecture.md`
- `docs/ui-upgrade/03-figma-design-map.md`
- `docs/ui-upgrade/04-design-system.md`
- `docs/ui-upgrade/05-implementation-plan.md`
- `docs/ui-upgrade/06-functional-qa.md`
- `docs/ui-upgrade/07-final-report.md`

Screenshots:

- `artifacts/ui-upgrade/before/`
- `artifacts/ui-upgrade/after/`

Final report must include:

- inspected routes;
- Figma file and relevant frames;
- design decisions;
- changed components;
- changed files;
- functional improvements;
- test results;
- screenshot paths;
- unresolved limitations;
- suggested next iteration.
