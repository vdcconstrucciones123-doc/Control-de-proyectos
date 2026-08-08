(function(){
  const storageKey = 'siteAuditLite_v1';
  const FRONT_TEMPLATE = [
    'Fachada Norte', 'Fachada Sur', 'Fachada Este', 'Fachada Oeste',
    'Estacionamiento', 'Accesos principales', 'Área común', 'Instalaciones',
    'Cimentación', 'Estructura', 'Instalaciones eléctricas', 'Instalaciones hidráulicas'
  ];
  const STATUS_BADGE = {
    'En proceso': 'bg-primary',
    'Terminado': 'bg-success',
    'Pendiente': 'bg-secondary',
    'Observado': 'bg-warning text-dark'
  };

  let state = {
    companyName: 'VDC CONSTRUCCIONES SAC',
    projectName: '',
    projectLocation: '',
    reportTitle: 'REPORTE FOTOGRÁFICO DE OBRA',
    forWhom: '',
    fromWhom: '',
    fronts: [],
    entries: [],
    autoMergeDup: false,
    combineByStatus: false
  };

  function $(id){ return document.getElementById(id); }

  function save(){ localStorage.setItem(storageKey, JSON.stringify(state)); }

  function load(){
    const v = localStorage.getItem(storageKey);
    if(v){
      state = { ...state, ...JSON.parse(v) };
      state.autoMergeDup = !!state.autoMergeDup;
      state.combineByStatus = !!state.combineByStatus;
    }
    renderAll();
  }

  function normalizeName(name){
    return (name || '').trim().toLowerCase().replace(/\s+/g, ' ');
  }

  function cleanFrontName(name){
    let value = (name || '').trim().replace(/\s+/g, ' ');
    if(!value) return '';

    while(/^frente\b/i.test(value)){
      value = value.replace(/^frente\s*[:\-]?\s*/i, '').trim();
    }

    value = value.replace(/^\s*#\s*/i, '').trim();
    value = value.replace(/^\d+\s*[:\-]?\s*/i, '').trim();

    if(!value) return 'Frente';
    return value;
  }

  function getFrontIndex(id){ return state.fronts.findIndex(f => f.id === id); }

  function frontNumber(id){
    const i = getFrontIndex(id);
    return i >= 0 ? i + 1 : null;
  }

  function formatFrontName(frontNameValue){
    const value = (frontNameValue || '').trim();
    if(!value) return '';
    return value.replace(/^(?:frente|frente\s*#?)\s*\d+\s*[:\-]*\s*/i, '').trim();
  }

  function frontLabel(front){
    const n = frontNumber(front.id);
    return n ? `F${n} · ${front.name}` : front.name;
  }

  function suggestFrontName(){
    return `Frente ${state.fronts.length + 1}`;
  }

  function findFrontByName(name){
    const key = normalizeName(cleanFrontName(name));
    return state.fronts.find(f => normalizeName(f.name) === key);
  }

  function findDuplicateGroups(){
    const map = {};
    state.fronts.forEach(f => {
      const key = normalizeName(f.name);
      if(!map[key]) map[key] = [];
      map[key].push(f);
    });
    return Object.values(map).filter(g => g.length > 1);
  }

  function mergeFronts(keepId, removeIds){
    removeIds.forEach(id => {
      state.entries.forEach(e => { if(e.frontId === id) e.frontId = keepId; });
      state.fronts = state.fronts.filter(f => f.id !== id);
    });
    save();
    renderAll();
  }

  function addFront(name, opts){
    const cleanedName = cleanFrontName(name) || name.trim();
    if(!cleanedName) return false;
    const existing = findFrontByName(cleanedName);
    const autoMerge = opts?.autoMerge ?? state.autoMergeDup;

    if(existing){
      if(autoMerge) return true;
      if(confirm(`Ya existe el frente "${existing.name}". ¿Fusionar con el existente?`)){
        return true;
      }
      return false;
    }

    const finalName = cleanedName || `Frente ${state.fronts.length + 1}`;
    state.fronts.push({ id: Date.now() + Math.random(), name: finalName });
    save();
    renderAll();
    return true;
  }

  function removeFront(id){
    state.fronts = state.fronts.filter(f => f.id !== id);
    state.entries = state.entries.filter(e => e.frontId !== id);
    save();
    renderAll();
  }

  function loadTemplate(){
    let added = 0;
    FRONT_TEMPLATE.forEach(name => {
      if(!findFrontByName(name)){
        state.fronts.push({ id: Date.now() + Math.random(), name });
        added++;
      }
    });
    if(added === 0){ alert('Todos los frentes de la plantilla ya existen.'); return; }
    save();
    renderAll();
    alert(`Plantilla cargada: ${added} frente(s) agregado(s).`);
  }

  function mergeAllDuplicates(){
    const groups = findDuplicateGroups();
    if(!groups.length){ alert('No hay frentes duplicados.'); return; }
    let merged = 0;
    groups.forEach(group => {
      const keep = group[0];
      const remove = group.slice(1).map(f => f.id);
      remove.forEach(id => {
        state.entries.forEach(e => { if(e.frontId === id) e.frontId = keep.id; });
        state.fronts = state.fronts.filter(f => f.id !== id);
        merged++;
      });
    });
    save();
    renderAll();
    alert(`Fusión completada: ${merged} frente(s) duplicado(s) eliminado(s).`);
  }

  function addEntry(frontId, status, desc, images){
    state.entries.unshift({
      id: Date.now(), frontId, status, desc, images,
      ts: new Date().toISOString()
    });
    save();
    renderAll();
  }

  function statusBadge(status, extra){
    const cls = STATUS_BADGE[status] || 'bg-info text-dark';
    const label = extra ? `${escapeHtml(status)} ${extra}` : escapeHtml(status);
    return `<span class="badge badge-status ${cls}">${label}</span>`;
  }

  function getReportItems(){
    if(!state.combineByStatus) return state.entries.map(e => ({ ...e, combined: false }));

    const map = new Map();
    const order = [];
    state.entries.forEach(e => {
      const key = `${e.frontId}::${e.status}`;
      if(!map.has(key)){
        map.set(key, { frontId: e.frontId, status: e.status, descs: [], images: [], ts: e.ts, count: 0, combined: true });
        order.push(key);
      }
      const g = map.get(key);
      if(e.desc) g.descs.push(e.desc);
      g.images.push(...(e.images || []));
      if(e.ts > g.ts) g.ts = e.ts;
      g.count++;
    });

    return order.map(key => {
      const g = map.get(key);
      return {
        frontId: g.frontId,
        status: g.status,
        desc: g.descs.join(' · '),
        images: g.images,
        ts: g.ts,
        combined: g.count > 1,
        count: g.count
      };
    });
  }

  function chunkImages(images, size = 2){
    const safeImages = Array.isArray(images) ? images : [];
    const chunks = [];
    for(let i = 0; i < safeImages.length; i += size){
      chunks.push(safeImages.slice(i, i + size));
    }
    return chunks;
  }

  function buildReportPages(entries){
    const pages = [];
    let currentPage = { rows: [], photoCount: 0 };

    const finalizeCurrentPage = () => {
      if(currentPage.rows.length){
        pages.push(currentPage);
        currentPage = { rows: [], photoCount: 0 };
      }
    };

    entries.forEach(entry => {
      const photos = Array.isArray(entry.images) ? entry.images : [];

      if(!photos.length){
        finalizeCurrentPage();
        pages.push({ rows: [{ entry, photos: [] }], photoCount: 0 });
        return;
      }

      let start = 0;
      while(start < photos.length){
        const space = 2 - currentPage.photoCount;
        const chunk = photos.slice(start, start + space);
        currentPage.rows.push({ entry, photos: chunk, continuation: start > 0 });
        currentPage.photoCount += chunk.length;
        start += chunk.length;

        if(currentPage.photoCount === 2){
          finalizeCurrentPage();
        }
      }
    });

    finalizeCurrentPage();
    return pages;
  }

  function renderAll(){
    $('companyName').value = state.companyName || 'VDC CONSTRUCCIONES SAC';
    $('projectName').value = state.projectName || '';
    $('projectLocation').value = state.projectLocation || '';
    $('reportTitle').value = state.reportTitle || 'REPORTE FOTOGRÁFICO DE OBRA';
    $('forWhom').value = state.forWhom || '';
    $('fromWhom').value = state.fromWhom || '';
    $('autoMergeDup').checked = !!state.autoMergeDup;
    $('combineByStatus').checked = !!state.combineByStatus;
    renderFrontList();
    renderDuplicateAlert();
    renderFrontSelect();
    renderReport();
  }

  function renderFrontList(){
    const container = $('frontList');
    container.innerHTML = '';
    if(!state.fronts.length){
      container.innerHTML = '<p class="text-muted small mb-0">Sin frentes. Agrega uno o carga la plantilla.</p>';
      return;
    }
    state.fronts.forEach(f => {
      const n = frontNumber(f.id);
      const div = document.createElement('div');
      div.className = 'front-item d-flex align-items-center justify-content-between';
      div.innerHTML = `
        <div class="d-flex align-items-center gap-2">
          <span class="badge bg-dark front-num">F${n}</span>
          <span>${escapeHtml(f.name)}</span>
        </div>
        <button data-id="${f.id}" class="btn btn-sm btn-danger rm-front">Eliminar</button>`;
      container.appendChild(div);
    });
    container.querySelectorAll('.rm-front').forEach(b => {
      b.addEventListener('click', e => {
        const id = Number(e.target.dataset.id);
        if(confirm('¿Eliminar frente y sus entradas?')) removeFront(id);
      });
    });
  }

  function renderDuplicateAlert(){
    const el = $('duplicateAlert');
    const groups = findDuplicateGroups();
    if(!groups.length){ el.innerHTML = ''; return; }

    el.innerHTML = groups.map(group => {
      const names = group.map(f => `F${frontNumber(f.id)} (${escapeHtml(f.name)})`).join(', ');
      const keepId = group[0].id;
      const removeIds = group.slice(1).map(f => f.id);
      return `<div class="dup-group small">
        <strong>Duplicados:</strong> ${names}
        <button class="btn btn-sm btn-warning ms-2 merge-group" data-keep="${keepId}" data-remove="${removeIds.join(',')}">Fusionar</button>
      </div>`;
    }).join('');

    el.querySelectorAll('.merge-group').forEach(btn => {
      btn.addEventListener('click', e => {
        const keepId = Number(e.target.dataset.keep);
        const removeIds = e.target.dataset.remove.split(',').map(Number);
        mergeFronts(keepId, removeIds);
      });
    });
  }

  function renderFrontSelect(){
    const sel = $('selectFront');
    sel.innerHTML = '';
    state.fronts.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f.id;
      opt.textContent = frontLabel(f);
      sel.appendChild(opt);
    });
  }

  function renderCompanyHeader(){
    return `
      <div class="report-page-header">
        <div class="report-header-line"></div>
      </div>
    `;
  }

  function renderPageFooter(){
    return `
      <div class="report-page-footer">
        <div class="report-footer-line"></div>
        <div class="report-footer-text">JR. BAHAMONDE 152, SURCO.</div>
      </div>
    `;
  }

  function renderCoverFooterBlock(){
    const company = (state.companyName || 'VDC CONSTRUCCIONES SAC').trim().toUpperCase();
    return `
      <div class="report-cover-footer-block">
        <div class="report-footer-separator"></div>
        <div class="report-footer-company">${escapeHtml(company)}</div>
        <div class="report-footer-address">JR. BAHAMONDE 152, SURCO.</div>
      </div>
    `;
  }

  function renderReport(){
    const rc = $('reportContainer');
    rc.innerHTML = '';

    const cover = document.createElement('div');
    cover.className = 'report-page report-cover';
    const reportTitle = (state.reportTitle || 'REPORTE FOTOGRÁFICO DE OBRA').trim();
    cover.innerHTML = `
      ${renderCompanyHeader()}
      <div class="report-page-tag">HOJA 1 • PORTADA</div>
      <div class="report-cover-title">${escapeHtml(reportTitle)}</div>
      ${renderCoverFooterBlock()}
    `;
    rc.appendChild(cover);

    const mainImage = (() => {
      const allImages = state.entries.flatMap(e => e.images || []);
      return allImages[0] || '';
    })();

    const infoPage = document.createElement('div');
    infoPage.className = 'report-page report-secondary-page';
    const fecha = new Date().toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    infoPage.innerHTML = `
      ${renderCompanyHeader()}
      <div class="report-page-tag">HOJA 2 • FICHA TÉCNICA</div>
      <div class="secondary-head">
        <div><strong>Proyecto:</strong> ${escapeHtml(state.projectName || 'Sin nombre')}</div>
        <div><strong>Ubicación:</strong> ${escapeHtml(state.projectLocation || 'Sin ubicación')}</div>
        <div><strong>Fecha:</strong> ${escapeHtml(fecha)}</div>
      </div>
      <div class="secondary-photo-wrap">
        ${mainImage ? `<img src="${mainImage}" class="secondary-main-photo" alt="Foto principal">` : '<div class="secondary-photo-placeholder">Insertar foto principal</div>'}
      </div>
      <div class="secondary-meta-row">
        <div class="secondary-meta-block">
          <label>Solicitado por</label>
          <div>${escapeHtml(state.forWhom || 'Sin dato')}</div>
        </div>
        <div class="secondary-meta-block">
          <label>Responsable</label>
          <div>${escapeHtml(state.fromWhom || 'Sin dato')}</div>
        </div>
      </div>
      ${renderPageFooter()}
    `;
    rc.appendChild(infoPage);

    const title = document.createElement('div');
    title.className = 'mb-3 report-header-inline';
    title.innerHTML = `<strong>${escapeHtml(state.projectName || 'Proyecto sin nombre')}</strong><br><small class="text-muted">Fecha: ${new Date().toLocaleString()}</small>`;
    rc.appendChild(title);

    if(!state.fronts.length){
      rc.innerHTML += '<p class="text-muted small">Sin frentes creados.</p>';
      return;
    }

    const items = getReportItems();
    if(!items.length){
      rc.innerHTML += '<p class="text-muted small">Sin observaciones en el reporte.</p>';
      return;
    }

    const grouped = state.fronts.map(front => ({
      front,
      entries: items.filter(e => e.frontId === front.id)
    })).filter(section => section.entries.length);

    let pageCounter = 3;

    grouped.forEach((section) => {
      const sectionPages = buildReportPages(section.entries);
      sectionPages.forEach(pageData => {
        const page = document.createElement('div');
        page.className = 'report-page report-front-page';

        const rowsHtml = pageData.rows.map(row => {
          const entry = row.entry;
          const extra = entry.combined ? `(${entry.count})` : '';
          const imgs = row.photos && row.photos.length ? row.photos.map(src => `<img src="${src}" class="thumb" alt="foto">`).join('') : '';
          const continuation = row.continuation ? `<div class="text-muted small mt-1">Continuación</div>` : '';

          return `
            <div class="report-entry">
              <div class="d-flex mb-1 flex-wrap gap-2 align-items-center">
                <div style="flex:1; min-width:180px">
                  <div class="text-muted small mb-1">${new Date(entry.ts).toLocaleString()}</div>
                  <div class="mt-1">${statusBadge(entry.status, extra)}</div>
                </div>
              </div>
              ${imgs ? `<div class="report-entry-images">${imgs}</div>` : ''}
              ${continuation}
              <div class="mt-2">${escapeHtml(entry.desc || '')}</div>
            </div>
          `;
        }).join('');

        page.innerHTML = `
          ${renderCompanyHeader()}
          <div class="report-page-tag">HOJA ${pageCounter} • ${escapeHtml(section.front.name.toUpperCase())}</div>
          <div class="front-report-group mb-3">
            <div class="mb-2"><span class="badge bg-dark me-2">F${frontNumber(section.front.id)}</span><strong>${escapeHtml(section.front.name)}</strong></div>
            ${rowsHtml}
          </div>
          ${renderPageFooter()}
        `;

        rc.appendChild(page);
        pageCounter += 1;
      });
    });
  }

  function escapeHtml(s){
    if(!s) return '';
    return s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  }

  function handleFiles(files, cb){
    const readers = [];
    for(const f of files){
      readers.push(new Promise(res => {
        const r = new FileReader();
        r.onload = ev => res(ev.target.result);
        r.readAsDataURL(f);
      }));
    }
    Promise.all(readers).then(list => cb(list));
  }

  function exportPdf(){
    const rc = $('reportContainer');
    if(!rc.innerHTML.trim() || !state.entries.length){
      alert('No hay contenido para exportar.');
      return;
    }

    const pages = Array.from(rc.querySelectorAll('.report-page'));
    if(!pages.length){
      alert('No hay páginas para exportar.');
      return;
    }

    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF('p', 'mm', 'a4');
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    const contentWidth = pageWidth - margin * 2;
    const companyName = (state.companyName || 'VDC CONSTRUCCIONES SAC').trim().toUpperCase();
    const footerText = 'JR. BAHAMONDE 152, SURCO.';

    function drawFrame(pageNum){
      pdf.setDrawColor(0, 0, 0);
      pdf.setLineWidth(0.7);
      pdf.line(margin, 12, pageWidth - margin, 12);
      pdf.line(margin, pageHeight - 12, pageWidth - margin, pageHeight - 12);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(10);
      pdf.text(companyName, pageWidth / 2, 18, { align: 'center' });
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(8);
      pdf.text('HOJA ' + pageNum, pageWidth / 2, 24, { align: 'center' });
      pdf.text(footerText, pageWidth / 2, pageHeight - 17, { align: 'center' });
    }

    Promise.all(pages.map(pageEl => html2canvas(pageEl, {
      scale: 2,
      useCORS: true,
      backgroundColor: '#ffffff'
    }).then(canvas => ({
      canvas,
      width: canvas.width,
      height: canvas.height
    })))).then(renderedPages => {
      renderedPages.forEach(({ canvas }, idx) => {
        if(idx > 0) pdf.addPage();
        drawFrame(idx + 1);

        const imgData = canvas.toDataURL('image/jpeg', 0.95);
        const imgWidth = contentWidth;
        const imgHeight = (canvas.height * imgWidth) / canvas.width;
        const topY = 28;
        const maxHeight = pageHeight - 42;
        const finalHeight = Math.min(imgHeight, maxHeight);
        const finalWidth = (canvas.width * finalHeight) / canvas.height;

        pdf.addImage(
          imgData,
          'JPEG',
          (pageWidth - finalWidth) / 2,
          topY,
          finalWidth,
          finalHeight,
          undefined,
          'FAST'
        );
      });

      const fileName = (state.projectName || 'reporte').replace(/[^a-zA-Z0-9\s-_]/g, '').trim() || 'reporte';
      pdf.save(fileName + '.pdf');
    }).catch(err => {
      console.error(err);
      alert('Error generando PDF: ' + err.message);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    load();

    $('addFrontBtn').addEventListener('click', () => {
      const name = $('frontName').value.trim();
      if(!name){ alert('Ingrese nombre del frente'); return; }
      if(addFront(name)){ $('frontName').value = suggestFrontName(); }
    });

    $('frontName').value = suggestFrontName();

    $('frontName').addEventListener('keydown', e => {
      if(e.key === 'Enter') $('addFrontBtn').click();
    });

    $('companyName').addEventListener('input', e => {
      state.companyName = e.target.value || 'VDC CONSTRUCCIONES SAC';
      save();
      renderReport();
    });

    $('projectName').addEventListener('input', e => {
      state.projectName = e.target.value;
      save();
      renderReport();
    });

    $('projectLocation').addEventListener('input', e => {
      state.projectLocation = e.target.value;
      save();
      renderReport();
    });

    $('reportTitle').addEventListener('input', e => {
      state.reportTitle = e.target.value || 'REPORTE FOTOGRÁFICO DE OBRA';
      save();
      renderReport();
    });

    $('forWhom').addEventListener('input', e => {
      state.forWhom = e.target.value;
      save();
      renderReport();
    });

    $('fromWhom').addEventListener('input', e => {
      state.fromWhom = e.target.value;
      save();
      renderReport();
    });

    $('autoMergeDup').addEventListener('change', e => {
      state.autoMergeDup = e.target.checked;
      save();
    });

    $('combineByStatus').addEventListener('change', e => {
      state.combineByStatus = e.target.checked;
      save();
      renderReport();
    });

    $('loadTemplateBtn').addEventListener('click', loadTemplate);
    $('mergeAllDupBtn').addEventListener('click', mergeAllDuplicates);

    const getEntryPhotoFiles = () => [
      ...($('photoInput')?.files ? Array.from($('photoInput').files) : []),
      ...($('photoCameraInput')?.files ? Array.from($('photoCameraInput').files) : [])
    ];

    const clearEntryPhotoInputs = () => {
      if($('photoInput')) $('photoInput').value = '';
      if($('photoCameraInput')) $('photoCameraInput').value = '';
    };

    $('takePhotoBtn')?.addEventListener('click', () => $('photoCameraInput')?.click());
    $('choosePhotoBtn')?.addEventListener('click', () => $('photoInput')?.click());

    $('addEntryBtn').addEventListener('click', () => {
      const frontId = Number($('selectFront').value);
      if(!frontId){ alert('Cree al menos un frente'); return; }
      const status = $('statusSelect').value;
      const desc = $('entryDesc').value.trim();
      const files = getEntryPhotoFiles();
      if(files && files.length){
        handleFiles(files, list => {
          addEntry(frontId, status, desc, list);
          clearEntryPhotoInputs();
          $('entryDesc').value = '';
        });
      } else {
        addEntry(frontId, status, desc, []);
        $('entryDesc').value = '';
      }
    });

    $('exportPdfBtn').addEventListener('click', exportPdf);

    $('saveJsonBtn').addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(state)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (state.projectName || 'site-audit') + '.json';
      a.click();
      URL.revokeObjectURL(url);
    });

    $('loadJsonBtn').addEventListener('click', () => {
      const inp = document.createElement('input');
      inp.type = 'file';
      inp.accept = 'application/json';
      inp.onchange = e => {
        const f = e.target.files[0];
        if(!f) return;
        const r = new FileReader();
        r.onload = ev => {
          try {
            state = { ...state, ...JSON.parse(ev.target.result) };
            save();
            renderAll();
          } catch(err){ alert('JSON inválido'); }
        };
        r.readAsText(f);
      };
      inp.click();
    });
  });
})();
