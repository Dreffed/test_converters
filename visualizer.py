#!/usr/bin/env python3
"""
Visualizer for document converter block overlays and coverage metrics.

Phase 1: PyMuPDF-based rendering and PyMuPDF block overlays.
Fallbacks: OpenCV preferred, Pillow if OpenCV is unavailable.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

try:
    from PIL import Image, ImageDraw  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


@dataclass
class TextBlock:
    page_index: int
    x0: float  # normalized [0,1]
    y0: float
    x1: float
    y1: float
    text: str = ""
    confidence: Optional[float] = None
    source: str = ""


def iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    aw = max(0.0, ax1 - ax0)
    ah = max(0.0, ay1 - ay0)
    bw = max(0.0, bx1 - bx0)
    bh = max(0.0, by1 - by0)
    union = aw * ah + bw * bh - inter
    if union <= 0:
        return 0.0
    return inter / union


class Visualizer:
    def __init__(self, output_dir: Path, dpi: int = 200, iou_thr: float = 0.5):
        self.output_dir = Path(output_dir)
        self.dpi = dpi
        self.iou_thr = iou_thr
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _render_pages_pymupdf(self, pdf_path: str) -> List[Tuple[Path, int, int]]:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        rendered: List[Tuple[Path, int, int]] = []
        try:
            # Scale based on dpi vs 72
            zoom = self.dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=mat)
                img_path = self.output_dir / f"page_{i:03d}.png"
                pix.save(str(img_path))
                rendered.append((img_path, pix.width, pix.height))
        finally:
            doc.close()
        return rendered

    def _draw_rects(self, img_path: Path, rects: List[Tuple[int, int, int, int]], color: Tuple[int, int, int], thickness: int = 2) -> None:
        if _HAS_CV2:
            img = cv2.imread(str(img_path))
            if img is None:
                return
            for (x0, y0, x1, y1) in rects:
                cv2.rectangle(img, (x0, y0), (x1, y1), color, thickness)
            cv2.imwrite(str(img_path), img)
        elif _HAS_PIL:
            with Image.open(img_path) as im:
                draw = ImageDraw.Draw(im)
                for (x0, y0, x1, y1) in rects:
                    draw.rectangle([x0, y0, x1, y1], outline=color, width=thickness)
                im.save(img_path)

    def _scale_norm_to_px(self, blocks: List[TextBlock], width: int, height: int) -> List[Tuple[int, int, int, int]]:
        rects: List[Tuple[int, int, int, int]] = []
        for b in blocks:
            x0 = max(0, min(width - 1, int(round(b.x0 * width))))
            y0 = max(0, min(height - 1, int(round(b.y0 * height))))
            x1 = max(0, min(width, int(round(b.x1 * width))))
            y1 = max(0, min(height, int(round(b.y1 * height))))
            if x1 > x0 and y1 > y0:
                rects.append((x0, y0, x1, y1))
        return rects

    def _dedupe_union(self, per_engine_blocks: Dict[str, List[TextBlock]]) -> List[TextBlock]:
        union: List[TextBlock] = []
        def overlaps_any(tb: TextBlock) -> int:
            for idx, u in enumerate(union):
                if iou((tb.x0, tb.y0, tb.x1, tb.y1), (u.x0, u.y0, u.x1, u.y1)) >= 0.9:
                    return idx
            return -1
        for engine, blocks in per_engine_blocks.items():
            for b in blocks:
                idx = overlaps_any(b)
                if idx < 0:
                    union.append(b)
                # else: already represented
        return union

    def _coverage_for_engine(self, engine_blocks: List[TextBlock], union_blocks: List[TextBlock]) -> float:
        if not union_blocks:
            return 0.0
        matched = 0
        used = [False] * len(union_blocks)
        for eb in engine_blocks:
            best_iou = 0.0
            best_idx = -1
            for i, ub in enumerate(union_blocks):
                if used[i]:
                    continue
                v = iou((eb.x0, eb.y0, eb.x1, eb.y1), (ub.x0, ub.y0, ub.x1, ub.y1))
                if v >= self.iou_thr and v > best_iou:
                    best_iou = v
                    best_idx = i
            if best_idx >= 0:
                used[best_idx] = True
                matched += 1
        return matched / len(union_blocks)

    def process_document(self,
                         pdf_path: str,
                         per_engine_blocks_norm: Dict[str, Dict[int, List[Dict]]],
                         export_blocks_json: bool = False) -> Dict:
        """
        per_engine_blocks_norm: engine -> page_index -> list of dicts {x0,y0,x1,y1,text}
        Returns metrics dict containing per-page and document coverage per engine.
        """
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        doc_out_dir = self.output_dir / pdf_name
        doc_out_dir.mkdir(parents=True, exist_ok=True)

        # Render pages
        rendered = self._render_pages_pymupdf(pdf_path)

        colors = {
            'pymupdf': (0, 255, 0),
            'pdfplumber': (255, 0, 0),
            'pypdf2': (0, 0, 255),
            'tesseract': (255, 255, 0),
            'markitdown': (255, 0, 255),
        }

        per_page_metrics: List[Dict] = []
        # For export: canonical union blocks per page
        export_blocks: Dict[int, List[Dict]] = {}

        for page_idx, (img_path, w, h) in enumerate(rendered):
            # Collect blocks for each engine on this page
            blocks_by_engine: Dict[str, List[TextBlock]] = {}
            for eng, pages in per_engine_blocks_norm.items():
                raw = pages.get(page_idx, [])
                tbs = [TextBlock(page_index=page_idx,
                                 x0=b.get('x0', 0.0), y0=b.get('y0', 0.0),
                                 x1=b.get('x1', 0.0), y1=b.get('y1', 0.0),
                                 text=b.get('text', ''), source=eng)
                       for b in raw]
                if tbs:
                    blocks_by_engine[eng] = tbs

            if not blocks_by_engine:
                per_page_metrics.append({'page': page_idx, 'union': 0, 'engines': {}})
                continue

            union_blocks = self._dedupe_union(blocks_by_engine)
            export_blocks[page_idx] = [asdict(b) for b in union_blocks]

            # Draw overlays per engine
            for eng, tbs in blocks_by_engine.items():
                rects = self._scale_norm_to_px(tbs, w, h)
                eng_img = doc_out_dir / f"page_{page_idx:03d}_{eng}.png"
                # copy base image
                if _HAS_CV2:
                    base = cv2.imread(str(img_path))
                    if base is None:
                        continue
                    cv2.imwrite(str(eng_img), base)
                elif _HAS_PIL:
                    with Image.open(img_path) as im:
                        im.save(eng_img)
                self._draw_rects(eng_img, rects, colors.get(eng, (0, 255, 255)), thickness=2)

            # Composite overlay
            comp_img = doc_out_dir / f"page_{page_idx:03d}_composite.png"
            if _HAS_CV2:
                base = cv2.imread(str(img_path))
                if base is not None:
                    for eng, tbs in blocks_by_engine.items():
                        rects = self._scale_norm_to_px(tbs, w, h)
                        for (x0, y0, x1, y1) in rects:
                            cv2.rectangle(base, (x0, y0), (x1, y1), colors.get(eng, (0, 255, 255)), 2)
                    cv2.imwrite(str(comp_img), base)
            elif _HAS_PIL:
                with Image.open(img_path) as im:
                    draw = ImageDraw.Draw(im)
                    for eng, tbs in blocks_by_engine.items():
                        rects = self._scale_norm_to_px(tbs, w, h)
                        for (x0, y0, x1, y1) in rects:
                            draw.rectangle([x0, y0, x1, y1], outline=colors.get(eng, (0, 255, 255)), width=2)
                    im.save(comp_img)

            # Coverage per engine
            eng_metrics: Dict[str, float] = {}
            for eng, tbs in blocks_by_engine.items():
                eng_metrics[eng] = self._coverage_for_engine(tbs, union_blocks)

            per_page_metrics.append({
                'page': page_idx,
                'union': len(union_blocks),
                'engines': eng_metrics
            })

        # Aggregate per document (weighted by union size)
        totals = {eng: 0.0 for eng in per_engine_blocks_norm.keys()}
        weights = 0
        for pm in per_page_metrics:
            u = pm['union']
            if u <= 0:
                continue
            weights += u
            for eng, cov in pm['engines'].items():
                totals[eng] = totals.get(eng, 0.0) + cov * u
        doc_coverage = {eng: (totals[eng] / weights if weights > 0 else 0.0) for eng in totals.keys()}

        metrics = {
            'document': os.path.basename(pdf_path),
            'dpi': self.dpi,
            'iou_threshold': self.iou_thr,
            'per_page': per_page_metrics,
            'per_document': doc_coverage,
            'output_dir': str(doc_out_dir)
        }

        # Save metrics JSON
        with open(doc_out_dir / 'visual_metrics.json', 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2)

        if export_blocks_json:
            with open(doc_out_dir / 'visual_blocks.json', 'w', encoding='utf-8') as f:
                json.dump(export_blocks, f, indent=2)

        return metrics

