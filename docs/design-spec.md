# Tailmate Organic Frontend Design Specification

Version: `draft`
Status: Versioned design-language reference for future Tailmate web surfaces

This document translates the completed `sample-demo-ui3` visual analysis into an implementation-ready frontend design specification.
It defines the canonical "Soft Organic" language for future Tailmate product, marketing, and admin-facing web surfaces that intentionally adopt this visual direction.

## 1. Design Intent

Tailmate Organic is built around a soft, grounded, and natural visual language.
It should feel calm, human, and tactile instead of glossy, synthetic, or aggressively technical.

Core attributes:

- soft
- organic
- trustworthy
- handcrafted
- breathable
- warm

Visual cues should reference soil, parchment, leaves, stone, and hand-shaped objects.
Layouts must preserve generous whitespace and avoid rigid or mechanical geometry.

## 2. Visual Principles

All implementations that adopt this design language must follow these rules:

- prefer warm neutrals over pure white or high-contrast grayscale
- use irregular curves and asymmetric radii instead of relying on a single rounded preset
- keep elevation soft, diffused, and low-contrast
- allow decorative atmospheric layers such as blobs, grain, and light glass surfaces without overwhelming content
- create rhythm through whitespace, typography contrast, and staggered motion rather than dense UI chrome
- keep interfaces expressive but still usable on mobile and desktop

Designers and engineers should reject surfaces that feel too corporate, sharp, flat, or grid-rigid.

## 3. Color System

### 3.1 Core Palette

| Role | Hex | HSL | Primary use |
| --- | --- | --- | --- |
| Organic Primary | `#5D7052` | `98 16% 38%` | Brand color, primary CTA, active navigation, icons |
| Organic Primary Hover | `#4A5A41` | N/A | Primary hover and pressed states |
| Organic Secondary | `#C18C5D` | `28 43% 56%` | Emphasis, reward, ranking, progress accents |
| Organic Foreground | `#2C2C24` | `60 10% 16%` | Headlines and primary body text |
| Organic Muted Text | `#78786C` | `60 5% 45%` | Secondary copy and inactive navigation |
| Organic Background | `#FDFCFB` | `50 44% 98%` | Page background |
| Organic Card | `#FEFEFA` | N/A | Cards and panels |
| Organic Muted | `#F0EBE5` | `33 30% 92%` | Tags, chips, soft fills |
| Organic Accent | `#E6DCCD` | `36 40% 85%` | Decorative soft background blocks and blobs |
| Organic Border | `#DED8CF` | `36 20% 84%` | Borders and dividers |
| Organic Destructive | `#A85448` | `7 40% 47%` | Dangerous or exit actions |
| Organic Login Green | `#829563` | N/A | Login-specific CTA variant |
| Organic Deep Login Green | `#5C6B45` | N/A | Login-state depth or badge support |
| Organic Step Green | `#768960` | N/A | Step markers and numbered status elements |

### 3.2 Semantic Usage

| Semantic meaning | Recommended color |
| --- | --- |
| Positive, healthy, stable | `#5D7052` |
| Reward, emphasis, progress | `#C18C5D` |
| Neutral support text | `#78786C` |
| Destructive or high-risk action | `#A85448` |
| Success state outside the core palette | `emerald-600` |

### 3.3 Color Rules

- primary actions should use forest green before introducing alternative accent fills
- terracotta should be used as a highlight, not as the dominant base color of the page
- muted parchment and sand tones should do most of the layout work
- avoid pure black text and cold blue-gray neutrals unless the product surface has an explicit exception

## 4. Typography System

### 4.1 Font Families

| Role | Primary family | Fallbacks | Usage |
| --- | --- | --- | --- |
| Heading | `Fraunces` | `Playfair Display`, `serif` | All headings and large data numerals |
| Body | `Nunito` | `Quicksand`, `sans-serif` | Body copy, buttons, labels, navigation |

### 4.2 Type Scale

| Element | Typical size | Weight | Family |
| --- | --- | --- | --- |
| Hero headline | `text-6xl` to `text-[5.5rem]` | `font-bold` | Heading |
| Page headline | `text-5xl` to `text-7xl` | `font-bold` | Heading |
| Section headline | `text-4xl` to `text-5xl` | `font-bold` | Heading |
| Card headline | `text-2xl` to `text-3xl` | `font-bold` | Heading |
| Large body | `text-xl` to `text-2xl` | `font-medium` | Body |
| Standard body | `text-lg` | `font-medium` | Body |
| Small label | `text-sm` | `font-semibold tracking-wide` | Body |
| Micro label | `text-xs` or `text-[9px]` | `font-bold` | Body |

### 4.3 Typography Rules

- headings should use `tracking-tight`
- serif headings should carry most of the visual identity
- body text should remain rounded and approachable instead of condensed or sterile
- selective use of `italic font-light` inside hero headlines is encouraged to create a breathing rhythm

Example:

```tsx
Understand <span className="italic font-light text-[#C18C5D]">every</span> step.
```

## 5. Shape Language

Irregular radii are the most important visual signature of this system.
Do not reduce this language to generic `rounded-xl` usage.

### 5.1 Radius Tokens

| Token | Border radius | Usage |
| --- | --- | --- |
| Pebble | `3rem 2rem 4rem 2rem` | Main cards and large panels |
| Leaf | `40% 60% 70% 30% / 40% 50% 60% 50%` | Logo containers and decorative avatars |
| Drop A | `30% 70% 70% 30% / 30% 30% 70% 70%` | Secondary CTA and card variations |
| Drop B | `70% 30% 30% 70% / 70% 70% 30% 30%` | Alternating card variations |
| Soft | `2rem` | Standard card default |
| Large Soft | `2.5rem` to `3rem` | Device mockups and large framed surfaces |
| Pill | `9999px` | Buttons, chips, pills, nav items |

### 5.2 Shape Rules

- alternate irregular shapes across repeated cards to prevent a templated grid look
- use the pebble radius for high-importance surfaces
- keep circular or pill shapes for controls, not for every container
- nested panel systems may use a larger irregular outer shell and a slightly tighter inner shell

Example step-card rotation:

```tsx
const radiusClassByIndex = [
  "rounded-[2rem]",
  "rounded-[30%_70%_70%_30%_/_30%_30%_70%_70%]",
  "rounded-[70%_30%_30%_70%_/_70%_70%_30%_30%]",
];
```

## 6. Elevation And Surfaces

### 6.1 Shadow System

| Token | Typical value | Usage |
| --- | --- | --- |
| `shadow-soft` | `0 4px 10px rgba(93, 112, 82, 0.15)` | Buttons, pills, small controls |
| `shadow-float` | `0 10px 40px -10px rgba(93, 112, 82, 0.18)` | Highlight panels and floating surfaces |
| Organic card shadow | `0 4px 20px -2px rgba(93, 112, 82, 0.08)` | Standard content cards |
| Organic nav shadow | `0 4px 20px -2px rgba(93, 112, 82, 0.15)` | Floating navigation |

### 6.2 Surface Rules

- shadows must be soft, wide, and slightly green-tinted rather than dark gray
- borders should remain subtle and warm
- cards should usually sit on off-white or parchment backgrounds, not stark white voids

Recommended base card pattern:

```html
class="bg-[#FEFEFA] rounded-[3rem_2rem_4rem_2rem] border border-[#DED8CF]/50 p-10 md:p-14 shadow-[0_4px_20px_-2px_rgba(93,112,82,0.08)] transition-transform duration-500 hover:-translate-y-2"
```

## 7. Glass And Texture

### 7.1 Glass Usage

Use glass surfaces sparingly for floating navigation, dropdowns, and auxiliary controls.

Recommended recipes:

- `bg-white/40 backdrop-blur-md`
- `bg-white/70 backdrop-blur-md`
- `bg-white/95 backdrop-blur-xl`
- `bg-white/60 backdrop-blur-sm`

### 7.2 Grain Texture

The design language includes an ultra-light grain overlay across the whole page.
It should be fixed, non-interactive, and subtle enough to be felt more than noticed.

```css
#grain-texture {
  position: fixed;
  inset: 0;
  z-index: 9999;
  pointer-events: none;
  background-image: url("data:image/svg+xml,...feTurbulence fractalNoise...");
  opacity: 0.04;
  mix-blend-mode: multiply;
}
```

Texture rules:

- opacity should remain around `0.04`
- do not animate the grain
- keep it above the page visually but below interaction by disabling pointer events

## 8. Atmospheric Background Blobs

Soft organic blobs are required for depth and mood in hero and feature sections.
They should sit behind content and extend beyond the viewport edges.

Recommended palette:

- warm sand blob: `bg-[#E6DCCD]/30` to `bg-[#E6DCCD]/40`
- green blob: `bg-[#5D7052]/10`
- terracotta blob: `bg-[#C18C5D]/10`

Recommended treatment:

- irregular radii
- `blur-3xl` or approximately `blur-[90px]`
- negative offsets
- optional scroll-based parallax

Example:

```tsx
<motion.div
  style={{ y: y1 }}
  className="absolute -top-20 -right-20 h-[600px] w-[600px] rounded-[60%_40%_30%_70%_/_60%_30%_70%_40%] bg-[#E6DCCD]/40 blur-3xl -z-10"
/>
```

## 9. Motion System

### 9.1 Standard Easing

```ts
const organicEase = [0.22, 1, 0.36, 1];
```

### 9.2 Motion Patterns

| Pattern | Recommended behavior | Usage |
| --- | --- | --- |
| Fade in up | `opacity: 0 -> 1`, `y: 40 -> 0`, `duration: 0.8` | Hero copy, section headings |
| Stagger | `staggerChildren: 0.2` | Multi-element hero or card groups |
| Slide in | `opacity: 0 -> 1`, `x: +/-30 -> 0`, `duration: 0.6` | Side-entry cards |
| Scale in | `opacity: 0 -> 1`, `scale: 0.9 -> 1`, `delay: 0.2` | Device or hero mockups |
| Parallax | `useTransform(scrollYProgress, [0, 1], [40, -40])` | Feature mockups |
| Blob drift | `useTransform(scrollY, [0, 500], [0, +/-150])` | Hero atmospheric layers |

### 9.3 Hover Language

Common interaction patterns:

- `hover:-translate-y-1`
- `hover:-translate-y-2`
- `hover:scale-105`
- `hover:rotate-0`
- `group-hover:-rotate-6 group-hover:scale-105`
- `transition-all duration-300` to `duration-500`

Motion rules:

- interactions should feel floaty, not snappy
- do not stack too many simultaneous hover effects on a single element
- prefer one meaningful transform over multiple competing transforms

### 9.4 Keyframes

```css
@keyframes water-spin {
  0% {
    rotate: 0deg;
  }

  100% {
    rotate: 360deg;
  }
}
```

Use only when the composition benefits from a slow ambient motion loop.

## 10. Layout System

### 10.1 Width Constraints

| Container | Typical width |
| --- | --- |
| Global content | `max-w-7xl` |
| Mid-size sections | `max-w-6xl` |
| Hero text | `max-w-4xl` |
| Compact CTA text | `max-w-2xl` |

### 10.2 Spacing Rhythm

| Token pattern | Usage |
| --- | --- |
| `px-6` | Global horizontal page padding |
| `py-32` | Large section spacing |
| `gap-10` to `gap-14` | Grid spacing |
| `mb-8` to `mb-16` | Heading to content spacing |
| `p-10 md:p-14` | Large card padding |

### 10.3 Navigation Pattern

Public-facing surfaces should prefer an embedded or floating pill-based top navigation rather than a conventional hard-edged bar.

Recommended characteristics:

- `sticky top-4`
- `rounded-full`
- `bg-white/70 backdrop-blur-md`
- horizontally arranged navigation items
- active state with `bg-[#5D7052] text-[#F3F4F1] rounded-full`
- mobile collapse into a soft panel around `rounded-[2rem]`

### 10.4 Dashboard Composition

For dashboard-style pages, the system supports an asymmetric 12-column split:

- left `7` columns for hero CTA and timeline content
- right `5` columns for rankings, highlights, or summary widgets

## 11. Component Recipes

### 11.1 Buttons

| Component | Recommended pattern |
| --- | --- |
| Primary CTA | `bg-[#5D7052] text-[#F3F4F1] rounded-[60px] h-16 px-10 font-bold shadow-soft hover:scale-105` |
| Secondary CTA | `bg-[#C18C5D] text-white rounded-[30%_70%_70%_30%_/_30%_30%_70%_70%] px-8 py-6 font-bold` |
| Dark CTA | `bg-[#2C2C24] text-white rounded-full h-16 px-12 font-bold shadow-float` |
| Ghost button | `border border-[#DED8CF]/60 bg-[#FEFEFA] rounded-full px-8 text-sm font-bold` |
| Login button | `bg-[#829563] text-white rounded-xl w-full py-3.5 font-bold shadow-md` |

### 11.2 Tags And Badges

```html
class="rounded-full border border-[#DED8CF]/50 bg-[#F0EBE5] px-5 py-2.5 text-sm font-bold text-[#5D7052] shadow-sm transition-transform hover:-translate-y-1"
```

### 11.3 Step Markers

Large marker:

```html
class="h-16 w-16 rounded-[40%_60%_50%_40%] bg-[#F0EBE5] text-[#5D7052]"
```

Compact marker:

```html
class="h-12 w-12 rounded-2xl bg-[#768960] text-white rotate-3 transition-transform hover:rotate-0"
```

### 11.4 Text Selection

Recommended selection colors:

```css
selection:bg-[#5D7052]/20 selection:text-[#2C2C24];
selection:bg-[#C18C5D]/30 selection:text-[#2C2C24];
```

## 12. Implementation Tokens

The following token block can be used as a starting point for CSS variable definition.

```css
:root {
  --organic-primary: #5d7052;
  --organic-primary-hover: #4a5a41;
  --organic-secondary: #c18c5d;
  --organic-secondary-hover: #a6774f;
  --organic-foreground: #2c2c24;
  --organic-muted-text: #78786c;
  --organic-background: #fdfcfb;
  --organic-card: #fefefa;
  --organic-muted: #f0ebe5;
  --organic-accent: #e6dccd;
  --organic-border: #ded8cf;
  --organic-destructive: #a85448;
  --organic-login-green: #829563;
  --organic-step-green: #768960;

  --font-heading: "Fraunces", "Playfair Display", serif;
  --font-body: "Nunito", "Quicksand", sans-serif;

  --radius-pebble: 3rem 2rem 4rem 2rem;
  --radius-leaf: 40% 60% 70% 30% / 40% 50% 60% 50%;
  --radius-drop-a: 30% 70% 70% 30% / 30% 30% 70% 70%;
  --radius-drop-b: 70% 30% 30% 70% / 70% 70% 30% 30%;
  --radius-soft: 2rem;
  --radius-pill: 9999px;

  --ease-organic: cubic-bezier(0.22, 1, 0.36, 1);
  --grain-opacity: 0.04;
}
```

## 13. Guardrails

When applying this design language, avoid the following:

- cold monochrome palettes
- generic app-shell sidebars unless the product flow requires one
- uniform card radii across every surface
- harsh gray drop shadows
- overuse of glass effects
- purple-accented defaults
- motion that is too fast, too bouncy, or too dense

This system should feel natural and composed.
If a screen starts to look like a standard SaaS dashboard with swapped colors, the implementation has drifted away from the intended language.
