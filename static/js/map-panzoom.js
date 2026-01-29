// Simple pan & zoom for inline SVG with dynamic map loading
(() => {
  function qs(sel) { return document.querySelector(sel); }

  const wrapper = qs('#map-svg-wrapper');
  const zoomInBtn = qs('#zoom-in');
  const zoomOutBtn = qs('#zoom-out');
  const zoomResetBtn = qs('#zoom-reset');

  let svgEl; // the loaded SVG element
  let viewport; // group inside svg that we'll transform

  // transform state
  let scale = 1;
  let minScale = 0.2;
  let maxScale = 10;
  let translate = { x: 0, y: 0 };
  const zoomInFactor = 4.0; // initial extra zoom applied after fitting (increase to make 'super close')

  // pointer drag state
  let dragging = false;
  let lastPos = null;
  let lastWorld = null;
  const panSensitivity = 1.6; // increase to make panning more responsive
  let lastPointerClient = null; // tracks last pointer position over svg (client coords)

  // event listeners that need to be cleaned up
  let eventListeners = [];

  function setTransform() {
    if (!viewport) return;
    viewport.setAttribute('transform', `translate(${translate.x} ${translate.y}) scale(${scale})`);
  }

  // cleanup function to remove event listeners
  function cleanup() {
    eventListeners.forEach(({ element, event, handler, options }) => {
      element.removeEventListener(event, handler, options);
    });
    eventListeners = [];
    
    if (svgEl) {
      try { svgEl.releasePointerCapture?.(); } catch (e) {}
    }
    
    dragging = false;
    lastPos = null;
    lastWorld = null;
    lastPointerClient = null;
  }

  // helper to add event listener and track it for cleanup
  function addEventListenerTracked(element, event, handler, options) {
    element.addEventListener(event, handler, options);
    eventListeners.push({ element, event, handler, options });
  }

  // load the SVG file and inline it
  function loadMap(svgPath) {
    // cleanup previous state
    cleanup();
    
    // reset transform state
    scale = 1;
    translate = { x: 0, y: 0 };
    
    fetch(svgPath)
      .then(r => r.text())
      .then(text => {
      wrapper.innerHTML = text;
      svgEl = wrapper.querySelector('svg');
      if (!svgEl) return console.error('No <svg> found in', svgPath);

      // ensure svg fills the wrapper
      svgEl.style.width = '100%';
      svgEl.style.height = '100%';
      svgEl.style.maxWidth = 'none';

      // create a group wrapper if not present
      let g = svgEl.querySelector('g#viewport-group');
      if (!g) {
        g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('id', 'viewport-group');

        // move all existing children into g
        while (svgEl.firstChild) {
          g.appendChild(svgEl.firstChild);
        }
        svgEl.appendChild(g);
      }
      viewport = g;

      // Prefer the SVG to preserve aspect ratio and center content visually
      try { svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet'); } catch (e) {}

      // compute a scale that fits the viewport group's bbox into the wrapper, then center it
      try {
        const padding = 40; // pixels padding inside wrapper
        const bbox = viewport.getBBox();
        const wrapperW = wrapper.clientWidth - padding;
        const wrapperH = wrapper.clientHeight - padding;
        let fitScale = 1;
        if (bbox.width > 0 && bbox.height > 0) {
          // fill height: scale so the bbox height fills the wrapper height
          fitScale = (wrapperH / bbox.height) * 1.0;
        }
  // apply an initial zoom factor to make the map larger on open
  fitScale = fitScale * zoomInFactor;
  // don't exceed maxScale and don't go below minScale
  fitScale = clamp(fitScale, minScale, maxScale);

  // set scale and translate so the bbox is centered in the SVG viewBox center
  scale = fitScale;
        // center of bbox in SVG coords
        const cx = bbox.x + bbox.width / 2;
        const cy = bbox.y + bbox.height / 2;
        // use SVG viewBox center if available so centering is correct when viewBox is present
        let vbCenterX = 0, vbCenterY = 0;
        if (svgEl.viewBox && svgEl.viewBox.baseVal) {
          vbCenterX = svgEl.viewBox.baseVal.x + svgEl.viewBox.baseVal.width / 2;
          vbCenterY = svgEl.viewBox.baseVal.y + svgEl.viewBox.baseVal.height / 2;
        } else {
          // fallback: approximate using wrapper center in world coords
          const rect = svgEl.getBoundingClientRect();
          const wc = screenToWorld(rect.width / 2, rect.height / 2);
          vbCenterX = wc.x; vbCenterY = wc.y;
        }

        // compute translate in SVG user units so that (cx,cy) -> viewBox center after scaling
        translate.x = vbCenterX - (cx * scale);
        translate.y = vbCenterY - (cy * scale);
      } catch (e) {
        // fallback: leave translate/scale as-is
      }

      setTransform();

      // Additional centering step: compute screen-space delta between bbox center and wrapper center
      try {
        const bbox = viewport.getBBox();
        const cx = bbox.x + bbox.width / 2;
        const cy = bbox.y + bbox.height / 2;
        // center point of bbox in screen coordinates
        const pt = svgEl.createSVGPoint(); pt.x = cx; pt.y = cy;
        const screenPt = pt.matrixTransform(svgEl.getScreenCTM());
        const wrapperRect = wrapper.getBoundingClientRect();
        const wrapperCenterScreen = { x: wrapperRect.left + wrapperRect.width / 2, y: wrapperRect.top + wrapperRect.height / 2 };
        const dxScreen = wrapperCenterScreen.x - screenPt.x;
        const dyScreen = wrapperCenterScreen.y - screenPt.y;
        // convert screen delta back to SVG user units
        const p1 = svgEl.createSVGPoint(); p1.x = screenPt.x; p1.y = screenPt.y;
        const p2 = svgEl.createSVGPoint(); p2.x = screenPt.x + dxScreen; p2.y = screenPt.y + dyScreen;
        const user1 = p1.matrixTransform(svgEl.getScreenCTM().inverse());
        const user2 = p2.matrixTransform(svgEl.getScreenCTM().inverse());
        const deltaUser = { x: user2.x - user1.x, y: user2.y - user1.y };
        // apply delta to translate (the translate is in user units before scaling)
        translate.x += deltaUser.x;
        translate.y += deltaUser.y;
        setTransform();
      } catch (e) {
        // non-fatal
      }

      // event listeners
      addEventListenerTracked(svgEl, 'wheel', onWheel, { passive: false });
      addEventListenerTracked(svgEl, 'pointerdown', onPointerDown);
      addEventListenerTracked(svgEl, 'pointermove', (e) => { lastPointerClient = { x: e.clientX, y: e.clientY }; });
      addEventListenerTracked(window, 'pointermove', onPointerMove);
      addEventListenerTracked(window, 'pointerup', onPointerUp);

      // buttons
      addEventListenerTracked(zoomInBtn, 'click', () => {
        if (lastPointerClient) zoomByAtClient(1.2, lastPointerClient.x, lastPointerClient.y);
        else zoomBy(1.2);
      });
      addEventListenerTracked(zoomOutBtn, 'click', () => {
        if (lastPointerClient) zoomByAtClient(1/1.2, lastPointerClient.x, lastPointerClient.y);
        else zoomBy(1/1.2);
      });
      addEventListenerTracked(zoomResetBtn, 'click', resetView);

      // touch double-tap for reset
      let lastTap = 0;
      addEventListenerTracked(svgEl, 'touchend', e => {
        const t = Date.now();
        if (t - lastTap < 300) resetView();
        lastTap = t;
      });

      // Re-center/fit when wrapper resizes (modal open or window resize)
      try {
        const ro = new ResizeObserver(() => {
          // recompute fit and center similar to resetView
          resetView();
        });
        ro.observe(wrapper);
      } catch (e) {
        // ResizeObserver not available: ignore
      }

      // wire up clickable rects (plots) to open modal with sequential numbers
      try {
        const modalOverlay = document.getElementById('plotModalOverlay');
        const modalTitle = document.getElementById('modalPlotTitle');
        const modalBlock = document.getElementById('modalBlock');
        const modalPlot = document.getElementById('modalPlot');
        const modalRow = document.getElementById('modalRow');
        const modalPrice = document.getElementById('modalPrice');
        const modalAvailability = document.getElementById('modalAvailability');
        const closeModalBtn = document.getElementById('closeModalBtn');
        const reserveBtn = document.getElementById('reserveBtn');

        const rects = viewport.querySelectorAll('rect');
        // Filter out rects that are in defs or other non-plot containers
        const plotRects = Array.from(rects).filter(r => {
          // Only include rects that are actual plots (not in defs, etc.)
          let parent = r.parentElement;
          while (parent && parent !== viewport) {
            if (parent.tagName.toLowerCase() === 'defs') return false;
            parent = parent.parentElement;
          }
          return true;
        });
        
        plotRects.forEach((r, idx) => {
          // Determine plot number based on which map is loaded
          let plotNum;
          if (svgPath.includes('apartment_1.svg')) {
            plotNum = 284 + idx; // Apartment 1 plots: 284-333 (continuous from main map)
          } else if (svgPath.includes('apartment_2.svg')) {
            plotNum = 334 + idx; // Apartment 2 plots: 334-373 (continuous from apartment 1)
          } else {
            plotNum = idx + 1; // Main map plots: 1, 2, 3... up to 283
          }
          r.dataset.plot = plotNum;
          r.style.cursor = 'pointer';

          // prevent the map pan from starting when interacting with rects
          r.addEventListener('pointerdown', (ev) => { ev.stopPropagation(); ev.preventDefault(); });

          r.addEventListener('click', (ev) => {
            ev.stopPropagation();
            ev.preventDefault();
            // populate modal with demo values (replace with real data later)
            if (modalBlock) modalBlock.textContent = Math.ceil(plotNum/10); // demo block calc
            if (modalPlot) modalPlot.textContent = plotNum;
            if (modalRow) modalRow.textContent = ((plotNum % 5) || 5);
            if (modalPrice) modalPrice.textContent = `₱${(20000 + (plotNum * 1000)).toLocaleString()}`;
            if (modalAvailability) {
              modalAvailability.textContent = 'Available';
              modalAvailability.style.color = '#10b981';
            }
            if (modalTitle) modalTitle.textContent = `Block #: ${Math.ceil(plotNum/10)}`;
            if (modalOverlay) modalOverlay.style.display = 'flex';
          });

          // create a centered label for the rect so each plot shows its number
          try {
            // get numeric geometry from attributes
            const xAttr = r.getAttribute('x');
            const yAttr = r.getAttribute('y');
            const wAttr = r.getAttribute('width');
            const hAttr = r.getAttribute('height');
            if (xAttr != null && yAttr != null && wAttr != null && hAttr != null) {
              const bx = parseFloat(xAttr);
              const by = parseFloat(yAttr);
              const bw = parseFloat(wAttr);
              const bh = parseFloat(hAttr);
              const cx = bx + bw / 2;
              const cy = by + bh / 2;

              const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
              txt.textContent = plotNum;
              // position and alignment
              txt.setAttribute('x', cx);
              txt.setAttribute('y', cy);
              txt.setAttribute('text-anchor', 'middle');
              txt.setAttribute('dominant-baseline', 'central');
              txt.setAttribute('pointer-events', 'none'); // let clicks go to rects underneath

              // font sizing: consider rect dimensions and number of digits so multi-digit numbers fit
              const digits = String(plotNum).length;
              const minFont = 6; // smallest readable size
              const fontSizeByHeight = bh * 0.6;
              // allow less width per digit so longer numbers shrink to fit horizontally
              const fontSizeByWidth = (bw * 0.8) / Math.max(1, digits);
              const fontSize = Math.max(minFont, Math.min(fontSizeByHeight, fontSizeByWidth));
              txt.setAttribute('font-size', fontSize);
              txt.style.fill = '#0b0b0b';
              txt.style.fontWeight = '700';
              txt.style.fontFamily = 'Arial, Helvetica, sans-serif';
              // add a subtle white stroke (halo) so numbers stay readable over map; scale with font
              txt.setAttribute('stroke', '#ffffff');
              txt.setAttribute('stroke-width', Math.max(0.35, fontSize * 0.12));
              txt.setAttribute('paint-order', 'stroke');
              // ensure perfectly centered vertically across browsers
              txt.setAttribute('dominant-baseline', 'middle');

              // Prevent the label text from receiving focus or being highlighted/selected
              try {
                txt.setAttribute('focusable', 'false');
                txt.setAttribute('draggable', 'false');
                txt.style.userSelect = 'none';
                txt.style.webkitUserSelect = 'none';
                txt.style.msUserSelect = 'none';
                // prevent default on mousedown to stop browser text selection
                txt.setAttribute('onmousedown', 'event.preventDefault();');
              } catch (selErr) {
                // non-fatal if styling isn't supported
              }

              // if the rect has a transform, copy it to the text so the label rotates/scales similarly
              if (r.hasAttribute('transform')) txt.setAttribute('transform', r.getAttribute('transform'));

              // append label as a sibling so it renders above the rect
              const parent = r.parentNode || viewport;
              parent.appendChild(txt);
            }
          } catch (labelErr) {
            console.warn('Failed to create plot label for', r, labelErr);
          }
        });

        if (closeModalBtn && modalOverlay) closeModalBtn.addEventListener('click', () => { modalOverlay.style.display = 'none'; });
        if (modalOverlay) modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) modalOverlay.style.display = 'none'; });
        if (reserveBtn) reserveBtn.addEventListener('click', () => { console.log('Reserve clicked'); if (modalOverlay) modalOverlay.style.display = 'none'; });
      } catch (err) {
        console.warn('Modal wiring skipped', err);
      }

      // dispatch custom event to signal SVG is loaded
      const event = new CustomEvent('svgloaded', { 
        detail: { svgPath, svgEl, viewport } 
      });
      window.dispatchEvent(event);
    })
    .catch(err => console.error('Failed to load svg', err));
  }

  function svgPoint(clientX, clientY) {
    const pt = svgEl.createSVGPoint();
    pt.x = clientX; pt.y = clientY;
    return pt.matrixTransform(svgEl.getScreenCTM().inverse());
  }

  function screenToWorldClient(clientX, clientY) {
    // clientX/clientY are window (client) coordinates
    const pt = svgEl.createSVGPoint(); pt.x = clientX; pt.y = clientY;
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return { x: clientX, y: clientY };
    const inv = ctm.inverse();
    const transformed = pt.matrixTransform(inv);
    return {
      x: (transformed.x - translate.x) / scale,
      y: (transformed.y - translate.y) / scale
    };
  }

  function onWheel(e) {
    e.preventDefault();
    const delta = -e.deltaY;
    const zoomFactor = delta > 0 ? 1.1 : 1/1.1;
    // zoom toward mouse position
  const before = screenToWorldClient(e.clientX, e.clientY);
  scale = clamp(scale * zoomFactor, minScale, maxScale);
  const after = screenToWorldClient(e.clientX, e.clientY);

    // adjust translate so the point under cursor stays in place
    translate.x += (after.x - before.x) * scale;
    translate.y += (after.y - before.y) * scale;

    setTransform();
  }

  function screenToWorld(sx, sy) {
    // convert screen (wrapper) coordinates to SVG local coords (before transform)
    const pt = svgEl.createSVGPoint(); pt.x = sx; pt.y = sy;
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return { x: sx, y: sy };
    const inv = ctm.inverse();
    const transformed = pt.matrixTransform(inv);
    // account for current translate/scale on viewport
    return {
      x: (transformed.x - translate.x) / scale,
      y: (transformed.y - translate.y) / scale
    };
  }

  function onPointerDown(e) {
    if (e.pointerType === 'mouse' && e.button !== 0) return; // only left button
    dragging = true;
    lastPos = { x: e.clientX, y: e.clientY };
    // capture a world-space position for smoother, correctly-scaled panning
    try {
      const rect = svgEl.getBoundingClientRect();
      lastWorld = screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
    } catch (err) {
      lastWorld = null;
    }
    svgEl.setPointerCapture?.(e.pointerId);
  }

  function onPointerMove(e) {
    if (!dragging || !lastPos) return;
    // Convert pointer movement to world-space delta (consistent regardless of scale)
    try {
      const rect = svgEl.getBoundingClientRect();
      const before = screenToWorld(lastPos.x - rect.left, lastPos.y - rect.top);
      const after = screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
      // apply the world delta to translate (scale to keep behavior consistent)
      translate.x += (after.x - before.x) * scale * panSensitivity;
      translate.y += (after.y - before.y) * scale * panSensitivity;
      lastPos = { x: e.clientX, y: e.clientY };
    } catch (err) {
      // fallback to previous pixel-based approach if anything goes wrong
      const dx = e.clientX - lastPos.x;
      const dy = e.clientY - lastPos.y;
      translate.x += dx * panSensitivity;
      translate.y += dy * panSensitivity;
      lastPos = { x: e.clientX, y: e.clientY };
    }
    setTransform();
  }

  function onPointerUp(e) {
    dragging = false;
    lastPos = null;
    try { svgEl.releasePointerCapture?.(e.pointerId); } catch (err) {}
  }

  function zoomBy(factor) {
    // center in client coords
    const rect = wrapper.getBoundingClientRect();
    const clientCenter = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    zoomByAtClient(factor, clientCenter.x, clientCenter.y);
  }

  function zoomByAtClient(factor, clientX, clientY) {
    const before = screenToWorldClient(clientX, clientY);
    scale = clamp(scale * factor, minScale, maxScale);
    const after = screenToWorldClient(clientX, clientY);
    translate.x += (after.x - before.x) * scale;
    translate.y += (after.y - before.y) * scale;
    setTransform();
  }

  function resetView() {
    // Reset to the computed fit-to-wrapper view if possible
    try {
      // recompute fit scale and center as during load
  const bbox = viewport.getBBox();
      const padding = 40;
      const wrapperW = wrapper.clientWidth - padding;
      const wrapperH = wrapper.clientHeight - padding;
      let fitScale = 1;
  if (bbox.width > 0 && bbox.height > 0) fitScale = (wrapperH / bbox.height) * 1.0;
  fitScale = fitScale * zoomInFactor;
  fitScale = clamp(fitScale, minScale, maxScale);
      scale = fitScale;
      const cx = bbox.x + bbox.width / 2;
      const cy = bbox.y + bbox.height / 2;
      // use viewBox center when available
      if (svgEl.viewBox && svgEl.viewBox.baseVal) {
        const vb = svgEl.viewBox.baseVal;
        translate.x = (vb.x + vb.width / 2) - (cx * scale);
        translate.y = (vb.y + vb.height / 2) - (cy * scale);
      } else {
        translate.x = (wrapper.clientWidth / 2 - (cx * scale));
        translate.y = (wrapper.clientHeight / 2 - (cy * scale));
      }
    } catch (e) {
      scale = 1; translate = { x: 0, y: 0 };
    }
    setTransform();
  }

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  // expose loadMap function on window
  window.loadMap = loadMap;

  // initialize with default map
  loadMap('/static/map.svg');
})();
