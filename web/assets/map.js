/* JAMap: a small, dependency-free Web Mercator map.
   - Raster tiles from MAP_TILE_URL (OpenStreetMap by default) when the network allows.
   - If tiles cannot load, an offline basemap (graticule + labels) keeps every marker in its true
     position, and a notice says the background is offline. No CDN, no external JavaScript.
   - Drag to pan, wheel / double-click / buttons / pinch to zoom, arrow keys and +/- on focus. */
(function () {
  "use strict";
  const TILE = 256;

  function project(lat, lon, z) {
    const s = TILE * Math.pow(2, z);
    const sin = Math.min(Math.max(Math.sin((lat * Math.PI) / 180), -0.9999), 0.9999);
    return { x: ((lon + 180) / 360) * s, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * s };
  }
  function unproject(x, y, z) {
    const s = TILE * Math.pow(2, z);
    const n = Math.PI - (2 * Math.PI * y) / s;
    return { lat: (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))), lon: (x / s) * 360 - 180 };
  }

  class JAMap {
    constructor(el, opts = {}) {
      this.el = el;
      this.tileUrl = opts.tileUrl || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
      this.attribution = opts.attribution || "© OpenStreetMap contributors";
      this.minZoom = opts.minZoom || 8;
      this.maxZoom = opts.maxZoom || 17;
      this.center = opts.center || { lat: 18.39, lon: 73.79 };
      this.zoom = opts.zoom || 12;
      this.layers = {};
      this.tiles = new Map();
      this.loaded = 0;
      this.failed = 0;
      this.offline = false;
      this.onmove = opts.onmove || null;
      el.classList.add("jamap");
      el.innerHTML = "";
      this.vp = document.createElement("div");
      this.vp.className = "jamap-vp";
      this.vp.tabIndex = 0;
      this.vp.setAttribute("role", "application");
      this.vp.setAttribute("aria-label", opts.label || "Map. Drag to move, use plus and minus to zoom.");
      this.base = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      this.base.setAttribute("class", "jamap-base");
      this.tileBox = document.createElement("div");
      this.tileBox.className = "jamap-tiles";
      this.markBox = document.createElement("div");
      this.markBox.className = "jamap-markers";
      this.vp.append(this.base, this.tileBox, this.markBox);
      const ctr = document.createElement("div");
      ctr.className = "jamap-ctrl";
      ctr.innerHTML = '<button type="button" data-z="1" aria-label="Zoom in">+</button><button type="button" data-z="-1" aria-label="Zoom out">−</button><button type="button" data-fit aria-label="Show all">⤢</button>';
      ctr.addEventListener("click", (e) => {
        const b = e.target.closest("button"); if (!b) return;
        if (b.hasAttribute("data-fit")) this.fit(); else this.zoomAt(this.w / 2, this.h / 2, +b.dataset.z);
      });
      this.note = document.createElement("div");
      this.note.className = "jamap-note";
      this.note.hidden = true;
      this.note.textContent = "Map background offline. Village positions are still exact.";
      const attr = document.createElement("div");
      attr.className = "jamap-attr";
      attr.textContent = this.attribution;
      this.attrEl = attr;
      el.append(this.vp, ctr, this.note, attr);
      this._bind();
      this._fitPoints = null;
      new ResizeObserver(() => this.render()).observe(el);
      this.render();
    }

    get w() { return this.el.clientWidth || 600; }
    get h() { return this.el.clientHeight || 400; }
    origin() { const c = project(this.center.lat, this.center.lon, this.zoom); return { x: c.x - this.w / 2, y: c.y - this.h / 2 }; }
    toPixel(lat, lon) { const p = project(lat, lon, this.zoom), o = this.origin(); return { x: p.x - o.x, y: p.y - o.y }; }

    setView(center, zoom) {
      this.center = { lat: center.lat, lon: center.lon };
      if (zoom != null) this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, Math.round(zoom)));
      this.render();
    }

    fit(points, pad = 56) {
      points = points || this._fitPoints;
      if (!points || !points.length) return;
      this._fitPoints = points;
      if (points.length === 1) return this.setView(points[0], 13);
      let lo = { lat: 90, lon: 180 }, hi = { lat: -90, lon: -180 };
      for (const p of points) { lo = { lat: Math.min(lo.lat, p.lat), lon: Math.min(lo.lon, p.lon) }; hi = { lat: Math.max(hi.lat, p.lat), lon: Math.max(hi.lon, p.lon) }; }
      let z = this.maxZoom;
      for (; z > this.minZoom; z--) {
        const a = project(hi.lat, lo.lon, z), b = project(lo.lat, hi.lon, z);
        if (b.x - a.x <= this.w - 2 * pad && b.y - a.y <= this.h - 2 * pad) break;
      }
      this.setView({ lat: (lo.lat + hi.lat) / 2, lon: (lo.lon + hi.lon) / 2 }, Math.min(z, 14));
    }

    zoomAt(px, py, dz) {
      const nz = Math.max(this.minZoom, Math.min(this.maxZoom, this.zoom + dz));
      if (nz === this.zoom) return;
      const o = this.origin();
      const ll = unproject(o.x + px, o.y + py, this.zoom);
      const p = project(ll.lat, ll.lon, nz);
      this.zoom = nz;
      this.center = unproject(p.x - (px - this.w / 2), p.y - (py - this.h / 2), nz);
      this.render();
    }

    panBy(dx, dy) {
      const c = project(this.center.lat, this.center.lon, this.zoom);
      this.center = unproject(c.x - dx, c.y - dy, this.zoom);
      this._schedule();
    }

    _schedule() { if (!this._raf) this._raf = requestAnimationFrame(() => { this._raf = null; this.render(); }); }

    // ---------------------------------------------------------------- markers
    setLayer(name, items) {
      // items: [{lat, lon, el}] ; replaces the layer
      (this.layers[name] || []).forEach((m) => m.el.remove());
      this.layers[name] = items.filter((m) => m.lat != null && m.lon != null);
      for (const m of this.layers[name]) { m.el.classList.add("jamap-mk"); this.markBox.append(m.el); }
      this._placeMarkers();
    }
    _placeMarkers() {
      for (const items of Object.values(this.layers))
        for (const m of items) { const p = this.toPixel(m.lat, m.lon); m.el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`; }
    }

    // ---------------------------------------------------------------- rendering
    render() {
      const o = this.origin(), z = this.zoom, n = Math.pow(2, z);
      const need = new Set();
      const x0 = Math.floor(o.x / TILE), x1 = Math.floor((o.x + this.w) / TILE);
      const y0 = Math.max(0, Math.floor(o.y / TILE)), y1 = Math.min(n - 1, Math.floor((o.y + this.h) / TILE));
      if (!this.offline) {
        for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
          const key = `${z}/${x}/${y}`; need.add(key);
          let img = this.tiles.get(key);
          if (!img) {
            img = new Image(TILE, TILE);
            img.alt = ""; img.decoding = "async"; img.draggable = false; img.className = "jamap-tile";
            img.referrerPolicy = "strict-origin-when-cross-origin";
            const wx = ((x % n) + n) % n;
            img.onload = () => { this.loaded++; img.classList.add("in"); };
            img.onerror = () => { this.failed++; img.remove(); this.tiles.delete(key); if (this.failed >= 4 && this.loaded === 0) this._goOffline(); };
            img.src = this.tileUrl.replace("{z}", z).replace("{x}", wx).replace("{y}", y).replace("{s}", "abc"[(x + y) % 3]);
            this.tiles.set(key, img); this.tileBox.append(img);
          }
          img.style.transform = `translate(${x * TILE - o.x}px, ${y * TILE - o.y}px)`;
        }
        for (const [key, img] of this.tiles) if (!need.has(key)) { img.remove(); this.tiles.delete(key); }
      }
      this._drawBase(o);
      this._placeMarkers();
      if (this.onmove) this.onmove(this);
    }

    _goOffline() {
      this.offline = true;
      for (const img of this.tiles.values()) img.remove();
      this.tiles.clear();
      this.note.hidden = false;
      this.el.classList.add("is-offline");
      this.render();
    }

    _drawBase(o) {
      const w = this.w, h = this.h, z = this.zoom;
      const nw = unproject(o.x, o.y, z), se = unproject(o.x + w, o.y + h, z);
      const span = Math.max(se.lon - nw.lon, 1e-6);
      const steps = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1];
      const step = steps.find((s) => (span / s) <= 9) || 1;
      let out = `<rect width="${w}" height="${h}" class="jb-bg"/>`;
      for (let lon = Math.ceil(nw.lon / step) * step; lon <= se.lon; lon += step) {
        const x = project(0, lon, z).x - o.x;
        out += `<line x1="${x}" y1="0" x2="${x}" y2="${h}" class="jb-grid"/><text x="${x + 4}" y="${h - 8}" class="jb-lbl">${lon.toFixed(step < 0.01 ? 3 : 2)}°E</text>`;
      }
      for (let lat = Math.ceil(se.lat / step) * step; lat <= nw.lat; lat += step) {
        const y = project(lat, 0, z).y - o.y;
        out += `<line x1="0" y1="${y}" x2="${w}" y2="${y}" class="jb-grid"/><text x="6" y="${y - 4}" class="jb-lbl">${lat.toFixed(step < 0.01 ? 3 : 2)}°N</text>`;
      }
      this.base.setAttribute("viewBox", `0 0 ${w} ${h}`);
      this.base.setAttribute("width", w);
      this.base.setAttribute("height", h);
      this.base.innerHTML = out;
    }

    // ---------------------------------------------------------------- input
    _bind() {
      const vp = this.vp, pts = new Map();
      let last = null, pinch = null, moved = 0;
      vp.addEventListener("pointerdown", (e) => {
        if (e.target.closest(".jamap-mk button, .jamap-mk a")) return;
        vp.setPointerCapture(e.pointerId); pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pts.size === 1) { last = { x: e.clientX, y: e.clientY }; moved = 0; }
        if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) }; }
      });
      vp.addEventListener("pointermove", (e) => {
        if (!pts.has(e.pointerId)) return;
        pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pts.size === 2 && pinch) {
          const [a, b] = [...pts.values()], d = Math.hypot(a.x - b.x, a.y - b.y), r = this.el.getBoundingClientRect();
          if (d / pinch.d > 1.45 || d / pinch.d < 0.69) { this.zoomAt((a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top, d > pinch.d ? 1 : -1); pinch.d = d; }
          return;
        }
        if (last) { const dx = e.clientX - last.x, dy = e.clientY - last.y; moved += Math.abs(dx) + Math.abs(dy); last = { x: e.clientX, y: e.clientY }; this.panBy(dx, dy); vp.classList.add("grabbing"); }
      });
      const up = (e) => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; if (!pts.size) { last = null; vp.classList.remove("grabbing"); } };
      vp.addEventListener("pointerup", up); vp.addEventListener("pointercancel", up);
      vp.addEventListener("click", (e) => { if (moved > 6) { e.stopPropagation(); e.preventDefault(); } }, true);
      let wheelAt = 0;
      vp.addEventListener("wheel", (e) => {
        e.preventDefault();
        if (Date.now() - wheelAt < 260) return;
        wheelAt = Date.now();
        const r = this.el.getBoundingClientRect();
        this.zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1 : -1);
      }, { passive: false });
      vp.addEventListener("dblclick", (e) => { const r = this.el.getBoundingClientRect(); this.zoomAt(e.clientX - r.left, e.clientY - r.top, 1); });
      vp.addEventListener("keydown", (e) => {
        const k = e.key, d = 90;
        if (k === "ArrowLeft") this.panBy(d, 0); else if (k === "ArrowRight") this.panBy(-d, 0);
        else if (k === "ArrowUp") this.panBy(0, d); else if (k === "ArrowDown") this.panBy(0, -d);
        else if (k === "+" || k === "=") this.zoomAt(this.w / 2, this.h / 2, 1);
        else if (k === "-" || k === "_") this.zoomAt(this.w / 2, this.h / 2, -1);
        else return;
        e.preventDefault();
      });
    }
  }

  JAMap.project = project;
  JAMap.unproject = unproject;
  window.JAMap = JAMap;
})();
