# Visual Composite Viewer — Implementation Plan

## Overview
Build an interactive viewer to:
- Render page images with overlays per parser.
- Navigate pages (single document, bottom pager).
- Toggle grayscale, bbox numbering, and per-tool layers.
- Select regions and compare extracted text across tools in a bottom panel.
- Zoom and pan smoothly.
- Persist bounding boxes in JSON with stable IDs and export a full analysis package (PNG, SVG, JSON/CSV, HTML summary).

## Assumptions
- FastAPI + Jinja UI (current repo) with static assets.
- Page images and per-engine overlays available via API or artifact paths.
- Converters provide `metadata.blocks_per_page` with normalized coords.
- Limit initial pages to 10, allow override with warning.

## UI Structure
- Left Panel
  - Parsers multi-select (checkboxes); color legend per parser.
  - Toggles: Grayscale, Show BBox numbers.
  - Overlay Opacity slider (0–100%).
- Center Viewport
  - Base page image `<img id="pageImg">`.
  - SVG overlay `<svg id="overlay">` with one `<g>` per tool and one composite group.
  - Drag selection rectangle; highlights intersecting boxes.
- Bottom Bar
  - Prev/Next page, page index, total pages, “>10 pages” warning with override.
  - Zoom in/out, reset, fit-to-width.
  - Export button.
- Bottom Panel
  - Tabs/columns per selected tool; shows extracted text for current selection region.

## State & Behavior
- Page state: `{docId, pageIndex, selectedParsers[], showNumbers, grayscale, overlayOpacity, zoom, pan, selectionRect, limitOverride}`.
- Layer visibility: toggle SVG groups by parser; composite visible via toggle or when no parser selected.
- Selection: drag to create normalized rect; intersect with boxes; update bottom panel.
- Zoom/pan: wheel+ctrl for zoom, drag background for pan; apply transform to overlay and image container.

## API Endpoints (FastAPI)
- `GET /api/runs/{run_id}/docs`
  - List docs with page counts and available parsers; provide color map and total pages.
- `GET /api/runs/{run_id}/doc/{doc}/page/{page}/bboxes?tools=a,b&withText=1&withIds=1`
  - Returns `{ page, tools, boxes: { tool: BBox[] } }`.
- `GET /api/runs/{run_id}/doc/{doc}/page/{page}/composite`
  - Returns pre-rendered composite PNG (existing artifact), or generated SVG.
- `GET /api/runs/{run_id}/doc/{doc}/page/{page}/words|characters?tool=...` (optional)
  - Returns word/char boxes if provided by converters.
- `POST /api/runs/{run_id}/doc/{doc}/page/{page}/merge`
  - Body: `{ mode: 'vertical'|'horizontal'|'paragraph', tools?: string[] }`.
  - Returns merged groups with union bboxes and member ids.
- `POST /api/runs/{run_id}/doc/{doc}/state`
  - Persist UI state + saved selections to `results/run_{id}/ui_state.json`.
- `POST /api/runs/{run_id}/doc/{doc}/export`
  - Produce ZIP with images, SVG overlays, boxes JSON, CSV summaries, overlap analysis, text comparison, HTML report.

Note: Images can still be served via existing `/api/artifacts?path=...`.

## Data Sources
- Blocks: `ConversionResult.metadata.blocks_per_page` → engine → page → `{x0,y0,x1,y1,text}` normalized.
- Optional: `words_per_page`, `chars_per_page` if provided.
- Visual artifacts: `results/run_{id}/visual/<doc>/page_XXX_*.png`.

## Canonical Schemas
- BBox
  - `{ id: string, page: number, tool: string, type: 'block'|'word'|'char'|'merged', bbox: {x:number,y:number,w:number,h:number}, rotation?:number, confidence?:number, text?:string, parent_id?:string, children_ids?:string[], order?:number }`
- Page payload
  - `{ page:number, tools:string[], boxes: { [tool:string]: BBox[] } }`
- Merge response
  - `{ mode:string, groups:[{ id:string, tool:'merged', bbox:{...}, members:string[] }] }`
- Export manifest
  - `{ run_id, doc, pages, tools, generated_at, artifacts:{ images:[], overlays_svg:[], boxes_json, summary_csv, overlaps_csv, text_compare_csv, report_html } }`

## Server Changes
- Extend `visualizer.py` to write `visual_blocks_by_engine.json`:
  - `{ [pageIndex:number]: { [tool:string]: BBox[] } }` with stable `id`s; keep `visual_blocks.json` (union) for reference.
- Implement endpoints in `ui_server.py` that read detailed results and visual JSON; memoize on disk.
- Grayscale: prefer CSS filter on client; optional server-side grayscale endpoint using Pillow/OpenCV.
- Export: build `exports/<doc>_<ts>.zip` with PNGs, SVG overlays, JSON/CSV, HTML summary + manifest.

## UI Template/Assets
- Update `templates/run_view.html` to include:
  - Left control panel, viewport with `<img>` + `<svg>`, bottom panel and bar.
- Add `static/js/run_view.js` to manage fetch/render, selection, zoom/pan, and export.
- Add `static/css/viewer.css` for layout, accessible styles, legend, and overlays.

## Merge Modes
- Vertical: merge by x-overlap and y adjacency (line stacking).
- Horizontal: merge by y-overlap and x adjacency (row grouping).
- Paragraph: cluster by proximity/alignment; union bounds; return ordered groups with `members`.
- Deterministic IDs: `merged-p{page}-m{hash}`.

## Numbers & Legend
- Draw `<text>` labels on SVG at top-left of each rect when “Show BBox numbers” enabled.
- Consistent color map per tool (re-use `visualizer.py` colors and expose via docs endpoint).

## Performance & Limits
- Default to 10 pages; lazy-load per page as navigated.
- Client cache per page/tool; reduce repeated fetches.
- SVG overlays to avoid regenerating base images.

## Accessibility
- Keyboard: Tab focus, Arrow keys for pages, `+/-` for zoom, `0` reset.
- ARIA labels and roles for controls; color contrast compliant; text-only overlay fallback.

## Milestones & Checklist
- [ ] M1: Viewport (image + SVG), page nav, zoom/pan, grayscale (CSS)
- [ ] M2: Parsers multi-select, color legend, overlay opacity, bbox numbers
- [ ] M3: Selection box + bottom compare panel wired to `/bboxes`
- [ ] M4: Merge endpoint + UI; show merged layer
- [ ] M5: Emit `visual_blocks_by_engine.json`; implement `/bboxes` and `/words|/characters`
- [ ] M6: Export zip + manifest; summary, overlap, text comparison outputs
- [ ] M7: Persist UI state; docs in README

## Open Items
- Confirm available per-tool outputs beyond blocks (words/characters).
- Finalize CSV column sets and naming conventions for exports.
- Decide on HTML report content depth and branding.

## Notes
This plan aligns with the current FastAPI/Jinja architecture and existing `visualizer.py` outputs, minimizing churn while enabling the requested interactive capabilities and export workflow.

