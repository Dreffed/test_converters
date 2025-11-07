#!/usr/bin/env python3
import os
import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from converter_benchmark import DocumentConverterBenchmark
from converter_implementations import get_available_converters
import urllib.parse
import markdown as md


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
def save_settings(
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
    converters = []
    pages = set()
    data: Dict[str, Dict[str, List]] = {}
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
                    cdict = data.setdefault(conv, {})
                    for page_str, tables in tp.items():
                        # keys might be strings or ints in JSON
                        try:
                            p = int(page_str)
                        except Exception:
                            p = page_str
                        pages.add(p)
                        cdict[str(p)] = tables
        except Exception:
            pass
    pages_list = sorted(list(pages))
    return templates.TemplateResponse("run_tables.html", {
        "request": request,
        "run": run,
        "converters": converters,
        "pages": pages_list,
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


@app.get("/api/artifacts")
def artifact(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(str(p))
