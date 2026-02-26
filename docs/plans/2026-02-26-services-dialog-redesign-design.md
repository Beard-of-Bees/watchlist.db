# Services Dialog Redesign (Design)

Date: 2026-02-26

## Goal

Update the "Manage services" dialog so it visually matches the redesigned main page (glass dark UI, blue accent, softer contrast) and improve positioning/sizing for better usability across desktop and mobile.

## Chosen Pattern

- Desktop: centered modal dialog
- Mobile: bottom sheet

This preserves the current dialog interaction model and JS behavior while improving visual consistency and ergonomics.

## Visual Design

- Reuse the main page visual language:
- Translucent dark glass surface
- Subtle light border
- Blur and soft shadow
- Primary blue accent for interactive states
- Keep rounded corners on desktop and rounded top corners on mobile sheet.
- Backdrop should be darker with blur, but still allow page context to show through.

## Positioning and Size

- Desktop width: `min(560px, calc(100vw - 32px))`
- Desktop max height: `min(72dvh, 680px)`
- Desktop placement: centered in viewport with comfortable breathing room.
- Mobile breakpoint: treat small screens as bottom-sheet layout (recommended around `640px` and below).
- Mobile width: full width
- Mobile max height: ~`82-88dvh`
- Mobile sheet should include safe-area-aware bottom padding.

## Interaction and UX

- Keep current `<dialog>` semantics and existing close/open JS handlers.
- Header gets more spacious padding and a glass-style close button hover/focus treatment.
- "Select all" / "Deselect all" become pill-style utility buttons (not plain text links).
- Service rows get larger tap targets and clearer hover/focus states.
- Preserve existing checkbox + custom toggle behavior, but recolor toggle to the page accent.
- Footer action remains visible (sticky footer inside dialog) so `Done` is accessible on long lists.
- Internal scrolling should be limited to the services list; header/footer stay fixed within the dialog sheet.

## Implementation Scope

- Primary changes in `static/style.css` (dialog styles only).
- Optional minor markup class adjustments in `templates/index.html` if required for sticky footer/header spacing.
- No JS logic changes expected.

## Risks / Notes

- Sticky footer/header inside a `<dialog>` must be tested on mobile Safari/Chrome for scroll behavior.
- Maintain keyboard focus visibility and avoid reducing contrast for interactive controls.
