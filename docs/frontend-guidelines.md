# Frontend guidelines

## Design direction

The interface should feel like an instrument panel for an auditor: calm, precise, and easy to scan, with strong contrast for data. Motion appears only where it explains cause and effect, like a record turning into a leaf, a hash climbing to the root, or a check failing. No gradient-heavy startup styling and no glass effects.

Verification state is the core visual language. Verified is green, failed is red, pending or unverified is neutral, and refused is amber. Each state always pairs color with an icon and a word, so nothing depends on color alone.

Hashes appear in a monospace font, shortened in the middle (`3f9a…c21e`), with the full value on hover or focus and a copy button.

## Design tokens

Every color, shadow, radius, and duration is a CSS custom property, and both themes are defined from the first component:

```css
:root {
  --bg: ...; --bg-elevated: ...; --fg: ...; --fg-muted: ...;
  --border: ...; --accent: ...;
  --ok: ...; --fail: ...; --warn: ...; --info: ...;
  --font-sans: ...; --font-mono: ...;
  --radius-sm: 4px; --radius-md: 8px;
  --shadow-1: ...;
  --dur-fast: 120ms; --dur-base: 240ms; --dur-story: 900ms;
  --ease-standard: cubic-bezier(.2, 0, 0, 1);
}
[data-theme="dark"] { /* every token redefined */ }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { /* the same */ } }
```

Tailwind reads these through `@theme`. Components never use raw color values.

## Typography

One sans-serif face for the interface and one monospace face for hashes, amounts, and IDs. Money always uses tabular numerals, sits right-aligned in tables, and shows its currency.

## Layout

Layouts are built mobile first, with breakpoints at 375, 768, and 1280 pixels. The proof-path visualization becomes a vertical list on small screens. The page never scrolls sideways; a wide table scrolls inside its own container.

## Motion

- Motion handles component state changes. GSAP is used only for the landing page story.
- Every animation shows what caused what. Nothing loops for decoration.
- With reduced motion enabled, movement becomes a fade or an instant change.
- The landing story never blocks interaction, runs under six seconds, and can be skipped.

## Accessibility

- Every interactive element can be reached by keyboard and shows a visible focus ring.
- Text meets WCAG AA contrast in both themes, checked automatically in browser tests with axe.
- Verification results are announced through a live region.

## Code structure

```
frontend/src/
  app/                 routes (App Router)
  features/<feature>/  components, hooks, and a README per feature
  lib/verify/          canonical JSON, hashing, Merkle verification, Ed25519
  lib/api/             typed client generated from the OpenAPI schema
  lib/replay/          loader for the public demo bundle
  styles/tokens.css
```

The API URL, WebSocket URL, and mode (`live` or `replay`) come from environment variables. No hostnames are hardcoded.

## Rendering answers safely

Model output is never rendered as HTML or Markdown. An answer arrives as plain text segments plus typed claim components, which closes off links and images as a way to leak data ([threat-model.md](threat-model.md)).
