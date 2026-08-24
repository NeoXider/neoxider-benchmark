# Summary (TL;DR)

Goal: rebuild the GitHub social preview as a polished, deterministic 1280x640 PNG generated locally.
Status: complete. Final cover is a deterministic 1280x640 RGB PNG and remains readable at 640x320.

# Checklist

- [x] Read existing checkpoint/generator and image workflow instructions.
- [x] Inspect current cover, mascot bounds, and local font/runtime availability.
- [x] Implement the redesigned deterministic Pillow composition.
- [x] Render and visually review multiple iterations, including 640x320.
- [x] Verify exact PNG dimensions and one-command rebuild.

# Log

- 2026-08-24: No prior checkpoint existed. Read `docs/make_cover.py`; current layout is a flat left text stack with outlined chips and an ungrounded right-side mascot.
- 2026-08-24: Inspected `docs/cover.png` and canonical 1254x1254 RGBA mascot; visible mascot alpha bounds are `(223, 215, 1032, 1030)`, so the redesign crops transparent padding before placement.
- 2026-08-24: Replaced the generator with a 2x supersampled Pillow composition: stronger type hierarchy, gradient title, 3x2 category cards, mascot light stage, vignette, grid, and restrained contour traces.
- 2026-08-24: Rendered iteration 1 and inspected both 1280x640 and a real 640x320 downsample. Title, category labels, and mascot remain clear; footer is readable but benefits from a slight size increase. The explanatory copy will be tightened for more natural English.
- 2026-08-24: Applied iteration 2 polish: changed the body copy to “work carried through — format intact” / “honesty to admit when an attempt didn't work,” and raised footer type from 20px to 21px.
- 2026-08-24: Inspected iteration 2 at 1280x640 and 640x320. The title dominates correctly, all six axes remain legible, the two-line explanation reads cleanly, and the mascot stays prominent without colliding with copy.
- 2026-08-24: Final verification passed with `python docs\\make_cover.py`: PNG is exactly 1280x640 RGB (345,444 bytes). Two consecutive builds matched SHA256 `72EF445DDEB7C5BA7FB19DF7D19B3EBF19AEF6E7E750F8E1388E44757A717943`; `git diff --check` passed. Removed the temporary 640x320 preview after inspection.

# Conclusions / next steps

Complete. Deliverables are `docs/make_cover.py` and `docs/cover.png`. Rebuild with `python docs\\make_cover.py`; no internet or external service is used. Existing unrelated working-tree changes were left untouched.
