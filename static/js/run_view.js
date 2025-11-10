(function(){
  const runId = window.__RUN_ID__;
  const $ = (s, d=document)=>d.querySelector(s);
  const $$ = (s, d=document)=>Array.from(d.querySelectorAll(s));

  const docSelect = $('#docSelect');
  const pageInput = $('#pageInput');
  const pageTotal = $('#pageTotal');
  const prevBtn = $('#prevBtn');
  const nextBtn = $('#nextBtn');
  const viewport = $('#viewport');
  const canvas = $('#canvas');
  const img = $('#pageImg');
  const svg = $('#overlay');
  const toggleGray = $('#toggleGray');
  const toggleNums = $('#toggleNums');
  const toggleGrayServer = document.getElementById('toggleGrayServer');
  const opacity = $('#opacity');
  const parsersDiv = $('#parsers');
  const legendDiv = $('#legend');
  const exportBtn = $('#exportBtn');
  const clearSelBtn = document.getElementById('clearSel');
  const warn = $('#pageLimitWarn');
  const overrideBtn = $('#overrideLimit');
  const toggleMerged = document.getElementById('toggleMerged');
  const toggleTextBoxes = document.getElementById('toggleTextBoxes');
  const toggleTableBoxes = document.getElementById('toggleTableBoxes');
  const mergeModeSel = document.getElementById('mergeMode');
  const applyMergeBtn = document.getElementById('applyMerge');
  const consToolSel = document.getElementById('consTool');
  const consStrategySel = document.getElementById('consStrategy');
  const runConsBtn = document.getElementById('runCons');
  const showConsRedundant = document.getElementById('showConsRedundant');
  const showConsUnique = document.getElementById('showConsUnique');
  const showConsGroups = document.getElementById('showConsGroups');

  const tabs = $('#resultTabs');
  const panels = $('#resultPanels');
  const tablesTabs = document.getElementById('tablesTabs');
  const tablesPanels = document.getElementById('tablesPanels');

  const state = {
    docs: [], colors: {},
    docId: null, page: 0, pageCount: 0,
    selected: new Set(),
    showNums: false,
    gray: false,
    zoom: 1,
    limit: 10,
    limitOverride: false,
    boxesCache: new Map(), // key: `${docId}:${page}` => { tool: boxes[] }
    selection: null,
    mergedCache: new Map(), // key: `${docId}:${page}:${mode}:${toolsKey}` => groups
    tablesCache: new Map(), // key: `${docId}:${page}` => [{id,bbox}]
    consolidatedCache: new Map(), // key: `${docId}:${page}:${tool}:${strategy}` => {boxes, merged_groups, layout_groups}
  };

  function artifactUrl(path){ return '/api/artifacts?path=' + encodeURIComponent(path); }

  async function fetchJSON(url){
    const r = await fetch(url);
    if(!r.ok) throw new Error('HTTP '+r.status);
    return r.json();
  }

  function setZoom(z){ state.zoom = Math.max(0.25, Math.min(4, z)); canvas.style.transform = `scale(${state.zoom})`; }

  function setupZoomButtons(){
    $('#zoomIn').onclick = ()=> setZoom(state.zoom + 0.1);
    $('#zoomOut').onclick = ()=> setZoom(state.zoom - 0.1);
    $('#zoomReset').onclick = ()=> setZoom(1);
    viewport.addEventListener('wheel', (e)=>{
      if(!e.ctrlKey) return; e.preventDefault();
      setZoom(state.zoom + (e.deltaY<0? 0.1 : -0.1));
    }, { passive:false });
  }

  async function loadDocs(){
    const data = await fetchJSON(`/api/runs/${runId}/docs`);
    state.docs = data.docs || []; state.colors = data.colors || {};
    // Build select
    docSelect.innerHTML = '';
    state.docs.forEach(d=>{
      const opt = document.createElement('option');
      opt.value = d.id; opt.textContent = d.id; docSelect.appendChild(opt);
    });
    // Legend
    legendDiv.innerHTML = '';
    const toolMap = (state.colors && state.colors.tools) ? state.colors.tools : {};
    Object.entries(toolMap).forEach(([tool,color])=>{
      const div = document.createElement('div'); div.className='item';
      div.innerHTML = `<span class="swatch" style="background:${color}"></span> <span>${tool}</span>`;
      legendDiv.appendChild(div);
    });
    const overlays = (state.colors && state.colors.overlays) ? state.colors.overlays : {};
    [['merged','Merged'], ['tables','Tables']].forEach(([key,label])=>{
      const color = overlays[key]; if(!color) return;
      const div = document.createElement('div'); div.className='item';
      div.innerHTML = `<span class="swatch" style="background:${color}"></span> <span>${label}</span>`;
      legendDiv.appendChild(div);
    });
    if(state.docs.length){ selectDoc(state.docs[0].id); }
  }

  function selectDoc(id){
    state.docId = id;
    const d = state.docs.find(x=>x.id===id);
    state.pageCount = d? d.pages : 0;
    state.page = 0;
    pageInput.value = '0'; pageTotal.textContent = String(state.pageCount-1);
    // Parsers list
    parsersDiv.innerHTML = '';
    (d.engines||[]).forEach(tool=>{
      const id = `tool_${tool}`;
      const row = document.createElement('div'); row.className='row';
      row.innerHTML = `<input type="checkbox" id="${id}" data-tool="${tool}"><label for="${id}">${tool}</label>`;
      const cb = row.querySelector('input');
      cb.addEventListener('change', ()=>{ if(cb.checked) state.selected.add(tool); else state.selected.delete(tool); renderOverlay(); renderBottom(); });
      parsersDiv.appendChild(row);
    });
    if (consToolSel) {
      consToolSel.innerHTML = '';
      (d.engines||[]).forEach(tool => { const opt = document.createElement('option'); opt.value = tool; opt.textContent = tool; consToolSel.appendChild(opt); });
    }
    warn.hidden = state.pageCount <= state.limit || state.limitOverride;
    loadPage();
  }

  function updateBaseImageSrc(baseEntry){
    if(!baseEntry || !baseEntry.base) return;
    const path = baseEntry.base;
    if(toggleGray && toggleGray.checked){
      if (toggleGrayServer && toggleGrayServer.checked) {
        img.src = `/api/image_gray?path=${encodeURIComponent(path)}`;
      } else {
        img.src = artifactUrl(path);
        // apply CSS grayscale filter after load to ensure dimensions are known
        img.onload = ()=>{ img.style.filter = 'grayscale(100%)'; };
        return;
      }
    } else {
      img.src = artifactUrl(path);
    }
  }

  async function loadPage(){
    const docId = state.docId; const p = state.page;
    // Base image path: use existing visual index for fallback
    let baseEntry = null;
    try {
      const vi = window.__VISUAL_INDEX__ || [];
      const doc = vi.find(d=>d.doc===docId);
      if(doc){ baseEntry = (doc.pages||[]).find(e=>e.page===p); }
    } catch {}
    updateBaseImageSrc(baseEntry);
    img.onload = ()=> { renderOverlay(); };
    await loadBoxes();
    if (toggleTableBoxes && toggleTableBoxes.checked) { await loadTableBoxes(); }
    renderOverlay();
    renderBottom();
  }

  async function runConsolidation(){
    const tool = consToolSel ? consToolSel.value : null;
    const strat = consStrategySel ? consStrategySel.value : 'overlap';
    if (!tool) return;
    try{
      const resp = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/page/${state.page}/consolidate?tool=${encodeURIComponent(tool)}&strategy=${encodeURIComponent(strat)}`, { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        state.consolidatedCache.set(`${state.docId}:${state.page}:${tool}:${strat}`, data);
        renderOverlay();
      } else {
        alert('Consolidation failed');
      }
    } catch {}
  }

  async function loadConsolidated(tool){
    const strat = consStrategySel ? consStrategySel.value : 'overlap';
    const key = `${state.docId}:${state.page}:${tool}:${strat}`;
    if (state.consolidatedCache.has(key)) return state.consolidatedCache.get(key);
    try{
      const resp = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/page/${state.page}/consolidated?tool=${encodeURIComponent(tool)}&strategy=${encodeURIComponent(strat)}`);
      if (resp.ok) {
        const data = await resp.json();
        state.consolidatedCache.set(key, data);
        return data;
      }
    } catch {}
    return null;
  }

  async function loadBoxes(){
    const key = `${state.docId}:${state.page}`;
    if(state.boxesCache.has(key)) return;
    const q = new URLSearchParams({ withText:'1', withIds:'1' });
    const data = await fetchJSON(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/page/${state.page}/bboxes?${q}`);
    const byTool = data.boxes || {};
    // Annotate each bbox with a stable overlay index to keep numbering consistent between overlay and text panel
    Object.keys(byTool).forEach(tool=>{
      const arr = byTool[tool] || [];
      arr.forEach((b, i)=>{ if (b && typeof b === 'object') b._idx = (i+1); });
    });
    state.boxesCache.set(key, byTool);
  }

  async function loadTableBoxes(){
    const key = `${state.docId}:${state.page}`;
    if (state.tablesCache.has(key)) return;
    try{
      const resp = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/page/${state.page}/table_bboxes`);
      if(resp.ok){
        const data = await resp.json();
        state.tablesCache.set(key, data.tables || []);
      }
    } catch {}
  }

  async function loadTablesForPage(){
    const docId = state.docId; const p = state.page;
    const boxesByTool = getBoxes();
    const tools = state.selected.size? Array.from(state.selected) : Object.keys(boxesByTool);
    // Fetch per-tool tables
    const results = await Promise.all(tools.map(async tool => {
      try{
        const resp = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(docId)}/page/${p}/tables?tool=${encodeURIComponent(tool)}`);
        if(!resp.ok) return [tool, []];
        const data = await resp.json();
        return [tool, (data.tables||{})[tool] || []];
      } catch { return [tool, []]; }
    }));
    const perTool = {};
    results.forEach(([tool, tables])=> perTool[tool] = tables);
    return perTool;
  }

  function getBoxes(){
    const key = `${state.docId}:${state.page}`;
    return state.boxesCache.get(key) || {};
  }

  function sizeOverlay(){
    const w = img.naturalWidth || 0, h = img.naturalHeight || 0;
    if (w>0 && h>0) {
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    }
    svg.style.width = img.clientWidth+'px';
    svg.style.height = img.clientHeight+'px';
    svg.style.left = img.offsetLeft+'px';
    svg.style.top = img.offsetTop+'px';
  }

  function renderOverlay(){
    sizeOverlay();
    svg.innerHTML = '';
    const gRoot = document.createElementNS('http://www.w3.org/2000/svg','g');
    gRoot.setAttribute('opacity', String((+opacity.value||70)/100));
    svg.appendChild(gRoot);
    const boxesByTool = getBoxes();
    const tools = state.selected.size? Array.from(state.selected) : Object.keys(boxesByTool);
    // Precompute selected ids for highlight
    const selectedIdsByTool = {};
    if (state.selection) {
      const s = state.selection;
      tools.forEach(tool => {
        const list = boxesByTool[tool] || [];
        let chosen = [];
        if ((s.w||0) < 0.005 && (s.h||0) < 0.005) {
          const px = s.x, py = s.y;
          chosen = list.filter(b=> px >= b.bbox.x && px <= b.bbox.x + b.bbox.w && py >= b.bbox.y && py <= b.bbox.y + b.bbox.h);
        } else {
          chosen = list.filter(b=> intersect(s, b.bbox).area > 0);
        }
        selectedIdsByTool[tool] = new Set(chosen.map(b => b.id));
      });
    }
    // Draw per-tool text boxes if enabled
    if (!toggleTextBoxes || toggleTextBoxes.checked) {
      tools.forEach(tool=>{
        const g = document.createElementNS('http://www.w3.org/2000/svg','g');
        g.setAttribute('data-tool', tool);
        gRoot.appendChild(g);
        const color = (state.colors && state.colors.tools && state.colors.tools[tool]) || (state.colors && state.colors.overlays && state.colors.overlays.text) || '#00FFFF';
        const textColor = (function(){
        const hex = color.replace('#','');
        const h = hex.length===3 ? hex.split('').map(c=>c+c).join('') : hex;
        const n = parseInt(h,16);
        const r=(n>>16)&255, g=(n>>8)&255, b=n&255;
        const L=(0.299*r+0.587*g+0.114*b)/255; return L>0.6?'#000':'#FFF';
      })();
      const list = boxesByTool[tool] || [];
      list.forEach((b, i)=>{
        const {x,y,w,h} = b.bbox || {}; if(w<=0 || h<=0) return;
        const r = document.createElementNS('http://www.w3.org/2000/svg','rect');
        r.setAttribute('class','bbox');
        const xpx = x*img.naturalWidth, ypx = y*img.naturalHeight, wpx = w*img.naturalWidth, hpx = h*img.naturalHeight;
        r.setAttribute('x', String(xpx));
        r.setAttribute('y', String(ypx));
        r.setAttribute('width', String(wpx));
        r.setAttribute('height', String(hpx));
        r.setAttribute('stroke', color);
        g.appendChild(r);
        if (selectedIdsByTool[tool] && selectedIdsByTool[tool].has(b.id)) {
          const rs = document.createElementNS('http://www.w3.org/2000/svg','rect');
          rs.setAttribute('class','bbox-selected');
          rs.setAttribute('x', String(xpx));
          rs.setAttribute('y', String(ypx));
          rs.setAttribute('width', String(wpx));
          rs.setAttribute('height', String(hpx));
          g.appendChild(rs);
        }
        if(toggleNums.checked){
          const radius = 9;
          const cx = xpx + radius + 3;
          const cy = ypx + radius + 3;
          const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
          circle.setAttribute('class','bbox-badge-circle');
          circle.setAttribute('cx', String(cx));
          circle.setAttribute('cy', String(cy));
          circle.setAttribute('r', String(radius));
          circle.setAttribute('fill', color);
          g.appendChild(circle);
          const t = document.createElementNS('http://www.w3.org/2000/svg','text');
          t.setAttribute('class','bbox-badge-text');
          t.setAttribute('x', String(cx));
          t.setAttribute('y', String(cy));
          t.setAttribute('fill', textColor);
          t.textContent = String(b._idx || (i+1));
          g.appendChild(t);
        }
      });
      });
    }
    // Render merged layer if enabled and cached
    if(toggleMerged && toggleMerged.checked){
      const key = `${state.docId}:${state.page}:${mergeModeSel ? mergeModeSel.value : 'vertical'}:${tools.slice().sort().join(',')}`;
      const merged = state.mergedCache.get(key);
      if(merged && merged.groups){
        const g = document.createElementNS('http://www.w3.org/2000/svg','g');
        g.setAttribute('data-tool','merged');
        gRoot.appendChild(g);
        const color = (state.colors && state.colors.overlays && state.colors.overlays.merged) || '#FFA500';
        const textColor = '#000';
        merged.groups.forEach((m,i)=>{
          const {x,y,w,h} = m.bbox || {}; if(w<=0||h<=0) return;
          const xpx=x*img.naturalWidth, ypx=y*img.naturalHeight, wpx=w*img.naturalWidth, hpx=h*img.naturalHeight;
          const r=document.createElementNS('http://www.w3.org/2000/svg','rect');
          r.setAttribute('class','bbox');
          r.setAttribute('x', String(xpx)); r.setAttribute('y', String(ypx)); r.setAttribute('width', String(wpx)); r.setAttribute('height', String(hpx));
          r.setAttribute('stroke', color); g.appendChild(r);
          if(toggleNums && toggleNums.checked){
            const radius=9, cx=xpx+radius+3, cy=ypx+radius+3;
            const c=document.createElementNS('http://www.w3.org/2000/svg','circle'); c.setAttribute('class','bbox-badge-circle'); c.setAttribute('cx', String(cx)); c.setAttribute('cy', String(cy)); c.setAttribute('r', String(radius)); c.setAttribute('fill', color); g.appendChild(c);
            const t=document.createElementNS('http://www.w3.org/2000/svg','text'); t.setAttribute('class','bbox-badge-text'); t.setAttribute('x', String(cx)); t.setAttribute('y', String(cy)); t.setAttribute('fill', textColor); t.textContent=String(i+1); g.appendChild(t);
          }
        });
      }
    }
    img.style.filter = toggleGray.checked? 'grayscale(100%)' : 'none';
    // Consolidation overlays if any toggles enabled
    const consTool = consToolSel ? consToolSel.value : null;
    if (consTool && ((showConsRedundant && showConsRedundant.checked) || (showConsUnique && showConsUnique.checked) || (showConsGroups && showConsGroups.checked))){
      // async render after fetch
      (async () => {
        const cons = await loadConsolidated(consTool);
        if (!cons) return;
        const g = document.createElementNS('http://www.w3.org/2000/svg','g');
        g.setAttribute('data-tool','consolidated'); gRoot.appendChild(g);
        const boxes = cons.boxes || [];
        boxes.forEach(b => {
          const bb = b.bbox||{}; if (!bb.w || !bb.h) return;
          const xpx=bb.x*img.naturalWidth, ypx=bb.y*img.naturalHeight, wpx=bb.w*img.naturalWidth, hpx=bb.h*img.naturalHeight;
          if (showConsRedundant && showConsRedundant.checked && b.redundant){
            const r1 = document.createElementNS('http://www.w3.org/2000/svg','rect'); r1.setAttribute('class','bbox bbox-redundant'); r1.setAttribute('x', String(xpx)); r1.setAttribute('y', String(ypx)); r1.setAttribute('width', String(wpx)); r1.setAttribute('height', String(hpx)); g.appendChild(r1);
          }
          if (showConsUnique && showConsUnique.checked && b.unique_extra){
            const r2 = document.createElementNS('http://www.w3.org/2000/svg','rect'); r2.setAttribute('class','bbox bbox-unique'); r2.setAttribute('x', String(xpx)); r2.setAttribute('y', String(ypx)); r2.setAttribute('width', String(wpx)); r2.setAttribute('height', String(hpx)); g.appendChild(r2);
          }
        });
        if (showConsGroups && showConsGroups.checked){
          const grp = cons.layout_groups || [];
          grp.forEach((ginfo) => {
            const bb=ginfo.bbox||{}; if (!bb.w || !bb.h) return;
            const xpx=bb.x*img.naturalWidth, ypx=bb.y*img.naturalHeight, wpx=bb.w*img.naturalWidth, hpx=bb.h*img.naturalHeight;
            const rr = document.createElementNS('http://www.w3.org/2000/svg','rect'); rr.setAttribute('class','cons-group'); rr.setAttribute('x', String(xpx)); rr.setAttribute('y', String(ypx)); rr.setAttribute('width', String(wpx)); rr.setAttribute('height', String(hpx)); rr.setAttribute('data-group-type', ginfo.type || 'group'); g.appendChild(rr);
          });
        }
      })();
    }
    // Render table bboxes if toggled
    if (toggleTableBoxes && toggleTableBoxes.checked) {
      const key = `${state.docId}:${state.page}`;
      const tables = state.tablesCache.get(key) || [];
      const g = document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('data-tool','tables');
      gRoot.appendChild(g);
      const color = (state.colors && state.colors.overlays && state.colors.overlays.tables) || '#32CD32';
      const textColor = '#000';
      tables.forEach((tb, i)=>{
        const {x,y,w,h} = tb.bbox || {}; if(w<=0||h<=0) return;
        const xpx=x*img.naturalWidth, ypx=y*img.naturalHeight, wpx=w*img.naturalWidth, hpx=h*img.naturalHeight;
        const r=document.createElementNS('http://www.w3.org/2000/svg','rect');
        r.setAttribute('class','bbox'); r.setAttribute('x', String(xpx)); r.setAttribute('y', String(ypx)); r.setAttribute('width', String(wpx)); r.setAttribute('height', String(hpx)); r.setAttribute('stroke', color);
        g.appendChild(r);
        if(toggleNums && toggleNums.checked){
          const radius=9, cx=xpx+radius+3, cy=ypx+radius+3;
          const c=document.createElementNS('http://www.w3.org/2000/svg','circle'); c.setAttribute('class','bbox-badge-circle'); c.setAttribute('cx', String(cx)); c.setAttribute('cy', String(cy)); c.setAttribute('r', String(radius)); c.setAttribute('fill', color); g.appendChild(c);
          const t=document.createElementNS('http://www.w3.org/2000/svg','text'); t.setAttribute('class','bbox-badge-text'); t.setAttribute('x', String(cx)); t.setAttribute('y', String(cy)); t.setAttribute('fill', textColor); t.textContent=String(i+1); g.appendChild(t);
        }
      });
    }
  }

  function intersect(a,b){
    const ax1=a.x+a.w, ay1=a.y+a.h, bx1=b.x+b.w, by1=b.y+b.h;
    const ix=Math.max(a.x,b.x), iy=Math.max(a.y,b.y), iw=Math.max(0, Math.min(ax1,bx1)-ix), ih=Math.max(0, Math.min(ay1,by1)-iy);
    return {x:ix,y:iy,w:iw,h:ih, area: iw*ih};
  }

  function renderBottom(){
    // Build tabs for selected tools (or all if none selected)
    const boxesByTool = getBoxes();
    const tools = state.selected.size? Array.from(state.selected) : Object.keys(boxesByTool);
    tabs.innerHTML=''; panels.innerHTML='';
    tools.forEach(async (tool,idx)=>{
      const btn=document.createElement('button'); btn.textContent=tool; btn.setAttribute('role','tab'); btn.setAttribute('aria-selected', String(idx===0));
      btn.onclick=()=>{
        $$('.tabs button', tabs).forEach(b=>b.setAttribute('aria-selected','false'));
        btn.setAttribute('aria-selected','true');
        $$('.panel', panels).forEach(p=>p.setAttribute('aria-hidden','true'));
        $('#panel_'+tool, panels)?.setAttribute('aria-hidden','false');
      };
      tabs.appendChild(btn);
      const panel=document.createElement('div'); panel.id='panel_'+tool; panel.className='panel'; panel.setAttribute('aria-hidden', String(idx!==0));
      // Text from boxes that intersect selection (or whole page when no selection)
      const boxes = boxesByTool[tool]||[];
      // Determine chosen boxes for this tool
      let chosen = [];
      if(state.selection){
        const s = state.selection; // normalized
        if ((s.w||0) < 0.005 && (s.h||0) < 0.005) {
          const px = s.x, py = s.y;
          chosen = boxes.filter(b=> px >= b.bbox.x && px <= b.bbox.x + b.bbox.w && py >= b.bbox.y && py <= b.bbox.y + b.bbox.h);
        } else {
          chosen = boxes.filter(b=> intersect(s, b.bbox).area > 0);
        }
      }
      const taId = 'ta_'+tool;
      const label = document.createElement('label'); label.setAttribute('for', taId); label.textContent = `Text (${tool})`;
      const ta=document.createElement('textarea'); ta.id=taId; ta.setAttribute('aria-label', `Extracted text for ${tool}`); ta.readOnly = true; ta.value=''; ta.style.width='100%'; ta.style.height='160px';
      panel.appendChild(label);
      panel.appendChild(ta);
      // If we have chosen boxes, fetch text per box to show detailed results
      if(chosen.length){
        ta.value = 'Loading text…';
        try{
          const results = await Promise.all(chosen.map(async (b)=>{
            try{
              const r = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/page/${state.page}/text_for_boxes`, {
                method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({ boxes: [b.bbox] })
              });
              if(!r.ok) return '';
              const data = await r.json();
              return (data.text||'').trim();
            } catch { return ''; }
          }));
          const lines = [];
          results.forEach((txt, i)=>{
            const bb = chosen[i].bbox || {x:0,y:0,w:0,h:0};
            const dims = `x:${(bb.x||0).toFixed(3)}, y:${(bb.y||0).toFixed(3)}, w:${(bb.w||0).toFixed(3)}, h:${(bb.h||0).toFixed(3)}`;
            const num = chosen[i]._idx || (i+1);
            lines.push(`BBox ${num} - ${dims}`);
            lines.push(`- ${txt || '(No text found)'}`);
          });
          ta.value = lines.join('\n');
        } catch(e){
          ta.value = '(Error extracting text)';
        }
      } else {
        ta.value = '(Select a region or click a box)';
      }
      panels.appendChild(panel);
    });

    // Render tables section (per selected tool)
    (async () => {
      if (!tablesTabs || !tablesPanels) return;
      tablesTabs.innerHTML=''; tablesPanels.innerHTML='';
      const perTool = await loadTablesForPage();
      const ttools = tools;
      ttools.forEach((tool, idx) => {
        const btn = document.createElement('button'); btn.textContent = tool; btn.setAttribute('role','tab'); btn.setAttribute('aria-selected', String(idx===0));
        btn.onclick = ()=>{
          $$('.tabs button', tablesTabs).forEach(b=>b.setAttribute('aria-selected','false'));
          btn.setAttribute('aria-selected','true');
          $$('.panel', tablesPanels).forEach(p=>p.setAttribute('aria-hidden','true'));
          document.getElementById('tables_panel_'+tool)?.setAttribute('aria-hidden','false');
        };
        tablesTabs.appendChild(btn);
        const panel = document.createElement('div'); panel.id='tables_panel_'+tool; panel.className='panel'; panel.setAttribute('aria-hidden', String(idx!==0));
        const tables = perTool[tool] || [];
        if (!tables.length) {
          const p = document.createElement('p'); p.textContent = 'No tables found for this page/tool.'; panel.appendChild(p);
        } else {
          tables.forEach((t, i) => {
            const tbl = document.createElement('table'); tbl.style.borderCollapse='collapse'; tbl.style.marginBottom='0.75rem';
            const caption = document.createElement('caption'); caption.textContent = `Table #${i+1}`; caption.style.textAlign = 'left'; tbl.appendChild(caption);
            (t.rows||[]).forEach(row => {
              const tr = document.createElement('tr');
              row.forEach(cell => { const td = document.createElement('td'); td.textContent = cell; td.style.border='1px solid #ccc'; td.style.padding='4px 6px'; tr.appendChild(td); });
              tbl.appendChild(tr);
            });
            panel.appendChild(tbl);
          });
        }
        tablesPanels.appendChild(panel);
      });
    })();
  }

  function setupSelection(){
    let dragging=false; let start=null; let rectEl=null;
    svg.addEventListener('pointerdown', (e)=>{
      const r=svg.getBoundingClientRect();
      dragging=true; start={x:(e.clientX-r.left)/r.width, y:(e.clientY-r.top)/r.height};
      rectEl = document.createElementNS('http://www.w3.org/2000/svg','rect'); rectEl.setAttribute('class','select-rect'); svg.appendChild(rectEl);
    });
    window.addEventListener('pointermove', (e)=>{
      if(!dragging||!start) return; const r=svg.getBoundingClientRect();
      const cur={x:(e.clientX-r.left)/r.width, y:(e.clientY-r.top)/r.height};
      const x=Math.min(start.x,cur.x), y=Math.min(start.y,cur.y), w=Math.abs(cur.x-start.x), h=Math.abs(cur.y-start.y);
      rectEl.setAttribute('x', String(x*img.naturalWidth));
      rectEl.setAttribute('y', String(y*img.naturalHeight));
      rectEl.setAttribute('width', String(w*img.naturalWidth));
      rectEl.setAttribute('height', String(h*img.naturalHeight));
    });
    window.addEventListener('pointerup', ()=>{
      if(!dragging) return; dragging=false;
      if(rectEl){
        const x = parseFloat(rectEl.getAttribute('x'))/img.naturalWidth;
        const y = parseFloat(rectEl.getAttribute('y'))/img.naturalHeight;
        const w = parseFloat(rectEl.getAttribute('width'))/img.naturalWidth;
        const h = parseFloat(rectEl.getAttribute('height'))/img.naturalHeight;
        state.selection = {x,y,w,h};
        rectEl.remove(); rectEl=null;
        renderBottom();
      }
    });
  }

  function setupControls(){
    prevBtn.onclick = ()=>{ if(state.page>0){ state.page--; pageInput.value=String(state.page); loadPage(); } };
    nextBtn.onclick = ()=>{ if(state.page < state.pageCount-1){ state.page++; pageInput.value=String(state.page); loadPage(); } };
    pageInput.addEventListener('change', ()=>{ const v=parseInt(pageInput.value||'0'); if(!isNaN(v)){ state.page=Math.max(0, Math.min(state.pageCount-1, v)); loadPage(); }});
    docSelect.addEventListener('change', ()=> selectDoc(docSelect.value));
    opacity.addEventListener('input', renderOverlay);
    toggleGray.addEventListener('change', ()=>{ loadPage(); });
    if (toggleGrayServer) toggleGrayServer.addEventListener('change', ()=>{ if (toggleGray && toggleGray.checked) loadPage(); });
    toggleNums.addEventListener('change', renderOverlay);
    if (clearSelBtn) { clearSelBtn.addEventListener('click', ()=>{ state.selection=null; renderOverlay(); renderBottom(); }); }
    if(applyMergeBtn){
      applyMergeBtn.addEventListener('click', async ()=>{
        const boxesByTool = getBoxes();
        const tools = state.selected.size? Array.from(state.selected) : Object.keys(boxesByTool);
        try{
          const resp = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/page/${state.page}/merge`, {
            method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({ mode: mergeModeSel ? mergeModeSel.value : 'vertical', tools })
          });
          if(resp.ok){
            const data = await resp.json();
            const key = `${state.docId}:${state.page}:${mergeModeSel ? mergeModeSel.value : 'vertical'}:${tools.slice().sort().join(',')}`;
            state.mergedCache.set(key, data);
            renderOverlay();
          }
        } catch(e){}
      });
    }
    if(toggleMerged){ toggleMerged.addEventListener('change', renderOverlay); }
    if (toggleTextBoxes) toggleTextBoxes.addEventListener('change', renderOverlay);
    if (toggleTableBoxes) toggleTableBoxes.addEventListener('change', async ()=>{ if(toggleTableBoxes.checked) await loadTableBoxes(); renderOverlay(); });
    if (runConsBtn) runConsBtn.addEventListener('click', runConsolidation);
    if (consStrategySel) consStrategySel.addEventListener('change', renderOverlay);
    if (showConsRedundant) showConsRedundant.addEventListener('change', renderOverlay);
    if (showConsUnique) showConsUnique.addEventListener('change', renderOverlay);
    if (showConsGroups) showConsGroups.addEventListener('change', renderOverlay);
    exportBtn.onclick = async ()=>{
      const body = { state: { page: state.page, selected: Array.from(state.selected), selection: state.selection }};
      const r = await fetch(`/api/runs/${runId}/doc/${encodeURIComponent(state.docId)}/export`, { method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(body) });
      if(r.ok){ const blob = await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`${state.docId}_export.zip`; a.click(); }
    };
    overrideBtn.onclick = ()=>{ state.limitOverride=true; warn.hidden=true; };
  }

  // init
  setupZoomButtons();
  setupControls();
  setupSelection();
  setZoom(1);
  window.addEventListener('resize', ()=>{ renderOverlay(); });
  loadDocs();
})();
