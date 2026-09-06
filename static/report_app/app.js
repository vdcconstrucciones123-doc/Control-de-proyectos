(function(){
  const currentUser = document.body?.dataset?.currentUser || 'guest';
  const storageKey = `siteAuditLite_v1_${currentUser}`;
  const storageMetaKey = 'siteAuditLite_v1_meta';
  const PROJECT_ROLE_LABELS = {
    viewer: 'Lector',
    editor: 'Editor',
    admin: 'Administrador'
  };
  const FRONT_TEMPLATE = [
    'Fachada Norte', 'Fachada Sur', 'Fachada Este', 'Fachada Oeste',
    'Estacionamiento', 'Accesos principales', 'Área común', 'Instalaciones',
    'Cimentación', 'Estructura', 'Instalaciones eléctricas', 'Instalaciones hidráulicas'
  ];
  const STATUS_BADGE = {
    'En proceso': 'bg-primary',
    'Terminado': 'bg-success',
    'Pendiente': 'bg-secondary',
    'Observado': 'bg-warning text-dark',
    'Recepción': 'bg-primary',
    'Validación': 'bg-info text-dark',
    'Entrega': 'bg-success'
  };
  const PDF_RENDER_SCALE = 1.25;
  const PDF_IMAGE_QUALITY = 0.82;
  const PDF_PAGE_MARGIN_MM = 1.5;
  const UPLOAD_MAX_DIMENSION = 1800;
  const UPLOAD_IMAGE_QUALITY = 0.8;
  const UPLOAD_FILE_MIME = 'image/jpeg';
  let pendingCoverPhotoFile = null;
   let pendingProjectPhotoFile = null;
  let pendingProfilePhotoFile = null;
  let showProjectShare = false;
  let projectDashboardView = 'summary';
  let projectDashboardReportType = '';
  let issueFormManuallyOpened = false;
  let selectedPlanId = null;
  let planZoom = 1;
  let planMarkerMode = false;
  let planPanX = 0;
  let planPanY = 0;
  const planMaxZoom = 10;
  const planPdfCache = new Map();
  let planRenderToken = 0;
  let previewRenderToken = 0;
  let issuePlanPoint = null;
  let pendingProjectPhotoId = null;
  let pendingRemovedEntryImageIds = new Set();

  let state = {
    projects: [],
    currentProjectId: null,
    currentReportId: null,
    selectionStage: 'project',
    showProjectForm: true,
    companyName: 'VDC CONSTRUCCIONES SAC',
    projectName: '',
    projectLocation: '',
    reportType: '',
    reportTitle: 'REPORTE FOTOGRÁFICO DE OBRA',
    reportWeek: '8',
    reportDate: new Date().toISOString().slice(0, 10),
    reportMetaComplete: false,
    existingReportOpen: false,
    showPreviewMode: false,
    workspaceView: 'fronts',
    currentFrontId: null,
    selectedEntryId: null,
    editingFrontId: null,
    laborDateFrom: '',
    laborDateTo: '',
    forWhom: '',
    fromWhom: '',
    objectiveText: '',
    analysisText: '',
    conclusionText: '',
    recommendationText: '',
    conclusionItems: [],
    recommendationItems: [],
    coverImage: '',
    fronts: [],
    entries: [],
    autoMergeDup: false,
    combineByStatus: false,
    editingEntryId: null,
    showIssueForm: false,
    editingProjectInfo: false,
    editingReportMeta: false
  };

  function $(id){ return document.getElementById(id); }
  function isEquipmentReport(){ return state.reportType === 'equipos'; }
  function getReportTypeLabel(type){
    const value = type || state.reportType || '';
    if(value === 'incidencia') return 'Reporte de incidencia';
    if(value === 'equipos') return 'Recepción y entrega de equipos';
    if(value === 'avances') return 'Reporte de avances';
    return '';
  }
  function formatPlanDate(value){
    if(!value) return 'Sin fecha';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Sin fecha' : date.toLocaleDateString('es-PE');
  }
  function getClampedViewport(page, scale, maxDimension = 4096, maxArea = 16000000){
    let viewport = page.getViewport({ scale });
    const limitRatio = Math.max(1, Math.max(viewport.width, viewport.height) / maxDimension, Math.sqrt((viewport.width * viewport.height) / maxArea));
    if(limitRatio > 1){
      viewport = page.getViewport({ scale: scale / limitRatio });
    }
    return viewport;
  }
  function getPlanRenderSettings(){
    const isMobile = window.matchMedia?.('(max-width: 767px)').matches || window.innerWidth < 768;
    return isMobile
      ? { quality: 1.1, devicePixelRatio: 1, maxDimension: 1800, maxArea: 4000000 }
      : { quality: 2, devicePixelRatio: Math.min(window.devicePixelRatio || 1, 1.5), maxDimension: 3000, maxArea: 9000000 };
  }
  let lastPlanRenderSignature = null;
  let planViewerInFlightSignature = null;
  let planViewerInFlightPromise = null;
  function renderPlanViewer(plan, project){
    const empty = $('planViewerEmpty');
    const viewer = $('planViewer');
    const canvas = $('planCanvas');
    if(!plan || !window.pdfjsLib || !empty || !viewer || !canvas){
      empty?.classList.remove('d-none');
      viewer?.classList.add('d-none');
      lastPlanRenderSignature = null;
      return;
    }
    empty.classList.add('d-none');
    viewer.classList.remove('d-none');
    $('planViewerName').textContent = plan.name;
    const originalLink = $('planOriginalLink');
    if(originalLink) originalLink.href = plan.url;
    const issueMarkerSignature = (project?.reports || []).flatMap(report => (report.type === 'incidencia' || report.type === 'avances')
      ? (report.entries || []).filter(entry => Number(entry.planId) === Number(plan.id) && entry.planX != null && entry.planY != null).map(entry => `${entry.id}:${entry.planX}:${entry.planY}:${entry.buildingLocation}:${entry.status}`)
      : []);
    const renderSignature = JSON.stringify({
      planId: plan.id,
      canEdit: !!project?.canEdit,
      markerMode: planMarkerMode,
      width: $('planCanvasWrap')?.clientWidth || 0,
      issueMarkerSignature,
      planMarkers: (plan.markers || []).map(marker => `${marker.id}:${marker.x}:${marker.y}`)
    });
    // Avoid re-fetching/re-rasterizing the same plan on every renderAll() pass, which overlapped renders and left mobile devices stuck on "Cargando plano...".
    if(renderSignature === lastPlanRenderSignature && canvas.width > 0){
      return;
    }
    // Coalesce simultaneous identical calls (e.g. renderAll() firing from several places at once) into a single in-flight render.
    if(renderSignature === planViewerInFlightSignature && planViewerInFlightPromise){
      return planViewerInFlightPromise;
    }
    const renderToken = ++planRenderToken;
    $('planViewerHint').textContent = 'Cargando plano...';
    planViewerInFlightSignature = renderSignature;
    planViewerInFlightPromise = (async () => {
      try {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        let pdfPromise = planPdfCache.get(plan.url);
        if(!pdfPromise){
          pdfPromise = window.pdfjsLib.getDocument(plan.url).promise;
          planPdfCache.set(plan.url, pdfPromise);
        }
        const pdf = await pdfPromise;
        if(renderToken !== planRenderToken) return;
        const page = await pdf.getPage(1);
        const baseViewport = page.getViewport({ scale: 1 });
        $('planCanvasWrap')?.classList.toggle('is-landscape-plan', baseViewport.width > baseViewport.height);
        const width = Math.max(320, Math.min(1100, $('planCanvasWrap').clientWidth || 700));
        const baseScale = width / baseViewport.width;
        const baseHeight = baseViewport.height * baseScale;
        const renderSettings = getPlanRenderSettings();
        const svgContainer = $('planSvg');
        if(svgContainer) svgContainer.replaceChildren();
        const tileLayer = $('planTiles');
        if(tileLayer) tileLayer.replaceChildren();
        const rasterViewport = getClampedViewport(
          page,
          baseScale * renderSettings.quality * renderSettings.devicePixelRatio,
          renderSettings.maxDimension,
          renderSettings.maxArea
        );
        const context = canvas.getContext('2d');
        context.clearRect(0, 0, canvas.width, canvas.height);
        canvas.width = rasterViewport.width;
        canvas.height = rasterViewport.height;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${baseHeight}px`;
        canvas.style.display = 'block';
        await page.render({ canvasContext: context, viewport: rasterViewport }).promise;
        if(renderToken !== planRenderToken) return;
        const layer = $('planMarkers');
        const stage = $('planCanvasStage');
        if(stage){
          stage.style.width = `${width}px`;
          stage.style.height = `${baseHeight}px`;
        }
        if(layer){
          layer.style.width = `${width}px`;
          layer.style.height = `${baseHeight}px`;
          layer.style.left = '0px';
          layer.style.top = '0px';
        }
        applyPlanTransform();
        const issueMarkers = (project?.reports || []).flatMap(report => (report.type === 'incidencia' || report.type === 'avances')
          ? (report.entries || []).filter(entry => Number(entry.planId) === Number(plan.id) && entry.planX != null && entry.planY != null).map(entry => ({ id: `issue-${entry.id}`, entryId: entry.id, page: 1, x: entry.planX, y: entry.planY, label: `${entry.buildingLocation || 'Punto'} · ${entry.status || 'Sin estado'} · ${entry.responsibleCompany || 'Sin empresa'}` }))
          : []);
        renderPlanMarkers(issueMarkers.length ? issueMarkers : (plan.markers || []), project?.canEdit);
        $('planZoomValue').textContent = `${Math.round(planZoom * 100)}%`;
        const markerModeButton = $('planMarkerModeBtn');
        if(markerModeButton){
          markerModeButton.classList.toggle('d-none', !project?.canEdit);
          markerModeButton.setAttribute('aria-pressed', String(planMarkerMode));
        }
        $('planCanvasWrap')?.classList.toggle('is-marker-mode', !!planMarkerMode && !!project?.canEdit);
        lastPlanRenderSignature = renderSignature;
      } catch(error) {
        lastPlanRenderSignature = null;
        $('planViewerHint').textContent = 'No se pudo visualizar el PDF. Ábrelo desde la lista.';
      } finally {
        if(planViewerInFlightSignature === renderSignature){
          planViewerInFlightSignature = null;
          planViewerInFlightPromise = null;
        }
      }
    })();
    return planViewerInFlightPromise;
  }
  function renderPlanMarkers(markers, canEdit){
    const layer = $('planMarkers');
    if(!layer) return;
    const markerScale = Math.max(0.1, Math.min(1, 1 / planZoom));
    layer.innerHTML = markers.filter(marker => Number(marker.page) === 1).map((marker, index) => `
      <button type="button" class="plan-marker" data-marker-id="${marker.id}" data-entry-id="${marker.entryId || ''}" style="left:${marker.x * 100}%;top:${marker.y * 100}%;transform:translate(-50%, -50%) scale(${markerScale})" title="${escapeHtml(marker.label || `Punto ${index + 1}`)}" aria-label="${escapeHtml(marker.label || `Punto ${index + 1}`)}">${index + 1}</button>`).join('');
    $('planViewerHint').textContent = canEdit
      ? (planMarkerMode ? 'Selecciona una ubicación en el plano' : 'Activa "Agregar punto" para marcar una ubicación')
      : 'Vista de solo lectura';
  }
  function applyPlanTransform(){
    const stage = $('planCanvasStage');
    if(stage) stage.style.transform = `translate(${planPanX}px, ${planPanY}px) scale(${planZoom})`;
    const value = $('planZoomValue');
    if(value) value.textContent = `${Math.round(planZoom * 100)}%`;
  }
  function setPlanZoom(nextZoom, anchorX, anchorY){
    const wrap = $('planCanvasWrap');
    const stage = $('planCanvasStage');
    if(!wrap || !stage) return;
    const bounds = wrap.getBoundingClientRect();
    const contentX = anchorX - bounds.left + wrap.scrollLeft;
    const contentY = anchorY - bounds.top + wrap.scrollTop;
    const localX = (contentX - stage.offsetLeft - planPanX) / planZoom;
    const localY = (contentY - stage.offsetTop - planPanY) / planZoom;
    planZoom = Math.max(0.5, Math.min(planMaxZoom, nextZoom));
    planPanX = contentX - stage.offsetLeft - localX * planZoom;
    planPanY = contentY - stage.offsetTop - localY * planZoom;
    applyPlanTransform();
  }
  function refreshSelectedPlanViewer(){
    const project = getCurrentProject();
    const plan = project?.plans?.find(item => item.id === selectedPlanId);
    if(plan) renderPlanViewer(plan, project);
  }
  async function renderIssuePlanPicker(plan){
    const canvas = $('issuePlanPickerCanvas');
    const hint = $('issuePlanPickerHint');
    if(!canvas || !plan || !window.pdfjsLib) return;
    if(hint) hint.textContent = 'Cargando plano...';
    try {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      let pdfPromise = planPdfCache.get(plan.url);
      if(!pdfPromise){ pdfPromise = window.pdfjsLib.getDocument(plan.url).promise; planPdfCache.set(plan.url, pdfPromise); }
      const pdf = await pdfPromise;
      const page = await pdf.getPage(1);
      const base = page.getViewport({ scale: 1 });
      const width = Math.min(900, Math.max(320, $('issuePlanPickerCanvas').parentElement.clientWidth - 4));
      const scale = width / base.width;
      const renderSettings = getPlanRenderSettings();
      const viewport = getClampedViewport(
        page,
        scale * renderSettings.devicePixelRatio,
        renderSettings.maxDimension,
        renderSettings.maxArea
      );
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${width * (viewport.height / viewport.width)}px`;
      await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
      if(hint) hint.textContent = 'Haz clic sobre el plano para colocar el punto.';
      if(issuePlanPoint?.planId === plan.id){
        const marker = $('issuePlanPickerMarker');
        const pointNumber = (state.entries || []).filter(entry => Number(entry.planId) === Number(plan.id) && entry.id !== state.editingEntryId && entry.planX != null && entry.planY != null).length + 1;
        marker.textContent = pointNumber;
        marker.style.left = `${issuePlanPoint.x * width}px`;
        marker.style.top = `${issuePlanPoint.y * (width * (viewport.height / viewport.width))}px`;
        marker.classList.remove('d-none');
      }
    } catch(error) {
      if(hint) hint.textContent = 'No se pudo cargar el plano en este dispositivo. Intenta desde otro dispositivo o con menos zoom.';
    }
  }
  function getCsrfToken(){
    return document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
  }
  async function requestJson(url, options = {}){
    const isFormData = options.body instanceof FormData;
    const headers = {
      'X-CSRFToken': getCsrfToken(),
      ...(options.headers || {})
    };
    if(!isFormData && !headers['Content-Type']){
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers,
      ...options
    });
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch(error) {
      throw new Error(response.redirected
        ? 'La sesión expiró. Recarga la página e inténtalo nuevamente.'
        : `El servidor devolvió una respuesta no válida (${response.status}).`);
    }
    if(!response.ok){
      throw new Error(data.error || 'No se pudo completar la operación.');
    }
    return data;
  }
  async function requestBlob(url, options = {}){
    const isFormData = options.body instanceof FormData;
    const headers = {
      'X-CSRFToken': getCsrfToken(),
      ...(options.headers || {})
    };
    if(!isFormData && !headers['Content-Type']){
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers,
      ...options
    });
    if(!response.ok){
      const errorText = await response.text();
      try {
        const errorData = errorText ? JSON.parse(errorText) : {};
        throw new Error(errorData.error || 'No se pudo descargar el PDF.');
      } catch {
        throw new Error(errorText || 'No se pudo descargar el PDF.');
      }
    }
    return response.blob();
  }
  async function loadProfile(){
    const profile = await requestJson('/api/profile/', { method: 'GET' });
    updateProfileAvatar(profile?.profileImage);
    $('profileFirstName').value = profile.firstName || '';
    $('profileLastName').value = profile.lastName || '';
    $('profileUsername').textContent = `@${profile.username}`;
    $('profileEmail').textContent = profile.email || 'No registrado';
    if(profile.profileImage){
      $('profileAvatarImage').src = profile.profileImage;
      $('profileAvatarImage').classList.remove('d-none');
      $('profileAvatarInitial').classList.add('d-none');
    }
  }
  function updateProfileAvatar(imageUrl){
    document.querySelectorAll('.app-user-avatar').forEach(avatar => {
      const image = avatar.querySelector('.app-user-avatar-image');
      const initial = avatar.querySelector('.app-user-avatar-initial');
      if(!image || !initial) return;
      if(imageUrl){
        image.src = imageUrl;
        image.classList.remove('d-none');
        initial.classList.add('d-none');
      } else {
        image.removeAttribute('src');
        image.classList.add('d-none');
        initial.classList.remove('d-none');
      }
    });
  }
  function mergeServerProject(serverProject){
    const existing = state.projects.find(project => project.slug === serverProject.slug || project.dbId === serverProject.id);
    if(existing){
      const currentReportId = existing.currentReportId || state.currentReportId || null;
      Object.assign(existing, serverProject);
      existing.currentReportId = currentReportId && existing.reports?.some(report => report.id === currentReportId)
        ? currentReportId
        : existing.reports?.[0]?.id || null;
      return existing;
    }
    const nextProject = { ...serverProject, currentReportId: serverProject.reports?.[0]?.id || null };
    state.projects.push(nextProject);
    return nextProject;
  }
  function mergeServerReport(project, serverReport){
    project.reports = project.reports || [];
    const index = project.reports.findIndex(report => report.id === serverReport.id);
    if(index >= 0){
      project.reports[index] = { ...project.reports[index], ...serverReport };
    } else {
      project.reports.push(serverReport);
    }
    project.currentReportId = serverReport.id;
    state.currentReportId = serverReport.id;
    return project.reports.find(report => report.id === serverReport.id);
  }
  async function createReportRemote(project, formData){
    const data = await requestJson(`/api/projects/${project.slug}/reports/`, { method: 'POST', body: formData });
    return data.report;
  }
  async function updateReportRemote(project, reportId, formData){
    const data = await requestJson(`/api/projects/${project.slug}/reports/${reportId}/update/`, { method: 'POST', body: formData });
    return data.report;
  }
  async function deleteReportRemote(project, reportId){
    await requestJson(`/api/projects/${project.slug}/reports/${reportId}/`, { method: 'DELETE' });
  }
  async function shareReportRemote(project, reportId, payload){
    const data = await requestJson(`/api/projects/${project.slug}/reports/${reportId}/members/`, { method: 'POST', body: JSON.stringify(payload) });
    return data;
  }
  async function createFrontRemote(project, reportId, name){
    const data = await requestJson(`/api/projects/${project.slug}/reports/${reportId}/fronts/`, { method: 'POST', body: JSON.stringify({ name }) });
    return data.front;
  }
  async function updateFrontRemote(project, reportId, frontId, name){
    const data = await requestJson(`/api/projects/${project.slug}/reports/${reportId}/fronts/${frontId}/`, { method: 'POST', body: JSON.stringify({ name }) });
    return data.front;
  }
  async function deleteFrontRemote(project, reportId, frontId){
    await requestJson(`/api/projects/${project.slug}/reports/${reportId}/fronts/${frontId}/`, { method: 'DELETE' });
  }
  async function createEntryRemote(project, reportId, formData){
    const data = await requestJson(`/api/projects/${project.slug}/reports/${reportId}/entries/`, { method: 'POST', body: formData });
    return data.entry;
  }
  async function updateEntryRemote(project, reportId, entryId, formData){
    const data = await requestJson(`/api/projects/${project.slug}/reports/${reportId}/entries/${entryId}/`, { method: 'POST', body: formData });
    return data.entry;
  }
  async function deleteEntryRemote(project, reportId, entryId){
    await requestJson(`/api/projects/${project.slug}/reports/${reportId}/entries/${entryId}/`, { method: 'DELETE' });
  }
  async function fetchProjectsFromServer(){
    try {
      const data = await requestJson('/api/projects/', { method: 'GET' });
      const remoteProjects = Array.isArray(data.projects) ? data.projects : [];
      state.projects = remoteProjects.map(project => ({ ...project, currentReportId: project.currentReportId || project.reports?.[0]?.id || null }));
      const activeProject = getCurrentProject();
      if(activeProject){
        loadProject(activeProject);
      }
      renderAll();
      updateSelectionScreenSections();
      syncViewWithCurrentRoute();
      save();
    } catch (error) {
      console.warn('No se pudieron cargar los proyectos del servidor', error);
    }
  }
  async function createProjectRemote(payload){
     const data = await requestJson('/api/projects/', { method: 'POST', body: payload });
    return data.project;
  }
  async function updateProjectRemote(project, payload){
    const data = await requestJson(`/api/projects/${project.slug}/`, { method: 'POST', body: payload });
    return data.project;
  }
  async function deleteProjectRemote(project){
    if(!project?.slug) return;
    await requestJson(`/api/projects/${project.slug}/`, { method: 'DELETE' });
  }
  async function createProjectPlanRemote(project, file){
    const formData = new FormData();
    formData.append('planFile', file);
    formData.append('name', file.name);
    const data = await requestJson(`/api/projects/${project.slug}/plans/`, { method: 'POST', body: formData });
    return data.plan;
  }
  async function deleteProjectPlanRemote(project, planId){
    await requestJson(`/api/projects/${project.slug}/plans/${planId}/`, { method: 'DELETE' });
  }
  async function createProjectResponsibleRemote(project, name){
    const data = await requestJson(`/api/projects/${project.slug}/responsibles/`, { method: 'POST', body: JSON.stringify({ name }) });
    return data.responsibleCompanies;
  }
  async function deleteProjectResponsibleRemote(project, responsibleId){
    const data = await requestJson(`/api/projects/${project.slug}/responsibles/${responsibleId}/`, { method: 'DELETE' });
    return data.responsibleCompanies;
  }
  async function deleteProjectPlanMarkerRemote(project, planId, markerId){
    await requestJson(`/api/projects/${project.slug}/plans/${planId}/markers/${markerId}/`, { method: 'DELETE' });
  }
  async function createProjectPlanMarkerRemote(project, planId, point){
    const data = await requestJson(`/api/projects/${project.slug}/plans/${planId}/markers/`, { method: 'POST', body: JSON.stringify({ page: 1, x: point.x, y: point.y }) });
    return data.marker;
  }
  async function shareProjectRemote(project, payload){
    const data = await requestJson(`/api/projects/${project.slug}/members/`, { method: 'POST', body: JSON.stringify(payload) });
    return data;
  }
  function save(){
    const isCreatingNewProject = state.selectionStage === 'project' && state.showProjectForm && state.currentProjectId === null;
    if(!isCreatingNewProject){
      syncCurrentReport();
      syncCurrentProject();
    }
    localStorage.setItem(storageKey, JSON.stringify(state));
    localStorage.setItem(storageMetaKey, JSON.stringify({ user: currentUser }));
  }

  function resetClientState(){
    state = {
      projects: [],
      currentProjectId: null,
      currentReportId: null,
      selectionStage: 'project',
      showProjectForm: true,
      companyName: 'VDC CONSTRUCCIONES SAC',
      projectName: '',
      projectLocation: '',
      reportType: '',
      reportTitle: 'REPORTE FOTOGRÁFICO DE OBRA',
      reportWeek: '8',
      reportDate: new Date().toISOString().slice(0, 10),
      reportMetaComplete: false,
      existingReportOpen: false,
      showPreviewMode: false,
      workspaceView: 'fronts',
      currentFrontId: null,
      selectedEntryId: null,
      editingFrontId: null,
      laborDateFrom: '',
      laborDateTo: '',
      forWhom: '',
      fromWhom: '',
      objectiveText: '',
      analysisText: '',
      conclusionText: '',
      recommendationText: '',
      conclusionItems: [],
      recommendationItems: [],
      coverImage: '',
      fronts: [],
      entries: [],
      autoMergeDup: false,
      combineByStatus: false,
      editingEntryId: null,
      showIssueForm: false,
      editingProjectInfo: false,
      editingReportMeta: false,
      showProfileView: false
    };
  }

  function getProjectById(id){ return state.projects.find(p => p.id === id); }
  function getCurrentProject(){ return getProjectById(state.currentProjectId); }
  function getCurrentReport(){ const project = getCurrentProject(); return project?.reports?.find(r => r.id === state.currentReportId) || null; }

  function syncCurrentReport(){
    const report = getCurrentReport();
    if(!report) return;
    report.type = state.reportType;
    report.title = state.reportTitle;
    report.week = state.reportWeek;
    report.date = state.reportDate;
    report.laborDateFrom = state.laborDateFrom;
    report.laborDateTo = state.laborDateTo;
    report.forWhom = state.forWhom;
    report.fromWhom = state.fromWhom;
    clearEntryPhotoInputs();
    report.analysisText = state.analysisText;
    report.conclusionText = state.conclusionText;
    report.recommendationText = state.recommendationText;
    report.conclusionItems = [...state.conclusionItems];
    report.recommendationItems = [...state.recommendationItems];
    report.coverImage = state.coverImage;
    report.fronts = [...state.fronts];
    report.entries = [...state.entries];
    report.currentFrontId = state.currentFrontId;
    report.showPreviewMode = state.showPreviewMode;
    report.autoMergeDup = state.autoMergeDup;
    report.combineByStatus = state.combineByStatus;
    report.editingEntryId = state.editingEntryId;
    report.showIssueForm = state.showIssueForm;
    report.metaComplete = state.reportMetaComplete;
  }

  function syncCurrentProject(){
    const current = getCurrentProject();
    if(!current) return;
    current.companyName = state.companyName;
    current.projectName = state.projectName;
    current.projectLocation = state.projectLocation;
    current.currentReportId = state.currentReportId;
    current.reportTitle = state.reportTitle;
    current.reportWeek = state.reportWeek;
    current.reportDate = state.reportDate;
    current.laborDateFrom = state.laborDateFrom;
    current.laborDateTo = state.laborDateTo;
    current.forWhom = state.forWhom;
    current.fromWhom = state.fromWhom;
    current.objectiveText = state.objectiveText;
    current.analysisText = state.analysisText;
    current.conclusionText = state.conclusionText;
    current.recommendationText = state.recommendationText;
    current.conclusionItems = [...state.conclusionItems];
    current.recommendationItems = [...state.recommendationItems];
    current.coverImage = state.coverImage;
    current.fronts = [...state.fronts];
    current.entries = [...state.entries];
    current.currentFrontId = state.currentFrontId;
    current.showPreviewMode = state.showPreviewMode;
    current.autoMergeDup = state.autoMergeDup;
    current.combineByStatus = state.combineByStatus;
    current.editingEntryId = state.editingEntryId;
    current.showIssueForm = state.showIssueForm;
    current.metaComplete = state.reportMetaComplete;
  }

  function loadProject(project){
    if(!project) return;
    issueFormManuallyOpened = false;
    state.editingProjectInfo = false;
    state.editingReportMeta = false;
    state.showProfileView = false;
    state.companyName = project.companyName || 'VDC CONSTRUCCIONES SAC';
    state.projectName = project.projectName || '';
    state.projectLocation = project.projectLocation || '';
    state.currentReportId = project.currentReportId || null;
    const report = project.reports?.find(r => r.id === state.currentReportId) || null;
    if(report){
      state.reportType = report.type || '';
      state.reportTitle = report.title || 'REPORTE FOTOGRÁFICO DE OBRA';
      state.reportWeek = report.week || '8';
      state.reportDate = report.date || new Date().toISOString().slice(0, 10);
      state.laborDateFrom = report.laborDateFrom || '';
      state.laborDateTo = report.laborDateTo || '';
      state.forWhom = report.forWhom || '';
      state.fromWhom = report.fromWhom || '';
      state.objectiveText = report.objectiveText || '';
      state.analysisText = report.analysisText || '';
      state.conclusionText = report.conclusionText || '';
      state.recommendationText = report.recommendationText || '';
      state.conclusionItems = [...(report.conclusionItems || [])];
      state.recommendationItems = [...(report.recommendationItems || [])];
      state.coverImage = report.coverImage || '';
      state.fronts = [...(report.fronts || [])];
      state.entries = [...(report.entries || [])];
      state.autoMergeDup = !!report.autoMergeDup;
      state.combineByStatus = !!report.combineByStatus;
      state.editingEntryId = null;
      state.showIssueForm = false;
      state.showPreviewMode = !!report.showPreviewMode;
      state.workspaceView = state.showPreviewMode
        ? 'preview'
        : (report.type === 'equipos'
          ? 'equipment'
          : 'summary');
      state.reportMetaComplete = report.metaComplete !== undefined ? !!report.metaComplete : true;
      if(state.existingReportOpen){
        state.reportMetaComplete = true;
      }
      state.currentFrontId = report.currentFrontId || (report.type === 'incidencia' ? state.fronts[0]?.id || null : null);
    } else {
      state.reportType = '';
      state.reportTitle = 'REPORTE FOTOGRÁFICO DE OBRA';
      state.reportWeek = '8';
      state.reportDate = new Date().toISOString().slice(0, 10);
      state.laborDateFrom = '';
      state.laborDateTo = '';
      state.forWhom = '';
      state.fromWhom = '';
      state.objectiveText = '';
      state.analysisText = '';
      state.conclusionText = '';
      state.recommendationText = '';
      state.conclusionItems = [];
      state.recommendationItems = [];
      state.coverImage = '';
      state.fronts = [];
      state.entries = [];
      state.autoMergeDup = false;
      state.combineByStatus = false;
      state.editingEntryId = null;
      state.showIssueForm = false;
      state.workspaceView = 'fronts';
      state.reportMetaComplete = false;
    }
  }

  function resetProjectForm(){
    state.editingProjectInfo = false;
    state.editingReportMeta = false;
    state.editingFrontId = null;
    state.companyName = 'VDC CONSTRUCCIONES SAC';
    state.projectName = '';
    state.projectLocation = '';
    state.reportTitle = 'REPORTE FOTOGRÁFICO DE OBRA';
    state.reportWeek = '8';
    state.reportDate = new Date().toISOString().slice(0, 10);
    state.laborDateFrom = '';
    state.laborDateTo = '';
    state.forWhom = '';
    state.fromWhom = '';
    state.reportMetaComplete = false;
    state.existingReportOpen = false;
    state.showPreviewMode = false;
    state.currentFrontId = null;
    state.objectiveText = '';
    state.analysisText = '';
    state.conclusionText = '';
    state.recommendationText = '';
    state.conclusionItems = [];
    state.recommendationItems = [];
    state.coverImage = '';
    state.fronts = [];
    state.entries = [];
    state.autoMergeDup = false;
    state.combineByStatus = false;
    state.editingEntryId = null;
    state.showIssueForm = false;
    save();
    renderAll();
  }

  function generateProjectId(){
    let id;
    do {
      id = Date.now() + Math.floor(Math.random() * 1000);
    } while(state.projects.some(p => p.id === id));
    return id;
  }

  function generateUniqueSlug(base = 'proyecto'){
    let n = 1;
    let slug = `${base}${n}`;
    const exists = () => state.projects.some(p => p.slug === slug);
    while(exists()){
      n++;
      slug = `${base}${n}`;
    }
    return slug;
  }

  async function createProject(name, location, slug, routeOptions = {}){
     const payload = new FormData();
    payload.append('companyName', state.companyName || 'VDC CONSTRUCCIONES SAC');
     payload.append('projectName', name || `Proyecto ${state.projects.length + 1}`);
     payload.append('projectLocation', location || '');
     payload.append('slug', slug || generateUniqueSlug('proyecto'));
     payload.append('reportTitle', state.reportTitle);
     payload.append('forWhom', state.forWhom);
     payload.append('fromWhom', state.fromWhom);
     if(pendingProjectPhotoFile) payload.append('projectPhoto', pendingProjectPhotoFile);
     const remoteProject = await createProjectRemote(payload);
     pendingProjectPhotoFile = null;
    const project = mergeServerProject(remoteProject);
    project.reports = project.reports || [];
    state.currentProjectId = project.id;
    state.currentReportId = null;
    state.selectionStage = 'reportType';
    state.showProjectForm = false;
    loadProject(project);
    save();
    renderAll();
    updateSelectionScreenSections();
    setProjectRoute(project, routeOptions);
  }

  function createInitialReportForProject(project){
    const reportId = generateProjectId();
    const defaultReport = {
      id: reportId,
      type: 'avances',
      title: 'REPORTE DE AVANCES',
      week: '8',
      date: new Date().toISOString().slice(0, 10),
      forWhom: '',
      fromWhom: '',
      objectiveText: '',
      analysisText: '',
      conclusionText: '',
      recommendationText: '',
      conclusionItems: [],
      recommendationItems: [],
      laborDateFrom: '',
      laborDateTo: '',
      coverImage: '',
      fronts: [],
      entries: [],
      autoMergeDup: false,
      combineByStatus: false,
      editingEntryId: null
    };
    project.reports = project.reports || [];
    project.reports.push(defaultReport);
    project.currentReportId = reportId;
    state.currentReportId = reportId;
    state.reportType = 'avances';
    state.reportTitle = defaultReport.title;
    state.reportWeek = defaultReport.week;
    state.reportDate = defaultReport.date;
    state.laborDateFrom = defaultReport.laborDateFrom;
    state.laborDateTo = defaultReport.laborDateTo;
    state.forWhom = defaultReport.forWhom;
    state.fromWhom = defaultReport.fromWhom;
    state.reportMetaComplete = false;
  }

  function switchProject(id, options = {}){
    const { openDashboardOnly = false } = options;
    const projectId = Number(id);
    if(projectId === state.currentProjectId){
      if(openDashboardOnly){
        resetReportDraftState();
        state.showProjectForm = false;
        state.selectionStage = 'reportType';
        save();
        renderAll();
        updateSelectionScreenSections();
        return;
      }
      if(state.selectionStage !== 'reportType'){
        state.showProjectForm = false;
        state.selectionStage = 'reportType';
        save();
        renderAll();
        updateSelectionScreenSections();
      }
      return;
    }
    syncCurrentReport();
    state.currentProjectId = projectId;
    state.currentReportId = null;
    state.showProjectForm = false;
    const project = getCurrentProject();
    if(project) loadProject(project);
    if(openDashboardOnly){
      resetReportDraftState();
    }
    state.selectionStage = 'reportType';
    save();
    renderAll();
    updateSelectionScreenSections();
    setProjectRoute(project);
  }

  async function deleteProject(id){
    const currentProject = getProjectById(id);
    if(currentProject && !currentProject.canDelete){
      alert('Solo el propietario puede eliminar este proyecto.');
      return;
    }
    if(currentProject?.dbId){
      await deleteProjectRemote(currentProject);
    }
    const wasCurrent = id === state.currentProjectId;
    state.projects = state.projects.filter(p => p.id !== id);
    if(wasCurrent){
      state.currentProjectId = state.projects.length ? state.projects[0].id : null;
      if(state.currentProjectId){
        loadProject(getCurrentProject());
        state.selectionStage = 'reportType';
      } else {
        state.selectionStage = 'project';
        state.reportType = '';
        state.existingReportOpen = false;
        state.reportMetaComplete = false;
      }
    }
    save();
    renderAll();
    updateSelectionScreenSections();
    if(state.currentProjectId){
      setProjectRoute(getCurrentProject());
    } else {
      setPanelRoute();
      showSelectionScreen();
    }
  }

  async function deleteReport(reportId){
    const project = getCurrentProject();
    if(!project || !project.reports?.length) return;
    if(!ensureCanEditReport('No tienes permisos para eliminar este reporte.')){
      return;
    }
    if(!confirm('¿Eliminar este reporte? Esta acción no se puede deshacer.')) return;
    await deleteReportRemote(project, reportId);
    project.reports = project.reports.filter(r => r.id !== reportId);
    if(state.currentReportId === reportId){
      state.currentReportId = project.reports.length ? project.reports[0].id : null;
      project.currentReportId = state.currentReportId;
      if(state.currentReportId){
        loadProject(project);
        setReportRoute(project, state.currentReportId);
      } else {
        state.reportType = '';
        state.reportMetaComplete = false;
        state.existingReportOpen = false;
        setProjectRoute(project);
        showSelectionScreen();
      }
    }
    save();
    renderAll();
    updateSelectionScreenSections();
  }

  function getRouteInfo(){
    const path = (window.location.pathname || '').replace(/^\/+/, '').replace(/\/+$/, '');
    const parts = path ? path.split('/') : [];
    const info = {
      onPanelPath: /^panel-principal$/.test(path),
      onNewProjectPath: /^panel-principal\/proyecto\/nuevo$/.test(path),
      onProjectPath: false,
      onEditProjectPath: false,
      onNewReportPath: false,
      onReportPath: false,
      onFrontPath: false,
      projectSlug: null,
      reportId: null
      ,frontId: null
    };

    if(parts[0] === 'proyecto' && parts[1]){
      info.projectSlug = parts[1];
      if(parts.length === 2){
        info.onProjectPath = true;
      } else if(parts[2] === 'editar' && parts.length === 3){
        info.onEditProjectPath = true;
      } else if(parts[2] === 'reporte' && parts[3] === 'nuevo' && parts.length === 4){
        info.onNewReportPath = true;
      } else if(parts[2] === 'reporte' && /^\d+$/.test(parts[3] || '') && parts.length === 4){
        info.onReportPath = true;
        info.reportId = Number(parts[3]);
      } else if(parts[2] === 'reporte' && /^\d+$/.test(parts[3] || '') && parts[4] === 'frente' && /^\d+$/.test(parts[5] || '') && parts.length === 6){
        info.onFrontPath = true;
        info.reportId = Number(parts[3]);
        info.frontId = Number(parts[5]);
      }
      return info;
    }

    if(/^proyecto\d+$/.test(parts[0] || '')){
      info.projectSlug = parts[0];
      info.onProjectPath = true;
    }

    return info;
  }

  function getProjectIdFromUrl(){
    const params = new URLSearchParams(window.location.search);
    const projectId = params.get('project');
    if(projectId){
      const parsed = Number(projectId);
      if(!Number.isNaN(parsed)) return parsed;
    }
    const routeInfo = getRouteInfo();
    if(!routeInfo.projectSlug) return null;
    const project = state.projects.find(p => p.slug === routeInfo.projectSlug);
    return project ? project.id : null;
  }

  function updateBrowserRoute(path, options = {}){
    const { replace = false } = options;
    const method = replace ? 'replaceState' : 'pushState';
    try { history[method]({ path }, '', path); } catch (e) {}
  }

  function setPanelRoute(options = {}){
    updateBrowserRoute('/panel-principal/', options);
  }

  function setNewProjectRoute(options = {}){
    updateBrowserRoute('/panel-principal/proyecto/nuevo/', options);
  }

  function setProjectRoute(project, options = {}){
    const slug = project?.slug;
    if(!slug) return;
    updateBrowserRoute(`/proyecto/${slug}/`, options);
  }

  function setEditProjectRoute(project, options = {}){
    const slug = project?.slug;
    if(!slug) return;
    updateBrowserRoute(`/proyecto/${slug}/editar/`, options);
  }

  function setNewReportRoute(project, options = {}){
    const slug = project?.slug;
    if(!slug) return;
    updateBrowserRoute(`/proyecto/${slug}/reporte/nuevo/`, options);
  }

  function setReportRoute(project, reportId, options = {}){
    const slug = project?.slug;
    const nextReportId = Number(reportId);
    if(!slug || Number.isNaN(nextReportId) || !nextReportId) return;
    updateBrowserRoute(`/proyecto/${slug}/reporte/${nextReportId}/`, options);
  }

  function setFrontRoute(project, reportId, frontId, options = {}){
    const slug = project?.slug;
    const nextReportId = Number(reportId);
    const nextFrontId = Number(frontId);
    if(!slug || Number.isNaN(nextReportId) || !nextReportId || Number.isNaN(nextFrontId) || !nextFrontId) return;
    updateBrowserRoute(`/proyecto/${slug}/reporte/${nextReportId}/frente/${nextFrontId}/`, options);
  }

  function canEditProjectFromCurrentRoute(){
    const routeInfo = getRouteInfo();
    const current = getCurrentProject();
    const onEditableRoute = !!(routeInfo.onProjectPath || routeInfo.onPanelPath || routeInfo.onNewProjectPath);
    return onEditableRoute && !!current?.canEdit;
  }

  function canEditCurrentProject(){
    const current = getCurrentProject();
    return !!current?.canEdit;
  }

  function canEditCurrentReport(){
    const currentReport = getCurrentReport();
    return !!currentReport?.canEdit;
  }

  function ensureCanEditProject(message){
    const current = getCurrentProject();
    if(current && !current.canEdit){
      alert(message || 'Solo tienes permisos de lectura en este proyecto.');
      return false;
    }
    return true;
  }

  function ensureCanEditReport(message){
    const currentReport = getCurrentReport();
    if(currentReport && !currentReport.canEdit){
      alert(message || 'Solo tienes permisos de lectura en este reporte.');
      return false;
    }
    return true;
  }

  function setDisabledById(elementId, disabled){
    const element = $(elementId);
    if(element){
      element.disabled = disabled;
    }
  }

  function applyPermissionLocks(){
    const currentProject = getCurrentProject();
    const currentReport = getCurrentReport();
    const hasProject = !!currentProject;
    const hasReport = !!currentReport;
    const canEditProject = canEditCurrentProject();
    const canEditReport = canEditCurrentReport();
    const lockProject = hasProject && !canEditProject;
    const lockReport = hasReport && !canEditReport;
    const lockReportMeta = hasProject && (hasReport ? !canEditReport : !canEditProject);

    [
      'editProjectInfoBtn',
      'saveProjectInfoBtn',
      'dashboardSaveProjectBtn',
      'dashboardCompanyName',
      'dashboardProjectName',
      'dashboardProjectLocation',
      'editCompanyName',
      'editProjectName',
      'editProjectLocation',
      'shareProjectBtn',
      'shareUsername',
      'shareRole'
    ].forEach(id => setDisabledById(id, lockProject));

    [
      'reportTitle',
      'reportWeek',
      'reportDate',
      'laborDateFrom',
      'laborDateTo',
      'forWhom',
      'fromWhom',
      'objectiveText',
      'analysisText',
      'coverPhotoInput',
      'continueToEditorBtn',
      'editReportInfoBtn',
      'addFrontBtn',
      'frontName',
      'openIssueFormBtn',
      'addEntryBtn',
      'statusSelect',
      'entryDesc',
      'photoInput',
      'photoCameraInput',
      'takePhotoBtn',
      'choosePhotoBtn',
      'addEquipmentBtn',
      'equipmentName',
      'equipmentBuilding',
      'equipmentQuantity',
      'equipmentStatusSelect',
      'equipmentComments',
      'equipmentPhotoInput',
      'equipmentPhotoCameraInput',
      'equipmentTakePhotoBtn',
      'equipmentChoosePhotoBtn',
      'addConclusionBtn',
      'addRecommendationBtn',
      'conclusionItemInput',
      'recommendationItemInput',
      'conclusionText',
      'recommendationText'
    ].forEach(id => setDisabledById(id, lockReportMeta));

    document.querySelectorAll('.rm-front, .edit-entry, .delete-entry, .edit-equipment, .delete-equipment, .edit-entry-detail').forEach(button => {
      button.disabled = lockReport;
    });
  }

  function isOnNewReportRoute(){
    const routeInfo = getRouteInfo();
    return !!routeInfo.onNewReportPath;
  }

  function isOnReportRoute(){
    const routeInfo = getRouteInfo();
    return !!routeInfo.onReportPath;
  }

  function isOnReportWorkspaceRoute(){
    const routeInfo = getRouteInfo();
    return !!(routeInfo.onNewReportPath || routeInfo.onReportPath || routeInfo.onFrontPath);
  }

  function hasActiveReportWorkspaceContext(){
    const routeInfo = getRouteInfo();
    const currentProject = getCurrentProject();
    const currentReport = getCurrentReport();
    const routeMatchesCurrentReport = routeInfo.onFrontPath || routeInfo.onReportPath
      ? routeInfo.reportId === state.currentReportId
      : false;
    if(routeInfo.onNewReportPath){
      return !!(currentProject && (state.reportType || routeInfo.onNewReportPath));
    }
    if(routeInfo.onReportPath || routeInfo.onFrontPath){
      return !!(currentProject && (routeMatchesCurrentReport || !!state.reportType));
    }
    return !!(currentProject && currentReport && routeMatchesCurrentReport);
  }

  function resetReportDraftState(){
    state.currentReportId = null;
    state.reportType = '';
    state.reportTitle = 'REPORTE FOTOGRÁFICO DE OBRA';
    state.reportWeek = '8';
    state.reportDate = new Date().toISOString().slice(0, 10);
    state.laborDateFrom = '';
    state.laborDateTo = '';
    state.forWhom = '';
    state.fromWhom = '';
    state.objectiveText = '';
    state.analysisText = '';
    state.conclusionText = '';
    state.recommendationText = '';
    state.conclusionItems = [];
    state.recommendationItems = [];
    state.coverImage = '';
    state.fronts = [];
    state.entries = [];
    state.autoMergeDup = false;
    state.combineByStatus = false;
    state.editingEntryId = null;
    state.currentFrontId = null;
    state.showIssueForm = false;
    state.existingReportOpen = false;
    state.reportMetaComplete = false;
    state.showPreviewMode = false;
    state.editingReportMeta = false;
  }

  function captureReportDraftState(){
    return {
      currentReportId: state.currentReportId,
      reportType: state.reportType,
      reportTitle: state.reportTitle,
      reportWeek: state.reportWeek,
      reportDate: state.reportDate,
      laborDateFrom: state.laborDateFrom,
      laborDateTo: state.laborDateTo,
      forWhom: state.forWhom,
      fromWhom: state.fromWhom,
      objectiveText: state.objectiveText,
      analysisText: state.analysisText,
      conclusionText: state.conclusionText,
      recommendationText: state.recommendationText,
      conclusionItems: [...state.conclusionItems],
      recommendationItems: [...state.recommendationItems],
      coverImage: state.coverImage,
      fronts: [...state.fronts],
      entries: [...state.entries],
      autoMergeDup: state.autoMergeDup,
      combineByStatus: state.combineByStatus,
      editingEntryId: state.editingEntryId,
      showIssueForm: state.showIssueForm,
      currentFrontId: state.currentFrontId,
      existingReportOpen: state.existingReportOpen,
      reportMetaComplete: state.reportMetaComplete,
      showPreviewMode: state.showPreviewMode,
      editingReportMeta: state.editingReportMeta
    };
  }

  function restoreReportDraftState(draft){
    if(!draft) return;
    state.currentReportId = draft.currentReportId ?? null;
    state.reportType = draft.reportType || '';
    state.reportTitle = draft.reportTitle || 'REPORTE FOTOGRÁFICO DE OBRA';
    state.reportWeek = draft.reportWeek || '8';
    state.reportDate = draft.reportDate || new Date().toISOString().slice(0, 10);
    state.laborDateFrom = draft.laborDateFrom || '';
    state.laborDateTo = draft.laborDateTo || '';
    state.forWhom = draft.forWhom || '';
    state.fromWhom = draft.fromWhom || '';
    state.objectiveText = draft.objectiveText || '';
    state.analysisText = draft.analysisText || '';
    state.conclusionText = draft.conclusionText || '';
    state.recommendationText = draft.recommendationText || '';
    state.conclusionItems = [...(draft.conclusionItems || [])];
    state.recommendationItems = [...(draft.recommendationItems || [])];
    state.coverImage = draft.coverImage || '';
    state.fronts = [...(draft.fronts || [])];
    state.entries = [...(draft.entries || [])];
    state.autoMergeDup = !!draft.autoMergeDup;
    state.combineByStatus = !!draft.combineByStatus;
    state.editingEntryId = draft.editingEntryId || null;
    state.showIssueForm = !!draft.showIssueForm;
    state.currentFrontId = draft.currentFrontId || null;
    state.existingReportOpen = !!draft.existingReportOpen;
    state.reportMetaComplete = !!draft.reportMetaComplete;
    state.showPreviewMode = !!draft.showPreviewMode;
    state.editingReportMeta = !!draft.editingReportMeta;
  }

  function activatePanelView(){
    state.selectionStage = 'project';
    state.currentProjectId = null;
    state.currentReportId = null;
    state.reportType = '';
    state.existingReportOpen = false;
    state.reportMetaComplete = false;
    state.showPreviewMode = false;
    state.workspaceView = 'fronts';
    state.currentFrontId = null;
    state.selectedEntryId = null;
    state.editingEntryId = null;
    state.showIssueForm = false;
    state.editingProjectInfo = false;
    state.editingReportMeta = false;
    state.showProjectForm = state.projects.length === 0 ? true : state.showProjectForm === true;
    save();
    renderAll();
    updateSelectionScreenSections();
    showAppScreen();
  }

  function activateNewProjectView(){
    state.selectionStage = 'project';
    state.showProjectForm = true;
    state.currentProjectId = null;
    state.currentReportId = null;
    resetProjectForm();
    renderAll();
    updateSelectionScreenSections();
    showSelectionScreen();
  }

  function activateEditProjectView(projectId){
    const project = getProjectById(Number(projectId));
    if(!project) return false;
    state.currentProjectId = project.id;
    state.selectionStage = 'project';
    state.showProjectForm = true;
    loadProject(project);
    renderAll();
    updateSelectionScreenSections();
    showSelectionScreen();
    return true;
  }

  function activateProjectView(projectId, options = {}){
    const { preserveDraft = false } = options;
    const project = getProjectById(Number(projectId));
    if(!project) return false;
    showProjectShare = false;
    projectDashboardView = 'summary';
    planZoom = 1;
    selectedPlanId = null;
    const draftState = preserveDraft ? captureReportDraftState() : null;
    state.currentProjectId = project.id;
    state.selectionStage = 'reportType';
    state.showProjectForm = false;
    loadProject(project);
    if(draftState){
      restoreReportDraftState(draftState);
    }
    save();
    renderAll();
    updateSelectionScreenSections();
    showAppScreen();
    return true;
  }

  function syncViewWithCurrentRoute(){
    const routeInfo = getRouteInfo();
    const urlProjectId = getProjectIdFromUrl();

    if(routeInfo.onNewProjectPath || window.INIT_NEW_PROJECT){
      activateNewProjectView();
      return;
    }

    if((routeInfo.onEditProjectPath || window.INIT_EDIT_PROJECT) && urlProjectId && activateEditProjectView(urlProjectId)){
      return;
    }

    if((routeInfo.onProjectPath || routeInfo.onNewReportPath || routeInfo.onReportPath || routeInfo.onFrontPath) && urlProjectId && activateProjectView(urlProjectId, { preserveDraft: routeInfo.onNewReportPath })){
      const project = getCurrentProject();
      if(routeInfo.onProjectPath){
        resetReportDraftState();
        save();
        renderAll();
        showAppScreen();
        return;
      }
      if(routeInfo.onReportPath || routeInfo.onFrontPath){
        const report = project?.reports?.find(item => item.id === routeInfo.reportId);
        if(report){
          project.currentReportId = routeInfo.reportId;
          state.currentReportId = routeInfo.reportId;
          state.existingReportOpen = true;
          state.reportMetaComplete = true;
          loadProject(project);
          if(routeInfo.onFrontPath){
            const front = state.fronts.find(item => item.id === routeInfo.frontId);
            if(front){
              state.currentFrontId = routeInfo.frontId;
            } else {
              setReportRoute(project, routeInfo.reportId, { replace: true });
            }
          }
          save();
          renderAll();
          showAppScreen();
          return;
        }
        setProjectRoute(project, { replace: true });
        showSelectionScreen();
        return;
      }

      if(routeInfo.onNewReportPath){
        save();
        renderAll();
        showAppScreen();
        return;
      }

      showAppScreen();
      return;
    }

    activatePanelView();
  }

  function normalizeLoadedState(data){
    if(!data || typeof data !== 'object') return;
    const nextState = {
      ...state,
      ...data,
      projects: Array.isArray(data.projects) ? data.projects : state.projects,
      fronts: Array.isArray(data.fronts) ? data.fronts : state.fronts,
      entries: Array.isArray(data.entries) ? data.entries : state.entries,
      conclusionItems: Array.isArray(data.conclusionItems) ? data.conclusionItems : state.conclusionItems,
      recommendationItems: Array.isArray(data.recommendationItems) ? data.recommendationItems : state.recommendationItems,
      autoMergeDup: !!data.autoMergeDup,
      combineByStatus: !!data.combineByStatus,
      showPreviewMode: !!data.showPreviewMode,
      reportMetaComplete: !!data.reportMetaComplete,
      editingProjectInfo: !!data.editingProjectInfo,
      editingReportMeta: !!data.editingReportMeta,
      showIssueForm: !!data.showIssueForm,
      workspaceView: data.workspaceView || state.workspaceView,
      laborDateFrom: data.laborDateFrom || state.laborDateFrom,
      laborDateTo: data.laborDateTo || state.laborDateTo,
      forWhom: data.forWhom || state.forWhom,
      fromWhom: data.fromWhom || state.fromWhom,
      currentProjectId: data.currentProjectId !== undefined ? Number(data.currentProjectId) : state.currentProjectId,
      currentReportId: data.currentReportId !== undefined ? Number(data.currentReportId) : state.currentReportId,
      currentFrontId: data.currentFrontId !== undefined ? Number(data.currentFrontId) : state.currentFrontId,
      editingFrontId: data.editingFrontId !== undefined && data.editingFrontId !== null ? Number(data.editingFrontId) : null,
      selectionStage: data.selectionStage || state.selectionStage,
      showProjectForm: data.showProjectForm !== undefined ? !!data.showProjectForm : state.showProjectForm,
    };
    state = nextState;
    state.selectionStage = state.selectionStage || (state.currentProjectId ? 'reportType' : 'project');
    state.showProjectForm = state.projects.length === 0 ? (state.showProjectForm !== false) : state.showProjectForm === true;
    // Ensure legacy projects have a slug
    state.projects.forEach((p, idx) => {
      if(!p.slug){
        // try to reuse existing name to build slug, fallback to proyectoN
        const base = 'proyecto';
        let n = idx + 1;
        let slug = `${base}${n}`;
        while(state.projects.some(x => x !== p && x.slug === slug)){
          n++;
          slug = `${base}${n}`;
        }
        p.slug = slug;
      }
    });
  }

  function load(){
    const routeInfo = getRouteInfo();
    let storedUser = null;
    try {
      storedUser = JSON.parse(localStorage.getItem(storageMetaKey) || 'null')?.user || null;
    } catch (err) {
      console.warn('Error leyendo metadato de sesión', err);
    }

    const hasStoredState = !!localStorage.getItem(storageKey);
    if(storedUser && storedUser !== currentUser){
      resetClientState();
      localStorage.removeItem(storageKey);
      localStorage.setItem(storageMetaKey, JSON.stringify({ user: currentUser }));
    } else if(!storedUser && hasStoredState){
      localStorage.removeItem(storageKey);
      localStorage.setItem(storageMetaKey, JSON.stringify({ user: currentUser }));
      resetClientState();
    }

    const v = localStorage.getItem(storageKey);
    if(v){
      try {
        normalizeLoadedState(JSON.parse(v));
      } catch (err) {
        console.warn('Error leyendo estado desde localStorage', err);
      }
    } else {
      resetClientState();
    }

    // Si la plantilla inyectó un slug inicial, abrir o crear el proyecto localmente
    try {
      const initSlug = (window.INIT_PROJECT_SLUG || '').toString().trim();
      if(initSlug){
        const draftState = routeInfo.onNewReportPath ? captureReportDraftState() : null;
        let existing = state.projects.find(p => p.slug === initSlug);
        if(existing){
          state.currentProjectId = existing.id;
          state.selectionStage = 'reportType';
          state.showProjectForm = false;
          loadProject(existing);
          if(draftState){
            restoreReportDraftState(draftState);
          }
        } else {
          state.currentProjectId = null;
        }
        save();
      }
    } catch (err) {
      console.warn('Error procesando INIT_PROJECT_SLUG', err);
    }

    const urlProjectId = getProjectIdFromUrl();
    if(urlProjectId && state.projects.some(p => p.id === urlProjectId)){
      state.currentProjectId = urlProjectId;
      state.selectionStage = 'reportType';
      state.showProjectForm = false;
    } else if(routeInfo.onPanelPath || routeInfo.onNewProjectPath || routeInfo.onEditProjectPath){
      state.selectionStage = 'project';
      state.currentProjectId = null;
      state.currentReportId = null;
      state.showProjectForm = routeInfo.onNewProjectPath || window.INIT_NEW_PROJECT || routeInfo.onEditProjectPath || window.INIT_EDIT_PROJECT
        ? true
        : state.projects.length === 0 ? true : state.showProjectForm === true;
    } else if(state.currentProjectId && state.projects.some(p => p.id === state.currentProjectId)){
      state.selectionStage = state.selectionStage || 'reportType';
      state.showProjectForm = false;
    } else {
      state.selectionStage = 'project';
      state.currentProjectId = null;
      state.currentReportId = null;
      state.showProjectForm = state.projects.length === 0 ? true : state.showProjectForm === true;
    }

    if(state.currentProjectId){
      const project = getCurrentProject();
      if(project){
        const draftState = routeInfo.onNewReportPath ? captureReportDraftState() : null;
        if((routeInfo.onReportPath || routeInfo.onFrontPath) && routeInfo.reportId){
          project.currentReportId = routeInfo.reportId;
          state.currentReportId = routeInfo.reportId;
          state.existingReportOpen = true;
          state.reportMetaComplete = true;
        }
        loadProject(project);
        if(routeInfo.onFrontPath && routeInfo.frontId){
          const front = state.fronts.find(item => item.id === routeInfo.frontId);
          state.currentFrontId = front ? routeInfo.frontId : null;
        }
        if(draftState){
          restoreReportDraftState(draftState);
        }
      }
    }
    if(routeInfo.onProjectPath){
      resetReportDraftState();
    }
    renderAll();
    updateSelectionScreenSections();

    if(routeInfo.onNewProjectPath || window.INIT_NEW_PROJECT){
      setNewProjectRoute({ replace: true });
      showSelectionScreen();
    } else if((routeInfo.onEditProjectPath || window.INIT_EDIT_PROJECT) && state.currentProjectId){
      setEditProjectRoute(getCurrentProject(), { replace: true });
      showSelectionScreen();
    } else if(routeInfo.onPanelPath){
      setPanelRoute({ replace: true });
      showAppScreen();
    } else if(routeInfo.onProjectPath && state.currentProjectId){
      const proj = getCurrentProject();
      setProjectRoute(proj, { replace: true });
      showAppScreen();
    } else if(routeInfo.onNewReportPath && state.currentProjectId){
      const proj = getCurrentProject();
      setNewReportRoute(proj, { replace: true });
      showAppScreen();
    } else if(routeInfo.onReportPath && state.currentProjectId){
      const proj = getCurrentProject();
      setReportRoute(proj, routeInfo.reportId, { replace: true });
      showAppScreen();
    } else if(routeInfo.onFrontPath && state.currentProjectId){
      const proj = getCurrentProject();
      setFrontRoute(proj, routeInfo.reportId, routeInfo.frontId, { replace: true });
      showAppScreen();
    } else {
      setPanelRoute({ replace: true });
      showAppScreen();
    }
  }

  function normalizeName(name){ return (name || '').trim().toLowerCase().replace(/\s+/g, ' '); }
  function cleanFrontName(name){
    let value = (name || '').trim().replace(/\s+/g, ' ');
    if(!value) return '';
    while(/^frente\b/i.test(value)) value = value.replace(/^frente\s*[:\-]?\s*/i, '').trim();
    value = value.replace(/^\s*#\s*/i, '').trim();
    value = value.replace(/^\d+\s*[:\-]?\s*/i, '').trim();
    return value || 'Frente';
  }
  function getFrontIndex(id){ return state.fronts.findIndex(f => f.id === id); }
  function frontNumber(id){ const i = getFrontIndex(id); return i >= 0 ? i + 1 : null; }
  function frontLabel(front){ const n = frontNumber(front.id); return n ? `${n}. ${front.name}` : front.name; }
  function findFrontByName(name){ const key = normalizeName(cleanFrontName(name)); return state.fronts.find(f => normalizeName(f.name) === key); }
  function findDuplicateGroups(){ const map = {}; state.fronts.forEach(f => { const key = normalizeName(f.name); if(!map[key]) map[key] = []; map[key].push(f); }); return Object.values(map).filter(g => g.length > 1); }

  async function addFront(name, opts){
    if(!ensureCanEditReport('No tienes permisos para agregar frentes en este reporte.')){
      return false;
    }
    const cleanedName = cleanFrontName(name) || name.trim();
    if(!cleanedName) return false;
    const project = getCurrentProject();
    if(!project || !state.currentReportId){
      alert('Primero crea o abre un reporte antes de agregar frentes.');
      return false;
    }
    const existing = findFrontByName(cleanedName);
    const autoMerge = opts?.autoMerge ?? state.autoMergeDup;
    if(existing){ if(autoMerge) return true; if(confirm(`Ya existe el frente "${existing.name}". ¿Fusionar con el existente?`)) return true; return false; }
    const finalName = cleanedName || `Frente ${state.fronts.length + 1}`;
    const front = await createFrontRemote(project, state.currentReportId, finalName);
    state.fronts.push(front);
    state.currentFrontId = front.id;
    const report = getCurrentReport();
    if(report) report.fronts = [...state.fronts];
    save(); renderAll(); return true;
  }
  async function saveFrontEdit(name){
    if(!ensureCanEditReport('No tienes permisos para editar frentes en este reporte.')){
      return false;
    }
    const frontId = Number(state.editingFrontId);
    const front = state.fronts.find(item => Number(item.id) === frontId);
    const project = getCurrentProject();
    if(!front || !project || !state.currentReportId){
      state.editingFrontId = null;
      return false;
    }
    const cleanedName = cleanFrontName(name) || name.trim();
    if(!cleanedName) return false;
    const duplicate = state.fronts.find(item => Number(item.id) !== frontId && normalizeName(item.name) === normalizeName(cleanedName));
    if(duplicate){
      alert(`Ya existe el frente "${duplicate.name}".`);
      return false;
    }
    const updatedFront = await updateFrontRemote(project, state.currentReportId, frontId, cleanedName);
    front.name = updatedFront.name;
    state.editingFrontId = null;
    const report = getCurrentReport();
    if(report) report.fronts = [...state.fronts];
    save();
    renderAll();
    return true;
  }

  async function ensureDefaultIncidentFront(){
    if(state.reportType !== 'incidencia') return;
    if(state.fronts.length) {
      state.currentFrontId = state.currentFrontId || state.fronts[0].id;
      return;
    }
    const created = await addFront('Frente principal', { autoMerge: false });
    if(created && state.fronts.length) {
      state.currentFrontId = state.fronts[0].id;
    }
  }

  function getEntryById(id){ return state.entries.find(e => e.id === id); }
  function getFrontName(frontId){ const front = state.fronts.find(f => f.id === frontId); return front ? front.name : 'Frente eliminado'; }
  function getIssueLocationLabel(entry, index = null){
    if(entry?.buildingLocation) return entry.buildingLocation;
    if(entry?.planId && entry?.planX != null && entry?.planY != null){
      return index != null ? `Punto ${index + 1}` : 'Punto registrado en plano';
    }
    return 'Sin ubicación';
  }
  async function removeFront(id){
    if(!ensureCanEditReport('No tienes permisos para eliminar frentes en este reporte.')){
      return;
    }
    const project = getCurrentProject();
    if(project && state.currentReportId){
      await deleteFrontRemote(project, state.currentReportId, id);
    }
    state.fronts = state.fronts.filter(f => f.id !== id);
    state.entries = state.entries.filter(e => e.frontId !== id);
    const report = getCurrentReport();
    if(report){ report.fronts = [...state.fronts]; report.entries = [...state.entries]; }
    save(); renderAll();
  }
  function editFront(id){
    if(!ensureCanEditReport('No tienes permisos para editar frentes en este reporte.')){
      return;
    }
    const front = state.fronts.find(item => Number(item.id) === Number(id));
    if(!front) return;
    state.editingFrontId = front.id;
    renderAll();
    if($('frontName')) $('frontName').value = front.name || '';
    $('frontName')?.focus();
  }
  async function removeEntry(id){
    if(!ensureCanEditReport('No tienes permisos para modificar issues en este reporte.')){
      return;
    }
    const project = getCurrentProject();
    if(project && state.currentReportId){
      await deleteEntryRemote(project, state.currentReportId, id);
    }
    state.entries = state.entries.filter(e => e.id !== id);
    const report = getCurrentReport();
    if(report) report.entries = [...state.entries];
    if(state.editingEntryId === id){ resetEntryEditor(); }
    save(); renderAll();
  }
  function clearEntryPhotoInputs(){ if($('photoInput')) $('photoInput').value = ''; if($('photoCameraInput')) $('photoCameraInput').value = ''; }
  function getEntryPhotoFiles(){ return [...($('photoInput')?.files ? Array.from($('photoInput').files) : []), ...($('photoCameraInput')?.files ? Array.from($('photoCameraInput').files) : [])]; }
  function renderResponsibleCompanySelect(value){
    const select = $('responsibleCompany');
    if(!select) return;
    const project = getCurrentProject();
    const list = Array.isArray(project?.responsibleCompanies) ? project.responsibleCompanies : [];
    const names = list.map(item => item.name);
    const current = value ?? select.value ?? '';
    if(current && !names.includes(current)) names.push(current);
    select.innerHTML = `<option value="">Selecciona un responsable</option>${names.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('')}`;
    select.value = current || '';
  }
  function resetEntryEditor(){ state.editingEntryId = null; state.showIssueForm = false; issuePlanPoint = null; pendingRemovedEntryImageIds = new Set(); $('addEntryBtn').textContent = 'Agregar issue'; $('cancelEntryEditBtn').classList.add('d-none'); clearEntryPhotoInputs(); $('entryDesc').value = ''; if($('incidentDate')) $('incidentDate').value = ''; renderResponsibleCompanySelect(''); if($('issueLocation')) $('issueLocation').value = ''; if($('issuePlanId')) $('issuePlanId').value = ''; if($('issuePlanX')) $('issuePlanX').value = ''; if($('issuePlanY')) $('issuePlanY').value = ''; if($('issuePlanPointStatus')) $('issuePlanPointStatus').textContent = ''; const frontId = Number($('selectFront').value); if(frontId){ $('selectFront').value = frontId; } $('selectFront').disabled = false; renderExistingEntryImages(); }
  function renderExistingEntryImages(){ const container = $('existingEntryImages'); if(!container) return; const entry = getEntryById(state.editingEntryId); const imageItems = Array.isArray(entry?.imageItems) ? entry.imageItems : []; const visibleItems = imageItems.filter(item => !pendingRemovedEntryImageIds.has(Number(item.id))); if(!state.editingEntryId || !visibleItems.length){ container.innerHTML = ''; container.classList.add('d-none'); return; } container.classList.remove('d-none'); container.innerHTML = `<div class="small text-muted mb-2">Fotos actuales</div>${visibleItems.map(item => `<div class="d-flex align-items-center justify-content-between gap-2 border rounded px-2 py-2 mb-2"><div class="d-flex align-items-center gap-2 overflow-hidden"><img src="${item.url}" alt="${escapeHtml(item.name || 'Foto')}" style="width: 48px; height: 48px; object-fit: cover; border-radius: 8px;"><span class="small text-truncate">${escapeHtml(item.name || 'Foto')}</span></div><button type="button" class="btn btn-sm btn-outline-danger remove-existing-entry-image" data-id="${item.id}">Quitar</button></div>`).join('')}`; container.querySelectorAll('.remove-existing-entry-image').forEach(btn => btn.addEventListener('click', () => { pendingRemovedEntryImageIds.add(Number(btn.dataset.id)); renderExistingEntryImages(); })); }
    function loadIncidentFields(entry){
      const entryIndex = state.entries.findIndex(item => Number(item.id) === Number(entry?.id));
      issuePlanPoint = null;
      if($('incidentDate')) $('incidentDate').value = entry.incidentDate || '';
      renderResponsibleCompanySelect(entry.responsibleCompany || '');
      if($('issueLocation')) $('issueLocation').value = getIssueLocationLabel(entry, entryIndex >= 0 ? entryIndex : null) === 'Sin ubicación' ? '' : getIssueLocationLabel(entry, entryIndex >= 0 ? entryIndex : null);
      if($('issuePlanId')) $('issuePlanId').value = '';
      if($('issuePlanX')) $('issuePlanX').value = '';
      if($('issuePlanY')) $('issuePlanY').value = '';
      if($('issuePlanPointStatus')) $('issuePlanPointStatus').textContent = '';
      if(entry.planId && entry.planX != null && entry.planY != null){
        issuePlanPoint = { planId: entry.planId, x: entry.planX, y: entry.planY };
        if($('issuePlanId')) $('issuePlanId').value = String(entry.planId);
        if($('issuePlanX')) $('issuePlanX').value = String(entry.planX);
        if($('issuePlanY')) $('issuePlanY').value = String(entry.planY);
        if($('issuePlanPointStatus')) $('issuePlanPointStatus').textContent = 'Punto guardado en el plano.';
      }
    }
  function loadTemplate(){ let added = 0; FRONT_TEMPLATE.forEach(name => { if(!findFrontByName(name)){ state.fronts.push({ id: Date.now() + Math.random(), name }); added++; } }); if(added === 0){ alert('Todos los frentes de la plantilla ya existen.'); return; } save(); renderAll(); alert(`Plantilla cargada: ${added} frente(s) agregado(s).`); }
  function mergeAllDuplicates(){ const groups = findDuplicateGroups(); if(!groups.length){ alert('No hay frentes duplicados.'); return; } let merged = 0; groups.forEach(group => { const keep = group[0]; const remove = group.slice(1).map(f => f.id); remove.forEach(id => { state.entries.forEach(e => { if(e.frontId === id) e.frontId = keep.id; }); state.fronts = state.fronts.filter(f => f.id !== id); merged++; }); }); save(); renderAll(); alert(`Fusión completada: ${merged} frente(s) duplicado(s) eliminado(s).`); }
  function mergeFronts(keepId, removeIds){ removeIds.forEach(id => { state.entries.forEach(e => { if(e.frontId === id) e.frontId = keepId; }); state.fronts = state.fronts.filter(f => f.id !== id); }); save(); renderAll(); }
  function addEntry(frontId, status, desc, images){ state.entries.push({ id: Date.now(), frontId, status, desc, images, ts: new Date().toISOString() }); save(); renderAll(); }

  function escapeHtml(value){ return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function normalizeListItems(value){ return String(value || '').split(/\r?\n/).map(i => i.trim()).filter(Boolean); }
  function renderBulletList(items, fallbackText){
    const normalizedItems = Array.isArray(items) ? items.map(i => String(i || '').trim()).filter(Boolean) : normalizeListItems(fallbackText);
    if(!normalizedItems.length){ return '<div class="report-empty-state">Sin elementos registrados.</div>'; }
    return `<ul class="report-list-items">${normalizedItems.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
  }
  function formatDateForDisplay(value){
    if(!value) return '';
    const parts = String(value).split('-');
    if(parts.length !== 3) return value;
    const [year, month, day] = parts;
    return `${day}/${month}/${year}`;
  }
  function getLaborDateRangeText(){
    const from = formatDateForDisplay(state.laborDateFrom || '');
    const to = formatDateForDisplay(state.laborDateTo || '');
    if(from && to) return `Del ${from} al ${to}`;
    if(from) return `Del ${from}`;
    if(to) return `Al ${to}`;
    return (state.laborDateRange || '').trim();
  }
  function statusBadge(status, extra){ const cls = STATUS_BADGE[status] || 'bg-info text-dark'; const label = extra ? `${escapeHtml(status)} ${extra}` : escapeHtml(status); return `<span class="badge badge-status ${cls}">${label}</span>`; }

  function getReportItems(){ if(!state.combineByStatus) return state.entries.map(e => ({ ...e, combined: false })); const map = new Map(); const order = []; state.entries.forEach(e => { const key = `${e.frontId}::${e.status}`; if(!map.has(key)){ map.set(key, { frontId: e.frontId, status: e.status, descs: [], images: [], ts: e.ts, count: 0, combined: true }); order.push(key); } const g = map.get(key); if(e.desc) g.descs.push(e.desc); g.images.push(...(e.images || [])); if(e.ts > g.ts) g.ts = e.ts; g.count++; }); return order.map(key => { const g = map.get(key); return { frontId: g.frontId, status: g.status, desc: g.descs.join(' · '), images: g.images, ts: g.ts, combined: g.count > 1, count: g.count }; }); }

  function buildSection2FrontList(groups){
    if(!groups.length){ return '<div class="report-empty-state">No hay frentes registrados.</div>'; }
    return groups.map((group, index) => {
      const subsectionTitle = `2.${index + 1}. ${group.front.name}`;
      return `<div class="report-subsection-block"><div class="report-subsection-title">${escapeHtml(subsectionTitle)}</div></div>`;
    }).join('');
  }

  function chunkImages(images, size = 2){
    const safeImages = Array.isArray(images) ? images : [];
    const chunks = [];
    for(let i = 0; i < safeImages.length; i += size){
      chunks.push(safeImages.slice(i, i + size));
    }
    return chunks;
  }

  function buildEquipmentEntryHtml(item){
    const photo = (item.images || [])[0] || '';
    const imageMarkup = photo
      ? `<div class="report-entry-image-frame"><img src="${photo}" class="thumb equipment-thumb" alt="Equipo"></div>`
      : '<div class="equipment-photo-placeholder">Sin foto</div>';
    return `
      <div class="report-equipment-entry">
        <div class="report-entry-body">
          <div class="report-entry-text">
            <div class="report-equipment-name">${escapeHtml(item.itemName || 'Sin nombre')}</div>
            <div class="report-equipment-meta"><strong>Ubicación:</strong> ${escapeHtml(item.buildingLocation || '—')}</div>
            <div class="report-equipment-meta"><strong>Cantidad:</strong> ${escapeHtml(String(item.quantity || 1))}</div>
            <div class="report-entry-status">${statusBadge(item.status)}</div>
            ${item.desc ? `<div class="report-entry-desc">${escapeHtml(item.desc)}</div>` : ''}
          </div>
          ${imageMarkup}
        </div>
      </div>
    `;
  }

  function buildEquipmentPages(entries){
    const items = Array.isArray(entries) ? entries : [];
    if(!items.length){
      return [{
        type: 'content',
        tag: 'REGISTRO DE EQUIPOS',
        body: '<div class="report-page-content"><div class="report-section-title">REGISTRO DE EQUIPOS</div><div class="report-empty-state">No hay equipos registrados.</div></div>'
      }];
    }
    const pages = [];
    for(let index = 0; index < items.length; index += 2){
      const chunk = items.slice(index, index + 2);
      const rowsHtml = chunk.map(item => buildEquipmentEntryHtml(item)).join('');
      pages.push({
        type: 'content',
        tag: 'REGISTRO DE EQUIPOS',
        body: `<div class="report-page-content">${pages.length === 0 ? '<div class="report-section-title">REGISTRO DE EQUIPOS</div>' : ''}${rowsHtml}</div>`
      });
    }
    return pages;
  }

  function buildSection3Pages(groups){
    if(!groups.length){
      return [{
        type: 'content',
        tag: 'OBSERVACIONES',
        body: '<div class="report-page-content"><div class="report-empty-state">No hay frentes ni entradas registradas.</div></div>'
      }];
    }

    const pages = [];
    const sectionHeader = '<div class="report-section-title">3. REPORTE FOTOGRÁFICO</div>';

    groups.forEach((group, groupIndex) => {
      const frontLabel = `3.${groupIndex + 1}. ${group.front.name}`;
      const items = Array.isArray(group.items) ? group.items : [];

      if(!items.length){
        pages.push({
          type: 'content',
          tag: frontLabel.toUpperCase(),
          body: `<div class="report-page-content">${pages.length === 0 ? sectionHeader : ''}<div class="report-subsection-title">${escapeHtml(frontLabel)}</div><div class="report-empty-state">Sin entradas para este frente.</div></div>`
        });
        return;
      }

      const pageGroups = [];
      let currentPage = { rows: [], photoCount: 0 };

      const addCurrentPage = () => {
        if(currentPage.rows.length){
          pageGroups.push(currentPage);
          currentPage = { rows: [], photoCount: 0 };
        }
      };

      items.forEach(item => {
        const photos = Array.isArray(item.images) ? item.images : [];
        if(!photos.length){
          addCurrentPage();
          pageGroups.push({ rows: [{ item, photos: [] }] });
          return;
        }

        let index = 0;
        while(index < photos.length){
          const available = 2 - currentPage.photoCount;
          const chunk = photos.slice(index, index + available);
          currentPage.rows.push({ item, photos: chunk, continuation: index > 0 });
          currentPage.photoCount += chunk.length;
          index += chunk.length;

          if(currentPage.photoCount === 2){
            addCurrentPage();
          }
        }
      });

      addCurrentPage();

      pageGroups.forEach((page, pageIndex) => {
        const rowsHtml = page.rows.map(row => {
          const imagesMarkup = row.photos.length ? `<div class="report-entry-images">${row.photos.map(src => `<div class="report-entry-image-frame"><img src="${src}" class="thumb" alt="Foto"></div>`).join('')}</div>` : '';
          const note = row.continuation ? `<div class="report-entry-note">Continuación</div>` : '';
          const item = row.item;
          const incidenceInfo = state.reportType === 'incidencia' ? `<div class="report-incident-info"><div><strong>Fecha:</strong> ${escapeHtml(item.incidentDate || 'Sin fecha')}</div><div><strong>Estado:</strong> ${escapeHtml(item.status || 'Sin estado')}</div><div><strong>Empresa responsable:</strong> ${escapeHtml(item.responsibleCompany || 'Sin empresa')}</div><div><strong>Ubicación:</strong> ${escapeHtml(item.buildingLocation || 'Sin ubicación')}</div></div>` : '';

          return `<div class="report-entry"><div class="report-entry-body"><div class="report-entry-text">${incidenceInfo}${item.desc ? `<div class="report-entry-desc"><strong>Descripción:</strong> ${escapeHtml(item.desc)}</div>` : ''}${note}</div>${imagesMarkup}</div></div>`;
        }).join('');

        pages.push({
          type: 'content',
          tag: frontLabel.toUpperCase(),
          body: `<div class="report-page-content">${pages.length === 0 ? sectionHeader : ''}<div class="report-subsection-title">${escapeHtml(frontLabel)}</div>${rowsHtml}</div>`
        });
      });
    });

    return pages;
  }

  function renderSelectionHeader(){
    const titleEl = $('selectionTitle');
    const subtitleEl = $('selectionSubtitle');
    const infoEl = $('selectedProjectInfo');
    const current = getCurrentProject();
    if(titleEl && subtitleEl){
      if(state.selectionStage === 'reportType' && current){
        titleEl.textContent = 'Crear reporte';
        subtitleEl.textContent = current.companyName
          ? `${current.companyName} · ${current.projectLocation || 'Sin ubicación'}`
          : current.projectLocation
            ? `Proyecto: ${current.projectName || 'Sin nombre'} · Ubicación: ${current.projectLocation}`
            : `Proyecto: ${current.projectName || 'Sin nombre'}`;
      } else if(state.showProjectForm && current){
        titleEl.textContent = 'Editar proyecto';
        subtitleEl.textContent = 'Actualiza la empresa, el nombre y la ubicación del proyecto.';
      } else if(state.projects.length > 0){
        titleEl.textContent = 'Selecciona un proyecto';
        subtitleEl.textContent = 'Elige un proyecto existente o crea uno nuevo para continuar.';
      } else {
        titleEl.textContent = 'Crea tu proyecto';
        subtitleEl.textContent = 'Completa los datos para empezar un nuevo reporte.';
      }
    }
    if(infoEl){
      if(state.selectionStage === 'reportType' && current){
        const canEditProject = canEditProjectFromCurrentRoute();
        infoEl.innerHTML = `
          <div class="project-summary-row mb-3">
            <div>
              <div class="fw-semibold mb-1">Proyecto activo</div>
              <div class="project-summary-value">${escapeHtml(current.projectName || 'Proyecto sin nombre')}</div>
            </div>
            ${canEditProject ? '<button id="selectionEditProjectInfoBtn" type="button" class="btn btn-link btn-sm project-edit-link"><i class="bi bi-pencil-square me-1"></i>Editar</button>' : ''}
          </div>
          <div class="project-summary-grid">
            <div>
              <div class="project-summary-label">Empresa</div>
              <div class="project-summary-value">${escapeHtml(current.companyName || 'Sin empresa')}</div>
            </div>
            <div>
              <div class="project-summary-label">Ubicación</div>
              <div class="project-summary-value">${escapeHtml(current.projectLocation || 'Sin ubicación')}</div>
            </div>
          </div>`;
      } else {
        infoEl.innerHTML = '';
      }
    }
  }

  function renderAll(){
    if(state.showIssueForm && state.existingReportOpen && !issueFormManuallyOpened){
      state.showIssueForm = false;
    }
    const profileSection = $('profileSection');
    const routeInfo = getRouteInfo();
    const showProfile = !!state.showProfileView && !routeInfo.onPanelPath;
    $('reportWorkspaceSection')?.classList.toggle('preview-only', !!state.showPreviewMode);
    profileSection?.classList.toggle('d-none', !showProfile);
    $('dashboardHubSection')?.classList.toggle('d-none', showProfile || (isOnReportWorkspaceRoute() && !routeInfo.onPanelPath));
    $('reportWorkspaceSection')?.classList.toggle('d-none', showProfile || (!isOnReportWorkspaceRoute() && !routeInfo.onPanelPath));
    renderSidebarContext();
    renderProjectSelect();
    renderProjectPanel();
    renderDashboardHub();
    renderSelectionHeader();
    renderSelectionReportList();
    renderReportList();
    const createProjectBtn = $('createProjectBtn');
    const backToMainPanelBtn = $('backToMainPanelBtn');
    const isEditingProject = !!(state.showProjectForm && state.currentProjectId);
    if(createProjectBtn){
      createProjectBtn.innerHTML = isEditingProject
        ? '<i class="bi bi-check2-circle me-2"></i>Guardar cambios'
        : '<i class="bi bi-plus-circle me-2"></i>Crear proyecto';
    }
    if(backToMainPanelBtn){
      backToMainPanelBtn.textContent = isEditingProject ? 'Cancelar edición' : 'Volver al panel principal';
    }
    const reportBackActions = $('reportBackActions');
    if(reportBackActions){
      reportBackActions.classList.toggle('d-none', !isOnReportWorkspaceRoute() || !!state.editingReportMeta);
    }
    const deleteCurrentReportBtn = $('deleteCurrentReportBtn');
    const editCurrentReportBtn = $('editCurrentReportBtn');
    const currentReport = getCurrentReport();
    if(deleteCurrentReportBtn){
      deleteCurrentReportBtn.classList.toggle('d-none', !isOnReportWorkspaceRoute() || !currentReport?.canEdit);
    }
    if(editCurrentReportBtn){
      editCurrentReportBtn.classList.toggle('d-none', !isOnReportWorkspaceRoute() || !currentReport?.canEdit || !!state.editingReportMeta);
    }
    const helperText = $('projectHelperText');
    if(helperText){
      if(state.currentProjectId){
        helperText.textContent = '';
        helperText.classList.add('d-none');
      } else {
        helperText.textContent = 'Selecciona un proyecto existente o crea uno nuevo para comenzar un reporte.';
        helperText.classList.remove('d-none');
      }
    }
    $('exportPdfBtn')?.classList.toggle('d-none', !isOnReportWorkspaceRoute());
    $('exportPdfMode')?.classList.toggle('d-none', !isOnReportWorkspaceRoute());
    renderReportEditorSections();
    renderReportTypeUi();
    applyWorkspaceView();
    renderFrontList();
    renderFrontSelect();
    renderFrontDetail();
    renderDuplicateAlert();
    renderExistingEntryImages();
    if($('addFrontBtn')) $('addFrontBtn').innerHTML = state.editingFrontId ? '<i class="bi bi-check2 me-1"></i>Guardar frente' : '<i class="bi bi-plus-lg me-1"></i>Agregar frente';
    const companyNameInput = $('companyName');
    const projectNameInput = $('projectName');
    const projectLocationInput = $('projectLocation');
    const reportTitleInput = $('reportTitle');
    const reportWeekInput = $('reportWeek');
    const reportDateInput = $('reportDate');
    const laborDateFromInput = $('laborDateFrom');
    const laborDateToInput = $('laborDateTo');
    const forWhomInput = $('forWhom');
    const fromWhomInput = $('fromWhom');
    const objectiveTextInput = $('objectiveText');
    const analysisTextInput = $('analysisText');
    if(companyNameInput) companyNameInput.value = state.companyName || 'VDC CONSTRUCCIONES SAC';
    if(projectNameInput) projectNameInput.value = state.projectName || '';
    if(projectLocationInput) projectLocationInput.value = state.projectLocation || '';
    if(reportTitleInput) reportTitleInput.value = state.reportTitle || 'REPORTE FOTOGRÁFICO DE OBRA';
    if(reportWeekInput) reportWeekInput.value = state.reportWeek || '8';
    if(reportDateInput) reportDateInput.value = state.reportDate || new Date().toISOString().slice(0, 10);
    if(laborDateFromInput) laborDateFromInput.value = state.laborDateFrom || '';
    if(laborDateToInput) laborDateToInput.value = state.laborDateTo || '';
    if(forWhomInput) forWhomInput.value = state.forWhom || '';
    if(fromWhomInput) fromWhomInput.value = state.fromWhom || '';
    if(objectiveTextInput) objectiveTextInput.value = state.objectiveText || '';
    if(analysisTextInput) analysisTextInput.value = state.analysisText || '';
    const metadataProjectName = $('metadataProjectName');
    const metadataReportType = $('metadataReportType');
    const metadataReportTypeDisplay = $('metadataReportTypeDisplay');
    const formExtras = $('reportFormExtras');
    if(metadataProjectName) metadataProjectName.value = state.projectName || '';
    if(metadataReportType) metadataReportType.value = state.reportType || '';
    if(metadataReportTypeDisplay) metadataReportTypeDisplay.value = getReportTypeLabel(state.reportType);
    const conclusionTextInput = $('conclusionText');
    const recommendationTextInput = $('recommendationText');
    if(conclusionTextInput) conclusionTextInput.value = state.conclusionText || '';
    if(recommendationTextInput) recommendationTextInput.value = state.recommendationText || '';
    if(formExtras){
      formExtras.classList.toggle('d-none', !(state.reportMetaComplete || state.existingReportOpen));
    }
    applyPermissionLocks();
    if(state.showPreviewMode && !$('previewSection')?.classList.contains('d-none')){
      refreshPreviewContent().catch(error => console.warn('No se pudo refrescar la vista previa del reporte', error));
    }
  }

  function renderReportTypeUi(){
    const equipmentMode = isEquipmentReport();
    const incidentMode = state.reportType === 'incidencia';
    $('incidentFields')?.classList.toggle('d-none', !incidentMode);
    $('entryLocationFields')?.classList.toggle('d-none', equipmentMode);
    if(incidentMode) renderResponsibleCompanySelect();
    document.querySelectorAll('.js-metadata-obra-only').forEach(el => {
      el.classList.toggle('d-none', equipmentMode);
    });
    const workspaceTitle = $('reportWorkspaceTitle');
    const workspaceDesc = $('reportWorkspaceDesc');
    if(workspaceTitle){
      workspaceTitle.textContent = equipmentMode ? 'Datos del acta de equipos' : 'Datos del reporte';
    }
    if(workspaceDesc){
      workspaceDesc.textContent = equipmentMode
        ? 'Completa portada y ficha técnica. Luego registra cada equipo con su foto.'
        : 'Completa la información general antes de registrar frentes e issues.';
    }
    document.querySelectorAll('.js-nav-equipos').forEach(el => el.classList.toggle('d-none', !equipmentMode));
    document.querySelectorAll('.js-nav-fronts, .js-nav-issues').forEach(el => el.classList.toggle('d-none', equipmentMode));
    const combineByStatus = $('combineByStatus');
    if(combineByStatus){
      combineByStatus.closest('.form-check')?.classList.toggle('d-none', equipmentMode);
    }
    $('reportConclusionsSection')?.classList.toggle('d-none', equipmentMode || incidentMode);
    $('reportFrontsSection')?.classList.toggle('d-none', equipmentMode);
  }

  function clearEquipmentPhotoInputs(){
    if($('equipmentPhotoInput')) $('equipmentPhotoInput').value = '';
    if($('equipmentPhotoCameraInput')) $('equipmentPhotoCameraInput').value = '';
  }

  function getEquipmentPhotoFiles(){
    const cameraFiles = $('equipmentPhotoCameraInput')?.files ? Array.from($('equipmentPhotoCameraInput').files) : [];
    const pickerFiles = $('equipmentPhotoInput')?.files ? Array.from($('equipmentPhotoInput').files) : [];
    return [...cameraFiles, ...pickerFiles].slice(0, 1);
  }

  function resetEquipmentEditor(){
    state.editingEntryId = null;
    if($('equipmentName')) $('equipmentName').value = '';
    if($('equipmentBuilding')) $('equipmentBuilding').value = '';
    if($('equipmentQuantity')) $('equipmentQuantity').value = '1';
    if($('equipmentStatusSelect')) $('equipmentStatusSelect').value = 'Recepción';
    if($('equipmentComments')) $('equipmentComments').value = '';
    if($('addEquipmentBtn')) $('addEquipmentBtn').textContent = 'Agregar equipo';
    $('cancelEquipmentEditBtn')?.classList.add('d-none');
    clearEquipmentPhotoInputs();
  }

  async function ensureEquipmentFront(){
    const existing = state.fronts.find(front => front.name === 'Equipos') || state.fronts[0];
    if(existing) return existing.id;
    const project = getCurrentProject();
    if(!project || !state.currentReportId){
      throw new Error('Primero guarda el reporte antes de registrar equipos.');
    }
    const front = await createFrontRemote(project, state.currentReportId, 'Equipos');
    state.fronts.push(front);
    const report = getCurrentReport();
    if(report) report.fronts = [...state.fronts];
    save();
    return front.id;
  }

  function renderEquipmentList(){
    const container = $('equipmentList');
    if(!container) return;
    if(!isEquipmentReport()){
      container.innerHTML = '';
      return;
    }
    if(!state.entries.length){
      container.innerHTML = '<p class="text-muted small mb-0">Aún no hay equipos registrados.</p>';
      return;
    }
    container.innerHTML = state.entries.map(entry => {
      const thumb = (entry.images || [])[0]
        ? `<img src="${entry.images[0]}" class="equipment-list-thumb" alt="">`
        : '<span class="equipment-list-thumb equipment-list-thumb-empty">Sin foto</span>';
      return `
        <div class="entry-list-item equipment-list-item">
          <div class="entry-list-meta d-flex align-items-start gap-2">
            ${thumb}
            <div>
              <strong>${escapeHtml(entry.itemName || 'Sin nombre')}</strong>
              <div class="small text-muted">${escapeHtml(entry.buildingLocation || 'Sin ubicación')} · Cant. ${escapeHtml(String(entry.quantity || 1))}</div>
              <span class="badge badge-status ${STATUS_BADGE[entry.status] || 'bg-info text-dark'}">${escapeHtml(entry.status)}</span>
              ${entry.desc ? `<div class="small mt-1">${escapeHtml(entry.desc)}</div>` : ''}
            </div>
          </div>
          <div class="entry-list-actions">
            <button data-id="${entry.id}" class="btn btn-sm btn-outline-primary edit-equipment">Editar</button>
            <button data-id="${entry.id}" class="btn btn-sm btn-outline-danger delete-equipment">Eliminar</button>
          </div>
        </div>
      `;
    }).join('');
    container.querySelectorAll('.edit-equipment').forEach(btn => btn.addEventListener('click', () => {
      const entry = getEntryById(Number(btn.dataset.id));
      if(!entry) return;
      state.editingEntryId = entry.id;
      $('equipmentName').value = entry.itemName || '';
      $('equipmentBuilding').value = entry.buildingLocation || '';
      $('equipmentQuantity').value = String(entry.quantity || 1);
      $('equipmentStatusSelect').value = entry.status || 'Recepción';
      $('equipmentComments').value = entry.desc || '';
      $('addEquipmentBtn').textContent = 'Guardar equipo';
      $('cancelEquipmentEditBtn')?.classList.remove('d-none');
      clearEquipmentPhotoInputs();
      $('equipmentName')?.focus();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }));
    container.querySelectorAll('.delete-equipment').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if(confirm('¿Eliminar este equipo del reporte?')) removeEntry(id);
    }));
  }

  function applyWorkspaceView(){
    const shouldShowWorkspaceControls = isOnReportWorkspaceRoute() && (
      hasActiveReportWorkspaceContext() || !!state.reportType || !!state.currentProjectId
    );
    const view = state.workspaceView || 'summary';
    const equipmentSection = $('equipmentSection');
    const reportFrontsSection = $('reportFrontsSection');
    const frontDetailSection = $('frontDetailSection');
    const entrySection = $('entrySection');
    const previewSection = $('previewSection');
    const existingReportSummarySection = $('existingReportSummarySection');
    const reportConclusionsSection = $('reportConclusionsSection');
    const equipmentMode = isEquipmentReport();
    const incidentMode = state.reportType === 'incidencia';
    const formOpen = !!state.showIssueForm && issueFormManuallyOpened;
    const detailOpen = !formOpen && !!state.selectedEntryId;

    document.querySelectorAll('[data-workspace-view]').forEach(link => {
      link.classList.toggle('active', shouldShowWorkspaceControls && link.dataset.workspaceView === view);
    });

    if(!shouldShowWorkspaceControls){
      return;
    }

    state.showPreviewMode = view === 'preview';

    if(existingReportSummarySection){
      existingReportSummarySection.classList.toggle('d-none', equipmentMode || view !== 'summary');
    }
    if(equipmentSection){
      equipmentSection.classList.toggle('d-none', !equipmentMode || view !== 'equipment');
    }
    if(reportFrontsSection){
      reportFrontsSection.classList.toggle('d-none', equipmentMode || view !== 'fronts');
    }
    if(frontDetailSection){
      const shouldShowFrontDetail = !equipmentMode && view === 'issues' && !formOpen && !detailOpen && (
        state.reportType === 'incidencia' || state.currentFrontId || state.fronts.length || state.entries.length
      );
      frontDetailSection.classList.toggle('d-none', !shouldShowFrontDetail);
    }
    if(entrySection){
      const shouldShowEntrySection = !equipmentMode && view === 'issues' && formOpen;
      entrySection.classList.toggle('d-none', !shouldShowEntrySection);
      entrySection.classList.toggle('issue-form-view', formOpen);
    }
    $('issueDetailPanel')?.classList.toggle('d-none', !(!equipmentMode && view === 'issues' && detailOpen));
    if(reportConclusionsSection){
      reportConclusionsSection.classList.toggle('d-none', equipmentMode || incidentMode || view !== 'summary');
    }
    if(previewSection){
      previewSection.classList.toggle('d-none', view !== 'preview');
    }
  }

  function renderSidebarContext(){
    const shouldShowWorkspaceControls = isOnReportWorkspaceRoute() && hasActiveReportWorkspaceContext();
    $('sidebarDashboardGroup')?.classList.toggle('d-none', shouldShowWorkspaceControls);
    $('sidebarWorkspaceGroup')?.classList.toggle('d-none', !shouldShowWorkspaceControls);
    document.querySelectorAll('.js-nav-equipos').forEach(el => el.classList.toggle('d-none', !isEquipmentReport()));
    document.querySelectorAll('.js-nav-fronts, .js-nav-issues').forEach(el => el.classList.toggle('d-none', isEquipmentReport()));
  }

  function renderFrontDetail(){
    const selectedFront = state.fronts.find(f => f.id === state.currentFrontId);
    const globalIncidentList = state.reportType === 'incidencia';
    const selectedName = $('selectedFrontName');
    const list = $('frontIssueList');
    const detailPanel = $('issueDetailPanel');
    if(selectedName){ selectedName.textContent = globalIncidentList ? 'Todos los frentes' : (selectedFront ? frontLabel(selectedFront) : ''); }
    if(!list) return;
    if(!selectedFront && !globalIncidentList){
      list.innerHTML = '<p class="text-muted small mb-0">Selecciona un frente para ver sus issues.</p>';
      if(detailPanel){ detailPanel.classList.add('d-none'); detailPanel.innerHTML = ''; }
      return;
    }
    const entries = globalIncidentList ? [...state.entries] : state.entries.filter(e => e.frontId === selectedFront.id);
    if(!entries.length){
      list.innerHTML = '<p class="text-muted small mb-0">No hay issues creados en este frente.</p>';
      if(detailPanel){ detailPanel.classList.add('d-none'); detailPanel.innerHTML = ''; }
      return;
    }
    if(state.reportType === 'incidencia'){
      list.innerHTML = `<div class="incident-table-wrap"><table class="incident-table"><thead><tr><th>N.º</th><th>Frente</th><th>Descripción</th><th>Ubicación</th><th>Estado</th><th>Fecha</th><th>Empresa responsable</th><th>Acciones</th></tr></thead><tbody>${entries.map((entry, index) => { const front = state.fronts.find(item => Number(item.id) === Number(entry.frontId)); return `<tr><td>${index + 1}</td><td>${escapeHtml(front?.name || 'Sin frente')}</td><td class="incident-table-description">${escapeHtml(entry.desc || 'Sin descripción')}</td><td>${escapeHtml(getIssueLocationLabel(entry, index))}</td><td>${statusBadge(entry.status || 'Sin estado')}</td><td>${escapeHtml(entry.incidentDate || 'Sin fecha')}</td><td>${escapeHtml(entry.responsibleCompany || 'Sin empresa')}</td><td><div class="incident-table-actions"><button data-id="${entry.id}" class="btn btn-sm btn-outline-secondary view-entry-detail" title="Ver detalle" aria-label="Ver detalle"><i class="bi bi-eye"></i></button><button data-id="${entry.id}" class="btn btn-sm btn-outline-primary edit-entry" title="Editar" aria-label="Editar"><i class="bi bi-pencil"></i></button><button data-id="${entry.id}" class="btn btn-sm btn-outline-danger delete-entry" title="Eliminar" aria-label="Eliminar"><i class="bi bi-trash3"></i></button></div></td></tr>`; }).join('')}</tbody></table></div>`;
    } else {
      list.innerHTML = entries.map((entry, index) => {
        const locationLabel = (entry.buildingLocation || (entry.planId && entry.planX != null && entry.planY != null)) ? getIssueLocationLabel(entry, index) : '';
        return `<div class="issue-item card mb-2 p-3"><div class="d-flex justify-content-between align-items-start flex-wrap gap-2"><div><strong>${escapeHtml(entry.desc || 'Issue sin descripción')}</strong><div class="small text-muted">${escapeHtml(entry.status)} · ${escapeHtml(selectedFront.name)}${locationLabel ? ` · ${escapeHtml(locationLabel)}` : ''}</div></div><div class="d-flex gap-2"><button data-id="${entry.id}" class="btn btn-sm btn-outline-secondary view-entry-detail">Ver detalle</button><button data-id="${entry.id}" class="btn btn-sm btn-outline-primary edit-entry">Editar</button><button data-id="${entry.id}" class="btn btn-sm btn-outline-danger delete-entry">Eliminar</button></div></div></div>`;
      }).join('');
    }
    list.querySelectorAll('.edit-entry').forEach(btn => btn.addEventListener('click', () => {
      const entry = getEntryById(Number(btn.dataset.id));
      if(!entry) return;
      state.selectedEntryId = null;
      state.editingEntryId = entry.id;
      state.showIssueForm = true;
      issueFormManuallyOpened = true;
      $('selectFront').value = entry.frontId;
      $('selectFront').disabled = false;
        $('selectFront').disabled = false;
      $('statusSelect').value = entry.status;
      loadIncidentFields(entry);
      $('entryDesc').value = entry.desc || '';
      $('addEntryBtn').textContent = 'Guardar cambios';
      $('cancelEntryEditBtn').classList.remove('d-none');
        pendingRemovedEntryImageIds = new Set();
        clearEntryPhotoInputs();
      save();
      renderAll();
        renderExistingEntryImages();
      $('entryDesc')?.focus();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }));
    list.querySelectorAll('.delete-entry').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if(confirm('¿Borrar esta entrada del reporte?')) removeEntry(id);
    }));
    list.querySelectorAll('.view-entry-detail').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      state.showIssueForm = false;
      state.selectedEntryId = id;
      renderAll();
    }));
    if(detailPanel){
      const selectedEntry = getEntryById(state.selectedEntryId);
      if(!selectedEntry || (!globalIncidentList && selectedEntry.frontId !== selectedFront.id)){
        detailPanel.classList.add('d-none');
        detailPanel.innerHTML = '';
        state.selectedEntryId = null;
      } else {
        const imagesHtml = Array.isArray(selectedEntry.images) && selectedEntry.images.length
          ? selectedEntry.images.map(src => `<img src="${src}" class="img-fluid mb-2" style="width: 100%; height: auto; display: block; margin-bottom: 0.75rem; object-fit: contain;">`).join('')
          : '<div class="text-muted small">No hay fotos disponibles.</div>';
        const entryIndex = entries.findIndex(item => Number(item.id) === Number(selectedEntry.id));
        const hasLocation = !!(selectedEntry.buildingLocation || (selectedEntry.planId && selectedEntry.planX != null && selectedEntry.planY != null));
        const incidentDetail = state.reportType === 'incidencia' ? `<div class="small text-muted mb-3"><div><strong>Fecha:</strong> ${escapeHtml(selectedEntry.incidentDate || 'Sin fecha')}</div><div><strong>Empresa responsable:</strong> ${escapeHtml(selectedEntry.responsibleCompany || 'Sin empresa')}</div><div><strong>Ubicación:</strong> ${escapeHtml(getIssueLocationLabel(selectedEntry, entryIndex >= 0 ? entryIndex : null))}</div></div>` : (hasLocation ? `<div class="small text-muted mb-3"><div><strong>Ubicación:</strong> ${escapeHtml(getIssueLocationLabel(selectedEntry, entryIndex >= 0 ? entryIndex : null))}</div></div>` : '');
        detailPanel.innerHTML = `<div class="section-card-header section-card-header-compact mb-3"><span class="section-icon"><i class="bi bi-eye"></i></span><div class="flex-grow-1"><h2 class="section-title mb-0">Detalle de issue</h2><p class="section-desc mb-0">Vista independiente del issue seleccionado.</p></div></div><div class="d-flex justify-content-between align-items-center gap-2 mb-3 issue-form-view-header"><span class="small text-muted">Detalle independiente de incidencia</span><button type="button" class="btn btn-outline-secondary btn-sm close-entry-detail"><i class="bi bi-arrow-left me-1"></i>Volver a incidencias</button></div><div class="mb-2"><span class="badge bg-secondary">${escapeHtml(selectedEntry.status)}</span></div>${incidentDetail}<div class="mb-3">${escapeHtml(selectedEntry.desc || 'Sin descripción')}</div>${imagesHtml}`;
        detailPanel.querySelector('.close-entry-detail').addEventListener('click', () => {
          state.selectedEntryId = null;
          renderAll();
        });
      }
    }
  }

  function renderFrontList(){ const container = $('frontList'); container.innerHTML = ''; if(!state.fronts.length){ container.innerHTML = '<p class="text-muted small mb-0">Sin frentes. Agrega uno para poder registrar issues.</p>'; return; } state.fronts.forEach(f => { const n = frontNumber(f.id); const div = document.createElement('div'); div.className = 'front-item d-flex align-items-center justify-content-between flex-wrap gap-2'; div.innerHTML = `<div class="d-flex align-items-center gap-2"><span class="badge bg-dark front-num">${n}</span><span>${escapeHtml(f.name)}</span></div><div class="d-flex gap-2 flex-wrap"><button data-id="${f.id}" class="btn btn-sm btn-outline-primary edit-front-btn">Editar</button><button data-id="${f.id}" class="btn btn-sm btn-danger rm-front">Eliminar</button></div>`; container.appendChild(div); }); container.querySelectorAll('.rm-front').forEach(b => b.addEventListener('click', () => { const id = Number(b.dataset.id); if(confirm('¿Eliminar frente y sus entradas?')) removeFront(id); })); container.querySelectorAll('.edit-front-btn').forEach(b => b.addEventListener('click', () => { const id = Number(b.dataset.id); if(id) editFront(id); })); }
  function renderEntryList(){ const container = $('entryList'); container.innerHTML = ''; const selectedFront = state.fronts.find(f => f.id === state.currentFrontId); const entries = selectedFront ? state.entries.filter(e => e.frontId === selectedFront.id) : state.entries; if(!entries.length){ container.innerHTML = '<p class="text-muted small mb-0">No hay issues en este frente. Crea una nueva issue cuando la necesites.</p>'; return; } entries.forEach(entry => { const front = state.fronts.find(f => f.id === entry.frontId); const name = front ? front.name : 'Frente eliminado'; const div = document.createElement('div'); div.className = 'entry-list-item'; div.innerHTML = `<div class="entry-list-meta"><div><strong>${escapeHtml(name)}</strong><br><span class="badge badge-status ${STATUS_BADGE[entry.status] || 'bg-info text-dark'}">${escapeHtml(entry.status)}</span></div><div class="entry-list-actions"><button data-id="${entry.id}" class="btn btn-sm btn-outline-primary edit-entry">Editar</button><button data-id="${entry.id}" class="btn btn-sm btn-outline-danger delete-entry">Borrar</button></div></div><div class="entry-list-body">${escapeHtml(entry.desc || 'Sin descripción')}</div>`; container.appendChild(div); }); container.querySelectorAll('.edit-entry').forEach(btn => btn.addEventListener('click', e => { const entry = getEntryById(Number(e.target.dataset.id)); if(!entry) return; state.editingEntryId = entry.id; state.showIssueForm = true; $('selectFront').value = entry.frontId; $('selectFront').disabled = true; $('statusSelect').value = entry.status; $('entryDesc').value = entry.desc || ''; $('addEntryBtn').textContent = 'Guardar cambios'; $('cancelEntryEditBtn').classList.remove('d-none'); $('photoInput').value = ''; save(); renderAll(); $('entryDesc')?.focus(); window.scrollTo({ top: 0, behavior: 'smooth' }); })); container.querySelectorAll('.delete-entry').forEach(btn => btn.addEventListener('click', e => { const id = Number(e.target.dataset.id); if(confirm('¿Borrar esta entrada del reporte?')) removeEntry(id); })); }
  function renderDuplicateAlert(){ const el = $('duplicateAlert'); if(!el) return; const groups = findDuplicateGroups(); if(!groups.length){ el.innerHTML = ''; return; } el.innerHTML = groups.map(group => { const names = group.map(f => `${frontNumber(f.id)}. ${escapeHtml(f.name)}`).join(', '); const keepId = group[0].id; const removeIds = group.slice(1).map(f => f.id); return `<div class="dup-group small"><strong>Duplicados:</strong> ${names}<button class="btn btn-sm btn-warning ms-2 merge-group" data-keep="${keepId}" data-remove="${removeIds.join(',')}">Fusionar</button></div>`; }).join(''); el.querySelectorAll('.merge-group').forEach(btn => btn.addEventListener('click', e => { const keepId = Number(e.target.dataset.keep); const removeIds = e.target.dataset.remove.split(',').map(Number); mergeFronts(keepId, removeIds); })); }
  function updatePreviewScale(){
    const previewCanvas = $('previewCanvas');
    const previewScaleShell = $('previewScaleShell');
    const reportContainer = $('reportContainer');
    const previewGutter = window.innerWidth <= 1366 ? 24 : 12;
    if(!previewCanvas || !previewScaleShell || !reportContainer) return;

    previewScaleShell.style.width = '';
    previewScaleShell.style.height = '';
    previewCanvas.style.minHeight = '';
    reportContainer.style.transform = '';
    reportContainer.style.transformOrigin = '';

    const previewBounds = previewCanvas.getBoundingClientRect();
    const visibleViewportWidth = Math.max(0, window.innerWidth - previewBounds.left - previewGutter);
    const availableWidth = Math.max(0, Math.min(previewCanvas.clientWidth - previewGutter, visibleViewportWidth));
    const reportWidth = reportContainer.offsetWidth;
    const reportHeight = reportContainer.offsetHeight;
    if(!availableWidth || !reportWidth || !reportHeight) return;

    const scale = Math.min(1, availableWidth / reportWidth);
    previewScaleShell.style.width = `${Math.ceil(reportWidth * scale)}px`;
    previewScaleShell.style.height = `${Math.ceil(reportHeight * scale)}px`;
    reportContainer.style.transformOrigin = 'top left';
    reportContainer.style.transform = `scale(${scale})`;
    previewCanvas.style.minHeight = `${Math.ceil(reportHeight * scale)}px`;
  }

  function renderProjectSelect(){ const sel = $('projectSelect'); if(!sel) return; sel.innerHTML = ''; if(!state.projects.length){ const empty = document.createElement('option'); empty.value = ''; empty.textContent = 'Ningún proyecto creado'; sel.appendChild(empty); return; } const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Selecciona un proyecto'; placeholder.disabled = true; placeholder.selected = !state.currentProjectId; sel.appendChild(placeholder); state.projects.forEach(p => { const opt = document.createElement('option'); opt.value = p.id; opt.textContent = p.projectName || `Proyecto ${state.projects.indexOf(p) + 1}`; if(p.id === state.currentProjectId) opt.selected = true; sel.appendChild(opt); }); }
  function renderReportList(){ const section = $('reportListSection'); const list = $('reportList'); const activeInfo = $('activeReportInfo'); if(!section || !list || !activeInfo) return; section.classList.add('d-none'); activeInfo.textContent = ''; }
  function renderProjectPanel(){
    const selectGroup = $('projectSelectGroup');
    const displayGroup = $('projectDisplayGroup');
    const summaryCard = $('projectSummaryCard');
    const editForm = $('projectEditForm');
    const currentCompany = $('currentCompanyName');
    const currentName = $('currentProjectName');
    const currentLocation = $('currentProjectLocation');
    const editCompany = $('editCompanyName');
    const editName = $('editProjectName');
    const editLocation = $('editProjectLocation');
    const editProjectInfoBtn = $('editProjectInfoBtn');
    const current = getCurrentProject();
    const routeInfo = getRouteInfo();
    const isReportRoute = !!(routeInfo.onNewReportPath || routeInfo.onReportPath);
    const canEditProject = !!(
      (routeInfo.onProjectPath || routeInfo.onPanelPath || routeInfo.onNewProjectPath)
      && !isReportRoute
      && current?.canEdit
    );

    if(current && state.currentProjectId){
      if(isReportRoute){
        state.editingProjectInfo = false;
      }
      if(selectGroup) selectGroup.classList.add('d-none');
      if(displayGroup) displayGroup.classList.remove('d-none');
      if(summaryCard) summaryCard.classList.toggle('d-none', !!state.editingProjectInfo && canEditProject);
      if(editForm) editForm.classList.toggle('d-none', !state.editingProjectInfo || !canEditProject);
      if(editProjectInfoBtn) editProjectInfoBtn.classList.toggle('d-none', !canEditProject);
      if(currentCompany) currentCompany.textContent = current.companyName || 'Sin empresa';
      if(currentName) currentName.textContent = current.projectName || 'Proyecto sin nombre';
      if(currentLocation) currentLocation.textContent = current.projectLocation || 'Sin ubicación';
      if(editCompany) editCompany.value = state.companyName || current.companyName || 'VDC CONSTRUCCIONES SAC';
      if(editName) editName.value = state.projectName || current.projectName || '';
      if(editLocation) editLocation.value = state.projectLocation || current.projectLocation || '';
    } else {
      if(selectGroup) selectGroup.classList.remove('d-none');
      if(displayGroup) displayGroup.classList.add('d-none');
      if(summaryCard) summaryCard.classList.remove('d-none');
      if(editForm) editForm.classList.add('d-none');
      if(editProjectInfoBtn) editProjectInfoBtn.classList.add('d-none');
      if(currentCompany) currentCompany.textContent = '';
      if(currentName) currentName.textContent = '';
      if(currentLocation) currentLocation.textContent = '';
      if(editCompany) editCompany.value = '';
      if(editName) editName.value = '';
      if(editLocation) editLocation.value = '';
    }
  }
  function renderDashboardHub(){
    const introHeader = $('dashboardIntroHeader');
    const introActions = $('dashboardIntroActions');
    const dashboardNewProjectBtn = $('dashboardNewProjectBtn');
    const projectList = $('dashboardProjectList');
    const projectFormCard = $('dashboardProjectForm');
    const dashboardCompanyName = $('dashboardCompanyName');
    const dashboardProjectName = $('dashboardProjectName');
    const dashboardProjectLocation = $('dashboardProjectLocation');
    const projectFormTitle = $('dashboardProjectFormTitle');
    const reportHub = $('dashboardReportHub');
    const currentProjectName = $('dashboardCurrentProjectName');
    const projectSummary = $('dashboardProjectSummary');
    const reportList = $('dashboardReportList');
    const projectShareSection = $('projectShareSection');
    const projectShareToggle = $('projectShareToggle');
    const projectPlansTab = $('projectPlansTab');
    const projectSummaryTab = $('projectSummaryTab');
    const projectResponsiblesTab = $('projectResponsiblesTab');
    const plansSection = $('dashboardPlansSection');
    const responsiblesSection = $('dashboardResponsiblesSection');
    const responsiblesList = $('dashboardResponsiblesList');
    const responsiblesCount = $('projectResponsiblesCount');
    const responsibleForm = $('dashboardResponsibleForm');
    const reportsLabel = $('dashboardReportsLabel');
    const addTypeReportButton = $('dashboardAddTypeReportBtn');
    const plansList = $('dashboardPlansList');
    const plansCount = $('projectPlansCount');
    const uploadPlanButton = $('dashboardUploadPlanBtn');
    const projectSearch = $('dashboardProjectSearch');
    const current = getCurrentProject();
    const routeInfo = getRouteInfo();
    const showProjectDashboard = !!current && !routeInfo.onPanelPath && !isOnReportWorkspaceRoute() && !state.currentReportId;
    const showProjectChooser = routeInfo.onPanelPath || (!state.showProjectForm && (!current || isOnReportWorkspaceRoute()));
    document.body.classList.toggle('portfolio-home', showProjectChooser);
    $('dashboardHubSection')?.classList.toggle('dashboard-project-mode', showProjectDashboard);

    if(introHeader){
      introHeader.classList.toggle('d-none', !showProjectChooser);
    }
    if(introActions){
      introActions.classList.toggle('d-none', !showProjectChooser);
    }
    if(dashboardNewProjectBtn){
      dashboardNewProjectBtn.classList.toggle('d-none', !!current);
    }

    const totalProjects = state.projects.length;
    const activeProjects = state.projects.filter(project => (project.reports || []).length > 0).length;
    const planningProjects = totalProjects - activeProjects;
    $('dashboardTotalProjects') && ($('dashboardTotalProjects').textContent = totalProjects);
    $('dashboardActiveProjects') && ($('dashboardActiveProjects').textContent = activeProjects);
    $('dashboardPlanningProjects') && ($('dashboardPlanningProjects').textContent = planningProjects);
    $('dashboardCompleteProjects') && ($('dashboardCompleteProjects').textContent = 0);

    if(projectFormCard){
      projectFormCard.classList.toggle('d-none', !state.showProjectForm);
    }
    if(projectFormTitle){
      projectFormTitle.textContent = state.editingProjectInfo ? 'Editar proyecto' : 'Nuevo proyecto';
    }
    if(dashboardCompanyName) dashboardCompanyName.value = state.companyName || 'VDC CONSTRUCCIONES SAC';
    if(dashboardProjectName) dashboardProjectName.value = state.projectName || '';
    if(dashboardProjectLocation) dashboardProjectLocation.value = state.projectLocation || '';

    if(projectList){
      projectList.classList.toggle('d-none', !showProjectChooser);
      if(!state.projects.length){
        projectList.innerHTML = '<div class="text-muted small">No hay proyectos creados todavía.</div>';
      } else {
        const searchTerm = (projectSearch?.value || '').trim().toLowerCase();
        const visibleProjects = state.projects.filter(project => {
          const searchable = `${project.projectName || ''} ${project.companyName || ''} ${project.projectLocation || ''}`.toLowerCase();
          return !searchTerm || searchable.includes(searchTerm);
        });
        projectList.innerHTML = visibleProjects.map(project => `
          <div class="project-member-item dashboard-project-item" data-open-project="${project.id}" role="button" tabindex="0" aria-label="Entrar al proyecto ${escapeHtml(project.projectName || 'Proyecto sin nombre')}" title="Entrar al proyecto">
            <button type="button" class="dashboard-project-image ${project.projectImage ? 'has-image' : ''}" data-id="${project.id}" aria-label="Cargar foto del proyecto" title="Cargar foto">
              ${project.projectImage ? `<img src="${project.projectImage}" alt="">` : '<i class="bi bi-building" aria-hidden="true"></i>'}
              <span class="dashboard-project-image-edit"><i class="bi bi-camera-fill" aria-hidden="true"></i></span>
            </button>
            <div class="dashboard-project-copy">
              <div class="project-member-name">${escapeHtml(project.projectName || 'Proyecto sin nombre')}</div>
              <div class="dashboard-project-meta-row"><span>Empresa</span><strong>${escapeHtml(project.companyName || 'Sin empresa')}</strong></div>
              <div class="dashboard-project-meta-row"><span>Dirección</span><strong>${escapeHtml(project.projectLocation || 'Sin ubicación')}</strong></div>
            </div>
            <span class="dashboard-project-status ${project.reports?.length ? 'is-active' : ''}">${project.reports?.length ? 'ACTIVO' : 'PLANNING'}</span>
            <div class="dashboard-project-actions d-flex gap-2 flex-wrap">
              ${project.canEdit ? `<button type="button" data-id="${project.id}" class="btn btn-sm btn-outline-secondary dashboard-project-edit" aria-label="Editar proyecto" title="Editar proyecto"><i class="bi bi-pencil-square" aria-hidden="true"></i></button>` : ''}
              ${project.canDelete ? `<button type="button" data-id="${project.id}" class="btn btn-sm btn-outline-danger dashboard-project-delete" aria-label="Eliminar proyecto" title="Eliminar proyecto"><i class="bi bi-trash3" aria-hidden="true"></i></button>` : ''}
            </div>
          </div>
        `).join('') || '<div class="dashboard-projects-empty">No se encontraron proyectos.</div>';
      }
    }

    if(reportHub){
      reportHub.classList.toggle('d-none', !showProjectDashboard || state.showProjectForm);
    }
    if(!showProjectDashboard){
      if(currentProjectName) currentProjectName.textContent = '';
      if(projectSummary) projectSummary.innerHTML = '';
      if(reportList) reportList.innerHTML = '';
      return;
    }

    if(currentProjectName) currentProjectName.textContent = current.projectName || 'Proyecto sin nombre';
    const showingPlans = projectDashboardView === 'plans';
    const showingResponsibles = projectDashboardView === 'responsibles';
    const showingReports = projectDashboardView === 'reports';
    const reportTypeLabels = { incidencia: 'Reporte de incidencia', avances: 'Reporte de avances', equipos: 'Recepción y entrega de equipos' };
    projectSummaryTab?.classList.toggle('is-active', !showingPlans && !showingResponsibles && !showingReports);
    projectPlansTab?.classList.toggle('is-active', showingPlans);
    projectResponsiblesTab?.classList.toggle('is-active', showingResponsibles);
    document.querySelectorAll('#dashboardPlanReportTypes [data-report-type]').forEach(button => button.classList.toggle('is-active', showingReports && button.dataset.reportType === projectDashboardReportType));
    projectSummary?.classList.toggle('d-none', showingPlans || showingResponsibles || showingReports);
    projectShareToggle?.classList.toggle('d-none', showingPlans || showingResponsibles || showingReports);
    projectShareSection?.classList.toggle('d-none', showingPlans || showingResponsibles || showingReports || !showProjectShare);
    reportsLabel?.classList.toggle('d-none', (showingPlans || showingResponsibles) && !showingReports);
    reportList?.classList.toggle('d-none', showingPlans || showingResponsibles);
    plansSection?.classList.toggle('d-none', !showingPlans);
    responsiblesSection?.classList.toggle('d-none', !showingResponsibles);
    const responsibleCompanies = Array.isArray(current.responsibleCompanies) ? current.responsibleCompanies : [];
    if(responsiblesCount) responsiblesCount.textContent = responsibleCompanies.length;
    responsibleForm?.classList.toggle('d-none', !current.canEdit);
    if(responsiblesList){
      responsiblesList.innerHTML = responsibleCompanies.length ? responsibleCompanies.map(item => `
        <div class="dashboard-plan-item">
          <div class="dashboard-plan-icon"><i class="bi bi-person-badge" aria-hidden="true"></i></div>
          <div class="dashboard-plan-copy"><span>${escapeHtml(item.name)}</span></div>
          ${current.canEdit ? `<button type="button" class="btn btn-sm btn-outline-danger dashboard-responsible-delete" data-id="${item.id}" title="Eliminar responsable" aria-label="Eliminar responsable"><i class="bi bi-trash3" aria-hidden="true"></i></button>` : ''}
        </div>`).join('') : '<div class="dashboard-plans-empty"><i class="bi bi-person-badge" aria-hidden="true"></i><span>Aún no hay responsables agregados.</span></div>';
    }
    addTypeReportButton?.classList.toggle('d-none', !showingReports);
    if(addTypeReportButton) addTypeReportButton.innerHTML = `<i class="bi bi-plus-circle me-1"></i>Agregar ${reportTypeLabels[projectDashboardReportType] || 'reporte'}`;
    const plans = Array.isArray(current.plans) ? current.plans : [];
    uploadPlanButton?.classList.toggle('d-none', !current.canEdit);
    if(plansCount) plansCount.textContent = plans.length;
    if(plansList){
      plansList.innerHTML = plans.length ? plans.map(plan => `
        <div class="dashboard-plan-item">
          <div class="dashboard-plan-icon"><i class="bi bi-file-earmark-pdf-fill" aria-hidden="true"></i></div>
          <div class="dashboard-plan-copy">
            <button type="button" class="dashboard-plan-name" data-plan-id="${plan.id}">${escapeHtml(plan.name)}</button>
            <div class="dashboard-plan-meta">PDF · ${formatPlanDate(plan.createdAt)}</div>
          </div>
          ${current.canEdit ? `<button type="button" class="btn btn-sm btn-outline-danger dashboard-plan-delete" data-id="${plan.id}" title="Eliminar plano" aria-label="Eliminar plano"><i class="bi bi-trash3" aria-hidden="true"></i></button>` : ''}
        </div>`).join('') : '<div class="dashboard-plans-empty"><i class="bi bi-file-earmark-pdf" aria-hidden="true"></i><span>Aún no hay planos cargados.</span></div>';
    }
    const selectedPlan = plans.find(plan => plan.id === selectedPlanId) || null;
    renderPlanViewer(selectedPlan, current);
    if(projectSummary){
      projectSummary.innerHTML = `
        <div class="project-summary-grid">
          <div>
            <div class="project-summary-label">Empresa</div>
            <div class="project-summary-value">${escapeHtml(current.companyName || 'Sin empresa')}</div>
          </div>
          <div>
            <div class="project-summary-label">Ubicación</div>
            <div class="project-summary-value">${escapeHtml(current.projectLocation || 'Sin ubicación')}</div>
          </div>
        </div>
        <div class="project-summary-share-note mt-3">
          <strong>${current.isOwned ? 'Propietario' : 'Compartido por'}:</strong>
          ${escapeHtml(current.ownerDisplayName || current.ownerUsername || 'Usuario')}
        </div>`;
    }
    const projectMembersList = $('projectMembersList');
    if(projectShareSection){
      projectShareSection.classList.toggle('d-none', !showProjectShare);
    }
    if(projectShareToggle){
      projectShareToggle.classList.toggle('is-open', showProjectShare);
      projectShareToggle.setAttribute('aria-expanded', String(showProjectShare));
    }
    if(projectMembersList){
      const members = Array.isArray(current.members) ? current.members : [];
      projectMembersList.innerHTML = members.length
        ? members.map(member => `
          <div class="project-member-item">
            <div>
              <div class="project-member-name">${escapeHtml(member.username)}</div>
              <div class="project-member-meta">${escapeHtml(PROJECT_ROLE_LABELS[member.role] || member.role)}${member.isOwner ? ' · Propietario' : ' · Usuario compartido'}</div>
            </div>
          </div>`).join('')
        : '<div class="text-muted small">No hay usuarios compartidos.</div>';
    }
    const projectShareControls = projectShareSection?.querySelector('.project-share-controls');
    if(projectShareControls){
      projectShareControls.classList.toggle('d-none', !current.canShare);
    }
    if(reportList){
      const reports = (Array.isArray(current.reports) ? current.reports : []).filter(report => !showingReports || report.type === projectDashboardReportType);
      reportsLabel.textContent = showingReports ? `${reportTypeLabels[projectDashboardReportType] || 'Reportes'} del proyecto` : 'Reportes del proyecto';
      reportList.innerHTML = reports.length
        ? reports.map(report => `
          <div class="list-group-item dashboard-report-item">
            <div class="d-flex justify-content-between align-items-center gap-2 flex-wrap">
              <button type="button" data-id="${report.id}" class="btn btn-link p-0 text-start flex-grow-1 dashboard-report-open">${escapeHtml(report.title || 'Reporte sin título')}</button>
              <div class="d-flex align-items-center gap-2">
                ${(report.canShare) ? `<button type="button" data-report-share="${report.id}" class="btn btn-sm btn-outline-secondary" title="Colaboración"><i class="bi bi-people"></i></button>` : ''}
                ${(report.canEdit) ? `<button type="button" data-report-delete="${report.id}" class="btn btn-sm btn-outline-danger" title="Eliminar reporte"><i class="bi bi-trash"></i></button>` : ''}
              </div>
            </div>
            ${report.canShare ? `
              <div id="reportSharePanel-${report.id}" class="report-share-panel d-none mt-2">
                <div class="small text-muted mb-2">Colaboración del reporte</div>
                <div class="small mb-2">${Array.isArray(report.members) && report.members.length ? report.members.map(member => `${escapeHtml(member.username)} · ${escapeHtml(PROJECT_ROLE_LABELS[member.role] || member.role)}${member.isOwner ? ' · Owner' : ''}`).join('<br>') : 'Sin usuarios asignados.'}</div>
                <div class="row g-2">
                  <div class="col-md-5">
                    <input id="reportShareUsername-${report.id}" class="form-control form-control-sm" placeholder="Usuario">
                  </div>
                  <div class="col-md-4">
                    <select id="reportShareRole-${report.id}" class="form-select form-select-sm">
                      <option value="viewer">Lector</option>
                      <option value="editor">Editor</option>
                      <option value="admin">Administrador</option>
                    </select>
                  </div>
                  <div class="col-md-3">
                    <button type="button" data-report-share-save="${report.id}" class="btn btn-outline-primary btn-sm w-100">Guardar</button>
                  </div>
                </div>
              </div>` : ''}
          </div>`).join('')
        : '<div class="text-muted small">Aún no hay reportes creados para este proyecto.</div>';
    }
  }
  function renderSelectionReportList(){ const section = $('selectionReportListSection'); const list = $('selectionReportList'); if(!section || !list) return; const project = getCurrentProject(); if(!project || state.selectionStage !== 'reportType'){ section.classList.add('d-none'); return; } section.classList.remove('d-none'); const reports = project.reports || []; if(!reports.length){ list.innerHTML = '<div class="text-muted small mb-0">Aún no hay reportes creados para este proyecto.</div>'; return; } list.innerHTML = reports.map(report => { const active = report.id === state.currentReportId ? 'active' : ''; return `<div class="list-group-item d-flex justify-content-between align-items-center ${active}"><button type="button" data-id="${report.id}" class="btn btn-link p-0 text-start flex-grow-1 report-select-btn">${escapeHtml(report.title || 'Reporte sin título')}</button><button type="button" data-delete-id="${report.id}" class="btn btn-sm btn-outline-danger ms-2">Eliminar</button></div>`; }).join(''); }
  function renderReportEditorSections(){ const metadataForm = $('metadataForm'); const formExtras = $('reportFormExtras'); const editorSections = $('reportEditorSections'); const existingReportSummarySection = $('existingReportSummarySection'); const reportFrontsSection = $('reportFrontsSection'); const frontDetailSection = $('frontDetailSection'); const entrySection = $('entrySection'); const previewSection = $('previewSection'); const continueBtn = $('continueToEditorBtn'); const cancelReportMetaEditBtn = $('cancelReportMetaEditBtn'); const editReportInfoBtn = $('editReportInfoBtn'); const projectHeaderSection = $('projectHeaderSection'); const reportConclusionsSection = $('reportConclusionsSection'); const isEditingReportMeta = !!(state.editingReportMeta && state.existingReportOpen && isOnReportRoute()); const isInsideFrontDetail = !!state.currentFrontId; if(metadataForm){ metadataForm.classList.toggle('d-none', ((state.reportMetaComplete || state.existingReportOpen) && !isEditingReportMeta) || state.showPreviewMode); } if(formExtras){ formExtras.classList.toggle('d-none', isEditingReportMeta || !(state.reportMetaComplete || state.existingReportOpen)); } if(editorSections){ editorSections.classList.toggle('d-none', isEditingReportMeta || !state.reportMetaComplete); } if(existingReportSummarySection){ existingReportSummarySection.classList.toggle('d-none', !state.existingReportOpen || state.showPreviewMode || isEditingReportMeta || isInsideFrontDetail); } if(reportFrontsSection){ reportFrontsSection.classList.toggle('d-none', isEditingReportMeta || isInsideFrontDetail || !(state.reportMetaComplete || state.existingReportOpen) || state.showPreviewMode); } if(frontDetailSection){ frontDetailSection.classList.toggle('d-none', isEditingReportMeta || !isInsideFrontDetail || state.showPreviewMode); } if(entrySection){ entrySection.classList.toggle('d-none', isEditingReportMeta || !isInsideFrontDetail || state.showPreviewMode || !state.showIssueForm); } if(previewSection){ previewSection.classList.toggle('d-none', isEditingReportMeta || !state.showPreviewMode); } if(reportConclusionsSection){ reportConclusionsSection.classList.toggle('d-none', isEditingReportMeta || isInsideFrontDetail || state.showPreviewMode); } if(continueBtn){ continueBtn.classList.toggle('d-none', ((!isEditingReportMeta && (state.reportMetaComplete || state.existingReportOpen)) || state.showPreviewMode)); continueBtn.innerHTML = isEditingReportMeta ? '<i class="bi bi-check2-circle me-2"></i>Guardar datos del reporte' : '<i class="bi bi-arrow-right-circle me-2"></i>Crear reporte'; } if(cancelReportMetaEditBtn){ cancelReportMetaEditBtn.classList.toggle('d-none', !isEditingReportMeta || state.showPreviewMode); } if(editReportInfoBtn){ editReportInfoBtn.classList.toggle('d-none', !state.existingReportOpen || state.showPreviewMode || !isOnReportRoute() || isInsideFrontDetail); } if(projectHeaderSection){ projectHeaderSection.classList.toggle('d-none', isEditingReportMeta || isInsideFrontDetail); } }
  function renderFrontSelect(){ const sel = $('selectFront'); sel.innerHTML = ''; state.fronts.forEach(f => { const opt = document.createElement('option'); opt.value = f.id; opt.textContent = frontLabel(f); sel.appendChild(opt); }); if(state.currentFrontId && state.fronts.some(f => Number(f.id) === Number(state.currentFrontId))) sel.value = state.currentFrontId; sel.disabled = false; }
  function renderCompanyHeader(){ const company = (state.companyName || 'VDC CONSTRUCCIONES SAC').trim().toUpperCase(); return `<div class="report-page-header"><div class="report-company-header">${escapeHtml(company)}</div><div class="report-header-line"></div></div>`; }
  function renderPageFooter(pageNumber, totalPages){
    const footerAddress = escapeHtml((state.projectLocation || 'JR. BAHAMONDE 152, SURCO.').trim() || 'JR. BAHAMONDE 152, SURCO.');
    return `<div class="report-page-footer"><div class="report-footer-line"></div><div class="report-footer-text">${footerAddress}</div><div class="report-page-number">${pageNumber}/${totalPages}</div></div>`;
  }
  function renderCoverFooterBlock(pageNumber, totalPages){
    const footerAddress = escapeHtml((state.projectLocation || 'JR. BAHAMONDE 152, SURCO.').trim() || 'JR. BAHAMONDE 152, SURCO.');
    return `<div class="report-cover-footer-block"><div class="report-footer-separator"></div><div class="report-footer-address">${footerAddress}</div><div class="report-page-number">${pageNumber}/${totalPages}</div></div>`;
  }

  function renderReport(){
    const rc = $('reportContainer');
    if(!rc) return;
    rc.innerHTML = '';

    const reportTitle = (state.reportTitle || 'REPORTE FOTOGRÁFICO DE OBRA').trim();
    const reportWeek = (state.reportWeek || '8').trim();
    const fecha = (state.reportDate || '').trim() || new Date().toISOString().slice(0, 10);
    const projectName = (state.projectName || '').trim();
    const projectLocation = (state.projectLocation || '').trim();
    const mainImage = state.coverImage || (() => {
      const fallbackEntry = state.entries.find(e => (e.images || []).length);
      return fallbackEntry ? (fallbackEntry.images || [])[0] : '';
    })();
    const objectiveText = (state.objectiveText || '').trim();
    const analysisText = (state.analysisText || '').trim();
    const conclusionText = (state.conclusionText || '').trim();
    const recommendationText = (state.recommendationText || '').trim();
    const conclusionMarkup = renderBulletList(state.conclusionItems, conclusionText);
    const recommendationMarkup = renderBulletList(state.recommendationItems, recommendationText);
    const laborDateRange = getLaborDateRangeText();
    const groups = state.fronts.map(front => ({ front, items: state.entries.filter(e => e.frontId === front.id) }));
    const pages = [];

    const coverTitle = reportTitle;

    pages.push({
      type: 'cover',
      tag: 'PORTADA',
      body: `<div class="report-cover-title">${escapeHtml(coverTitle)}</div>`
    });

    pages.push({
      type: 'info',
      tag: 'FICHA TÉCNICA',
      body: `<div class="report-page-content report-info-page-content"><div class="secondary-head"><div><strong>Semana:</strong> ${escapeHtml(reportWeek || 'Sin semana')}</div><div><strong>Proyecto:</strong> ${escapeHtml(projectName || 'Sin nombre')}</div><div><strong>Ubicación:</strong> ${escapeHtml(projectLocation || 'Sin ubicación')}</div><div><strong>Fecha:</strong> ${escapeHtml(fecha)}</div></div><div class="secondary-photo-wrap">${mainImage ? `<img src="${mainImage}" class="secondary-main-photo" alt="Foto principal">` : '<div class="secondary-photo-placeholder">Insertar foto principal</div>'}</div><div class="secondary-meta-row"><div class="secondary-meta-block"><label>Solicitado por</label><div>${escapeHtml(state.forWhom || 'Sin dato')}</div></div><div class="secondary-meta-block"><label>Responsable</label><div>${escapeHtml(state.fromWhom || 'Sin dato')}</div></div></div></div>`
    });

    if(isEquipmentReport()){
      pages.push(...buildEquipmentPages(state.entries));
    } else {
    pages.push({
      type: 'section',
      tag: '1. OBJETIVO + 2. ANÁLISIS',
      body: `<div class="report-page-content"><div class="report-section-title">1. OBJETIVO</div><div class="report-section-body">${escapeHtml(objectiveText || 'El presente informe tiene como objetivo registrar de manera técnica y fotográfica los avances físicos logrados durante la presente semana de trabajo, detallando las partidas ejecutadas en los frentes de demolición, estructuras, albañilería, instalaciones y acabados, asegurando el control de calidad en cada proceso.')}</div><div class="report-section-title" style="margin-top: 24px;">2. ANÁLISIS: AVANCES DE LA SEMANA</div>${laborDateRange ? `<div class="report-section-subtitle"><strong>Fecha de labores:</strong> ${escapeHtml(laborDateRange)}</div>` : ''}<div class="report-section-body">${escapeHtml(analysisText || 'Agregar el análisis de las actividades ejecutadas y avanzadas durante la semana.')}</div>${buildSection2FrontList(groups)}</div>`
    });

    pages.push(...buildSection3Pages(groups));

    if(state.reportType !== 'incidencia' && !isEquipmentReport()){
      pages.push({
        type: 'section',
        tag: '4. CONCLUSIONES + 5. RECOMENDACIONES',
        body: `<div class="report-page-content"><div class="report-section-title">4. CONCLUSIONES</div><div class="report-section-body">${conclusionMarkup || '<div class="report-empty-state">Escriba aquí las conclusiones del avance o las observaciones finales.</div>'}</div><div class="report-section-title" style="margin-top: 24px;">5. RECOMENDACIONES</div><div class="report-section-body">${recommendationMarkup || '<div class="report-empty-state">Escriba aquí las recomendaciones del trabajo o actividades pendientes.</div>'}</div></div>`
      });
    }
    }
    const totalPages = pages.length;
    pages.forEach((page, index) => {
      const number = index + 1;
      const pageNode = document.createElement('div');
      pageNode.className = page.type === 'cover' ? 'report-page report-cover' : 'report-page report-secondary-page';
      pageNode.innerHTML = `${renderCompanyHeader()}${page.body}${page.type === 'cover' ? renderCoverFooterBlock(number, totalPages) : renderPageFooter(number, totalPages)}`;
      rc.appendChild(pageNode);
    });

    updatePreviewScale();
  }

  async function refreshPreviewContent(){
    previewRenderToken += 1;
    renderReport();
    await appendIncidentPlanPage(previewRenderToken);
    updatePreviewScale();
  }

  function loadImageFromDataUrl(dataUrl){
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = reject;
      image.src = dataUrl;
    });
  }

  function readFileAsDataUrl(file){
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function getScaledSize(width, height, maxDimension){
    if(width <= maxDimension && height <= maxDimension){
      return { width, height };
    }
    const ratio = width / height;
    if(ratio >= 1){
      return { width: maxDimension, height: Math.round(maxDimension / ratio) };
    }
    return { width: Math.round(maxDimension * ratio), height: maxDimension };
  }

  async function optimizeImageDataUrl(dataUrl, { maxDimension = UPLOAD_MAX_DIMENSION, quality = UPLOAD_IMAGE_QUALITY } = {}){
    const image = await loadImageFromDataUrl(dataUrl);
    const size = getScaledSize(image.width, image.height, maxDimension);
    const canvas = document.createElement('canvas');
    canvas.width = size.width;
    canvas.height = size.height;
    const context = canvas.getContext('2d');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL(UPLOAD_FILE_MIME, quality);
  }

  async function optimizeImageFile(file, options){
    const dataUrl = await readFileAsDataUrl(file);
    return optimizeImageDataUrl(dataUrl, options);
  }

  function dataUrlToBlob(dataUrl){
    const [header, content] = String(dataUrl || '').split(',');
    if(!header || !content) throw new Error('No se pudo procesar la imagen optimizada.');
    const mimeMatch = header.match(/data:(.*?);base64/);
    const mime = mimeMatch ? mimeMatch[1] : UPLOAD_FILE_MIME;
    const binary = atob(content);
    const bytes = new Uint8Array(binary.length);
    for(let index = 0; index < binary.length; index++){
      bytes[index] = binary.charCodeAt(index);
    }
    return new Blob([bytes], { type: mime });
  }

  async function optimizeImageUploadFile(file, options){
    const optimizedDataUrl = await optimizeImageFile(file, options);
    const optimizedBlob = dataUrlToBlob(optimizedDataUrl);
    const baseName = (file?.name || 'imagen').replace(/\.[^.]+$/, '');
    return new File([optimizedBlob], `${baseName}.jpg`, {
      type: optimizedBlob.type || UPLOAD_FILE_MIME,
      lastModified: Date.now()
    });
  }

  async function optimizeImageUploadFiles(files, options){
    const safeFiles = Array.isArray(files) ? files : [];
    return Promise.all(safeFiles.map(file => optimizeImageUploadFile(file, options)));
  }

  function sanitizePdfFileSegment(value){
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9_-]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .toLowerCase();
  }

  function buildPdfFileName(){
    const reportName = sanitizePdfFileSegment(state.reportTitle || 'reporte');
    const projectName = sanitizePdfFileSegment(state.projectName || 'proyecto');
    const reportDate = sanitizePdfFileSegment(state.reportDate || new Date().toISOString().slice(0, 10));
    return `${projectName || 'proyecto'}-${reportName || 'reporte'}-${reportDate || 'fecha'}.pdf`;
  }

  function downloadBlobFile(blob, fileName){
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  function buildRealPdfHtml(){
    const reportContainer = $('reportContainer');
    return reportContainer ? reportContainer.innerHTML : '';
  }

  async function appendIncidentPlanPage(renderToken = null){
    document.querySelectorAll('.incident-plan-pdf-page').forEach(node => node.remove());
    const project = getCurrentProject();
    const entries = (state.entries || []).filter(entry => entry.planId != null && entry.planX != null && entry.planY != null);
    if(!project || !entries.length || !window.pdfjsLib) return;
    const entriesByPlan = entries.reduce((groups, entry) => {
      const key = Number(entry.planId);
      if(!Number.isFinite(key)) return groups;
      if(!groups.has(key)) groups.set(key, []);
      groups.get(key).push(entry);
      return groups;
    }, new Map());
    if(!entriesByPlan.size) return;
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    for(const [planId, planEntries] of entriesByPlan.entries()){
      const plan = project.plans?.find(item => Number(item.id) === planId);
      if(!plan) continue;
      let pdfPromise = planPdfCache.get(plan.url);
      if(!pdfPromise){ pdfPromise = window.pdfjsLib.getDocument(plan.url).promise; planPdfCache.set(plan.url, pdfPromise); }
      const sourcePdf = await pdfPromise;
      if(renderToken != null && renderToken !== previewRenderToken) return;
      const page = await sourcePdf.getPage(1);
      const isLandscape = page.view[2] > page.view[3];
      const viewport = page.getViewport({ scale: 0.9 });
      const ratio = 1;
      const canvas = document.createElement('canvas');
      canvas.width = Math.ceil(viewport.width * ratio);
      canvas.height = Math.ceil(viewport.height * ratio);
      await page.render({ canvasContext: canvas.getContext('2d'), viewport, transform: [ratio, 0, 0, ratio, 0, 0] }).promise;
      if(renderToken != null && renderToken !== previewRenderToken) return;
      const planPage = document.createElement('div');
      planPage.className = `report-page report-secondary-page incident-plan-pdf-page ${isLandscape ? 'is-landscape-plan' : 'is-portrait-plan'}`;
      planPage.dataset.planId = String(planId);
      const pointMarkup = planEntries.map((entry, index) => `<span class="incident-plan-pdf-marker" style="left:${entry.planX * 100}%;top:${entry.planY * 100}%">${index + 1}</span>`).join('');
      planPage.innerHTML = `${renderCompanyHeader()}<div class="report-page-content"><div class="report-page-tag">PLANO DE UBICACIÓN</div><div class="incident-plan-pdf-canvas"><img src="${canvas.toDataURL('image/png')}" alt="Plano de ubicación">${pointMarkup}</div></div>`;
      $('reportContainer')?.appendChild(planPage);
    }
  }

  async function exportRealPdf(){
    const project = getCurrentProject();
    if(!project || !state.currentReportId){
      throw new Error('Primero abre un reporte antes de exportar.');
    }
    renderReport();
    await appendIncidentPlanPage();
    const html = buildRealPdfHtml();
    if(!html.trim()){
      throw new Error('No hay contenido del reporte para exportar.');
    }
    const fileName = buildPdfFileName();
    const blob = await requestBlob(`/api/projects/${project.slug}/reports/${state.currentReportId}/export-pdf-real/`, {
      method: 'POST',
      body: JSON.stringify({ html, fileName })
    });
    downloadBlobFile(blob, fileName);
  }

  async function generateReportPdf(){
    await appendIncidentPlanPage();
    const { jsPDF } = window.jspdf;
    const pages = Array.from(document.querySelectorAll('.report-page'));
    const previewCanvas = $('previewCanvas');
    const previewScaleShell = $('previewScaleShell');
    const reportContainer = $('reportContainer');
    const previewState = {
      canvasMinHeight: previewCanvas?.style.minHeight || '',
      shellWidth: previewScaleShell?.style.width || '',
      shellHeight: previewScaleShell?.style.height || '',
      containerTransform: reportContainer?.style.transform || '',
      containerTransformOrigin: reportContainer?.style.transformOrigin || ''
    };
    if(previewCanvas) previewCanvas.style.minHeight = '';
    if(previewScaleShell){
      previewScaleShell.style.width = '';
      previewScaleShell.style.height = '';
    }
    if(reportContainer){
      reportContainer.style.transform = '';
      reportContainer.style.transformOrigin = '';
    }
    const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4', compress: true });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const printableWidth = Math.max(1, pageWidth - (PDF_PAGE_MARGIN_MM * 2));
    const printableHeight = Math.max(1, pageHeight - (PDF_PAGE_MARGIN_MM * 2));
    if(!pages.length){
      if(previewCanvas) previewCanvas.style.minHeight = previewState.canvasMinHeight;
      if(previewScaleShell){
        previewScaleShell.style.width = previewState.shellWidth;
        previewScaleShell.style.height = previewState.shellHeight;
      }
      if(reportContainer){
        reportContainer.style.transform = previewState.containerTransform;
        reportContainer.style.transformOrigin = previewState.containerTransformOrigin;
      }
      return pdf;
    }
    const renderPage = async (page, pageIndex) => {
      const canvas = await html2canvas(page, {
        scale: PDF_RENDER_SCALE,
        useCORS: true,
        backgroundColor: '#ffffff'
      });
      const imgData = canvas.toDataURL('image/jpeg', PDF_IMAGE_QUALITY);
      const canvasWidth = canvas.width || 1;
      const canvasHeight = canvas.height || 1;
      const scale = Math.min(printableWidth / canvasWidth, printableHeight / canvasHeight);
      const renderWidth = canvasWidth * scale;
      const renderHeight = canvasHeight * scale;
      const offsetX = PDF_PAGE_MARGIN_MM + ((printableWidth - renderWidth) / 2);
      const offsetY = PDF_PAGE_MARGIN_MM + ((printableHeight - renderHeight) / 2);
      if(pageIndex > 0){
        pdf.addPage();
      }
      pdf.addImage(imgData, 'JPEG', offsetX, offsetY, renderWidth, renderHeight, undefined, 'MEDIUM');
    };
    return pages.reduce((promise, page, pageIndex) => {
      return promise.then(() => renderPage(page, pageIndex));
    }, Promise.resolve()).then(() => pdf).finally(() => {
      if(previewCanvas) previewCanvas.style.minHeight = previewState.canvasMinHeight;
      if(previewScaleShell){
        previewScaleShell.style.width = previewState.shellWidth;
        previewScaleShell.style.height = previewState.shellHeight;
      }
      if(reportContainer){
        reportContainer.style.transform = previewState.containerTransform;
        reportContainer.style.transformOrigin = previewState.containerTransformOrigin;
      }
    });
  }

  function openReportForm(reportType){
    if(!state.currentProjectId){
      alert('Primero crea un proyecto para continuar.');
      return;
    }
    if(!reportType){
      alert('Selecciona el tipo de reporte antes de continuar.');
      return;
    }
    const defaultTitle = reportType === 'incidencia'
      ? 'REPORTE DE INCIDENCIA'
      : reportType === 'equipos'
        ? 'RECEPCIÓN, VALIDACIÓN Y ENTREGA DE EQUIPOS'
        : 'REPORTE DE AVANCES';
    resetReportDraftState();
    state.reportType = reportType;
    state.reportTitle = defaultTitle;
    state.selectionStage = 'reportType';
    save();
    setNewReportRoute(getCurrentProject());
    renderAll();
    showAppScreen();
  }

  function showSelectionScreen(){
    showAppScreen();
  }

  function showAppScreen(){
    $('selectionScreen')?.classList.add('d-none');
    $('appContent')?.classList.remove('d-none');
  }

  function renderSelectionProjects(){
    const container = $('projectButtons');
    if(!container) return;
    if(!state.projects.length){
      container.innerHTML = '<div class="text-white-50 small">No hay proyectos creados aún.</div>';
      return;
    }
    container.innerHTML = state.projects.map(project => {
      const active = project.id === state.currentProjectId ? 'btn-primary' : 'btn-light';
      return `
        <div class="d-flex gap-2">
          <button type="button" data-id="${project.id}" class="btn ${active} text-start flex-grow-1 project-select-btn">${escapeHtml(project.projectName || 'Proyecto sin nombre')}<div class="small opacity-75">${project.isOwned ? 'Propio' : `Compartido · ${escapeHtml(PROJECT_ROLE_LABELS[project.accessRole] || 'Acceso')}`}</div></button>
          ${project.canDelete ? `<button type="button" data-id="${project.id}" class="btn btn-outline-danger btn-sm project-delete-btn" title="Eliminar proyecto">×</button>` : ''}
        </div>
      `;
    }).join('');
  }

  function updateSelectionScreenSections(){
    const projectFormSection = $('projectFormSection');
    const projectCreatedSection = $('projectCreatedSection');
    const reportTypeSection = $('reportTypeSection');
    if(!projectFormSection && !projectCreatedSection && !reportTypeSection){
      return;
    }
    if(projectFormSection){
      const showForm = state.projects.length === 0 || state.showProjectForm;
      projectFormSection.classList.toggle('d-none', !showForm);
    }
    if(projectCreatedSection){
      const showProjects = state.projects.length > 0 && state.selectionStage === 'project' && !state.showProjectForm;
      projectCreatedSection.classList.toggle('d-none', !showProjects);
    }
    if(reportTypeSection){
      const showReportType = state.currentProjectId && state.selectionStage === 'reportType';
      reportTypeSection.classList.toggle('d-none', !showReportType);
    }
    renderSelectionProjects();
    renderSelectionReportList();
  }

  function setSidebarState(shouldOpen){
    const body = document.body;
    const sidebar = document.querySelector('.app-sidebar');
    const main = document.querySelector('.app-main');
    const isMobile = window.innerWidth <= 992;

    if(isMobile){
      body.classList.toggle('sidebar-open', shouldOpen);
      body.classList.toggle('sidebar-collapse', !shouldOpen);
      body.classList.toggle('sidebar-closed', !shouldOpen);
      if(sidebar){
        sidebar.style.transform = shouldOpen ? 'translateX(0)' : 'translateX(-100%)';
      }
      if(main){
        main.style.marginLeft = '0px';
      }
      return;
    }

    const shouldCollapse = !shouldOpen;
    body.classList.toggle('sidebar-collapse', shouldCollapse);
    body.classList.toggle('sidebar-open', false);
    body.classList.toggle('sidebar-closed', shouldCollapse);

    if(sidebar){
      sidebar.style.transform = shouldCollapse ? 'translateX(-100%)' : 'translateX(0)';
    }
    if(main){
      main.style.marginLeft = shouldCollapse ? '0px' : '280px';
    }
  }

  function toggleSidebarMenu(event){
    if(event){
      event.preventDefault();
      event.stopPropagation();
    }

    const shouldOpen = window.innerWidth <= 992
      ? !document.body.classList.contains('sidebar-open')
      : document.body.classList.contains('sidebar-collapse');
    setSidebarState(shouldOpen);
  }

  function bindEvents(){
    loadProfile().catch(error => console.warn('No se pudo cargar el perfil', error));
    document.querySelectorAll('[data-widget="pushmenu"]').forEach(toggle => {
      toggle.addEventListener('click', toggleSidebarMenu);
    });

    document.querySelectorAll('.app-sidebar-brand').forEach(link => {
      link.addEventListener('click', event => {
        event.preventDefault();
        activatePanelView();
        setPanelRoute();
        if(window.innerWidth <= 992){
          setSidebarState(false);
        }
      });
    });

    $('appUserProfileBtn')?.addEventListener('click', () => {
      state.showProfileView = true;
      state.showProjectForm = false;
      renderAll();
      loadProfile().catch(error => alert(error.message));
      setPanelRoute();
      if(window.innerWidth <= 992) setSidebarState(false);
    });

    $('profileBackBtn')?.addEventListener('click', () => {
      state.showProfileView = false;
      state.currentProjectId = null;
      state.currentReportId = null;
      state.selectionStage = 'project';
      state.showProjectForm = false;
      setPanelRoute();
      renderAll();
    });
    $('profilePhotoBtn')?.addEventListener('click', () => $('profilePhotoInput')?.click());
    $('profilePhotoInput')?.addEventListener('change', async () => {
      const file = $('profilePhotoInput').files[0];
      if(!file) return;
      pendingProfilePhotoFile = await optimizeImageUploadFile(file, { maxDimension: 800, quality: 0.82 });
      $('profileAvatarImage').src = URL.createObjectURL(pendingProfilePhotoFile);
      $('profileAvatarImage').classList.remove('d-none');
      $('profileAvatarInitial').classList.add('d-none');
    });
    $('profileSaveBtn')?.addEventListener('click', async () => {
      const saveButton = $('profileSaveBtn');
      const saveStatus = $('profileSaveStatus');
      const payload = new FormData();
      payload.append('firstName', $('profileFirstName').value.trim());
      payload.append('lastName', $('profileLastName').value.trim());
      if(pendingProfilePhotoFile) payload.append('profilePhoto', pendingProfilePhotoFile);
      try {
        saveButton.disabled = true;
        saveStatus.textContent = 'Guardando...';
        const profile = await requestJson('/api/profile/', { method: 'POST', body: payload });
        pendingProfilePhotoFile = null;
        updateProfileAvatar(profile.profileImage);
        await loadProfile();
        const name = [profile.firstName, profile.lastName].filter(Boolean).join(' ') || profile.username;
        document.querySelectorAll('.app-user-name').forEach(element => { element.textContent = name; });
        saveStatus.textContent = 'Cambios guardados';
      } catch(error) {
        saveStatus.textContent = 'No se pudo guardar';
        alert(error.message);
      } finally {
        saveButton.disabled = false;
      }
    });

    const closeMobileSidebarOnOutsideTap = event => {
      const path = event.composedPath ? event.composedPath() : [event.target];
      const insideSidebar = path.some(el => el instanceof Element && el.closest('.app-sidebar'));
      const toggleButton = path.some(el => el instanceof Element && el.closest('[data-widget="pushmenu"]'));
      if(window.innerWidth <= 992 && document.body.classList.contains('sidebar-open') && !insideSidebar && !toggleButton){
        setSidebarState(false);
      }
    };

    document.addEventListener('click', closeMobileSidebarOnOutsideTap);

    document.addEventListener('keydown', event => {
      if(event.key === 'Escape' && window.innerWidth <= 992){
        setSidebarState(false);
      }
    });

    document.querySelectorAll('[data-workspace-view]').forEach(link => {
      const handleWorkspaceLink = event => {
        event.preventDefault();
        const nextView = link.dataset.workspaceView;
        if(!nextView) return;
        state.workspaceView = nextView;
        state.showPreviewMode = nextView === 'preview';
        state.reportMetaComplete = true;
        state.existingReportOpen = true;
        if(nextView === 'equipment'){
          state.currentFrontId = null;
          state.showIssueForm = false;
          state.selectedEntryId = null;
          state.editingEntryId = null;
          resetEquipmentEditor();
        }
        if(nextView === 'summary'){
          state.currentFrontId = null;
          state.showIssueForm = false;
          state.selectedEntryId = null;
          state.editingEntryId = null;
        }
        if(nextView === 'fronts'){
          state.currentFrontId = null;
          state.showIssueForm = false;
          state.selectedEntryId = null;
          state.editingEntryId = null;
        }
        if(nextView === 'issues'){
          if(!state.currentFrontId && state.fronts.length){
            state.currentFrontId = state.fronts[0].id;
          }
          state.showIssueForm = !state.currentFrontId;
          state.selectedEntryId = null;
          state.editingEntryId = null;
        }
        save();
        renderAll();
        if(nextView === 'preview'){
          refreshPreviewContent().catch(error => console.warn('No se pudo mostrar la vista previa del reporte', error));
        }
        if(window.innerWidth <= 992){
          setSidebarState(false);
        }
        const target = document.querySelector(link.getAttribute('href'));
        target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      };
      link.addEventListener('click', handleWorkspaceLink);
    });
    $('createProjectBtn')?.addEventListener('click', async () => {
      const company = $('companyName').value.trim() || 'VDC CONSTRUCCIONES SAC';
      const projectName = $('projectName').value.trim();
      const projectLocation = $('projectLocation').value.trim();
      if(!projectName){
        alert('El nombre del proyecto es obligatorio.');
        $('projectName').focus();
        return;
      }
      if(state.currentProjectId && state.showProjectForm){
        const current = getCurrentProject();
        if(!current) return;
        if(!ensureCanEditProject('No tienes permisos para editar este proyecto.')){
          return;
        }
        try {
          const remoteProject = await updateProjectRemote(current, {
            companyName: company,
            projectName,
            projectLocation,
            reportTitle: state.reportTitle,
            forWhom: state.forWhom,
            fromWhom: state.fromWhom,
          });
          state.companyName = company;
          state.projectName = projectName;
          state.projectLocation = projectLocation;
          Object.assign(current, remoteProject, { reports: current.reports || [] });
        } catch (error) {
          alert(error.message);
          return;
        }
        state.showProjectForm = false;
        state.selectionStage = 'reportType';
        save();
        renderAll();
        updateSelectionScreenSections();
        setProjectRoute(current);
        showSelectionScreen();
        return;
      }
      state.currentProjectId = null;
      state.companyName = company;
      state.projectName = projectName;
      state.projectLocation = projectLocation;
      try {
        await createProject(projectName, projectLocation);
      } catch (error) {
        alert(error.message);
      }
      updateSelectionScreenSections();
    });
    $('selectedProjectInfo')?.addEventListener('click', e => {
      const editBtn = e.target.closest('#selectionEditProjectInfoBtn');
      const current = getCurrentProject();

      if(editBtn){
        if(!current || !canEditProjectFromCurrentRoute()) return;
        state.showProjectForm = true;
        state.selectionStage = 'project';
        setEditProjectRoute(current);
        renderAll();
        updateSelectionScreenSections();
        showSelectionScreen();
        return;
      }
    });
    $('editProjectInfoBtn')?.addEventListener('click', () => {
      const current = getCurrentProject();
      if(!current || !canEditProjectFromCurrentRoute()) return;
      state.showProjectForm = true;
      state.selectionStage = 'project';
      setEditProjectRoute(current);
      renderAll();
      updateSelectionScreenSections();
      showSelectionScreen();
    });
    $('backToMainPanelBtn')?.addEventListener('click', () => {
      const current = getCurrentProject();
      if(current && state.showProjectForm){
        state.showProjectForm = false;
        state.selectionStage = 'reportType';
        renderAll();
        updateSelectionScreenSections();
        setProjectRoute(current);
        showSelectionScreen();
        return;
      }
      state.selectionStage = 'project';
      state.showProjectForm = false;
      state.currentProjectId = null;
      state.currentReportId = null;
      state.reportType = '';
      state.existingReportOpen = false;
      state.reportMetaComplete = false;
      state.showPreviewMode = false;
      save();
      setPanelRoute();
      showAppScreen();
      renderAll();
      updateSelectionScreenSections();
    });
    $('projectButtons')?.addEventListener('click', e => {
      const deleteBtn = e.target.closest('.project-delete-btn');
      if(deleteBtn){
        const id = Number(deleteBtn.dataset.id);
        if(id && confirm('¿Eliminar este proyecto? Esta acción no se puede deshacer.')){
          deleteProject(id).catch(error => alert(error.message));
        }
        return;
      }
      const btn = e.target.closest('.project-select-btn');
      if(!btn) return;
      const id = Number(btn.dataset.id);
      if(id) switchProject(id);
      updateSelectionScreenSections();
      $('reportTypeSection')?.scrollIntoView({ behavior: 'smooth' });
    });
    $('dashboardNewProjectBtn')?.addEventListener('click', () => {
      state.showProjectForm = true;
      state.selectionStage = 'project';
      state.currentProjectId = null;
      pendingProjectPhotoFile = null;
      resetProjectForm();
      renderAll();
      $('dashboardProjectName')?.focus();
    });
    $('dashboardProjectForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const company = $('dashboardCompanyName')?.value.trim() || 'VDC CONSTRUCCIONES SAC';
      const projectName = $('dashboardProjectName')?.value.trim();
      const projectLocation = $('dashboardProjectLocation')?.value.trim() || '';
      if(!projectName){
        alert('El nombre del proyecto es obligatorio.');
        $('dashboardProjectName')?.focus();
        return;
      }
      const current = getCurrentProject();
      if(state.editingProjectInfo && current){
        if(!ensureCanEditProject('No tienes permisos para editar este proyecto.')){
          return;
        }
        try {
          const payload = new FormData();
          payload.append('companyName', company);
          payload.append('projectName', projectName);
          payload.append('projectLocation', projectLocation);
          if(pendingProjectPhotoFile) payload.append('projectPhoto', pendingProjectPhotoFile);
          const remoteProject = await updateProjectRemote(current, payload);
          Object.assign(current, remoteProject, { reports: current.reports || [] });
          pendingProjectPhotoFile = null;
          state.companyName = company;
          state.projectName = projectName;
          state.projectLocation = projectLocation;
        } catch (error) {
          alert(error.message);
          return;
        }
      } else {
        state.companyName = company;
        state.projectName = projectName;
        state.projectLocation = projectLocation;
        try {
          await createProject(projectName, projectLocation);
        } catch (error) {
          alert(error.message);
          return;
        }
      }
      state.showProjectForm = false;
      state.editingProjectInfo = false;
      save();
      renderAll();
    });
    $('dashboardCancelProjectBtn')?.addEventListener('click', () => {
      const wasEditing = state.editingProjectInfo;
      state.showProjectForm = false;
      state.editingProjectInfo = false;
      if(wasEditing){
        state.currentProjectId = null;
        state.currentReportId = null;
        state.selectionStage = 'project';
        setPanelRoute();
      } else {
        resetProjectForm();
      }
      save();
      renderAll();
    });
    $('dashboardProjectList')?.addEventListener('click', e => {
      const projectCard = e.target.closest('.dashboard-project-item');
      if(projectCard && !e.target.closest('button')){
        const id = Number(projectCard.dataset.openProject);
        if(id){
          switchProject(id, { openDashboardOnly: true });
          setProjectRoute(getCurrentProject());
          renderAll();
        }
        return;
      }
      const imageBtn = e.target.closest('.dashboard-project-image');
      if(imageBtn){
        const project = getProjectById(Number(imageBtn.dataset.id));
        if(project && project.canEdit){
          pendingProjectPhotoId = project.id;
          pendingProjectPhotoFile = null;
          $('dashboardProjectPhotoInput')?.click();
        }
        return;
      }
      const deleteBtn = e.target.closest('.dashboard-project-delete');
      if(deleteBtn){
        const id = Number(deleteBtn.dataset.id);
        if(id && confirm('¿Eliminar este proyecto? Esta acción no se puede deshacer.')){
          deleteProject(id).catch(error => alert(error.message));
        }
        return;
      }
      const openBtn = e.target.closest('.dashboard-project-open');
      if(openBtn){
        const id = Number(openBtn.dataset.id);
        if(!id) return;
        switchProject(id, { openDashboardOnly: true });
        setProjectRoute(getCurrentProject());
        renderAll();
        return;
      }
      const editBtn = e.target.closest('.dashboard-project-edit');
      if(editBtn){
        const id = Number(editBtn.dataset.id);
        if(!id) return;
        switchProject(id, { openDashboardOnly: true });
        const proj = getCurrentProject();
        if(proj){
          state.companyName = proj.companyName || '';
          state.projectName = proj.projectName || '';
          state.projectLocation = proj.projectLocation || '';
        }
        state.showProjectForm = true;
        state.editingProjectInfo = true;
        save();
        setProjectRoute(getCurrentProject());
        renderAll();
        return;
      }
    });
    $('dashboardProjectList')?.addEventListener('keydown', e => {
      if(e.key !== 'Enter' && e.key !== ' ') return;
      const projectCard = e.target.closest('.dashboard-project-item');
      if(!projectCard || e.target.closest('button')) return;
      e.preventDefault();
      const id = Number(projectCard.dataset.openProject);
      if(id){
        switchProject(id, { openDashboardOnly: true });
        setProjectRoute(getCurrentProject());
        renderAll();
      }
    });
    $('dashboardProjectSearch')?.addEventListener('input', () => renderDashboardHub());
    $('dashboardBackToProjectsBtn')?.addEventListener('click', () => {
      state.selectionStage = 'project';
      state.showProjectForm = false;
      state.currentProjectId = null;
      state.currentReportId = null;
      state.reportType = '';
      state.existingReportOpen = false;
      state.reportMetaComplete = false;
      state.showPreviewMode = false;
      state.workspaceView = 'fronts';
      state.currentFrontId = null;
      save();
      setPanelRoute();
      renderAll();
    });
    const startDashboardReportCreation = reportType => {
      const project = getCurrentProject();
      if(!project) return;
      if(!ensureCanEditProject('No tienes permisos para crear reportes en este proyecto.')){
        return;
      }
      if(!reportType){
        alert('Selecciona una pestaña de tipo de reporte antes de continuar.');
        return;
      }
      state.reportMetaComplete = false;
      state.currentReportId = null;
      state.existingReportOpen = false;
      state.editingReportMeta = false;
      resetReportDraftState();
      state.reportType = reportType;
      state.reportTitle = reportType === 'incidencia'
        ? 'REPORTE DE INCIDENCIA'
        : reportType === 'equipos'
          ? 'RECEPCIÓN, VALIDACIÓN Y ENTREGA DE EQUIPOS'
          : 'REPORTE DE AVANCES';
      save();
      setNewReportRoute(project);
      renderAll();
      showAppScreen();
    };
    $('projectShareToggle')?.addEventListener('click', () => {
      showProjectShare = !showProjectShare;
      renderAll();
    });
    $('projectSummaryTab')?.addEventListener('click', () => {
      projectDashboardView = 'summary';
      renderAll();
    });
    $('projectPlansTab')?.addEventListener('click', () => {
      projectDashboardView = 'plans';
      renderAll();
    });
    $('projectResponsiblesTab')?.addEventListener('click', () => {
      projectDashboardView = 'responsibles';
      renderAll();
    });
    $('dashboardAddResponsibleBtn')?.addEventListener('click', async () => {
      const project = getCurrentProject();
      const input = $('dashboardResponsibleName');
      const name = input?.value.trim() || '';
      if(!project || !name) return;
      try {
        project.responsibleCompanies = await createProjectResponsibleRemote(project, name);
        if(input) input.value = '';
        save();
        renderAll();
      } catch (error) {
        alert(error.message);
      }
    });
    $('dashboardResponsiblesList')?.addEventListener('click', async e => {
      const deleteButton = e.target.closest('.dashboard-responsible-delete');
      if(!deleteButton) return;
      const project = getCurrentProject();
      const responsibleId = Number(deleteButton.dataset.id);
      if(!project || !responsibleId || !confirm('¿Eliminar este responsable?')) return;
      try {
        project.responsibleCompanies = await deleteProjectResponsibleRemote(project, responsibleId);
        save();
        renderAll();
      } catch (error) {
        alert(error.message);
      }
    });
    $('dashboardPlanReportTypes')?.addEventListener('click', e => {
      const button = e.target.closest('[data-report-type]');
      if(!button) return;
      projectDashboardReportType = button.dataset.reportType;
      projectDashboardView = 'reports';
      renderAll();
    });
    $('dashboardAddTypeReportBtn')?.addEventListener('click', () => {
      startDashboardReportCreation(projectDashboardReportType || '');
    });
    $('planZoomIn')?.addEventListener('click', () => {
      const bounds = $('planCanvasWrap')?.getBoundingClientRect();
      if(bounds) setPlanZoom(planZoom + 0.25, bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
    });
    $('planZoomOut')?.addEventListener('click', () => {
      const bounds = $('planCanvasWrap')?.getBoundingClientRect();
      if(bounds) setPlanZoom(planZoom - 0.25, bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
    });
    $('planZoomReset')?.addEventListener('click', () => {
      planZoom = 1;
      planPanX = 0;
      planPanY = 0;
      applyPlanTransform();
    });
    $('planMarkerModeBtn')?.addEventListener('click', () => {
      planMarkerMode = !planMarkerMode;
      $('planMarkerModeBtn').setAttribute('aria-pressed', String(planMarkerMode));
      renderAll();
    });
    const planCanvasWrap = $('planCanvasWrap');
    let isPanningPlan = false;
    let lastPanX = 0;
    let lastPanY = 0;
    planCanvasWrap?.addEventListener('pointerdown', e => {
      if(e.button !== 1) return;
      e.preventDefault();
      e.stopPropagation();
      isPanningPlan = true;
      lastPanX = e.clientX;
      lastPanY = e.clientY;
      planCanvasWrap.setPointerCapture(e.pointerId);
      planCanvasWrap.classList.add('is-panning');
    });
    planCanvasWrap?.addEventListener('pointermove', e => {
      if(!isPanningPlan) return;
      planPanX += e.clientX - lastPanX;
      planPanY += e.clientY - lastPanY;
      lastPanX = e.clientX;
      lastPanY = e.clientY;
      applyPlanTransform();
    });
    planCanvasWrap?.addEventListener('wheel', e => {
      e.preventDefault();
      const nextZoom = e.deltaY < 0 ? planZoom + 0.15 : planZoom - 0.15;
      setPlanZoom(nextZoom, e.clientX, e.clientY);
    }, { passive: false });
    planCanvasWrap?.addEventListener('pointerup', e => {
      if(e.button !== 1) return;
      isPanningPlan = false;
      planCanvasWrap.releasePointerCapture(e.pointerId);
      planCanvasWrap.classList.remove('is-panning');
    });
    $('dashboardUploadPlanBtn')?.addEventListener('click', () => {
      const project = getCurrentProject();
      if(project?.canEdit) $('dashboardPlanInput')?.click();
    });
    $('dashboardPlanInput')?.addEventListener('change', async () => {
      const file = $('dashboardPlanInput').files[0];
      const project = getCurrentProject();
      if(!file || !project) return;
      try {
        if(!file.name.toLowerCase().endsWith('.pdf')) throw new Error('Solo se permiten archivos PDF.');
        const plan = await createProjectPlanRemote(project, file);
        project.plans = [plan, ...(project.plans || [])];
        selectedPlanId = plan.id;
        renderAll();
      } catch(error) {
        alert(error.message);
      } finally {
        $('dashboardPlanInput').value = '';
      }
    });
    $('dashboardPlansList')?.addEventListener('click', e => {
      const planButton = e.target.closest('[data-plan-id]');
      if(planButton){
        selectedPlanId = Number(planButton.dataset.planId);
        planZoom = 1;
        planPanX = 0;
        planPanY = 0;
        planMarkerMode = false;
        renderAll();
        return;
      }
      const deleteButton = e.target.closest('.dashboard-plan-delete');
      if(!deleteButton) return;
      const project = getCurrentProject();
      const planId = Number(deleteButton.dataset.id);
      if(!project || !planId || !confirm('¿Eliminar este plano?')) return;
      deleteProjectPlanRemote(project, planId).then(() => {
        project.plans = (project.plans || []).filter(plan => plan.id !== planId);
        if(selectedPlanId === planId){
          selectedPlanId = null;
          planZoom = 1;
          planPanX = 0;
          planPanY = 0;
          planMarkerMode = false;
        }
        renderAll();
      }).catch(error => alert(error.message));
    });
    $('planCanvasWrap')?.addEventListener('click', async e => {
      const project = getCurrentProject();
      const plan = project?.plans?.find(item => item.id === selectedPlanId);
      if(!project?.canEdit || !plan) return;
      const markerButton = e.target.closest('.plan-marker');
      if(markerButton){
        const entryId = Number(markerButton.dataset.entryId);
        if(entryId){
          const entry = (project.reports || []).flatMap(report => report.entries || []).find(item => Number(item.id) === entryId);
          const info = $('planMarkerInfo');
          if(entry && info){
            const pointNumber = Array.from(document.querySelectorAll('.plan-marker')).indexOf(markerButton) + 1;
            info.innerHTML = `<strong>Punto ${pointNumber}</strong><span>Fecha: ${escapeHtml(entry.incidentDate || 'Sin fecha')}</span><span>Estado: ${escapeHtml(entry.status || 'Sin estado')}</span><span>Ubicación: ${escapeHtml(entry.buildingLocation || `Punto ${pointNumber}`)}</span><span>Empresa responsable: ${escapeHtml(entry.responsibleCompany || 'Sin empresa')}</span><span>${escapeHtml(entry.desc || 'Sin descripción')}</span>`;
            info.style.left = `${Math.min(75, Math.max(25, Number(entry.planX) * 100))}%`;
            info.style.top = `${Math.min(85, Math.max(15, Number(entry.planY) * 100))}%`;
            info.classList.remove('d-none');
          }
          return;
        }
        const markerId = Number(markerButton.dataset.markerId);
        if(!markerId || !confirm('¿Eliminar este punto?')) return;
        try {
          await deleteProjectPlanMarkerRemote(project, plan.id, markerId);
          plan.markers = (plan.markers || []).filter(marker => marker.id !== markerId);
          renderPlanMarkers(plan.markers, project.canEdit);
        } catch(error) {
          alert(error.message);
        }
        return;
      }
      if(!planMarkerMode) return;
      const rect = $('planCanvas').getBoundingClientRect();
      const marker = {
        page: 1,
        x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
        y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
      };
      try {
        const data = await requestJson(`/api/projects/${project.slug}/plans/${plan.id}/markers/`, { method: 'POST', body: JSON.stringify(marker) });
        plan.markers = [...(plan.markers || []), data.marker];
        renderPlanMarkers(plan.markers, project.canEdit);
      } catch(error) {
        alert(error.message);
      }
    });
    $('dashboardReportList')?.addEventListener('click', e => {
      const deleteButton = e.target.closest('[data-report-delete]');
      if(deleteButton){
        const reportId = Number(deleteButton.dataset.reportDelete);
        if(reportId) deleteReport(reportId).catch(error => alert(error.message));
        return;
      }
      const shareToggle = e.target.closest('[data-report-share]');
      if(shareToggle){
        const reportId = Number(shareToggle.dataset.reportShare);
        if(!reportId) return;
        const panel = $(`reportSharePanel-${reportId}`);
        panel?.classList.toggle('d-none');
        return;
      }
      const shareSave = e.target.closest('[data-report-share-save]');
      if(shareSave){
        const reportId = Number(shareSave.dataset.reportShareSave);
        const project = getCurrentProject();
        const report = project?.reports?.find(item => item.id === reportId);
        if(!project || !report) return;
        const username = $(`reportShareUsername-${reportId}`)?.value.trim();
        const role = $(`reportShareRole-${reportId}`)?.value || 'viewer';
        if(!username){
          alert('Ingresa el usuario que quieres invitar.');
          $(`reportShareUsername-${reportId}`)?.focus();
          return;
        }
        shareReportRemote(project, reportId, { username, role })
          .then(data => {
            report.members = Array.isArray(data.members) ? data.members : report.members;
            save();
            renderAll();
          })
          .catch(error => alert(error.message));
        return;
      }
      const button = e.target.closest('.dashboard-report-open');
      if(!button) return;
      const reportId = Number(button.dataset.id);
      const project = getCurrentProject();
      if(!project || !reportId) return;
      project.currentReportId = reportId;
      state.currentReportId = reportId;
      state.existingReportOpen = true;
      state.reportMetaComplete = true;
      state.workspaceView = 'summary';
      loadProject(project);
      save();
      setReportRoute(project, reportId);
      renderAll();
    });
    $('dashboardProjectPhotoInput')?.addEventListener('change', async () => {
      const file = $('dashboardProjectPhotoInput').files[0];
      if(!file) return;
      try {
        pendingProjectPhotoFile = await optimizeImageUploadFile(file, { maxDimension: 1200, quality: 0.82 });
        const project = getProjectById(pendingProjectPhotoId);
        if(project){
          const payload = new FormData();
          payload.append('companyName', project.companyName || 'VDC CONSTRUCCIONES SAC');
          payload.append('projectName', project.projectName || 'Proyecto sin nombre');
          payload.append('projectLocation', project.projectLocation || '');
          payload.append('projectPhoto', pendingProjectPhotoFile);
          const remoteProject = await updateProjectRemote(project, payload);
          Object.assign(project, remoteProject, { reports: project.reports || [] });
          pendingProjectPhotoFile = null;
          pendingProjectPhotoId = null;
          save();
          renderAll();
        }
      } catch(error) {
        alert(error.message || 'No se pudo cargar la foto del proyecto.');
      } finally {
        $('dashboardProjectPhotoInput').value = '';
      }
    });
    $('createAnotherProjectBtn')?.addEventListener('click', () => {
      state.showProjectForm = true;
      state.selectionStage = 'project';
      state.currentProjectId = null;
      resetProjectForm();
      setNewProjectRoute();
      showSelectionScreen();
      renderAll();
      updateSelectionScreenSections();
      $('projectName').focus();
    });
    $('backToProjectsBtn')?.addEventListener('click', () => {
      state.selectionStage = 'project';
      state.showProjectForm = false;
      state.currentProjectId = null;
      state.currentReportId = null;
      state.reportType = '';
      state.existingReportOpen = false;
      state.reportMetaComplete = false;
      state.showPreviewMode = false;
      save();
      setPanelRoute();
      showAppScreen();
      renderAll();
      updateSelectionScreenSections();
      $('projectButtons').scrollIntoView({ behavior: 'smooth' });
    });
    $('createReportBtn')?.addEventListener('click', () => {
      const reportType = $('selectReportType')?.value || $('metadataReportType')?.value;
      if(!reportType){
        alert('Selecciona el tipo de reporte antes de continuar.');
        return;
      }
      openReportForm(reportType);
    });
    $('backToProjectBtn')?.addEventListener('click', () => {
      const current = getCurrentProject();
      if(!current) return;
      state.selectionStage = 'reportType';
      state.currentReportId = null;
      state.existingReportOpen = false;
      state.reportMetaComplete = false;
      state.showPreviewMode = false;
      state.workspaceView = 'fronts';
      state.editingReportMeta = false;
      save();
      setProjectRoute(current);
      renderAll();
      updateSelectionScreenSections();
      showSelectionScreen();
    });
    $('deleteCurrentReportBtn')?.addEventListener('click', () => {
      if(state.currentReportId){
        deleteReport(state.currentReportId).catch(error => alert(error.message));
      }
    });
    $('editCurrentReportBtn')?.addEventListener('click', () => {
      if(!state.currentReportId || !isOnReportRoute()) return;
      state.editingReportMeta = true;
      state.showPreviewMode = false;
      save();
      renderAll();
    });
    $('createNewReportBtn')?.addEventListener('click', () => {
      state.reportMetaComplete = false;
      state.selectionStage = 'reportType';
      state.currentReportId = null;
      state.existingReportOpen = false;
      state.editingReportMeta = false;
      save();
      setNewReportRoute(getCurrentProject());
      renderAll();
      updateSelectionScreenSections();
      showSelectionScreen();
      $('metadataReportType').value = '';
    });
    $('selectionReportList')?.addEventListener('click', e => {
      const deleteButton = e.target.closest('button[data-delete-id]');
      if(deleteButton){
        const reportId = Number(deleteButton.dataset.deleteId);
        if(reportId) deleteReport(reportId).catch(error => alert(error.message));
        return;
      }
      const button = e.target.closest('button[data-id]');
      if(!button) return;
      const reportId = Number(button.dataset.id);
      if(!reportId) return;
      const project = getCurrentProject();
      if(!project) return;
      project.currentReportId = reportId;
      state.currentReportId = reportId;
      state.selectionStage = 'reportType';
      state.reportMetaComplete = true;
      state.existingReportOpen = true;
      loadProject(project);
      save();
      setReportRoute(project, reportId);
      renderAll();
      showAppScreen();
    });
    $('reportList')?.addEventListener('click', e => {
      const deleteButton = e.target.closest('button[data-delete-id]');
      if(deleteButton){
        const reportId = Number(deleteButton.dataset.deleteId);
        if(reportId) deleteReport(reportId).catch(error => alert(error.message));
        return;
      }
      const button = e.target.closest('button[data-id]');
      if(!button) return;
      const reportId = Number(button.dataset.id);
      if(!reportId) return;
      const project = getCurrentProject();
      if(!project) return;
      project.currentReportId = reportId;
      state.currentReportId = reportId;
      state.existingReportOpen = true;
      const report = getCurrentReport();
      if(report){
        loadProject(project);
      }
      save();
      setReportRoute(project, reportId);
      renderAll();
    });
    $('continueToEditorBtn')?.addEventListener('click', async () => {
      const reportType = $('metadataReportType')?.value;
      if(!reportType){
        alert('Selecciona el tipo de reporte antes de continuar.');
        return;
      }
      if(!state.currentProjectId){
        alert('Primero crea o selecciona un proyecto.');
        return;
      }
      const project = getCurrentProject();
      if(!project) return;
      if(state.currentReportId){
        if(!ensureCanEditReport('No tienes permisos para editar este reporte.')){
          return;
        }
      } else if(!ensureCanEditProject('No tienes permisos para crear reportes en este proyecto.')){
        return;
      }
      const formData = new FormData();
      const defaultTitle = reportType === 'incidencia'
        ? 'REPORTE DE INCIDENCIA'
        : reportType === 'equipos'
          ? 'RECEPCIÓN, VALIDACIÓN Y ENTREGA DE EQUIPOS'
          : 'REPORTE DE AVANCES';
      formData.append('reportType', reportType);
      formData.append('reportTitle', state.reportTitle || defaultTitle);
      formData.append('reportWeek', state.reportWeek || '8');
      formData.append('reportDate', state.reportDate || new Date().toISOString().slice(0, 10));
      formData.append('laborDateFrom', state.laborDateFrom || '');
      formData.append('laborDateTo', state.laborDateTo || '');
      formData.append('forWhom', state.forWhom || '');
      formData.append('fromWhom', state.fromWhom || '');
      formData.append('objectiveText', state.objectiveText || '');
      formData.append('analysisText', state.analysisText || '');
      formData.append('conclusionText', state.conclusionText || '');
      formData.append('recommendationText', state.recommendationText || '');
      formData.append('conclusionItems', JSON.stringify(state.conclusionItems || []));
      formData.append('recommendationItems', JSON.stringify(state.recommendationItems || []));
      formData.append('autoMergeDup', String(!!state.autoMergeDup));
      formData.append('combineByStatus', String(!!state.combineByStatus));
      if(pendingCoverPhotoFile){
        const optimizedCoverFile = await optimizeImageUploadFile(pendingCoverPhotoFile);
        formData.append('coverPhoto', optimizedCoverFile);
      }
      let report;
      try {
        const serverReport = state.currentReportId
          ? await updateReportRemote(project, state.currentReportId, formData)
          : await createReportRemote(project, formData);
        report = mergeServerReport(project, serverReport);
        pendingCoverPhotoFile = null;
      } catch (error) {
        alert(error.message);
        return;
      }
      state.reportType = reportType;
      state.reportMetaComplete = true;
      state.existingReportOpen = true;
      state.workspaceView = reportType === 'equipos' ? 'equipment' : 'summary';
      state.editingReportMeta = false;
      loadProject(project);
      if(reportType === 'incidencia') {
        await ensureDefaultIncidentFront();
      }
      save();
      setReportRoute(project, state.currentReportId);
      renderAll();
      showAppScreen();
    });
    $('editReportInfoBtn')?.addEventListener('click', () => {
      if(!state.currentReportId || !isOnReportRoute()) return;
      if(!ensureCanEditReport('No tienes permisos para editar este reporte.')){
        return;
      }
      state.editingReportMeta = true;
      state.showPreviewMode = false;
      save();
      renderAll();
    });
    $('cancelReportMetaEditBtn')?.addEventListener('click', () => {
      const project = getCurrentProject();
      if(project){
        loadProject(project);
      }
      state.editingReportMeta = false;
      save();
      renderAll();
    });
    $('backToStartBtn')?.addEventListener('click', () => {
      state.reportType = '';
      state.selectionStage = 'project';
      state.showProjectForm = false;
      state.currentProjectId = null;
      state.currentReportId = null;
      state.existingReportOpen = false;
      state.reportMetaComplete = false;
      state.showPreviewMode = false;
      save();
      setPanelRoute();
      showSelectionScreen();
      updateSelectionScreenSections();
    });
    $('newProjectBtn')?.addEventListener('click', () => {
      const name = prompt('Nombre del proyecto:', `Proyecto ${state.projects.length + 1}`);
      if(!name) return;
      const location = prompt('Ubicación del proyecto:','');
      createProject(name.trim(), location ? location.trim() : '').catch(error => alert(error.message));
    });
    $('newProjectBtnDisplay')?.addEventListener('click', () => {
      const name = prompt('Nombre del proyecto:', `Proyecto ${state.projects.length + 1}`);
      if(!name) return;
      const location = prompt('Ubicación del proyecto:','');
      createProject(name.trim(), location ? location.trim() : '').catch(error => alert(error.message));
    });
    $('shareProjectBtn')?.addEventListener('click', async () => {
      const current = getCurrentProject();
      if(!current?.canShare){
        alert('No tienes permisos para compartir este proyecto.');
        return;
      }
      const username = $('shareUsername')?.value.trim();
      const role = $('shareRole')?.value || 'viewer';
      if(!username){
        alert('Ingresa el usuario que quieres invitar.');
        $('shareUsername')?.focus();
        return;
      }
      try {
        const data = await shareProjectRemote(current, { username, role });
        current.members = Array.isArray(data.members) ? data.members : current.members;
        save();
        renderAll();
        $('shareUsername').value = '';
      } catch (error) {
        alert(error.message);
      }
    });
    $('projectSelect')?.addEventListener('change', e => {
      const id = Number(e.target.value);
      if(id) switchProject(id);
    });
    $('companyName')?.addEventListener('input', e => { state.companyName = e.target.value; save(); renderReport(); });
    $('projectName')?.addEventListener('input', e => { state.projectName = e.target.value; save(); renderReport(); });
    $('projectLocation')?.addEventListener('input', e => { state.projectLocation = e.target.value; save(); renderReport(); });
    $('reportTitle')?.addEventListener('input', e => { state.reportTitle = e.target.value; save(); renderReport(); });
    $('reportWeek')?.addEventListener('input', e => { state.reportWeek = e.target.value; save(); renderReport(); });
    $('reportDate')?.addEventListener('input', e => { state.reportDate = e.target.value; save(); renderReport(); });
    $('laborDateFrom')?.addEventListener('input', e => { state.laborDateFrom = e.target.value; save(); renderReport(); });
    $('laborDateTo')?.addEventListener('input', e => { state.laborDateTo = e.target.value; save(); renderReport(); });
    $('forWhom')?.addEventListener('input', e => { state.forWhom = e.target.value; save(); renderReport(); });
    $('fromWhom')?.addEventListener('input', e => { state.fromWhom = e.target.value; save(); renderReport(); });
    $('objectiveText')?.addEventListener('input', e => { state.objectiveText = e.target.value; save(); renderReport(); });
    $('analysisText')?.addEventListener('input', e => { state.analysisText = e.target.value; save(); renderReport(); });
    $('objectiveText')?.addEventListener('input', e => { state.objectiveText = e.target.value; save(); renderReport(); });
    $('analysisText')?.addEventListener('input', e => { state.analysisText = e.target.value; save(); renderReport(); });
    $('metadataReportType')?.addEventListener('change', e => { state.reportType = e.target.value; save(); });
    $('conclusionText')?.addEventListener('input', e => { state.conclusionText = e.target.value; state.conclusionItems = normalizeListItems(e.target.value); save(); renderAll(); });
    $('recommendationText')?.addEventListener('input', e => { state.recommendationText = e.target.value; state.recommendationItems = normalizeListItems(e.target.value); save(); renderAll(); });
    $('addConclusionBtn')?.addEventListener('click', () => {
      const value = $('conclusionItemInput').value.trim();
      if(!value){ return; }
      state.conclusionItems.push(value);
      state.conclusionText = state.conclusionItems.join('\n');
      save(); renderAll();
      $('conclusionItemInput').value = '';
    });
    $('addRecommendationBtn')?.addEventListener('click', () => {
      const value = $('recommendationItemInput').value.trim();
      if(!value){ return; }
      state.recommendationItems.push(value);
      state.recommendationText = state.recommendationItems.join('\n');
      save(); renderAll();
      $('recommendationItemInput').value = '';
    });
    $('coverPhotoInput')?.addEventListener('change', async () => {
      const file = $('coverPhotoInput').files[0];
      pendingCoverPhotoFile = file || null;
      if(!file){ state.coverImage = ''; save(); renderReport(); return; }
      const optimizedImage = await optimizeImageFile(file);
      state.coverImage = optimizedImage;
      save(); renderReport();
    });
    $('equipmentTakePhotoBtn')?.addEventListener('click', () => $('equipmentPhotoCameraInput')?.click());
    $('equipmentChoosePhotoBtn')?.addEventListener('click', () => $('equipmentPhotoInput')?.click());
    $('cancelEquipmentEditBtn')?.addEventListener('click', () => { resetEquipmentEditor(); save(); renderAll(); });
    $('addEquipmentBtn')?.addEventListener('click', async () => {
      if(!ensureCanEditReport('No tienes permisos para modificar este reporte.')){
        return;
      }
      const itemName = $('equipmentName')?.value.trim();
      const buildingLocation = $('equipmentBuilding')?.value.trim();
      const quantity = Math.max(1, Number($('equipmentQuantity')?.value || 1));
      const status = $('equipmentStatusSelect')?.value || 'Recepción';
      const comments = $('equipmentComments')?.value.trim();
      const files = getEquipmentPhotoFiles();
      const project = getCurrentProject();
      if(!itemName){
        alert('Ingresa el tipo o nombre del equipo.');
        $('equipmentName')?.focus();
        return;
      }
      if(!project || !state.currentReportId){
        alert('Primero guarda el reporte antes de registrar equipos.');
        return;
      }
      if(!state.editingEntryId && !files.length){
        alert('Agrega una foto del equipo.');
        return;
      }
      try {
        const frontId = await ensureEquipmentFront();
        const formData = new FormData();
        formData.append('frontId', String(frontId));
        formData.append('itemName', itemName);
        formData.append('buildingLocation', buildingLocation);
        formData.append('quantity', String(quantity));
        formData.append('status', status);
        formData.append('desc', comments);
        if(state.editingEntryId != null && files.length){
          formData.append('replaceImages', 'true');
        }
        const optimizedFiles = await optimizeImageUploadFiles(files);
        optimizedFiles.forEach(file => formData.append('images', file));
        const serverEntry = state.editingEntryId != null
          ? await updateEntryRemote(project, state.currentReportId, state.editingEntryId, formData)
          : await createEntryRemote(project, state.currentReportId, formData);
        if(state.editingEntryId != null){
          const existingIndex = state.entries.findIndex(entry => entry.id === state.editingEntryId);
          if(existingIndex >= 0) state.entries[existingIndex] = serverEntry;
        } else {
          state.entries.push(serverEntry);
        }
        const report = getCurrentReport();
        if(report) report.entries = [...state.entries];
        resetEquipmentEditor();
        save();
        renderAll();
      } catch (error) {
        alert(error.message);
      }
    });
    $('takePhotoBtn')?.addEventListener('click', () => $('photoCameraInput')?.click());
    $('choosePhotoBtn')?.addEventListener('click', () => $('photoInput')?.click());
    $('addFrontBtn')?.addEventListener('click', async () => {
      if(!ensureCanEditReport('No tienes permisos para agregar frentes en este reporte.')){
        return;
      }
      const name = $('frontName').value;
      try {
        const ok = state.editingFrontId ? await saveFrontEdit(name) : await addFront(name);
        if(ok && $('frontName')) $('frontName').value = '';
      } catch (error) {
        alert(error.message);
      }
    });
    $('openIssueFormBtn')?.addEventListener('click', async () => {
      if(!ensureCanEditReport('No tienes permisos para crear issues en este reporte.')){
        return;
      }
      if(!state.currentFrontId && state.reportType === 'incidencia'){
        if(!state.fronts.length){
          const created = await addFront('Frente principal', { autoMerge: false });
          if(!created) return;
        }
        state.currentFrontId = state.fronts[0]?.id ?? null;
      }
      if(state.currentFrontId){
        issueFormManuallyOpened = true;
        resetEntryEditor();
        state.workspaceView = 'issues';
        state.showIssueForm = true;
        state.selectedEntryId = null;
        save();
        renderAll();
        $('entryDesc')?.focus();
      }
    });
    document.querySelectorAll('.togglePreviewBtn').forEach(btn => btn.addEventListener('click', () => {
      state.workspaceView = state.workspaceView === 'preview'
        ? (isEquipmentReport() ? 'equipment' : 'fronts')
        : 'preview';
      state.showPreviewMode = state.workspaceView === 'preview';
      save();
      renderAll();
      if(state.showPreviewMode){
        refreshPreviewContent().catch(error => console.warn('No se pudo mostrar la vista previa del reporte', error));
      }
    }));
    $('combineByStatus')?.addEventListener('change', e => {
      state.combineByStatus = e.target.checked;
      save();
      if(state.showPreviewMode){
        refreshPreviewContent().catch(error => console.warn('No se pudo actualizar la vista previa del reporte', error));
        return;
      }
      renderReport();
    });
    $('cancelEntryEditBtn')?.addEventListener('click', () => { resetEntryEditor(); save(); renderAll(); });
    $('backFromIssueFormBtn')?.addEventListener('click', () => { resetEntryEditor(); save(); renderAll(); });
    $('chooseIssuePlanPointBtn')?.addEventListener('click', async () => {
      if(isEquipmentReport()) return;
      const project = getCurrentProject();
      const plans = project?.plans || [];
      if(!plans.length){ alert('Primero sube un plano en la pestaña Planos del proyecto.'); return; }
      const picker = $('issuePlanPicker');
      const select = $('issuePlanSelect');
      select.innerHTML = plans.map(plan => `<option value="${plan.id}">${escapeHtml(plan.name)}</option>`).join('');
      if(issuePlanPoint?.planId) select.value = String(issuePlanPoint.planId);
      picker.classList.remove('d-none');
      await renderIssuePlanPicker(plans.find(plan => plan.id === Number(select.value)) || plans[0]);
    });
    $('issuePlanSelect')?.addEventListener('change', async e => {
      const project = getCurrentProject();
      const plan = project?.plans?.find(item => item.id === Number(e.target.value));
      issuePlanPoint = null;
      $('issuePlanPickerMarker')?.classList.add('d-none');
      await renderIssuePlanPicker(plan);
    });
    $('issuePlanPickerCanvas')?.addEventListener('click', e => {
      const canvas = $('issuePlanPickerCanvas');
      const rect = canvas.getBoundingClientRect();
      const planId = Number($('issuePlanSelect').value);
      issuePlanPoint = { planId, x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)) };
      const marker = $('issuePlanPickerMarker');
      const pointNumber = (state.entries || []).filter(entry => Number(entry.planId) === planId && entry.id !== state.editingEntryId && entry.planX != null && entry.planY != null).length + 1;
      marker.textContent = pointNumber;
      marker.style.left = `${e.clientX - rect.left}px`;
      marker.style.top = `${e.clientY - rect.top}px`;
      marker.classList.remove('d-none');
    });
    $('saveIssuePlanPointBtn')?.addEventListener('click', () => {
      if(!issuePlanPoint){ alert('Haz clic en el plano para elegir el punto.'); return; }
      $('issuePlanId').value = String(issuePlanPoint.planId);
      $('issuePlanX').value = String(issuePlanPoint.x);
      $('issuePlanY').value = String(issuePlanPoint.y);
      const project = getCurrentProject();
      const pointNumber = (state.entries || []).filter(entry => Number(entry.planId) === Number(issuePlanPoint.planId) && entry.id !== state.editingEntryId && entry.planX != null && entry.planY != null).length + 1;
      $('issueLocation').value = `Punto ${pointNumber}`;
      $('issuePlanPointStatus').textContent = `Punto ${pointNumber} seleccionado en el plano.`;
      $('issuePlanPicker').classList.add('d-none');
    });
    $('clearIssuePlanPointBtn')?.addEventListener('click', () => {
      const currentPointLabel = issuePlanPoint
        ? `Punto ${(state.entries || []).filter(entry => Number(entry.planId) === Number(issuePlanPoint.planId) && entry.id !== state.editingEntryId && entry.planX != null && entry.planY != null).length + 1}`
        : '';
      issuePlanPoint = null;
      $('issuePlanId').value = '';
      $('issuePlanX').value = '';
      $('issuePlanY').value = '';
      $('issuePlanPointStatus').textContent = '';
      if($('issueLocation')?.value === currentPointLabel){
        $('issueLocation').value = '';
      }
      $('issuePlanPicker').classList.add('d-none');
    });
    $('closeIssuePlanPickerBtn')?.addEventListener('click', () => $('issuePlanPicker').classList.add('d-none'));
    $('addEntryBtn')?.addEventListener('click', async () => {
      if(!ensureCanEditReport('No tienes permisos para modificar issues en este reporte.')){
        return;
      }
      const frontId = Number($('selectFront').value);
      const status = $('statusSelect').value;
      const desc = $('entryDesc').value;
      const incidentDate = $('incidentDate')?.value || '';
      const responsibleCompany = $('responsibleCompany')?.value.trim() || '';
      const issueLocation = $('issueLocation')?.value.trim() || '';
      const planId = $('issuePlanId')?.value || '';
      const planX = $('issuePlanX')?.value || '';
      const planY = $('issuePlanY')?.value || '';
      const files = getEntryPhotoFiles();
      const project = getCurrentProject();
      if(!project || !state.currentReportId){
        alert('Primero guarda el reporte antes de registrar issues.');
        return;
      }
      const formData = new FormData();
      formData.append('frontId', String(frontId));
      formData.append('status', status);
      formData.append('desc', desc);
      formData.append('incidentDate', incidentDate);
      formData.append('responsibleCompany', responsibleCompany);
      formData.append('buildingLocation', issueLocation);
      formData.append('planId', planId);
      formData.append('planX', planX);
      formData.append('planY', planY);
      formData.append('removeImageIds', JSON.stringify(Array.from(pendingRemovedEntryImageIds)));
      if(state.editingEntryId != null && files.length){
        formData.append('replaceImages', 'true');
      }
      const optimizedFiles = await optimizeImageUploadFiles(files);
      optimizedFiles.forEach(file => formData.append('images', file));
      try {
        const serverEntry = state.editingEntryId != null
          ? await updateEntryRemote(project, state.currentReportId, state.editingEntryId, formData)
          : await createEntryRemote(project, state.currentReportId, formData);
        if(state.editingEntryId != null){
          const existingIndex = state.entries.findIndex(entry => entry.id === state.editingEntryId);
          if(existingIndex >= 0){
            state.entries[existingIndex] = serverEntry;
          }
        } else {
          state.entries.push(serverEntry);
        }
        const report = getCurrentReport();
        if(report) report.entries = [...state.entries];
        resetEntryEditor();
        save(); renderAll();
      } catch (error) {
        alert(error.message);
      }
    });
    $('exportPdfBtn')?.addEventListener('click', async () => {
      const button = $('exportPdfBtn');
      const mode = $('exportPdfMode')?.value || 'capture';
      const originalLabel = button?.innerHTML || '';
      if(button){
        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Exportando...';
      }
      try {
        if(mode === 'real'){
          await exportRealPdf();
        } else {
          const pdf = await generateReportPdf();
          pdf.save(buildPdfFileName());
        }
      } catch (error) {
        alert(error.message || 'No se pudo exportar el PDF.');
      } finally {
        if(button){
          button.disabled = false;
          button.innerHTML = originalLabel;
        }
      }
    });
  }

  window.addEventListener('popstate', () => {
    syncViewWithCurrentRoute();
  });

  window.addEventListener('resize', () => {
    updatePreviewScale();
  });

  document.addEventListener('DOMContentLoaded', () => {
    load();
    bindEvents();
    updateSelectionScreenSections();
    fetchProjectsFromServer();
  });
})();
