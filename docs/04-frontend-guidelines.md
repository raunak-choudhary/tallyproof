# 04. Frontend Guidelines

> Design direction is a proposal for MC-01. The frontend-design skill (now installed at user scope) will be used when building UI tasks.

## 1. Design direction

**"Instrument panel for auditors."** Calm, precise, high-contrast data typography; motion only where it explains causality (an event becoming a leaf, a hash rising to a root, a check failing). Avoid generic AI-startup gradients and glassmorphism.

- Verification states are the visual language: **verified** (green), **failed** (red), **unverified / pending** (neutral), **refused** (amber). Always paired with an icon and text, never color alone (accessibility).
- Hashes are rendered in monospace, truncated in the middle (`3f9a…c21e`), full value on focus or hover, copy button.

## 2. Tokens (CSS custom properties, both themes from the first component)

```css
:root {
  --bg: ...; --bg-elevated: ...; --fg: ...; --fg-muted: ...;
  --border: ...; --accent: ...;
  --ok: ...; --fail: ...; --warn: ...; --info: ...;
  --font-sans: ...; --font-mono: ...;
  --radius-sm: 4px; --radius-md: 8px;
  --shadow-1: ...;
  --dur-fast: 120ms; --dur-base: 240ms; --dur-story: 900ms;
  --ease-standard: cubic-bezier(.2,.0,.0,1);
}
[data-theme="dark"] { /* every token redefined */ }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { /* same */ } }
```

Tailwind v4 reads these via `@theme`. No raw hex values in components.

## 3. Typography

One sans for UI, one mono for hashes, amounts, and IDs. Tabular numerals for all money (`font-variant-numeric: tabular-nums`). Amounts right-aligned in tables with currency code.

## 4. Layout and responsiveness

Mobile first. Breakpoints 375, 768, 1280 (shared rule). Proof path visualization collapses to a vertical list on mobile. No horizontal page scroll; wide tables scroll inside their container.

## 5. Motion rules

- Motion (`motion/react`) for component state transitions; GSAP for the landing story timeline only.
- Every animation answers "what caused what". No decorative loops.
- `prefers-reduced-motion`: replace movement with opacity and instant state changes.
- Landing animation must not block interaction; total story under 6 seconds, skippable.

## 6. Accessibility (REQ-UI-06)

- Keyboard: every interactive element reachable, visible focus ring using `--accent`.
- Contrast: WCAG AA minimum for text in both themes, checked in Playwright with axe.
- Live regions announce verification results.

## 7. Code structure

```
frontend/src/
  app/                    routes (App Router)
  features/<feature>/     components, hooks, README.md (REQ-DOC-02)
  lib/verify/             canonical JSON, hashing, Merkle verify, Ed25519 (mirrors core)
  lib/api/                typed client generated from OpenAPI
  lib/replay/             bundle loader
  styles/tokens.css
```

API base URL from `NEXT_PUBLIC_API_URL`, WebSocket from `NEXT_PUBLIC_WS_URL`, mode from `NEXT_PUBLIC_DATA_MODE` (`live` or `replay`). No hardcoded hosts.

## 8. Answer rendering safety

Model output is never rendered as HTML or Markdown. Answers are structured: plain text segments plus typed claim components. This blocks link and image exfiltration (threat model 3.2).
