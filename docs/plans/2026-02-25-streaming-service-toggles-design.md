# Streaming Service Toggle Filter

**Date:** 2026-02-25
**Status:** Approved

## Goal

Let users select which streaming services they subscribe to. The page then splits into two sections: films available on enabled services, and everything else.

---

## Data Flow

- `main.py` index route computes a deduplicated, name-sorted list of all platforms across all films and passes it as `all_platforms` to the template.
- Each `.film-card` gets a `data-platform-ids="8,337"` attribute (comma-separated provider IDs) so JS can classify films without re-parsing DOM children.
- No new endpoints. No schema changes.

---

## Toggle Bar UX

- Full-width bar between header and film grid.
- Each service renders as a chip: circular logo (28px) + provider name.
- **Active state**: full opacity, white border.
- **Inactive state**: 40% opacity, dim border. Hovering re-brightens — clearly re-selectable, not dead.
- "All" / "None" convenience links at the end of the chip row.
- Default: all services enabled (localStorage absent → all on).

---

## Film Grid Layout

- **All services enabled (default)**: flat grid, no section headers — identical to current behaviour.
- **Any service disabled**: grid splits into two sections:
  - **"Streaming on your services"** — films with ≥1 platform matching an enabled service.
  - **"Everything else"** — films with no matching platform, or no platforms at all. Section heading is slightly dimmer.

---

## State (localStorage)

- Key: `watchlist_enabled_services`
- Value: JSON array of enabled `provider_id` integers, e.g. `[8, 337, 2100]`
- On first load (key absent): default to all provider IDs enabled.
- "All" resets to full set. "None" clears to empty array.

---

## JS Logic (vanilla, inline)

On page load:
1. Read `watchlist_enabled_services` from localStorage. If absent, initialise with all provider IDs from the chip data.
2. Apply active/inactive CSS classes to chips.
3. If all services enabled → flat grid (no section headers).
4. If any disabled → split film cards into two `<section>` elements based on `data-platform-ids`.

On chip click:
1. Toggle provider ID in the enabled set.
2. Persist to localStorage.
3. Re-classify film cards and update DOM (move nodes between sections).

---

## Files to Change

| File | Change |
|---|---|
| `main.py` | Compute `all_platforms` (deduped, sorted) from films, pass to template |
| `templates/index.html` | Add toggle bar HTML; add `data-platform-ids` to film cards; add two-section layout; add inline `<script>` |
| `static/style.css` | Add chip styles, section heading styles, active/inactive states |
