# Nablix Content Authoring Portal — Frontend Design

Internal tool for curriculum authors. Frontend only — the backend authoring API
(`/authoring/*`, spec §16) is a separate team's work. This app talks to those
APIs and never writes to the database directly.

Source spec: `Nablix_Content_Authoring_Portal_Frontend_Specification_Final.docx`
(18 sections). Reference mock supplied by the founder = the Topic Workspace screen.

## Decisions

- **Separate app**, `Demo-1/nablix-authoring-ui`, sibling to `Numera-ui` and
  `nablix-backend`. Distinct from the learner-facing tutor (`Numera-ui`).
- **Stack** mirrors canonical `Numera-ui`: Next.js 15 App Router, React 19,
  TypeScript, Tailwind v3, Radix primitives, lucide icons.
- **Branding**: Numera brand tokens + the **liquid-glass** system ported from
  `Numera-ui/app/globals.css` (`.lg-glass`, `.lg-glass-dark`, `.lg-ambient`,
  `.lg-field`, brand `.btn-*`). Navy ambient backdrop; light glass work surfaces.
  CSS-only animation (the embedded browser pane suppresses `requestAnimationFrame`).
- **Data layer**: typed adapter behind `lib/api/`. `mockAdapter` (fixtures: Topic
  T02 from the spec) is the default so the portal runs standalone; `httpAdapter`
  hits the real backend when `NEXT_PUBLIC_API_MODE=http`. No rewrite when the
  backend ships — only an env flip.

## Information architecture

```
/                          Dashboard (§4)
/topics/[id]               Topic Workspace shell (§5): tree · editor · validation
  ├─ details               Topic Details (§6.1)         [built]
  ├─ scope-source          Scope & Source (§6.2–6.3)    [Increment 2]
  ├─ micro-skills          Micro-skills (§7)            [Increment 2]
  ├─ orientation           Orientation (§8)             [Increment 3]
  ├─ worked-examples       Worked Examples (§9)         [Increment 3]
  ├─ questions             Question Builder (§10)       [Increment 4]
  ├─ misconceptions        Errors & Misconceptions (§11)[Increment 5]
  ├─ hints-cues            Hints & Visual Cues (§12)     [Increment 5]
  ├─ scaffolds             Scaffolds & Parallel Ex (§13) [Increment 6]
  ├─ coverage              Coverage & Validation (§14)  [built]
  └─ publish               Preview & Publish (§15)      [Increment 8]
```

## Build sequence (spec §18)

1. **Foundation** *(this increment)* — scaffold, design system, AppShell, tree,
   mock API, Dashboard + Topic Workspace shell + Topic Details + Coverage grid.
2. Scope/Source + Micro-skills
3. Orientation + Worked Examples
4. Question Builder wizard (centerpiece)
5. Errors / Misconceptions / Hints / Visual Cues
6. Scaffolds / Parallel Examples
7. Coverage click-to-create
8. Preview / Review / Publish

## Run

```
npm --prefix Demo-1/nablix-authoring-ui run dev   # http://localhost:4123
```
