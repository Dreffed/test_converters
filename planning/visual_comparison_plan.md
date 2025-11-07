# Visual Block Comparison — Development Plan

## Objective
Add a visual comparison feature that renders each PDF page to an image and overlays text blocks recognized by each converter. Compute coverage metrics as “% of cumulative detected blocks” per page and per document.

## Outcomes
- Per-page PNGs with overlays (per engine and composite) showing detected text blocks.
- JSON metrics per page and aggregated per document: coverage per engine vs union of blocks.
- Markdown summary with tables and quick visual links.

## Dependencies
- Preferred: OpenCV (`opencv-python`, `numpy`)
- Fallback: Pillow (`Pillow`) if OpenCV is unavailable
- Rendering backends:
  - Primary: PyMuPDF (fast, cross-platform)
  - Fallback: `pdf2image` + Poppler (Windows requires `--poppler-path`)

Add to requirements (phase 1):
- opencv-python
- numpy
- (optional) Pillow

## Terminology & Coordinate Systems
- PDF coordinates: float points; origin varies by library. We will standardize to image pixel coordinates (origin: top-left, x right, y down).
- Block: rectangular region corresponding to a contiguous text chunk.
- IoU: Intersection over Union for block matching.

## Data Model Changes
- Add a canonical block schema to normalize layout output across engines.

```python
# converter_benchmark.py
@dataclass
class TextBlock:
    page_index: int
    x0: float  # pixel coords (top-left origin)
    y0: float
    x1: float  # pixel coords (bottom-right)
    y1: float
    text: str = ""
    confidence: float | None = None
    source: str = ""  # converter name

# Extend ConversionResult.metadata
# metadata["blocks_per_page"]: Dict[int, List[Dict]]  # list of TextBlock as dicts
```

Notes:
- Engines that don’t support block positions will omit `blocks_per_page` (no visuals).
- For engines with word-level data, we will group/cluster to blocks (phase 2).

## Extraction by Engine (Phase 1 scope first)
- PyMuPDF (fitz): `page.get_text("blocks")` returns (x0, y0, x1, y1, text, …) — good block coverage.
- Tesseract: use `pytesseract.image_to_data` (TSV) after rendering pages; build blocks from lines/paragraphs.
- pdfplumber: `page.extract_words()` / `extract_text()` and `page.layout` — implement basic grouping in phase 2.
- pdfminer.six: advanced (phase 2/3), extract from LA components.
- PyPDF2/MarkItDown/Tika/pypandoc/textract/unstructured: no reliable positions — skip visuals.

## Rendering Strategy
- Default renderer: PyMuPDF
  - `doc = fitz.open(pdf)`; `page.get_pixmap(dpi=VIZ_DPI)` to PNG
  - Transform PDF bbox to pixel coordinates using page matrix.
- Fallback renderer: `pdf2image.convert_from_path(..., dpi=VIZ_DPI, poppler_path=…)`
  - Use image size to scale/align Tesseract blocks.

Coordinate normalization
- For PyMuPDF: use `page.get_text("blocks", flags=...)` + `fitz.Matrix(scale)` mapping; verify y-axis orientation and flip if needed.
- For Tesseract TSV: coordinates are already pixel-based on the rendered image.

## Matching & Coverage Metrics
- Coverage baseline: aggregate union of detected blocks across ALL engines on each page (your preference).
- Per page:
  - Build union set U of blocks from all engines that produced blocks on that page; deduplicate near-identical boxes (IoU ≥ 0.9) into a canonical list.
  - For engine E, compute matches by greedy IoU ≥ `VIZ_IOU_THR` (default 0.5) between its blocks and U.
  - Coverage(E, page) = |matched U blocks| / |U|. Optional: also report area-weighted coverage.
- Per document: weighted average across pages using |U_page| as weights (default), plus unweighted mean as a secondary metric.

Implementation details
- Deduplication: consider two blocks equivalent if IoU ≥ 0.9; keep first occurrence and attach `sources: [engine names]`.
- Greedy matching: sort U by area desc; for each block in E, match the best-unmatched union block with IoU ≥ threshold.

## Visualization
- Overlay per engine: draw rectangles in a per-engine color on top of the page image.
- Composite: draw all engines with different colors; optional labels (engine initials) and legend.
- Options:
  - Colors: fixed palette mapping engine->color
  - Line thickness, alpha for transparency
  - Output paths: `{output_dir}/visual/{doc_basename}/page_{idx:03d}_{engine}.png`

## CLI Additions
- `--visualize-blocks` (bool): enable visual outputs and metrics
- `--viz-output-dir` (default: `benchmark_results/visual`)
- `--viz-dpi` (default: 200)
- `--viz-iou-thr` (default: 0.5)
- `--viz-renderer` (`pymupdf`|`pdf2image`, default: auto)
- `--viz-engines` (subset list; default: all that produce blocks)
- `--pages` (e.g., `1-5,8,10-` for large docs)
- `--poppler-path` (reuse existing, for Windows)
 - `--viz-export-blocks` (bool): export canonicalized blocks JSON for later UI consumption

Wire-through
- `run_benchmark.py` collects args; passes into converters and into a new `Visualizer` component inside `DocumentConverterBenchmark`.

## Architecture & Modules
- `visualization/blocks.py` — dataclass TextBlock, IoU, normalization utilities
- `visualization/extractors.py` — helpers to pull blocks from engines where supported
- `visualization/render.py` — PyMuPDF/pdf2image renderers and coordinate transforms
- `visualization/overlay.py` — drawing with OpenCV (or Pillow fallback)
- `visualization/metrics.py` — build union, dedupe, compute coverage per page/doc
- Integrate into `DocumentConverterBenchmark` with optional post-processing step if `--visualize-blocks`.

## Phase Plan & Status
- Phase 1 (MVP) — Completed
  - Added normalized `blocks_per_page` in converter metadata.
  - Implemented PyMuPDF blocks extraction (pymupdf_converter).
  - Implemented PyMuPDF rendering; per-engine and composite overlays.
  - Implemented union/dedupe and coverage metrics; per-page + doc JSON.
  - Added CLI flags: `--visualize-blocks`, `--viz-output-dir`, `--viz-dpi`, `--viz-iou-thr`, `--viz-export-blocks`.

- Phase 2 — Completed
  - Added Tesseract TSV parsing (line grouping) to produce blocks.
  - Added pdfplumber words→lines clustering for blocks.
  - Added `pdf2image` fallback renderer and `--viz-renderer` selection.

- Phase 3 — Completed
  - Added pdfminer.six block extraction (LTTextBox/Line) with coordinate normalization.
  - Added bipartite matching option for coverage (`--viz-match`), defaulting to bipartite.
  - Kept greedy matcher available for comparison.

## Output Artifacts
- Images: per page per engine and composite (PNG)
- JSON (metrics): `visual_metrics.json` with per-page coverage + doc summary
- JSON (blocks): `visual_blocks.json` with canonical union blocks per page, each entry containing bbox, page index, sources (engines covering it), and optional per-engine IoUs (when `--viz-export-blocks`).
- Markdown: append a “Visual Coverage” section to `summary_*.md` with tables and links to images

## Future UI (Optional)
- Store canonical blocks JSON per document and ship a lightweight static UI under `visualization/ui/`:
  - Single-page app (vanilla JS) loads `visual_blocks_*.json` and rendered page PNGs.
  - Toggles to show/hide engines, hover to see block text/sources, engine color legend.
  - No server required; serve via `python -m http.server` or open directly in browser.

## Risks & Mitigations
- Some engines don’t provide positions → scope them out of visuals; clearly mark N/A.
- Coordinate mismatches/y-axis flips → standardize transforms, add tests.
- Performance on large docs → page range flag, lower `--viz-dpi`, lazy rendering.
- Windows dependencies (Poppler) → reuse existing `--poppler-path`, docs in README.

## Testing Strategy
- Unit tests for IoU, dedupe, and coordinate mapping
- Golden-file tests for small sample PDF (2–3 pages)
- Manual visual inspection for overlays

## Current Support Matrix
- Overlays + blocks: PyMuPDF, pdfplumber (grouped lines), pdfminer, Tesseract (TSV lines)
- Planned/Not yet positional: PyPDF2, MarkItDown, Tika, pypandoc, textract, unstructured

## Estimated Effort
- Phase 1: 1–2 days
- Phase 2: 1–2 days
- Phase 3: 2–3 days (optional)

## Open Questions
- Is coverage computed vs union of all engines acceptable, or should we compare vs a chosen baseline (e.g., PyMuPDF/Tesseract)?
- Preferred default renderer (PyMuPDF vs pdf2image) and DPI?
- Image size and storage constraints for large documents?
