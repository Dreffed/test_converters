#!/usr/bin/env python3
import os
import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from converter_benchmark import DocumentConverterBenchmark
from converter_implementations import get_available_converters
import urllib.parse
import markdown as md
from math import isfinite
import io


APP_DATA_DIR = Path(os.environ.get("APP_DATA_DIR", "data")).resolve()
UPLOADS_DIR = APP_DATA_DIR / "uploads"
RESULTS_DIR = APP_DATA_DIR / "results"
LOGS_DIR = APP_DATA_DIR / "logs"
STATE_FILE = APP_DATA_DIR / "runs.json"
CONFIG_FILE = APP_DATA_DIR / "config.json"

for d in (APP_DATA_DIR, UPLOADS_DIR, RESULTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Converter Benchmark UI")
templates = Jinja2Templates(directory="templates")


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


STATE = load_json(STATE_FILE, {"runs": []})
CONFIG = load_json(CONFIG_FILE, {
    "baseline": "tesseract",
    "converters": [],
    "visualize": False,
    "viz": {"dpi": 200, "iou_thr": 0.5, "match": "bipartite", "renderer": "auto", "export_blocks": False},
    "tesseract_dpi": 300,
    "poppler_path": os.environ.get("POPPLER_PATH"),
    "colors": {
        "tools": {
            'pymupdf': '#00FF00',
            'pdfplumber': '#FF0000',
            'pypdf2': '#0000FF',
            'tesseract': '#FFFF00',
            'markitdown': '#FF00FF',
            'pdfminer': '#00FFFF',
        },
        "overlays": {
            "text": "#00FFFF",
            "merged": "#FFA500",
            "tables": "#32CD32"
        }
    }
})


def next_run_id() -> int:
    runs = STATE.get("runs", [])
    return (max((r.get("id", 0) for r in runs), default=0) + 1) if runs else 1


def append_run(run: Dict):
    STATE.setdefault("runs", []).insert(0, run)
    save_json(STATE_FILE, STATE)


def update_run(run_id: int, patch: Dict):
    for r in STATE.get("runs", []):
        if r.get("id") == run_id:
            r.update(patch)
            save_json(STATE_FILE, STATE)
            return r
    return None


def get_run(run_id: int) -> Optional[Dict]:
    for r in STATE.get("runs", []):
        if r.get("id") == run_id:
            return r
    return None


def delete_run_entry(run_id: int) -> bool:
    runs = STATE.get("runs", [])
    idx = None
    for i, r in enumerate(runs):
        if r.get("id") == run_id:
            idx = i
            break
    if idx is not None:
        runs.pop(idx)
        save_json(STATE_FILE, STATE)
        return True
    return False


def run_benchmark_job(run_id: int):
    run = get_run(run_id)
    if not run:
        return
    try:
        update_run(run_id, {"status": "running"})
        files: List[str] = run.get("files", [])
        # Resolve file paths: accept absolute paths or basenames under uploads dir
        resolved_files: List[str] = []
        for f in files:
            p = Path(f)
            if p.is_file():
                resolved_files.append(str(p))
                continue
            # Try basename under uploads
            p2 = UPLOADS_DIR / p.name
            if p2.is_file():
                resolved_files.append(str(p2))
                continue
        if not resolved_files:
            update_run(run_id, {"status": "failed", "error": "No valid input files found in /data/uploads or provided paths."})
            return
        converters_req: List[str] = run.get("converters", [])
        baseline: Optional[str] = run.get("baseline")
        visualize: bool = run.get("visualize", False)
        viz = run.get("viz", {})
        tesseract_dpi = int(run.get("tesseract_dpi", 300))
        poppler_path = run.get("poppler_path")

        # Available converters
        available = get_available_converters(test_imports=True)
        converters = {}
        if converters_req:
            for name in converters_req:
                if name in available:
                    converters[name] = available[name]
        else:
            converters = available
        # kwargs passed into converter functions
        converter_kwargs = {
            'verbose': True,
            'extract_tables': True,
            'dpi': tesseract_dpi,
            'poppler_path': poppler_path,
        }
        converters_wrapped = {name: (lambda fp, f=func: f(fp, **converter_kwargs)) for name, func in converters.items()}

        # Configure benchmark
        output_dir = RESULTS_DIR / f"run_{run_id}"
        bench = DocumentConverterBenchmark(
            output_dir=str(output_dir),
            visualize_blocks=visualize,
            viz_output_dir=str(output_dir / 'visual'),
            viz_dpi=int(viz.get("dpi", 200)),
            viz_iou_thr=float(viz.get("iou_thr", 0.5)),
            viz_export_blocks=bool(viz.get("export_blocks", False)),
            viz_renderer=str(viz.get("renderer", "auto")),
            viz_poppler_path=poppler_path,
            viz_match_mode=str(viz.get("match", "bipartite")),
        )

        # Run
        base = baseline if baseline in converters_wrapped else None
        report = bench.run_benchmark_suite(
            test_files=resolved_files,
            converters=converters_wrapped,
            baseline_converter=base,
        )
        bench.print_summary()

        # Save artifact pointers
        # Use latest summary/report in output_dir
        summary = None
        report_json = None
        details_json = None
        if output_dir.exists():
            for p in sorted(output_dir.glob("summary_*.md")):
                summary = str(p)
            for p in sorted(output_dir.glob("benchmark_report_*.json")):
                report_json = str(p)
            for p in sorted(output_dir.glob("detailed_results_*.json")):
                details_json = str(p)

        update_run(run_id, {
            "status": "done",
            "artifacts": {
                "summary": summary,
                "report": report_json,
                "details": details_json,
                "visual_dir": str(output_dir / 'visual') if visualize else None,
            }
        })
    except Exception as e:
        update_run(run_id, {"status": "failed", "error": f"{type(e).__name__}: {e}"})


# Static and templates
if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    runs = STATE.get("runs", [])
    uploads = []
    try:
        for p in sorted(UPLOADS_DIR.glob("*.pdf")):
            uploads.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    except Exception:
        pass
    return templates.TemplateResponse("index.html", {"request": request, "runs": runs, "uploads": uploads})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "config": CONFIG})


@app.post("/settings")
async def save_settings(request: Request,
    baseline: str = Form("tesseract"),
    converters: str = Form(""),
    visualize: Optional[str] = Form(None),
    viz_dpi: int = Form(200),
    viz_iou_thr: float = Form(0.5),
    viz_match: str = Form("bipartite"),
    viz_renderer: str = Form("auto"),
    viz_export_blocks: Optional[str] = Form(None),
    tesseract_dpi: int = Form(300),
    poppler_path: Optional[str] = Form(None),
):
    CONFIG.update({
        "baseline": baseline,
        "converters": [c for c in converters.split(",") if c.strip()],
        "visualize": bool(visualize),
        "viz": {
            "dpi": viz_dpi,
            "iou_thr": viz_iou_thr,
            "match": viz_match,
            "renderer": viz_renderer,
            "export_blocks": bool(viz_export_blocks),
        },
        "tesseract_dpi": tesseract_dpi,
        "poppler_path": poppler_path or None,
    })
    # Parse dynamic color fields
    try:
        form = await request.form()
        colors = CONFIG.setdefault('colors', {})
        tools_map = colors.setdefault('tools', {})
        overlays = colors.setdefault('overlays', {})
        for k, v in form.items():
            if not isinstance(v, str):
                continue
            if k.startswith('color_tool_'):
                name = k[len('color_tool_'):]
                if name:
                    tools_map[name] = v
            elif k == 'color_overlay_text':
                overlays['text'] = v
            elif k == 'color_overlay_merged':
                overlays['merged'] = v
            elif k == 'color_overlay_tables':
                overlays['tables'] = v
    except Exception:
        pass
    save_json(CONFIG_FILE, CONFIG)
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/runs/new", response_class=HTMLResponse)
def new_run_page(request: Request):
    available = list(get_available_converters(test_imports=True).keys())
    uploads = []
    try:
        for p in sorted(UPLOADS_DIR.glob("*.pdf")):
            uploads.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    except Exception:
        pass
    return templates.TemplateResponse(
        "runs_new.html",
        {"request": request, "available": available, "config": CONFIG, "uploads": uploads}
    )


@app.post("/runs")
def create_run(
    files: List[str] = Form([]),
    converters: str = Form(""),
    baseline: str = Form(""),
    extra_files: str = Form("")
):
    run_id = next_run_id()
    # Combine checkbox-selected files with any extra comma-separated paths
    selected_files = list(files) if isinstance(files, list) else ([files] if files else [])
    if extra_files:
        selected_files.extend([f.strip() for f in extra_files.split(",") if f.strip()])
    selected_converters = [c for c in converters.split(",") if c]
    run = {
        "id": run_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
        "files": selected_files,
        "converters": selected_converters,
        "baseline": baseline or CONFIG.get("baseline"),
        "visualize": bool(CONFIG.get("visualize", False)),
        "viz": CONFIG.get("viz", {}),
        "tesseract_dpi": CONFIG.get("tesseract_dpi", 300),
        "poppler_path": CONFIG.get("poppler_path"),
    }
    append_run(run)
    # Start background thread
    t = threading.Thread(target=run_benchmark_job, args=(run_id,), daemon=True)
    t.start()
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: int):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse("run_detail.html", {"request": request, "run": run})


@app.get("/runs/{run_id}/view", response_class=HTMLResponse)
def run_view(request: Request, run_id: int):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # Render summary markdown, if available
    summary_html = None
    art = run.get("artifacts") or {}
    summary_path = art.get("summary")
    if summary_path and Path(summary_path).exists():
        try:
            text = Path(summary_path).read_text(encoding='utf-8')
            summary_html = md.markdown(text)
        except Exception:
            summary_html = None
    # Build visual index
    visual_dir = art.get("visual_dir")
    visual_index = []
    if visual_dir and Path(visual_dir).exists():
        vdir = Path(visual_dir)
        for doc_dir in sorted([d for d in vdir.iterdir() if d.is_dir()]):
            # base images
            base_pages = sorted(doc_dir.glob('page_*.png'))
            # find overlay subdir(s)
            overlay_dirs = [d for d in doc_dir.iterdir() if d.is_dir()]
            ovr = overlay_dirs[0] if overlay_dirs else None
            pages_info = []
            for bp in base_pages:
                name = bp.stem  # page_000
                idx_str = name.split('_')[-1]
                try:
                    pidx = int(idx_str)
                except ValueError:
                    continue
                entry = {
                    'page': pidx,
                    'base': str(bp),
                    'composite': None,
                    'engines': {}
                }
                if ovr:
                    # composite
                    comp = ovr / f"page_{pidx:03d}_composite.png"
                    if comp.exists():
                        entry['composite'] = str(comp)
                    # engines
                    for img in ovr.glob(f"page_{pidx:03d}_*.png"):
                        stem = img.stem
                        if stem.endswith('_composite'):
                            continue
                        eng = stem.split('_', 3)[-1]
                        entry['engines'][eng] = str(img)
                pages_info.append(entry)
            visual_index.append({
                'doc': doc_dir.name,
                'pages': pages_info
            })
    return templates.TemplateResponse("run_view.html", {
        "request": request,
        "run": run,
        "summary_html": summary_html,
        "visual_index_json": json.dumps(visual_index)
    })


@app.get("/runs/{run_id}/tables", response_class=HTMLResponse)
def run_tables(request: Request, run_id: int):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    art = run.get("artifacts") or {}
    details_path = art.get("details")
    converters: List[str] = []
    docs_set = set()
    pages_by_doc: Dict[str, List[int]] = {}
    # data[doc][converter][page] = tables
    data: Dict[str, Dict[str, Dict[str, List]]] = {}
    if details_path and Path(details_path).exists():
        try:
            results = json.loads(Path(details_path).read_text(encoding='utf-8'))
            # results is a list of ConversionResult dicts
            for r in results:
                conv = r.get('converter_name')
                meta = r.get('metadata') or {}
                tp = meta.get('tables_per_page') or {}
                if tp:
                    if conv not in converters:
                        converters.append(conv)
                    fp = r.get('file_path') or ''
                    doc_name = Path(fp).stem
                    docs_set.add(doc_name)
                    cdict = data.setdefault(doc_name, {}).setdefault(conv, {})
                    for page_str, tables in tp.items():
                        # keys might be strings or ints in JSON
                        try:
                            p = int(page_str)
                        except Exception:
                            p = page_str
                        pages_by_doc.setdefault(doc_name, [])
                        if isinstance(p, int) and p not in pages_by_doc[doc_name]:
                            pages_by_doc[doc_name].append(p)
                        cdict[str(p)] = tables
        except Exception:
            pass
    # Sort pages per doc
    for dname, plist in pages_by_doc.items():
        pages_by_doc[dname] = sorted(plist)
    docs_list = sorted(list(docs_set))
    return templates.TemplateResponse("run_tables.html", {
        "request": request,
        "run": run,
        "converters": converters,
        "docs_json": json.dumps(docs_list),
        "pages_by_doc_json": json.dumps(pages_by_doc),
        "tables_json": json.dumps(data)
    })


@app.post("/api/files")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    dest = UPLOADS_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"ok": True, "path": str(dest)}


@app.get("/api/files")
def list_files():
    items = []
    for p in sorted(UPLOADS_DIR.glob("*.pdf")):
        items.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    return {"files": items}


@app.delete("/api/files/{filename}")
def delete_file(filename: str):
    # Security: operate only within uploads dir, only PDFs
    name = os.path.basename(filename)
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    target = UPLOADS_DIR / name
    try:
        if target.exists() and target.is_file():
            target.unlink()
            return {"ok": True}
        raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return CONFIG


@app.post("/api/config")
def set_config(config: Dict):
    CONFIG.update(config)
    save_json(CONFIG_FILE, CONFIG)
    return {"ok": True}


@app.get("/api/converters")
def converters():
    available = list(get_available_converters(test_imports=True).keys())
    return {"available": available}


@app.get("/api/runs")
def runs():
    return {"runs": STATE.get("runs", [])}


@app.get("/api/runs/{run_id}")
def get_run_api(run_id: int):
    r = get_run(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    return r


@app.get("/api/artifacts")
def artifact(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(str(p))


@app.delete("/api/runs/{run_id}")
def api_delete_run(run_id: int):
    # Remove results directory and state entry
    out_dir = RESULTS_DIR / f"run_{run_id}"
    try:
        if out_dir.exists():
            # Recursively delete
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)
    except Exception:
        # continue; attempt to remove state even if files fail
        pass
    ok = delete_run_entry(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"ok": True}


# -------------------------
# New APIs for composite UI
# -------------------------

_COLOR_MAP = {
    'pymupdf': '#00FF00',
    'pdfplumber': '#FF0000',
    'pypdf2': '#0000FF',
    'tesseract': '#FFFF00',
    'markitdown': '#FF00FF',
    'pdfminer': '#00FFFF',
}


def _run_visual_root(run_id: int) -> Path:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    art = run.get("artifacts") or {}
    visual_dir = art.get("visual_dir")
    if not visual_dir:
        raise HTTPException(status_code=404, detail="No visual artifacts for this run")
    vdir = Path(visual_dir)
    if not vdir.exists():
        raise HTTPException(status_code=404, detail="Visual directory missing")
    return vdir


@app.get("/api/runs/{run_id}/docs")
def api_docs(run_id: int):
    vdir = _run_visual_root(run_id)
    docs = []
    for doc_dir in sorted([d for d in vdir.iterdir() if d.is_dir()]):
        base_pages = sorted(doc_dir.glob('page_*.png'))
        pages = len(base_pages)
        engines = []
        # Overlays may be in subdir or same dir; scan both
        candidates = [doc_dir] + [d for d in doc_dir.iterdir() if d.is_dir()]
        seen = set()
        for cdir in candidates:
            for img in cdir.glob('page_*_*.png'):
                stem = img.stem
                if stem.endswith('_composite'):
                    continue
                eng = stem.split('_', 3)[-1]
                if eng and eng not in seen:
                    engines.append(eng)
                    seen.add(eng)
        docs.append({
            'id': doc_dir.name,
            'pages': pages,
            'engines': sorted(engines)
        })
    # Colors from CONFIG
    colors = CONFIG.get('colors') or {}
    # If tools map missing, fall back to defaults
    tool_colors = colors.get('tools') or {}
    overlay_colors = colors.get('overlays') or {}
    return { 'docs': docs, 'colors': { 'tools': tool_colors, 'overlays': overlay_colors } }


def _doc_dir_for(run_id: int, doc: str) -> Path:
    vdir = _run_visual_root(run_id)
    d = vdir / doc
    if not d.exists():
        raise HTTPException(status_code=404, detail="Doc not found")
    return d


def _find_pdf_for_doc(run_id: int, doc: str) -> Optional[Path]:
    run = get_run(run_id)
    if not run:
        return None
    # Prefer original files list
    files = run.get('files') or []
    for f in files:
        try:
            if Path(f).exists() and Path(f).stem == doc:
                return Path(f)
        except Exception:
            continue
    # Fallback to detailed results file paths
    art = run.get('artifacts') or {}
    details_path = art.get('details')
    if details_path and Path(details_path).exists():
        try:
            results = json.loads(Path(details_path).read_text(encoding='utf-8'))
            for r in results:
                fp = r.get('file_path') or ''
                if Path(fp).exists() and Path(fp).stem == doc:
                    return Path(fp)
        except Exception:
            pass
    return None


def _load_boxes_by_engine(doc_dir: Path) -> Optional[Dict]:
    p = doc_dir / 'visual_blocks_by_engine.json'
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return None
    return None


def _contains(a: Dict, b: Dict) -> bool:
    return (a['x'] <= b['x'] and a['y'] <= b['y'] and (a['x'] + a['w']) >= (b['x'] + b['w']) and (a['y'] + a['h']) >= (b['y'] + b['h']))


def _overlaps(a: Dict, b: Dict) -> bool:
    ax1 = a['x'] + a['w']; ay1 = a['y'] + a['h']; bx1 = b['x'] + b['w']; by1 = b['y'] + b['h']
    iw = max(0.0, min(ax1, bx1) - max(a['x'], b['x']))
    ih = max(0.0, min(ay1, by1) - max(a['y'], b['y']))
    return iw * ih > 0


def _union(a: Dict, b: Dict) -> Dict:
    x = min(a['x'], b['x']); y = min(a['y'], b['y'])
    x1 = max(a['x'] + a['w'], b['x'] + b['w']); y1 = max(a['y'] + a['h'], b['y'] + b['h'])
    return {'x': x, 'y': y, 'w': max(0.0, x1 - x), 'h': max(0.0, y1 - y)}


def _normalized_words_from_pdf(pdf_path: Path, page: int) -> List[Dict]:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        try:
            p = doc[page]
            rect = p.rect
            pw, ph = float(rect.width), float(rect.height)
            words = p.get_text('words') or []
            out = []
            for w in words:
                if len(w) < 5:
                    continue
                x0, y0, x1, y1, txt = float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4] or '')
                if not txt:
                    continue
                out.append({
                    'x': max(0.0, min(1.0, x0 / pw)),
                    'y': max(0.0, min(1.0, y0 / ph)),
                    'w': max(0.0, min(1.0, (x1 - x0) / pw)),
                    'h': max(0.0, min(1.0, (y1 - y0) / ph)),
                    'text': txt
                })
            return out
        finally:
            doc.close()
    except Exception:
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                p = pdf.pages[page]
                pw, ph = float(p.width), float(p.height)
                words = p.extract_words() or []
                out = []
                for w in words:
                    x0 = float(w.get('x0', 0)); y0 = float(w.get('top', 0)); x1 = float(w.get('x1', 0)); y1 = float(w.get('bottom', y0))
                    txt = str(w.get('text', '') or '')
                    if not txt:
                        continue
                    out.append({
                        'x': max(0.0, min(1.0, x0 / pw)), 'y': max(0.0, min(1.0, y0 / ph)),
                        'w': max(0.0, min(1.0, (x1 - x0) / pw)), 'h': max(0.0, min(1.0, (y1 - y0) / ph)),
                        'text': txt
                    })
                return out
        except Exception:
            return []


def _text_in_bbox(words_norm: List[Dict], bb: Dict) -> str:
    res = []
    for w in words_norm:
        if _overlaps(bb, {'x': w['x'], 'y': w['y'], 'w': w['w'], 'h': w['h']}):
            res.append(w['text'])
    # Rough ordering is fine; words are already page-order
    return ' '.join(res).strip()


def _load_boxes_from_detailed(run_id: int, doc: str) -> Dict[int, Dict[str, List[Dict]]]:
    run = get_run(run_id)
    art = run.get('artifacts') or {}
    details_path = art.get('details')
    result: Dict[int, Dict[str, List[Dict]]] = {}
    if not details_path or not Path(details_path).exists():
        return result
    try:
        results = json.loads(Path(details_path).read_text(encoding='utf-8'))
        for r in results:
            conv = r.get('converter_name')
            fp = r.get('file_path') or ''
            base = os.path.splitext(os.path.basename(fp))[0]
            if base != doc:
                continue
            meta = r.get('metadata') or {}
            bpp = meta.get('blocks_per_page') or {}
            for k, v in bpp.items():
                try:
                    pidx = int(k)
                except Exception:
                    continue
                lst = result.setdefault(pidx, {}).setdefault(conv, [])
                for i, b in enumerate(v):
                    x0 = float(b.get('x0', 0.0)); y0 = float(b.get('y0', 0.0))
                    x1 = float(b.get('x1', 0.0)); y1 = float(b.get('y1', 0.0))
                    lst.append({
                        'id': f"{conv}-p{pidx}-i{i}",
                        'page': pidx,
                        'tool': conv,
                        'type': 'block',
                        'bbox': {'x': x0, 'y': y0, 'w': max(0.0, x1-x0), 'h': max(0.0, y1-y0)},
                        'text': b.get('text', '')
                    })
    except Exception:
        return {}
    return result


@app.get("/api/runs/{run_id}/doc/{doc}/page/{page}/bboxes")
def api_bboxes(run_id: int, doc: str, page: int, tools: Optional[str] = None, withText: int = 1, withIds: int = 1):
    doc_dir = _doc_dir_for(run_id, doc)
    boxes_by_engine = _load_boxes_by_engine(doc_dir)
    if boxes_by_engine is None:
        boxes_by_engine = _load_boxes_from_detailed(run_id, doc)
    if boxes_by_engine is None:
        raise HTTPException(status_code=404, detail="No boxes available")
    page_data = boxes_by_engine.get(str(page)) or boxes_by_engine.get(page) or {}
    if tools:
        keep = set([t for t in tools.split(',') if t])
        page_data = {k: v for k, v in page_data.items() if k in keep}
    # Optionally strip text/ids
    if not withText:
        for lst in page_data.values():
            for b in lst:
                b.pop('text', None)
    if not withIds:
        for lst in page_data.values():
            for b in lst:
                b.pop('id', None)
    return { 'page': page, 'tools': list(page_data.keys()), 'boxes': page_data }


@app.get("/api/runs/{run_id}/doc/{doc}/page/{page}/table_bboxes")
def api_table_bboxes(run_id: int, doc: str, page: int):
    pdf_path = _find_pdf_for_doc(run_id, doc)
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Source PDF not found for document")
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            if page < 0 or page >= len(pdf.pages):
                raise HTTPException(status_code=400, detail="Invalid page index")
            p = pdf.pages[page]
            w, h = float(p.width), float(p.height)
            # Try find_tables (preferred for geometry), fallback to extract_tables (no geometry)
            bboxes = []
            try:
                tables = p.find_tables() or []
                for i, t in enumerate(tables):
                    # t.bbox: (x0, top, x1, bottom)
                    try:
                        x0, top, x1, bottom = [float(v) for v in t.bbox]
                        nx = max(0.0, min(1.0, x0 / w)); ny = max(0.0, min(1.0, top / h))
                        nw = max(0.0, min(1.0, (x1 - x0) / w)); nh = max(0.0, min(1.0, (bottom - top) / h))
                        bboxes.append({ 'id': f'table-p{page}-i{i}', 'bbox': { 'x': nx, 'y': ny, 'w': nw, 'h': nh } })
                    except Exception:
                        continue
            except Exception:
                pass
            return { 'page': page, 'tables': bboxes }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect tables: {e}")


@app.get("/api/runs/{run_id}/doc/{doc}/page/{page}/tables")
def api_tables(run_id: int, doc: str, page: int, tool: Optional[str] = None):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    art = run.get('artifacts') or {}
    details_path = art.get('details')
    out: Dict[str, List[Dict]] = {}
    if details_path and Path(details_path).exists():
        try:
            results = json.loads(Path(details_path).read_text(encoding='utf-8'))
            for r in results:
                conv = r.get('converter_name')
                if tool and conv != tool:
                    continue
                fp = r.get('file_path') or ''
                if Path(fp).stem != doc:
                    continue
                meta = r.get('metadata') or {}
                tpp = meta.get('tables_per_page') or {}
                tables = tpp.get(str(page)) or tpp.get(page)
                if tables:
                    out[conv] = tables
        except Exception:
            pass
    return { 'page': page, 'tables': out }


@app.post("/api/runs/{run_id}/doc/{doc}/state")
async def api_save_state(run_id: int, doc: str, request: Request):
    payload = await request.json()
    run_dir = RESULTS_DIR / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    f = run_dir / f"ui_state_{doc}.json"
    try:
        f.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save state: {e}")
    return { 'ok': True, 'path': str(f) }


@app.post("/api/runs/{run_id}/doc/{doc}/export")
async def api_export(run_id: int, doc: str, request: Request):
    # Basic export: package images, overlays (SVG), boxes JSON, and manifest
    doc_dir = _doc_dir_for(run_id, doc)
    payload = await request.json() if request.headers.get('content-type','').startswith('application/json') else {}
    export_dir = RESULTS_DIR / f"run_{run_id}" / 'exports'
    export_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    zip_path = export_dir / f"{doc}_{ts}.zip"

    # Create simple SVG overlays from boxes_by_engine
    boxes_by_engine = _load_boxes_by_engine(doc_dir)
    if boxes_by_engine is None:
        boxes_by_engine = _load_boxes_from_detailed(run_id, doc)

    import io
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        # Add page images
        for img in sorted(doc_dir.glob('page_*.png')):
            z.write(img, arcname=f"images/{img.name}")
        # Add composites if present
        for cdir in [doc_dir] + [d for d in doc_dir.iterdir() if d.is_dir()]:
            for comp in cdir.glob('page_*_composite.png'):
                z.write(comp, arcname=f"images/{comp.name}")
        # Add JSON
        if boxes_by_engine:
            data = json.dumps(boxes_by_engine, indent=2).encode('utf-8')
            z.writestr('boxes_by_engine.json', data)

        # Tables JSON and summary CSV
        try:
            tables_by_tool: Dict[str, Dict[str, List[Dict]]] = {}
            art = get_run(run_id).get('artifacts') or {}
            details_path = art.get('details')
            if details_path and Path(details_path).exists():
                results = json.loads(Path(details_path).read_text(encoding='utf-8'))
                for r in results:
                    fp = r.get('file_path') or ''
                    if Path(fp).stem != doc:
                        continue
                    conv = r.get('converter_name')
                    meta = r.get('metadata') or {}
                    tpp = meta.get('tables_per_page') or {}
                    if tpp:
                        tables_by_tool[conv] = { str(k): v for k, v in tpp.items() }
            if tables_by_tool:
                z.writestr('tables.json', json.dumps(tables_by_tool, indent=2))
                # summary CSV: counts per page/tool
                import csv
                tbuf = io.StringIO(); tw = csv.writer(tbuf)
                tw.writerow(['page','tool','table_count'])
                pages = set()
                for tool, per_page in tables_by_tool.items():
                    for pk, lst in per_page.items():
                        pages.add(int(pk))
                for pidx in sorted(pages):
                    for tool, per_page in tables_by_tool.items():
                        cnt = len(per_page.get(str(pidx), []) or [])
                        tw.writerow([pidx, tool, cnt])
                z.writestr('tables_summary.csv', tbuf.getvalue())
        except Exception:
            pass
        
        # Generate merged overlay SVGs for each mode and page
        def do_merge(mode: str, page_idx: int):
            entry = boxes_by_engine.get(str(page_idx)) or boxes_by_engine.get(page_idx) or {}
            # flatten
            boxes = []
            for t, lst in entry.items():
                for b in lst:
                    bb = b.get('bbox') or {}
                    boxes.append({'id': b.get('id'), 'tool': t, 'bbox': {'x': float(bb.get('x',0)), 'y': float(bb.get('y',0)), 'w': float(bb.get('w',0)), 'h': float(bb.get('h',0))}})
            def union(a,b):
                x=min(a['x'],b['x']); y=min(a['y'],b['y'])
                x1=max(a['x']+a['w'], b['x']+b['w']); y1=max(a['y']+a['h'], b['y']+b['h'])
                return {'x':x, 'y':y, 'w':max(0.0,x1-x), 'h':max(0.0,y1-y)}
            def overlap_x(a,b):
                ax1=a['x']+a['w']; bx1=b['x']+b['w']
                return max(0.0, min(ax1,bx1)-max(a['x'],b['x']))
            def overlap_y(a,b):
                ay1=a['y']+a['h']; by1=b['y']+b['h']
                return max(0.0, min(ay1,by1)-max(a['y'],b['y']))
            groups = []
            used = [False]*len(boxes)
            if mode == 'vertical':
                order = sorted(range(len(boxes)), key=lambda i:(boxes[i]['bbox']['y'], boxes[i]['bbox']['x']))
                gap_thr = 0.02
                for idx in order:
                    if used[idx]: continue
                    used[idx]=True
                    g_ids=[boxes[idx]['id']]; g_bbox=boxes[idx]['bbox']
                    changed=True
                    while changed:
                        changed=False
                        for j in range(len(boxes)):
                            if used[j]: continue
                            b = boxes[j]['bbox']
                            if overlap_x(g_bbox, b) > 0 and (b['y'] <= g_bbox['y']+g_bbox['h']+gap_thr and g_bbox['y'] <= b['y']+b['h']+gap_thr):
                                used[j]=True; g_ids.append(boxes[j]['id']); g_bbox = union(g_bbox, b); changed=True
                    groups.append({'bbox': g_bbox})
            elif mode == 'horizontal':
                order = sorted(range(len(boxes)), key=lambda i:(boxes[i]['bbox']['x'], boxes[i]['bbox']['y']))
                gap_thr = 0.02
                for idx in order:
                    if used[idx]: continue
                    used[idx]=True
                    g_bbox=boxes[idx]['bbox']
                    changed=True
                    while changed:
                        changed=False
                        for j in range(len(boxes)):
                            if used[j]: continue
                            b = boxes[j]['bbox']
                            if overlap_y(g_bbox, b) > 0 and (b['x'] <= g_bbox['x']+g_bbox['w']+gap_thr and g_bbox['x'] <= b['x']+b['w']+gap_thr):
                                used[j]=True; g_bbox = union(g_bbox, b); changed=True
                    groups.append({'bbox': g_bbox})
            else:
                def iou(bb_a, bb_b):
                    ax1=bb_a['x']+bb_a['w']; ay1=bb_a['y']+bb_a['h']
                    bx1=bb_b['x']+bb_b['w']; by1=bb_b['y']+bb_b['h']
                    iw=max(0.0, min(ax1,bx1)-max(bb_a['x'],bb_b['x']))
                    ih=max(0.0, min(ay1,by1)-max(bb_a['y'],bb_b['y']))
                    inter=iw*ih
                    if inter<=0: return 0.0
                    ua=bb_a['w']*bb_a['h']+bb_b['w']*bb_b['h']-inter
                    return inter/ua if ua>0 else 0.0
                prox = 0.03
                for i in range(len(boxes)):
                    if used[i]: continue
                    used[i]=True
                    g_bbox=boxes[i]['bbox']
                    queue=[i]
                    while queue:
                        u=queue.pop(0)
                        for v in range(len(boxes)):
                            if used[v]: continue
                            if iou(boxes[u]['bbox'], boxes[v]['bbox'])>0:
                                used[v]=True; queue.append(v); g_bbox = union(g_bbox, boxes[v]['bbox']); continue
                            cx = boxes[u]['bbox']['x']+boxes[u]['bbox']['w']/2
                            cy = boxes[u]['bbox']['y']+boxes[u]['bbox']['h']/2
                            dx = boxes[v]['bbox']['x']+boxes[v]['bbox']['w']/2
                            dy = boxes[v]['bbox']['y']+boxes[v]['bbox']['h']/2
                            if abs(cx-dx) <= prox or abs(cy-dy) <= prox:
                                used[v]=True; queue.append(v); g_bbox = union(g_bbox, boxes[v]['bbox'])
                    groups.append({'bbox': g_bbox})
            return groups

        # produce SVG overlays
        try:
            from PIL import Image
            # map page index -> (width, height)
            page_sizes = {}
            for imgp in sorted(doc_dir.glob('page_*.png')):
                stem = imgp.stem  # page_000
                try:
                    pidx = int(stem.split('_')[-1])
                except Exception:
                    continue
                with Image.open(imgp) as im:
                    page_sizes[pidx] = (im.width, im.height)
            for mode in ('vertical','horizontal','paragraph'):
                for pidx, (w,h) in page_sizes.items():
                    groups = do_merge(mode, pidx)
                    # build svg
                    svg_lines = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"]
                    color = '#FFA500'
                    for i, g in enumerate(groups):
                        bb = g['bbox']; x=int(bb['x']*w); y=int(bb['y']*h); ww=int(bb['w']*w); hh=int(bb['h']*h)
                        svg_lines.append(f"<rect x='{x}' y='{y}' width='{ww}' height='{hh}' fill='none' stroke='{color}' stroke-width='2' />")
                        cx = x+12; cy = y+12
                        svg_lines.append(f"<circle cx='{cx}' cy='{cy}' r='9' fill='{color}' stroke='#fff' stroke-width='1.2' />")
                        svg_lines.append(f"<text x='{cx}' y='{cy}' fill='#000' font-size='11' font-weight='600' text-anchor='middle' dominant-baseline='middle'>{i+1}</text>")
                    svg_lines.append("</svg>")
                    z.writestr(f"overlays/merged/{mode}/page_{pidx:03d}.svg", "\n".join(svg_lines))
        except Exception:
            pass
        # Summary CSV (counts per page/tool)
        try:
            import csv
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['page','tool','count'])
            # boxes_by_engine keys may be str/int
            for pk in sorted(boxes_by_engine.keys(), key=lambda x: int(x)):
                entry = boxes_by_engine[pk]
                for tool, lst in entry.items():
                    w.writerow([pk, tool, len(lst)])
            z.writestr('summary.csv', buf.getvalue())
        except Exception:
            pass
        # Overlap analysis CSV
        try:
            import csv
            def iou(bb_a, bb_b):
                ax1=bb_a['x']+bb_a['w']; ay1=bb_a['y']+bb_a['h']
                bx1=bb_b['x']+bb_b['w']; by1=bb_b['y']+bb_b['h']
                iw=max(0.0, min(ax1,bx1)-max(bb_a['x'],bb_b['x']))
                ih=max(0.0, min(ay1,by1)-max(bb_a['y'],bb_b['y']))
                inter=iw*ih
                if inter<=0: return 0.0
                ua=bb_a['w']*bb_a['h']+bb_b['w']*bb_b['h']-inter
                return inter/ua if ua>0 else 0.0
            obuf = io.StringIO(); ow = csv.writer(obuf)
            ow.writerow(['page','tool_a','tool_b','count_a','count_b','overlaps_a_to_b','avg_max_iou_a_to_b','overlaps_b_to_a','avg_max_iou_b_to_a'])
            for pk in sorted(boxes_by_engine.keys(), key=lambda x:int(x)):
                entry = boxes_by_engine[pk]
                tools_list = sorted(entry.keys())
                for i in range(len(tools_list)):
                    for j in range(i+1, len(tools_list)):
                        ta, tb = tools_list[i], tools_list[j]
                        A = entry.get(ta, []); B = entry.get(tb, [])
                        max_a=[]; overlaps_a=0
                        for a in A:
                            bb_a = a.get('bbox') or {}
                            best=0.0
                            for b in B:
                                bb_b=b.get('bbox') or {}
                                v=iou(bb_a, bb_b)
                                if v>best: best=v
                            if best>0: overlaps_a+=1
                            max_a.append(best)
                        avg_a = sum(max_a)/len(max_a) if max_a else 0.0
                        max_b=[]; overlaps_b=0
                        for b in B:
                            bb_b=b.get('bbox') or {}
                            best=0.0
                            for a in A:
                                bb_a=a.get('bbox') or {}
                                v=iou(bb_b, bb_a)
                                if v>best: best=v
                            if best>0: overlaps_b+=1
                            max_b.append(best)
                        avg_b = sum(max_b)/len(max_b) if max_b else 0.0
                        ow.writerow([pk, ta, tb, len(A), len(B), overlaps_a, f"{avg_a:.4f}", overlaps_b, f"{avg_b:.4f}"])
            z.writestr('overlaps.csv', obuf.getvalue())
        except Exception:
            pass
        # Textual comparison CSV
        try:
            import csv, re
            run = get_run(run_id)
            art = run.get('artifacts') or {}
            details_path = art.get('details')
            texts = {}
            if details_path and Path(details_path).exists():
                results = json.loads(Path(details_path).read_text(encoding='utf-8'))
                for r in results:
                    fp = r.get('file_path') or ''
                    if Path(fp).stem != doc:
                        continue
                    name = r.get('converter_name')
                    texts[name] = r.get('text_content') or r.get('text') or ''
            names = sorted(texts.keys())
            def sim(a,b):
                try:
                    from difflib import SequenceMatcher
                    return SequenceMatcher(None, a, b).ratio()
                except Exception:
                    return 0.0
            tbuf = io.StringIO(); tw = csv.writer(tbuf)
            tw.writerow(['converter_a','converter_b','similarity','char_diff','word_diff'])
            for i in range(len(names)):
                for j in range(i+1, len(names)):
                    na, nb = names[i], names[j]
                    ta, tb = texts[na], texts[nb]
                    s = sim(ta, tb)
                    char_diff = abs(len(ta)-len(tb))
                    wa = len(re.findall(r'\w+', ta)); wb = len(re.findall(r'\w+', tb))
                    tw.writerow([na, nb, f"{s:.4f}", char_diff, abs(wa-wb)])
            z.writestr('text_compare.csv', tbuf.getvalue())
        except Exception:
            pass
        # Manifest
        manifest = {
            'run_id': run_id,
            'doc': doc,
            'generated_at': ts,
            'artifacts': {
                'images_dir': 'images/',
                'boxes_json': 'boxes_by_engine.json',
                'summary_csv': 'summary.csv',
                'overlaps_csv': 'overlaps.csv',
                'text_compare_csv': 'text_compare.csv',
                'tables_json': 'tables.json',
                'tables_summary_csv': 'tables_summary.csv',
                'overlays_dir': 'overlays/merged/'
            }
        }
        z.writestr('manifest.json', json.dumps(manifest, indent=2))
    return FileResponse(str(zip_path), filename=zip_path.name)


@app.post("/api/runs/{run_id}/doc/{doc}/page/{page}/text_for_boxes")
async def api_text_for_boxes(run_id: int, doc: str, page: int, request: Request):
    payload = await request.json()
    boxes = payload.get('boxes') or []  # list of {x,y,w,h} normalized
    if not isinstance(boxes, list) or not boxes:
        return { 'page': page, 'text': '' }
    pdf_path = _find_pdf_for_doc(run_id, doc)
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Source PDF not found for document")
    # Try PyMuPDF first
    text_out = ''
    try:
        import fitz  # PyMuPDF
        doc_f = fitz.open(str(pdf_path))
        try:
            if page < 0 or page >= doc_f.page_count:
                raise HTTPException(status_code=400, detail="Invalid page index")
            p = doc_f[page]
            words = p.get_text('words') or []  # list of tuples (x0,y0,x1,y1,word,block,line,wordno)
            # Page size
            rect = p.rect
            pw, ph = float(rect.width), float(rect.height)
            norm_words = []
            for w in words:
                if len(w) < 5:
                    continue
                x0, y0, x1, y1, word = float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4])
                if not word:
                    continue
                nx = max(0.0, min(1.0, x0 / pw)); ny = max(0.0, min(1.0, y0 / ph))
                nw = max(0.0, min(1.0, (x1 - x0) / pw)); nh = max(0.0, min(1.0, (y1 - y0) / ph))
                norm_words.append((nx, ny, nw, nh, word, int(w[6]) if len(w) > 6 else 0, int(w[7]) if len(w) > 7 else 0))
            def intersects(a, b):
                ax1=a[0]+a[2]; ay1=a[1]+a[3]; bx1=b[0]+b[2]; by1=b[1]+b[3]
                iw=max(0.0, min(ax1,bx1)-max(a[0],b[0])); ih=max(0.0, min(ay1,by1)-max(a[1],b[1]));
                return iw*ih > 0
            collected = []
            for bx in boxes:
                try:
                    bb = (float(bx.get('x',0)), float(bx.get('y',0)), float(bx.get('w',0)), float(bx.get('h',0)))
                except Exception:
                    continue
                # add words that intersect this box
                for (x,y,w,h,word,ln,wn) in norm_words:
                    if intersects((x,y,w,h), bb):
                        collected.append((ln, wn, y, x, word))
            # sort by line, then word number, then by y then x
            collected.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
            # simple line break heuristic by y diff
            out_lines = []
            cur_y = None
            cur = []
            for (_,_,y,_,word) in collected:
                if cur_y is None:
                    cur_y = y
                if cur_y is not None and abs(y - cur_y) > 0.01:
                    out_lines.append(' '.join(cur)); cur = []; cur_y = y
                cur.append(word)
            if cur:
                out_lines.append(' '.join(cur))
            text_out = '\n'.join(out_lines)
        finally:
            doc_f.close()
    except Exception:
        # Fallback to pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                if page < 0 or page >= len(pdf.pages):
                    raise HTTPException(status_code=400, detail="Invalid page index")
                p = pdf.pages[page]
                words = p.extract_words() or []
                pw, ph = p.width, p.height
                norm_words = []
                for w in words:
                    try:
                        x0 = float(w.get('x0', 0)); y0=float(w.get('top',0)); x1=float(w.get('x1',0)); y1=float(w.get('bottom', y0))
                        word = str(w.get('text','') or '')
                        if not word:
                            continue
                        nx = max(0.0, min(1.0, x0/pw)); ny = max(0.0, min(1.0, y0/ph))
                        nw = max(0.0, min(1.0, (x1-x0)/pw)); nh = max(0.0, min(1.0, (y1-y0)/ph))
                        norm_words.append((nx, ny, nw, nh, word))
                    except Exception:
                        continue
                def intersects(a,b):
                    ax1=a[0]+a[2]; ay1=a[1]+a[3]; bx1=b[0]+b[2]; by1=b[1]+b[3]
                    iw=max(0.0, min(ax1,bx1)-max(a[0],b[0])); ih=max(0.0, min(ay1,by1)-max(a[1],b[1]));
                    return iw*ih > 0
                collected = []
                for bx in boxes:
                    try:
                        bb = (float(bx.get('x',0)), float(bx.get('y',0)), float(bx.get('w',0)), float(bx.get('h',0)))
                    except Exception:
                        continue
                    for (x,y,w,h,word) in norm_words:
                        if intersects((x,y,w,h), bb):
                            collected.append((y,x,word))
                collected.sort(key=lambda t:(t[0], t[1]))
                # join words by line proximity
                out_lines=[]; cur=[]; cur_y=None
                for (y,x,word) in collected:
                    if cur_y is None:
                        cur_y = y
                    if abs(y-cur_y) > 0.01:
                        out_lines.append(' '.join(cur)); cur=[]; cur_y=y
                    cur.append(word)
                if cur:
                    out_lines.append(' '.join(cur))
                text_out='\n'.join(out_lines)
        except Exception:
            text_out = ''
    return { 'page': page, 'text': text_out }


@app.post("/api/runs/{run_id}/doc/{doc}/page/{page}/merge")
async def api_merge_boxes(run_id: int, doc: str, page: int, request: Request):
    payload = await request.json()
    mode = (payload.get('mode') or 'vertical').lower()
    tools = payload.get('tools') or []
    doc_dir = _doc_dir_for(run_id, doc)
    boxes_by_engine = _load_boxes_by_engine(doc_dir)
    if boxes_by_engine is None:
        boxes_by_engine = _load_boxes_from_detailed(run_id, doc)
    page_data = boxes_by_engine.get(str(page)) or boxes_by_engine.get(page) or {}
    selected_tools = tools or list(page_data.keys())
    boxes = []
    for t in selected_tools:
        for b in page_data.get(t, []):
            bb = b.get('bbox') or {}
            boxes.append({'id': b.get('id'), 'tool': t, 'bbox': {'x': float(bb.get('x',0)), 'y': float(bb.get('y',0)), 'w': float(bb.get('w',0)), 'h': float(bb.get('h',0))}})
    def union(a,b):
        x=min(a['x'],b['x']); y=min(a['y'],b['y'])
        x1=max(a['x']+a['w'], b['x']+b['w']); y1=max(a['y']+a['h'], b['y']+b['h'])
        return {'x':x, 'y':y, 'w':max(0.0,x1-x), 'h':max(0.0,y1-y)}
    def overlap_x(a,b):
        ax1=a['x']+a['w']; bx1=b['x']+b['w']
        return max(0.0, min(ax1,bx1)-max(a['x'],b['x']))
    def overlap_y(a,b):
        ay1=a['y']+a['h']; by1=b['y']+b['h']
        return max(0.0, min(ay1,by1)-max(a['y'],b['y']))
    groups = []
    if not boxes:
        return {'mode': mode, 'groups': []}
    used = [False]*len(boxes)
    if mode == 'vertical':
        order = sorted(range(len(boxes)), key=lambda i:(boxes[i]['bbox']['y'], boxes[i]['bbox']['x']))
        gap_thr = 0.02
        for idx in order:
            if used[idx]: continue
            used[idx]=True
            g_ids=[boxes[idx]['id']]; g_bbox=boxes[idx]['bbox']
            changed=True
            while changed:
                changed=False
                for j in range(len(boxes)):
                    if used[j]: continue
                    b = boxes[j]['bbox']
                    if overlap_x(g_bbox, b) > 0 and (b['y'] <= g_bbox['y']+g_bbox['h']+gap_thr and g_bbox['y'] <= b['y']+b['h']+gap_thr):
                        used[j]=True; g_ids.append(boxes[j]['id']); g_bbox = union(g_bbox, b); changed=True
            groups.append({'id': f"merged-p{page}-m{len(groups)+1}", 'tool':'merged', 'bbox': g_bbox, 'members': g_ids})
    elif mode == 'horizontal':
        order = sorted(range(len(boxes)), key=lambda i:(boxes[i]['bbox']['x'], boxes[i]['bbox']['y']))
        gap_thr = 0.02
        for idx in order:
            if used[idx]: continue
            used[idx]=True
            g_ids=[boxes[idx]['id']]; g_bbox=boxes[idx]['bbox']
            changed=True
            while changed:
                changed=False
                for j in range(len(boxes)):
                    if used[j]: continue
                    b = boxes[j]['bbox']
                    if overlap_y(g_bbox, b) > 0 and (b['x'] <= g_bbox['x']+g_bbox['w']+gap_thr and g_bbox['x'] <= b['x']+b['w']+gap_thr):
                        used[j]=True; g_ids.append(boxes[j]['id']); g_bbox = union(g_bbox, b); changed=True
            groups.append({'id': f"merged-p{page}-m{len(groups)+1}", 'tool':'merged', 'bbox': g_bbox, 'members': g_ids})
    else:
        import math
        def iou(bb_a, bb_b):
            ax1=bb_a['x']+bb_a['w']; ay1=bb_a['y']+bb_a['h']
            bx1=bb_b['x']+bb_b['w']; by1=bb_b['y']+bb_b['h']
            iw=max(0.0, min(ax1,bx1)-max(bb_a['x'],bb_b['x']))
            ih=max(0.0, min(ay1,by1)-max(bb_a['y'],bb_b['y']))
            inter=iw*ih
            if inter<=0: return 0.0
            ua=bb_a['w']*bb_a['h']+bb_b['w']*bb_b['h']-inter
            return inter/ua if ua>0 else 0.0
        prox = 0.03
        for i in range(len(boxes)):
            if used[i]: continue
            used[i]=True
            queue=[i]; g_ids=[boxes[i]['id']]; g_bbox=boxes[i]['bbox']
            while queue:
                u = queue.pop(0)
                for v in range(len(boxes)):
                    if used[v]: continue
                    if iou(boxes[u]['bbox'], boxes[v]['bbox'])>0:
                        used[v]=True; queue.append(v); g_ids.append(boxes[v]['id']); g_bbox = union(g_bbox, boxes[v]['bbox'])
                        continue
                    cx = boxes[u]['bbox']['x']+boxes[u]['bbox']['w']/2
                    cy = boxes[u]['bbox']['y']+boxes[u]['bbox']['h']/2
                    dx = boxes[v]['bbox']['x']+boxes[v]['bbox']['w']/2
                    dy = boxes[v]['bbox']['y']+boxes[v]['bbox']['h']/2
                    if abs(cx-dx) <= prox or abs(cy-dy) <= prox:
                        used[v]=True; queue.append(v); g_ids.append(boxes[v]['id']); g_bbox = union(g_bbox, boxes[v]['bbox'])
            groups.append({'id': f"merged-p{page}-m{len(groups)+1}", 'tool':'merged', 'bbox': g_bbox, 'members': g_ids})
    for g in groups:
        bb = g['bbox']
        bb['x']=max(0.0,min(1.0,bb['x'])); bb['y']=max(0.0,min(1.0,bb['y']))
        bb['w']=max(0.0,min(1.0,bb['w'])); bb['h']=max(0.0,min(1.0,bb['h']))
    return {'mode': mode, 'groups': groups}


@app.post("/api/runs/{run_id}/doc/{doc}/page/{page}/consolidate")
async def api_consolidate(run_id: int, doc: str, page: int, tool: str = Query(...), strategy: str = Query("overlap")):
    doc_dir = _doc_dir_for(run_id, doc)
    boxes_by_engine = _load_boxes_by_engine(doc_dir)
    if boxes_by_engine is None:
        boxes_by_engine = _load_boxes_from_detailed(run_id, doc)
    page_data = boxes_by_engine.get(str(page)) or boxes_by_engine.get(page) or {}
    items = list(page_data.get(tool, []))
    # Words for text coverage
    pdf_path = _find_pdf_for_doc(run_id, doc)
    words = _normalized_words_from_pdf(pdf_path, page) if pdf_path else []
    # Build structures
    bboxes = []
    for b in items:
        bb = b.get('bbox') or {}
        entry = {
            'id': b.get('id'),
            'bbox': {'x': float(bb.get('x', 0)), 'y': float(bb.get('y', 0)), 'w': float(bb.get('w', 0)), 'h': float(bb.get('h', 0))},
            'text': _text_in_bbox(words, {'x': float(bb.get('x', 0)), 'y': float(bb.get('y', 0)), 'w': float(bb.get('w', 0)), 'h': float(bb.get('h', 0))}),
            'redundant': False,
            'unique_extra': False,
            'merged_group': None
        }
        bboxes.append(entry)
    # Containment and redundancy / unique-extra
    for i in range(len(bboxes)):
        for j in range(len(bboxes)):
            if i == j:
                continue
            A = bboxes[i]; B = bboxes[j]
            if _contains(A['bbox'], B['bbox']):
                # Compute inner text union for A
                # Check if A has extra text beyond B
                txtA = set(A['text'].split()) if A['text'] else set()
                txtB = set(B['text'].split()) if B['text'] else set()
                extra = txtA - txtB
                if extra:
                    A['unique_extra'] = True
                else:
                    A['redundant'] = True
    # Grouping per strategy
    groups = []
    n = len(bboxes)
    centers = [(bb['bbox']['x'] + bb['bbox']['w']/2.0, bb['bbox']['y'] + bb['bbox']['h']/2.0) for bb in bboxes]
    def build_groups_by_edges(edge_fn):
        visited = [False]*n
        out = []
        for i in range(n):
            if visited[i]:
                continue
            visited[i] = True
            comp = [i]
            queue = [i]
            gbb = dict(bboxes[i]['bbox'])
            while queue:
                u = queue.pop(0)
                for v in range(n):
                    if visited[v]:
                        continue
                    if edge_fn(u, v):
                        visited[v] = True
                        comp.append(v)
                        gbb = _union(gbb, bboxes[v]['bbox'])
                        queue.append(v)
            if len(comp) > 1:
                gid = f"merged-p{page}-g{len(out)+1}"
                for m in comp:
                    bboxes[m]['merged_group'] = gid
                out.append({'id': gid, 'bbox': gbb, 'members': [bboxes[m]['id'] for m in comp]})
        return out

    center_tol = 0.02
    gap_tol = 0.03
    x_overlap_frac = 0.3

    if strategy == 'overlap':
        def edge(u, v):
            return _overlaps(bboxes[u]['bbox'], bboxes[v]['bbox'])
        groups = build_groups_by_edges(edge)
    elif strategy == 'vertical_centers':
        def edge(u, v):
            cxu, cyu = centers[u]; cxv, cyv = centers[v]
            if abs(cxu - cxv) <= center_tol:
                # reasonable vertical separation
                return True
            return False
        groups = build_groups_by_edges(edge)
    elif strategy == 'paragraph':
        def x_overlap_ratio(a, b):
            ax0=a['x']; ax1=a['x']+a['w']; bx0=b['x']; bx1=b['x']+b['w']
            inter = max(0.0, min(ax1, bx1) - max(ax0, bx0))
            return inter / max(1e-6, min(a['w'], b['w']))
        def edge(u, v):
            au = bboxes[u]['bbox']; av = bboxes[v]['bbox']
            # close vertically, some horizontal overlap
            if abs(au['y'] - av['y']) <= gap_tol or abs((au['y']+au['h']) - (av['y']+av['h'])) <= gap_tol:
                return x_overlap_ratio(au, av) >= x_overlap_frac
            # also allow chaining by small vertical gaps
            ty = min(au['y']+au['h'], av['y']+av['h']) - max(au['y'], av['y'])
            if ty >= 0 and x_overlap_ratio(au, av) >= x_overlap_frac:
                return True
            return False
        groups = build_groups_by_edges(edge)
    else:
        groups = []

    # Classify groups into paragraph/row/column (heuristic)
    layout_groups = []
    def classify(member_indices: List[int]) -> str:
        xs = []; ys = []; widths = []; heights = []
        for m in member_indices:
            bb = bboxes[m]['bbox']
            xs.append(bb['x']); ys.append(bb['y']); widths.append(bb['w']); heights.append(bb['h'])
        import statistics
        try:
            std_x = statistics.pstdev(xs)
            std_y = statistics.pstdev(ys)
        except statistics.StatisticsError:
            std_x = std_y = 0.0
        if std_x < 0.01 and std_y > 0.02:
            return 'column'
        if std_y < 0.005 and std_x > 0.02:
            return 'row'
        return 'paragraph'
    for g in groups:
        # Map member ids back to indices
        idxs = [next((i for i, b in enumerate(bboxes) if b['id'] == mid), -1) for mid in g['members']]
        idxs = [i for i in idxs if i >= 0]
        if strategy == 'vertical_centers':
            ltype = 'column'
        elif strategy == 'paragraph':
            ltype = 'paragraph'
        else:
            ltype = classify(idxs)
        layout_groups.append({'type': ltype, 'bbox': g['bbox'], 'members': g['members']})

    # Persist consolidated annotations next to doc_dir
    cons_path = doc_dir / f"consolidated_{tool}.json"
    try:
        cons_all = {}
        if cons_path.exists():
            try:
                cons_all = json.loads(cons_path.read_text(encoding='utf-8'))
            except Exception:
                cons_all = {}
        page_entry = cons_all.get(str(page), {})
        page_entry[strategy] = {
            'boxes': bboxes,
            'merged_groups': groups,
            'layout_groups': layout_groups
        }
        cons_all[str(page)] = page_entry
        cons_path.write_text(json.dumps(cons_all, indent=2), encoding='utf-8')
    except Exception:
        pass
    return {
        'page': page,
        'tool': tool,
        'strategy': strategy,
        'boxes': bboxes,
        'merged_groups': groups,
        'layout_groups': layout_groups
    }


@app.get("/api/runs/{run_id}/doc/{doc}/page/{page}/consolidated")
def api_get_consolidated(run_id: int, doc: str, page: int, tool: str, strategy: str = Query("overlap")):
    doc_dir = _doc_dir_for(run_id, doc)
    cons_path = doc_dir / f"consolidated_{tool}.json"
    if cons_path.exists():
        try:
            data = json.loads(cons_path.read_text(encoding='utf-8'))
            page_entry = data.get(str(page)) or {}
            return page_entry.get(strategy) or {'boxes': [], 'merged_groups': [], 'layout_groups': []}
        except Exception:
            pass
    return {'boxes': [], 'merged_groups': [], 'layout_groups': []}


@app.get("/api/runs/{run_id}/doc/{doc}/page/{page}/words")
def api_words(run_id: int, doc: str, page: int, tool: Optional[str] = None):
    run = get_run(run_id)
    art = run.get('artifacts') or {}
    details_path = art.get('details')
    if not details_path or not Path(details_path).exists():
        return { 'page': page, 'words': {} }
    try:
        results = json.loads(Path(details_path).read_text(encoding='utf-8'))
        out = {}
        for r in results:
            conv = r.get('converter_name')
            if tool and conv != tool: continue
            fp = r.get('file_path') or ''
            if Path(fp).stem != doc: continue
            meta = r.get('metadata') or {}
            wpp = meta.get('words_per_page') or {}
            words = wpp.get(str(page)) or wpp.get(page)
            if words:
                out[conv] = words
        return { 'page': page, 'words': out }
    except Exception:
        return { 'page': page, 'words': {} }


@app.get("/api/runs/{run_id}/doc/{doc}/page/{page}/characters")
def api_chars(run_id: int, doc: str, page: int, tool: Optional[str] = None):
    run = get_run(run_id)
    art = run.get('artifacts') or {}
    details_path = art.get('details')
    if not details_path or not Path(details_path).exists():
        return { 'page': page, 'characters': {} }
    try:
        results = json.loads(Path(details_path).read_text(encoding='utf-8'))
        out = {}
        for r in results:
            conv = r.get('converter_name')
            if tool and conv != tool: continue
            fp = r.get('file_path') or ''
            if Path(fp).stem != doc: continue
            meta = r.get('metadata') or {}
            cpp = meta.get('chars_per_page') or meta.get('characters_per_page') or {}
            chars = cpp.get(str(page)) or cpp.get(page)
            if chars:
                out[conv] = chars
        return { 'page': page, 'characters': out }
    except Exception:
        return { 'page': page, 'characters': {} }


@app.get("/api/image_gray")
def api_image_gray(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        from PIL import Image
        with Image.open(p) as im:
            g = im.convert('L').convert('RGBA') if im.mode in ('RGBA','LA') else im.convert('L')
            bio = io.BytesIO()
            g.save(bio, format='PNG')
            bio.seek(0)
            return StreamingResponse(bio, media_type='image/png')
    except Exception:
        pass
    return FileResponse(str(p))
