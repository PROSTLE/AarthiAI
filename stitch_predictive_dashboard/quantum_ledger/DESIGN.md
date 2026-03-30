# Design System Specification: High-Tech Trading & Prediction

## 1. Overview & Creative North Star: "The Kinetic Observatory"
This design system is built to move beyond the static, "dashboard-in-a-box" aesthetic. Our Creative North Star is **The Kinetic Observatory**. In a high-stakes trading environment, the UI should not just display data; it should feel like a high-precision optical instrument—a lens that clarifies chaos.

We break the "standard" template by utilizing **intentional asymmetry** and **tonal depth**. Rather than rigid, boxed grids, we use a sophisticated layering of dark surfaces to create a sense of infinite spatial depth. The interface feels fast because it is "light" in construction—using blurs and gradients rather than heavy borders—and reliable because of its unwavering commitment to typographic clarity.

## 2. Colors & Surface Logic
The palette is rooted in deep obsidian tones to reduce eye strain, punctuated by high-frequency accents that signify movement and urgency.

### Surface Hierarchy & Nesting (The No-Line Rule)
To achieve a premium feel, **1px solid borders for sectioning are strictly prohibited.** We define boundaries through background color shifts.
*   **The Ground:** Use `surface` (#111318) for the main application background.
*   **The Stage:** Use `surface_container_low` (#1a1c20) for secondary sidebars or navigation zones.
*   **The Focus:** Use `surface_container_highest` (#333539) for active trading modules or primary data cards.
*   **Nesting:** A `surface_container_high` card sitting on a `surface_container` background creates a natural, soft lift that feels integrated, not "pasted on."

### The Glass & Gradient Rule
*   **Glassmorphism:** For floating modals, tooltips, or predictive overlays, use `surface_variant` (#333539) at 60% opacity with a `20px` backdrop-blur. This allows the "glow" of market trends to bleed through, maintaining context.
*   **Signature Textures:** Main Action Buttons and Hero Trends should use a subtle linear gradient (Top-Left to Bottom-Right) transitioning from `primary` (#a8e8ff) to `primary_container` (#00d4ff). This adds a "lithium-ion" energy to the UI.

### Key Tokens
*   **Primary (Data/Identity):** `primary` (#a8e8ff) — Electric Blue.
*   **Secondary (Growth):** `secondary` (#40e56c) — Emerald Green.
*   **Tertiary (Loss/Alert):** `on_tertiary_container` (#a30026) — Ruby Red.

## 3. Typography: Editorial Precision
The typography system balances the technicality of data with the authority of an editorial journal.

*   **Display & Headlines:** We use **Space Grotesk**. Its geometric quirks lend a "high-tech" laboratory feel. Use `display-lg` for portfolio totals and `headline-md` for market sectors.
*   **Body & Labels:** We use **Inter**. It is the workhorse of this system. Its high x-height ensures that dense tick data remains legible at `body-sm` (0.75rem).
*   **Data Densities:** Use `label-md` for metadata (timestamps, volume) to maintain a clear hierarchy between the "Story" (Headlines) and the "Evidence" (Labels).

## 4. Elevation & Depth
In this design system, elevation is a product of light and tone, not physical shadows.

*   **Tonal Layering:** Depth is achieved by "stacking" the surface-container tiers. For instance, an order-entry panel should be `surface_container_lowest` to feel recessed into the dashboard, while a real-time alert should be `surface_bright` to feel projected toward the user.
*   **Ambient Shadows:** If a "floating" effect is required (e.g., a context menu), use a shadow with a `40px` blur and `6%` opacity, using the `on_surface` color as the shadow tint. This mimics natural light reflecting off a dark surface.
*   **Ghost Borders:** If accessibility requirements demand a stroke, use the `outline_variant` token at **15% opacity**. This provides a "suggestion" of a boundary without breaking the seamless flow.

## 5. Components

### Buttons & Interaction
*   **Primary Action:** Gradient fill (`primary` to `primary_container`) with `on_primary` text. `0.25rem` (DEFAULT) roundedness for a sharp, precision-cut look.
*   **Secondary Action:** `outline` token at 20% opacity. No fill. On hover, transition to `surface_container_highest`.
*   **The "Trade" Button:** Use `secondary_container` for "Buy" and `tertiary_container` for "Sell". These must be high-contrast and utilize the `xl` (0.75rem) roundedness to stand out from the rigid data grid.

### Data Chips
*   Used for stock symbols and status indicators.
*   **Rule:** Forbid background fills for neutral chips. Use the `outline` token at 10% opacity with `on_surface_variant` text. Only use color fills (`secondary` or `tertiary`) when indicating a delta (price change).

### Input Fields
*   **State:** Background should be `surface_container_lowest`. 
*   **Focus State:** Do not use a thick border. Change the background to `surface_container_high` and add a `primary` "glow" (2px blur) to the bottom edge only.

### Cards & Lists (The "Breath" Rule)
*   **No Dividers:** Horizontal lines are banned. 
*   **Separation:** Use the `spacing scale` (Token `4` or `5`) to create "gutters" of negative space. 
*   **Interaction:** On hover, a list item should transition its background to `surface_container_low`. This "soft-highlight" is enough to indicate focus without cluttering the screen with lines.

### Predictive Trend Graphs
*   Use a `primary` stroke for the main price line.
*   Underlay the line with a vertical gradient: `primary_container` at 20% opacity fading to `surface` at 0% opacity. This creates a "holographic" projection effect.

## 6. Do's and Don'ts

### Do
*   **Do** use asymmetrical layouts (e.g., a wide chart paired with a slim, dense order book) to create visual interest.
*   **Do** use the `0.1rem` (Token 0.5) spacing for micro-adjustments in dense data tables.
*   **Do** leverage `spaceGrotesk` for all numerical displays to emphasize the "tech" nature of the product.

### Don't
*   **Don't** use a 100% opaque `outline`. It creates "grid-fever" and makes the UI feel dated.
*   **Don't** use standard "drop shadows." They look muddy on deep #111318 backgrounds.
*   **Don't** use pure white (#FFFFFF) for text. Always use `on_surface` (#e2e2e8) to prevent "halaction" (visual vibration) on dark backgrounds.