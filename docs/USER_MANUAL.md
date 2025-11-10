# User Manual — Document Converter Benchmark UI

## Overview
The web UI lets you upload documents, run multiple converters, and compare outputs visually. It also includes tooling to consolidate and analyze bounding boxes (BBoxes), browse tables per page, and export analysis packages.

## Start the UI
- Local reload: `uvicorn ui_server:app --host 0.0.0.0 --port 8080 --reload`
- Docker dev (auto‑reload): `docker compose --profile dev up --build app-dev`
- Open http://localhost:8080

## Pages
### Home (Index)
- Upload PDFs
- See recent runs with live status updates
- Actions: Details, Viewer, Tables, Delete (with confirmation)

### New Run
- Choose uploaded PDFs and converters
- Uses config defaults (Settings)
- Starts run in background; status updates on index/details pages

### Settings
- Baseline, default converters, visualization config
- Colors: per‑parser (tools) and overlays (text, merged, tables)
- Save to apply site‑wide

## Viewer
Top area shows a horizontal menu. Hover to open a menu; click items inside to toggle or apply.

### Document menu
- Select document (if multiple), and override the 10‑page limit warning

### View menu
- Grayscale (client or server mode)
- Show BBox numbers
- Overlay opacity

### Parsers menu
- Check/uncheck parsers to toggle their layers
- Legend shows tool colors; overlay colors are configurable in Settings

### Overlays menu
- Text BBoxes: per‑parser text blocks (color coded)
- Merged BBoxes: run a merge (see Merge menu), then toggle this layer
- Table BBoxes: auto‑detected tables (green)

### Merge menu
- Mode: Vertical / Horizontal / Paragraph
- Apply Merge: runs server‑side, caches result per page; toggle in Overlays menu

### Consolidation menu
- Tool: choose parser (e.g., tesseract)
- Strategy:
  - Overlap Merge — groups any overlapping boxes
  - Vertical Centers — groups boxes with near‑aligned center‑x (columns)
  - Paragraph — groups proximate lines with x‑overlap (paragraphs)
- Run Consolidation: runs server‑side and persists results per page/tool/strategy
- Show Redundant — outlines containers without extra text (dashed gray)
- Show Unique‑Extra — outlines containers with extra text (magenta)
- Show Groups — shows grouped extents (purple)

### Export menu
- Export Package — ZIP bundle containing images, merged overlays (SVG), boxes JSON, tables JSON + CSVs (summary, overlaps, text compare), and manifest

### Selection menu
- Clear Selection — clears the current region selection

### Canvas & Panels
- Canvas area with page image and SVG overlays; select region by drag or click
- Bottom panels:
  - Text tabs: per‑tool text inside selection; per‑box list with sizes
  - Tables tabs: per‑tool tables for current page

## Tables Page
- Multi‑document selector
- Converter and page selectors
- Renders extracted tables per page

## Details Page
- Shows run inputs and artifacts
- Live status; reloads when finished or failed

## Deleting Runs
- Index, Details, Viewer, and Tables pages include a Delete Run button
- Confirmation dialog, then run output directory and entry are removed

## Status Viewer
- The viewer shows backend activity:
  - Merge, Consolidation, Export — with busy/ok/fail indicators
  - Run status banner when active; page reloads on completion

## Tips
- Use paragraph grouping to identify line/paragraph blocks
- Use vertical centers to detect columns on multi‑column layouts
- Adjust tool / overlay colors in Settings for clarity
- The dev docker profile supports code + static hot reload

## Keyboard & Accessibility
- Page input supports direct typing; toolbar buttons for prev/next and zoom
- Controls have labels; color contrast is considered in default theme

## Troubleshooting
- If overlays look offset, reload the page (the viewer aligns SVG to image size)
- If server‑side grayscale is slow, switch to client grayscale (View menu)
- Consolidation runs per page — run per page as needed; results are cached and persisted

