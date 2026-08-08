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
  const PDF_RENDER_SCALE = 1.25;
  const PDF_IMAGE_QUALITY = 0.82;
  const UPLOAD_MAX_DIMENSION = 1800;
  const UPLOAD_IMAGE_QUALITY = 0.8;

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
    currentFrontId: null,
    selectedEntryId: null,
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
  function save(){
    const isCreatingNewProject = state.selectionStage === 'project' && state.showProjectForm && state.currentProjectId === null;
    if(!isCreatingNewProject){
      syncCurrentReport();
      syncCurrentProject();
    }
    localStorage.setItem(storageKey, JSON.stringify(state));
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
    state.editingProjectInfo = false;
    state.editingReportMeta = false;
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
      state.editingEntryId = report.editingEntryId || null;
      state.showIssueForm = !!report.showIssueForm;
      state.showPreviewMode = !!report.showPreviewMode;
      state.reportMetaComplete = report.metaComplete !== undefined ? !!report.metaComplete : true;
      if(state.existingReportOpen){
        state.reportMetaComplete = true;
      }
      state.currentFrontId = report.currentFrontId || null;
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
      state.reportMetaComplete = false;
    }
  }

  function resetProjectForm(){
    state.editingProjectInfo = false;
    state.editingReportMeta = false;
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

  function createProject(name, location, slug, routeOptions = {}){
    const id = generateProjectId();
    const project = {
      id,
      companyName: state.companyName,
      projectName: name || `Proyecto ${state.projects.length + 1}`,
      projectLocation: location || '',
      // slug legible para URLs: proyecto1, proyecto2, ... (acepta slug opcional)
      slug: slug || generateUniqueSlug('proyecto'),
      reports: []
    };
    state.projects.push(project);
    state.currentProjectId = id;
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

  function switchProject(id){
    const projectId = Number(id);
    if(projectId === state.currentProjectId){
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
    state.selectionStage = 'reportType';
    save();
    renderAll();
    updateSelectionScreenSections();
    setProjectRoute(project);
  }

  function deleteProject(id){
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

  function deleteReport(reportId){
    const project = getCurrentProject();
    if(!project || !project.reports?.length) return;
    if(!confirm('¿Eliminar este reporte? Esta acción no se puede deshacer.')) return;
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
    return !!routeInfo.onProjectPath;
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
    state.currentFrontId = null;
    state.showProjectForm = state.projects.length === 0 ? true : state.showProjectForm === true;
    save();
    renderAll();
    updateSelectionScreenSections();
    showSelectionScreen();
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

      showSelectionScreen();
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
      laborDateFrom: data.laborDateFrom || state.laborDateFrom,
      laborDateTo: data.laborDateTo || state.laborDateTo,
      forWhom: data.forWhom || state.forWhom,
      fromWhom: data.fromWhom || state.fromWhom,
      currentProjectId: data.currentProjectId !== undefined ? Number(data.currentProjectId) : state.currentProjectId,
      currentReportId: data.currentReportId !== undefined ? Number(data.currentReportId) : state.currentReportId,
      currentFrontId: data.currentFrontId !== undefined ? Number(data.currentFrontId) : state.currentFrontId,
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
    const v = localStorage.getItem(storageKey);
    if(v){
      try {
        normalizeLoadedState(JSON.parse(v));
      } catch (err) {
        console.warn('Error leyendo estado desde localStorage', err);
      }
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
          // Construir un nombre legible desde el slug
          let human = initSlug.replace(/[-_]/g, ' ').replace(/^proyecto\s*/i, 'Proyecto ');
          human = human.replace(/\b\w/g, c => c.toUpperCase()).trim();
          if(!human) human = `Proyecto ${state.projects.length + 1}`;
          // Crear proyecto local con el slug proporcionado
          createProject(human, '', initSlug, { replace: true });
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
      showSelectionScreen();
    } else if(routeInfo.onProjectPath && state.currentProjectId){
      const proj = getCurrentProject();
      setProjectRoute(proj, { replace: true });
      showSelectionScreen();
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
      showSelectionScreen();
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

  function addFront(name, opts){
    const cleanedName = cleanFrontName(name) || name.trim();
    if(!cleanedName) return false;
    const existing = findFrontByName(cleanedName);
    const autoMerge = opts?.autoMerge ?? state.autoMergeDup;
    if(existing){ if(autoMerge) return true; if(confirm(`Ya existe el frente "${existing.name}". ¿Fusionar con el existente?`)) return true; return false; }
    const finalName = cleanedName || `Frente ${state.fronts.length + 1}`;
    state.fronts.push({ id: Date.now() + Math.random(), name: finalName });
    save(); renderAll(); return true;
  }

  function getEntryById(id){ return state.entries.find(e => e.id === id); }
  function getFrontName(frontId){ const front = state.fronts.find(f => f.id === frontId); return front ? front.name : 'Frente eliminado'; }
  function removeFront(id){ state.fronts = state.fronts.filter(f => f.id !== id); state.entries = state.entries.filter(e => e.frontId !== id); save(); renderAll(); }
  function removeEntry(id){ state.entries = state.entries.filter(e => e.id !== id); if(state.editingEntryId === id){ resetEntryEditor(); } save(); renderAll(); }
  function clearEntryPhotoInputs(){ if($('photoInput')) $('photoInput').value = ''; if($('photoCameraInput')) $('photoCameraInput').value = ''; }
  function getEntryPhotoFiles(){ return [...($('photoInput')?.files ? Array.from($('photoInput').files) : []), ...($('photoCameraInput')?.files ? Array.from($('photoCameraInput').files) : [])]; }
  function resetEntryEditor(){ state.editingEntryId = null; state.showIssueForm = false; $('addEntryBtn').textContent = 'Agregar issue'; $('cancelEntryEditBtn').classList.add('d-none'); clearEntryPhotoInputs(); $('entryDesc').value = ''; const frontId = Number($('selectFront').value); if(frontId){ $('selectFront').value = frontId; } $('selectFront').disabled = false; }
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
          const imagesMarkup = row.photos.length ? `<div class="report-entry-images">${row.photos.map(src => `<img src="${src}" class="thumb" alt="Foto">`).join('')}</div>` : '';
          const note = row.continuation ? `<div class="report-entry-note">Continuación</div>` : '';
          const item = row.item;

          return `<div class="report-entry"><div class="report-entry-body"><div class="report-entry-text"><div class="report-entry-status">${statusBadge(item.status)}</div>${item.desc ? `<div class="report-entry-desc">${escapeHtml(item.desc)}</div>` : ''}${note}</div>${imagesMarkup}</div></div>`;
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
    renderProjectSelect();
    renderProjectPanel();
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
    renderReportEditorSections();
    $('companyName').value = state.companyName || 'VDC CONSTRUCCIONES SAC';
    $('projectName').value = state.projectName || '';
    $('projectLocation').value = state.projectLocation || '';
    $('reportTitle').value = state.reportTitle || 'REPORTE FOTOGRÁFICO DE OBRA';
    $('reportWeek').value = state.reportWeek || '8';
    $('reportDate').value = state.reportDate || new Date().toISOString().slice(0, 10);
    $('laborDateFrom').value = state.laborDateFrom || '';
    $('laborDateTo').value = state.laborDateTo || '';
    $('forWhom').value = state.forWhom || '';
    $('fromWhom').value = state.fromWhom || '';
    $('objectiveText').value = state.objectiveText || '';
    $('analysisText').value = state.analysisText || '';
    const metadataProjectName = $('metadataProjectName');
    const metadataReportType = $('metadataReportType');
    const metadataReportTypeDisplay = $('metadataReportTypeDisplay');
    if(metadataProjectName) metadataProjectName.value = state.projectName || '';
    if(metadataReportType) metadataReportType.value = state.reportType || '';
    if(metadataReportTypeDisplay) metadataReportTypeDisplay.value = state.reportType === 'incidencia' ? 'Reporte de incidencia' : state.reportType === 'avances' ? 'Reporte de avances' : '';
    $('conclusionText').value = state.conclusionText || '';
    $('recommendationText').value = state.recommendationText || '';
    const existingProjectName = $('existingProjectName');
    const existingReportTitle = $('existingReportTitle');
    const existingReportTitleCompact = $('existingReportTitleCompact');
    const existingReportTypeDisplay = $('existingReportTypeDisplay');
    const existingReportTypeCompact = $('existingReportTypeCompact');
    const existingReportWeek = $('existingReportWeek');
    const existingReportDate = $('existingReportDate');
    const existingLaborRange = $('existingLaborRange');
    const existingForWhom = $('existingForWhom');
    const existingFromWhom = $('existingFromWhom');
    const existingObjectiveText = $('existingObjectiveText');
    const existingAnalysisText = $('existingAnalysisText');
    if(existingProjectName) existingProjectName.value = state.projectName || '';
    if(existingReportTitle) existingReportTitle.value = state.reportTitle || '';
    if(existingReportTitleCompact) existingReportTitleCompact.textContent = state.reportTitle || 'Sin título';
    if(existingReportTypeDisplay) existingReportTypeDisplay.value = state.reportType === 'incidencia' ? 'Reporte de incidencia' : state.reportType === 'avances' ? 'Reporte de avances' : '';
    if(existingReportTypeCompact) existingReportTypeCompact.textContent = state.reportType === 'incidencia' ? 'Reporte de incidencia' : state.reportType === 'avances' ? 'Reporte de avances' : 'Sin tipo';
    if(existingReportWeek) existingReportWeek.value = state.reportWeek || '';
    if(existingReportDate) existingReportDate.value = state.reportDate || '';
    if(existingLaborRange) existingLaborRange.value = [formatDateForDisplay(state.laborDateFrom || ''), formatDateForDisplay(state.laborDateTo || '')].filter(Boolean).join(' al ') || 'Sin rango';
    if(existingForWhom) existingForWhom.value = state.forWhom || 'Sin dato';
    if(existingFromWhom) existingFromWhom.value = state.fromWhom || 'Sin dato';
    if(existingObjectiveText) existingObjectiveText.value = state.objectiveText || 'Sin objetivo registrado';
    if(existingAnalysisText) existingAnalysisText.value = state.analysisText || 'Sin análisis registrado';
    $('conclusionList').innerHTML = renderBulletList(state.conclusionItems, state.conclusionText);
    $('recommendationList').innerHTML = renderBulletList(state.recommendationItems, state.recommendationText);
    const autoMergeEl = $('autoMergeDup');
    if(autoMergeEl) autoMergeEl.checked = !!state.autoMergeDup;
    document.querySelectorAll('.togglePreviewBtn').forEach(btn => {
      btn.textContent = state.showPreviewMode ? 'Cerrar vista previa' : 'Ver vista previa';
      btn.classList.toggle('btn-primary', !state.showPreviewMode);
      btn.classList.toggle('btn-outline-primary', state.showPreviewMode);
    });
    $('combineByStatus').checked = !!state.combineByStatus;
    renderFrontList(); renderDuplicateAlert(); renderFrontSelect(); renderEntryList(); renderFrontDetail(); renderReport();
  }

  function renderFrontDetail(){
    const selectedFront = state.fronts.find(f => f.id === state.currentFrontId);
    const selectedName = $('selectedFrontName');
    const list = $('frontIssueList');
    const detailPanel = $('issueDetailPanel');
    if(selectedName){ selectedName.textContent = selectedFront ? frontLabel(selectedFront) : ''; }
    if(!list) return;
    if(!selectedFront){
      list.innerHTML = '<p class="text-muted small mb-0">Selecciona un frente para ver sus issues.</p>';
      if(detailPanel){ detailPanel.classList.add('d-none'); detailPanel.innerHTML = ''; }
      return;
    }
    const entries = state.entries.filter(e => e.frontId === selectedFront.id);
    if(!entries.length){
      list.innerHTML = '<p class="text-muted small mb-0">No hay issues creados en este frente.</p>';
      if(detailPanel){ detailPanel.classList.add('d-none'); detailPanel.innerHTML = ''; }
      return;
    }
    list.innerHTML = entries.map(entry => {
      return `<div class="issue-item card mb-2 p-3"><div class="d-flex justify-content-between align-items-start flex-wrap gap-2"><div><strong>${escapeHtml(entry.desc || 'Issue sin descripción')}</strong><div class="small text-muted">${escapeHtml(entry.status)} · ${escapeHtml(selectedFront.name)}</div></div><div class="d-flex gap-2"><button data-id="${entry.id}" class="btn btn-sm btn-outline-secondary view-entry-detail">Ver detalle</button><button data-id="${entry.id}" class="btn btn-sm btn-outline-primary edit-entry">Editar</button><button data-id="${entry.id}" class="btn btn-sm btn-outline-danger delete-entry">Eliminar</button></div></div></div>`;
    }).join('');
    list.querySelectorAll('.edit-entry').forEach(btn => btn.addEventListener('click', e => {
      const entry = getEntryById(Number(e.target.dataset.id));
      if(!entry) return;
      state.editingEntryId = entry.id;
      state.showIssueForm = true;
      $('selectFront').value = entry.frontId;
      $('selectFront').disabled = true;
      $('statusSelect').value = entry.status;
      $('entryDesc').value = entry.desc || '';
      $('addEntryBtn').textContent = 'Guardar cambios';
      $('cancelEntryEditBtn').classList.remove('d-none');
          clearEntryPhotoInputs();
      save();
      renderAll();
      $('entryDesc')?.focus();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }));
    list.querySelectorAll('.delete-entry').forEach(btn => btn.addEventListener('click', e => {
      const id = Number(e.target.dataset.id);
      if(confirm('¿Borrar esta entrada del reporte?')) removeEntry(id);
    }));
    list.querySelectorAll('.view-entry-detail').forEach(btn => btn.addEventListener('click', e => {
      const id = Number(e.target.dataset.id);
      state.selectedEntryId = id;
      renderAll();
    }));
    if(detailPanel){
      const selectedEntry = getEntryById(state.selectedEntryId);
      if(!selectedEntry || selectedEntry.frontId !== selectedFront.id){
        detailPanel.classList.add('d-none');
        detailPanel.innerHTML = '';
        state.selectedEntryId = null;
      } else {
        const imagesHtml = Array.isArray(selectedEntry.images) && selectedEntry.images.length
          ? selectedEntry.images.map(src => `<img src="${src}" class="img-fluid mb-2" style="width: 100%; height: auto; display: block; margin-bottom: 0.75rem; object-fit: contain;">`).join('')
          : '<div class="text-muted small">No hay fotos disponibles.</div>';
        detailPanel.classList.remove('d-none');
        detailPanel.innerHTML = `<div class="mb-3"><strong>Detalle de issue</strong></div><div class="mb-2"><span class="badge bg-secondary">${escapeHtml(selectedEntry.status)}</span></div><div class="mb-3">${escapeHtml(selectedEntry.desc || 'Sin descripción')}</div>${imagesHtml}<div class="d-flex gap-2 flex-wrap"><button type="button" class="btn btn-sm btn-primary edit-entry-detail" data-id="${selectedEntry.id}">Editar</button><button type="button" class="btn btn-sm btn-outline-secondary close-entry-detail">Cerrar detalle</button><button type="button" class="btn btn-sm btn-outline-danger delete-entry" data-id="${selectedEntry.id}">Eliminar</button></div>`;
        detailPanel.querySelector('.edit-entry-detail').addEventListener('click', () => {
          state.editingEntryId = selectedEntry.id;
          state.showIssueForm = true;
          $('selectFront').value = selectedEntry.frontId;
          $('selectFront').disabled = true;
          $('statusSelect').value = selectedEntry.status;
          $('entryDesc').value = selectedEntry.desc || '';
          $('addEntryBtn').textContent = 'Guardar cambios';
          $('cancelEntryEditBtn').classList.remove('d-none');
          $('photoInput').value = '';
          save();
          renderAll();
          $('entryDesc')?.focus();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });
        detailPanel.querySelector('.close-entry-detail').addEventListener('click', () => {
          state.selectedEntryId = null;
          renderAll();
        });
        detailPanel.querySelectorAll('.delete-entry').forEach(btn => btn.addEventListener('click', e => {
          const id = Number(e.target.dataset.id);
          if(confirm('¿Borrar esta entrada del reporte?')) removeEntry(id);
        }));
      }
    }
  }

  function renderFrontList(){ const container = $('frontList'); container.innerHTML = ''; if(!state.fronts.length){ container.innerHTML = '<p class="text-muted small mb-0">Sin frentes. Agrega uno para poder registrar issues.</p>'; return; } state.fronts.forEach(f => { const n = frontNumber(f.id); const div = document.createElement('div'); div.className = 'front-item d-flex align-items-center justify-content-between flex-wrap gap-2'; div.innerHTML = `<div class="d-flex align-items-center gap-2"><span class="badge bg-dark front-num">${n}</span><span>${escapeHtml(f.name)}</span></div><div class="d-flex gap-2 flex-wrap"><button data-id="${f.id}" class="btn btn-sm btn-primary open-front-btn">Ver detalle</button><button data-id="${f.id}" class="btn btn-sm btn-danger rm-front">Eliminar</button></div>`; container.appendChild(div); }); container.querySelectorAll('.rm-front').forEach(b => b.addEventListener('click', e => { const id = Number(e.target.dataset.id); if(confirm('¿Eliminar frente y sus entradas?')) removeFront(id); })); container.querySelectorAll('.open-front-btn').forEach(b => b.addEventListener('click', e => { const id = Number(e.target.dataset.id); const project = getCurrentProject(); if(id && project && state.currentReportId){ state.currentFrontId = id; state.showIssueForm = false; state.editingEntryId = null; state.selectedEntryId = null; save(); setFrontRoute(project, state.currentReportId, id); renderAll(); } })); }
  function renderEntryList(){ const container = $('entryList'); container.innerHTML = ''; const selectedFront = state.fronts.find(f => f.id === state.currentFrontId); const entries = selectedFront ? state.entries.filter(e => e.frontId === selectedFront.id) : state.entries; if(!entries.length){ container.innerHTML = '<p class="text-muted small mb-0">No hay issues en este frente. Crea una nueva issue cuando la necesites.</p>'; return; } entries.forEach(entry => { const front = state.fronts.find(f => f.id === entry.frontId); const name = front ? front.name : 'Frente eliminado'; const div = document.createElement('div'); div.className = 'entry-list-item'; div.innerHTML = `<div class="entry-list-meta"><div><strong>${escapeHtml(name)}</strong><br><span class="badge badge-status ${STATUS_BADGE[entry.status] || 'bg-info text-dark'}">${escapeHtml(entry.status)}</span></div><div class="entry-list-actions"><button data-id="${entry.id}" class="btn btn-sm btn-outline-primary edit-entry">Editar</button><button data-id="${entry.id}" class="btn btn-sm btn-outline-danger delete-entry">Borrar</button></div></div><div class="entry-list-body">${escapeHtml(entry.desc || 'Sin descripción')}</div>`; container.appendChild(div); }); container.querySelectorAll('.edit-entry').forEach(btn => btn.addEventListener('click', e => { const entry = getEntryById(Number(e.target.dataset.id)); if(!entry) return; state.editingEntryId = entry.id; state.showIssueForm = true; $('selectFront').value = entry.frontId; $('selectFront').disabled = true; $('statusSelect').value = entry.status; $('entryDesc').value = entry.desc || ''; $('addEntryBtn').textContent = 'Guardar cambios'; $('cancelEntryEditBtn').classList.remove('d-none'); $('photoInput').value = ''; save(); renderAll(); $('entryDesc')?.focus(); window.scrollTo({ top: 0, behavior: 'smooth' }); })); container.querySelectorAll('.delete-entry').forEach(btn => btn.addEventListener('click', e => { const id = Number(e.target.dataset.id); if(confirm('¿Borrar esta entrada del reporte?')) removeEntry(id); })); }
  function renderDuplicateAlert(){ const el = $('duplicateAlert'); if(!el) return; const groups = findDuplicateGroups(); if(!groups.length){ el.innerHTML = ''; return; } el.innerHTML = groups.map(group => { const names = group.map(f => `${frontNumber(f.id)}. ${escapeHtml(f.name)}`).join(', '); const keepId = group[0].id; const removeIds = group.slice(1).map(f => f.id); return `<div class="dup-group small"><strong>Duplicados:</strong> ${names}<button class="btn btn-sm btn-warning ms-2 merge-group" data-keep="${keepId}" data-remove="${removeIds.join(',')}">Fusionar</button></div>`; }).join(''); el.querySelectorAll('.merge-group').forEach(btn => btn.addEventListener('click', e => { const keepId = Number(e.target.dataset.keep); const removeIds = e.target.dataset.remove.split(',').map(Number); mergeFronts(keepId, removeIds); })); }
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
    const canEditProject = !!(routeInfo.onProjectPath && !isReportRoute);

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
  function renderSelectionReportList(){ const section = $('selectionReportListSection'); const list = $('selectionReportList'); if(!section || !list) return; const project = getCurrentProject(); if(!project || state.selectionStage !== 'reportType'){ section.classList.add('d-none'); return; } section.classList.remove('d-none'); const reports = project.reports || []; if(!reports.length){ list.innerHTML = '<div class="text-muted small mb-0">Aún no hay reportes creados para este proyecto.</div>'; return; } list.innerHTML = reports.map(report => { const active = report.id === state.currentReportId ? 'active' : ''; return `<div class="list-group-item d-flex justify-content-between align-items-center ${active}"><button type="button" data-id="${report.id}" class="btn btn-link p-0 text-start flex-grow-1 report-select-btn">${escapeHtml(report.title || 'Reporte sin título')}</button><button type="button" data-delete-id="${report.id}" class="btn btn-sm btn-outline-danger ms-2">Eliminar</button></div>`; }).join(''); }
  function renderReportEditorSections(){ const metadataForm = $('metadataForm'); const formExtras = $('reportFormExtras'); const editorSections = $('reportEditorSections'); const existingReportSummarySection = $('existingReportSummarySection'); const reportFrontsSection = $('reportFrontsSection'); const frontDetailSection = $('frontDetailSection'); const entrySection = $('entrySection'); const previewSection = $('previewSection'); const continueBtn = $('continueToEditorBtn'); const cancelReportMetaEditBtn = $('cancelReportMetaEditBtn'); const editReportInfoBtn = $('editReportInfoBtn'); const projectHeaderSection = $('projectHeaderSection'); const reportConclusionsSection = $('reportConclusionsSection'); const isEditingReportMeta = !!(state.editingReportMeta && state.existingReportOpen && isOnReportRoute()); const isInsideFrontDetail = !!state.currentFrontId; if(metadataForm){ metadataForm.classList.toggle('d-none', ((state.reportMetaComplete || state.existingReportOpen) && !isEditingReportMeta) || state.showPreviewMode); } if(formExtras){ formExtras.classList.toggle('d-none', isEditingReportMeta || !(state.reportMetaComplete || state.existingReportOpen)); } if(editorSections){ editorSections.classList.toggle('d-none', isEditingReportMeta || !state.reportMetaComplete); } if(existingReportSummarySection){ existingReportSummarySection.classList.toggle('d-none', !state.existingReportOpen || state.showPreviewMode || isEditingReportMeta || isInsideFrontDetail); } if(reportFrontsSection){ reportFrontsSection.classList.toggle('d-none', isEditingReportMeta || isInsideFrontDetail || !(state.reportMetaComplete || state.existingReportOpen) || state.showPreviewMode); } if(frontDetailSection){ frontDetailSection.classList.toggle('d-none', isEditingReportMeta || !isInsideFrontDetail || state.showPreviewMode); } if(entrySection){ entrySection.classList.toggle('d-none', isEditingReportMeta || !isInsideFrontDetail || state.showPreviewMode || !state.showIssueForm); } if(previewSection){ previewSection.classList.toggle('d-none', isEditingReportMeta || !state.showPreviewMode); } if(reportConclusionsSection){ reportConclusionsSection.classList.toggle('d-none', isEditingReportMeta || isInsideFrontDetail || state.showPreviewMode); } if(continueBtn){ continueBtn.classList.toggle('d-none', ((!isEditingReportMeta && (state.reportMetaComplete || state.existingReportOpen)) || state.showPreviewMode)); continueBtn.innerHTML = isEditingReportMeta ? '<i class="bi bi-check2-circle me-2"></i>Guardar datos del reporte' : '<i class="bi bi-arrow-right-circle me-2"></i>Crear reporte'; } if(cancelReportMetaEditBtn){ cancelReportMetaEditBtn.classList.toggle('d-none', !isEditingReportMeta || state.showPreviewMode); } if(editReportInfoBtn){ editReportInfoBtn.classList.toggle('d-none', !state.existingReportOpen || state.showPreviewMode || !isOnReportRoute() || isInsideFrontDetail); } if(projectHeaderSection){ projectHeaderSection.classList.toggle('d-none', isEditingReportMeta || isInsideFrontDetail); } }
  function renderFrontSelect(){ const sel = $('selectFront'); sel.innerHTML = ''; if(state.currentFrontId){ const front = state.fronts.find(f => f.id === state.currentFrontId); if(front){ const opt = document.createElement('option'); opt.value = front.id; opt.textContent = frontLabel(front); sel.appendChild(opt); sel.value = front.id; sel.disabled = true; return; } }
    state.fronts.forEach(f => { const opt = document.createElement('option'); opt.value = f.id; opt.textContent = frontLabel(f); sel.appendChild(opt); }); }
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

    pages.push({
      type: 'section',
      tag: '1. OBJETIVO + 2. ANÁLISIS',
      body: `<div class="report-page-content"><div class="report-section-title">1. OBJETIVO</div><div class="report-section-body">${escapeHtml(objectiveText || 'El presente informe tiene como objetivo registrar de manera técnica y fotográfica los avances físicos logrados durante la presente semana de trabajo, detallando las partidas ejecutadas en los frentes de demolición, estructuras, albañilería, instalaciones y acabados, asegurando el control de calidad en cada proceso.')}</div><div class="report-section-title" style="margin-top: 24px;">2. ANÁLISIS: AVANCES DE LA SEMANA</div>${laborDateRange ? `<div class="report-section-subtitle"><strong>Fecha de labores:</strong> ${escapeHtml(laborDateRange)}</div>` : ''}<div class="report-section-body">${escapeHtml(analysisText || 'Agregar el análisis de las actividades ejecutadas y avanzadas durante la semana.')}</div>${buildSection2FrontList(groups)}</div>`
    });

    pages.push(...buildSection3Pages(groups));

    pages.push({
      type: 'section',
      tag: '4. CONCLUSIONES + 5. RECOMENDACIONES',
      body: `<div class="report-page-content"><div class="report-section-title">4. CONCLUSIONES</div><div class="report-section-body">${conclusionMarkup || '<div class="report-empty-state">Escriba aquí las conclusiones del avance o las observaciones finales.</div>'}</div><div class="report-section-title" style="margin-top: 24px;">5. RECOMENDACIONES</div><div class="report-section-body">${recommendationMarkup || '<div class="report-empty-state">Escriba aquí las recomendaciones del trabajo o actividades pendientes.</div>'}</div></div>`
    });

    const totalPages = pages.length;
    pages.forEach((page, index) => {
      const number = index + 1;
      const pageNode = document.createElement('div');
      pageNode.className = page.type === 'cover' ? 'report-page report-cover' : 'report-page report-secondary-page';
      pageNode.innerHTML = `${renderCompanyHeader()}${page.body}${page.type === 'cover' ? renderCoverFooterBlock(number, totalPages) : renderPageFooter(number, totalPages)}`;
      rc.appendChild(pageNode);
    });
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
    return canvas.toDataURL('image/jpeg', quality);
  }

  async function optimizeImageFile(file, options){
    const dataUrl = await readFileAsDataUrl(file);
    return optimizeImageDataUrl(dataUrl, options);
  }

  function generateReportPdf(){
    const { jsPDF } = window.jspdf;
    const pages = Array.from(document.querySelectorAll('.report-page'));
    const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4', compress: true });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    if(!pages.length){
      return pdf;
    }
    const renderPage = async (page, pageIndex) => {
      const canvas = await html2canvas(page, {
        scale: PDF_RENDER_SCALE,
        useCORS: true,
        backgroundColor: '#ffffff'
      });
      const imgData = canvas.toDataURL('image/jpeg', PDF_IMAGE_QUALITY);
      if(pageIndex > 0){
        pdf.addPage();
      }
      pdf.addImage(imgData, 'JPEG', 0, 0, pageWidth, pageHeight, undefined, 'MEDIUM');
    };
    return pages.reduce((promise, page, pageIndex) => {
      return promise.then(() => renderPage(page, pageIndex));
    }, Promise.resolve()).then(() => pdf);
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
    $('selectionScreen').classList.remove('d-none');
    $('appContent').classList.add('d-none');
  }

  function showAppScreen(){
    $('selectionScreen').classList.add('d-none');
    $('appContent').classList.remove('d-none');
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
          <button type="button" data-id="${project.id}" class="btn ${active} text-start flex-grow-1 project-select-btn">${escapeHtml(project.projectName || 'Proyecto sin nombre')}</button>
          <button type="button" data-id="${project.id}" class="btn btn-outline-danger btn-sm project-delete-btn" title="Eliminar proyecto">×</button>
        </div>
      `;
    }).join('');
  }

  function updateSelectionScreenSections(){
    const projectFormSection = $('projectFormSection');
    const projectCreatedSection = $('projectCreatedSection');
    const reportTypeSection = $('reportTypeSection');
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

  function bindEvents(){
    $('createProjectBtn').addEventListener('click', () => {
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
        state.companyName = company;
        state.projectName = projectName;
        state.projectLocation = projectLocation;
        current.companyName = company;
        current.projectName = projectName;
        current.projectLocation = projectLocation;
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
      createProject(projectName, projectLocation);
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
      showSelectionScreen();
      renderAll();
      updateSelectionScreenSections();
    });
    $('projectButtons')?.addEventListener('click', e => {
      const deleteBtn = e.target.closest('.project-delete-btn');
      if(deleteBtn){
        const id = Number(deleteBtn.dataset.id);
        if(id && confirm('¿Eliminar este proyecto? Esta acción no se puede deshacer.')){
          deleteProject(id);
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
    $('createAnotherProjectBtn').addEventListener('click', () => {
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
      showSelectionScreen();
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
      state.editingReportMeta = false;
      save();
      setProjectRoute(current);
      renderAll();
      updateSelectionScreenSections();
      showSelectionScreen();
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
        if(reportId) deleteReport(reportId);
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
        if(reportId) deleteReport(reportId);
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
    $('continueToEditorBtn')?.addEventListener('click', () => {
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
      let report = getCurrentReport();
      if(!report){
        const id = generateProjectId();
        const defaultTitle = reportType === 'incidencia'
          ? 'REPORTE DE INCIDENCIA'
          : 'REPORTE DE AVANCES';
        report = {
          id,
          type: reportType,
          title: defaultTitle,
          week: state.reportWeek || '8',
          date: state.reportDate || new Date().toISOString().slice(0, 10),
          forWhom: state.forWhom || '',
          fromWhom: state.fromWhom || '',
          objectiveText: state.objectiveText || '',
          analysisText: state.analysisText || '',
          conclusionText: state.conclusionText || '',
          recommendationText: state.recommendationText || '',
          conclusionItems: [...state.conclusionItems],
          recommendationItems: [...state.recommendationItems],
          laborDateFrom: state.laborDateFrom || '',
          laborDateTo: state.laborDateTo || '',
          coverImage: state.coverImage || '',
          fronts: [...state.fronts],
          entries: [...state.entries],
          autoMergeDup: state.autoMergeDup,
          combineByStatus: state.combineByStatus,
          editingEntryId: state.editingEntryId,
          currentFrontId: state.currentFrontId,
          metaComplete: true
        };
        project.reports = project.reports || [];
        project.reports.push(report);
        state.currentReportId = id;
        project.currentReportId = id;
      }
      state.reportType = reportType;
      state.reportMetaComplete = true;
      state.existingReportOpen = true;
      state.editingReportMeta = false;
      save();
      setReportRoute(project, state.currentReportId);
      renderAll();
      showAppScreen();
    });
    $('editReportInfoBtn')?.addEventListener('click', () => {
      if(!state.currentReportId || !isOnReportRoute()) return;
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
    $('backToStartBtn').addEventListener('click', () => {
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
    $('newProjectBtn').addEventListener('click', () => {
      const name = prompt('Nombre del proyecto:', `Proyecto ${state.projects.length + 1}`);
      if(!name) return;
      const location = prompt('Ubicación del proyecto:','');
      createProject(name.trim(), location ? location.trim() : '');
    });
    $('newProjectBtnDisplay')?.addEventListener('click', () => {
      const name = prompt('Nombre del proyecto:', `Proyecto ${state.projects.length + 1}`);
      if(!name) return;
      const location = prompt('Ubicación del proyecto:','');
      createProject(name.trim(), location ? location.trim() : '');
    });
    $('projectSelect').addEventListener('change', e => {
      const id = Number(e.target.value);
      if(id) switchProject(id);
    });
    $('companyName').addEventListener('input', e => { state.companyName = e.target.value; save(); renderReport(); });
    $('projectName').addEventListener('input', e => { state.projectName = e.target.value; save(); renderReport(); });
    $('projectLocation').addEventListener('input', e => { state.projectLocation = e.target.value; save(); renderReport(); });
    $('reportTitle').addEventListener('input', e => { state.reportTitle = e.target.value; save(); renderReport(); });
    $('reportWeek').addEventListener('input', e => { state.reportWeek = e.target.value; save(); renderReport(); });
    $('reportDate').addEventListener('input', e => { state.reportDate = e.target.value; save(); renderReport(); });
    $('laborDateFrom').addEventListener('input', e => { state.laborDateFrom = e.target.value; save(); renderReport(); });
    $('laborDateTo').addEventListener('input', e => { state.laborDateTo = e.target.value; save(); renderReport(); });
    $('forWhom').addEventListener('input', e => { state.forWhom = e.target.value; save(); renderReport(); });
    $('fromWhom').addEventListener('input', e => { state.fromWhom = e.target.value; save(); renderReport(); });
    $('objectiveText').addEventListener('input', e => { state.objectiveText = e.target.value; save(); renderReport(); });
    $('analysisText').addEventListener('input', e => { state.analysisText = e.target.value; save(); renderReport(); });
    $('objectiveText').addEventListener('input', e => { state.objectiveText = e.target.value; save(); renderReport(); });
    $('analysisText').addEventListener('input', e => { state.analysisText = e.target.value; save(); renderReport(); });
    $('metadataReportType').addEventListener('change', e => { state.reportType = e.target.value; save(); });
    $('conclusionText').addEventListener('input', e => { state.conclusionText = e.target.value; state.conclusionItems = normalizeListItems(e.target.value); save(); renderAll(); });
    $('recommendationText').addEventListener('input', e => { state.recommendationText = e.target.value; state.recommendationItems = normalizeListItems(e.target.value); save(); renderAll(); });
    $('addConclusionBtn').addEventListener('click', () => {
      const value = $('conclusionItemInput').value.trim();
      if(!value){ return; }
      state.conclusionItems.push(value);
      state.conclusionText = state.conclusionItems.join('\n');
      save(); renderAll();
      $('conclusionItemInput').value = '';
    });
    $('addRecommendationBtn').addEventListener('click', () => {
      const value = $('recommendationItemInput').value.trim();
      if(!value){ return; }
      state.recommendationItems.push(value);
      state.recommendationText = state.recommendationItems.join('\n');
      save(); renderAll();
      $('recommendationItemInput').value = '';
    });
    $('coverPhotoInput').addEventListener('change', async () => {
      const file = $('coverPhotoInput').files[0];
      if(!file){ state.coverImage = ''; save(); renderReport(); return; }
      const optimizedImage = await optimizeImageFile(file);
      state.coverImage = optimizedImage;
      save(); renderReport();
    });
    $('takePhotoBtn')?.addEventListener('click', () => $('photoCameraInput')?.click());
    $('choosePhotoBtn')?.addEventListener('click', () => $('photoInput')?.click());
    $('addFrontBtn').addEventListener('click', () => { const name = $('frontName').value; if(addFront(name)) $('frontName').value = ''; });
    $('openIssueFormBtn')?.addEventListener('click', () => { if(state.currentFrontId){ resetEntryEditor(); state.showIssueForm = true; state.selectedEntryId = null; save(); renderAll(); $('entryDesc')?.focus(); } });
    document.querySelectorAll('.togglePreviewBtn').forEach(btn => btn.addEventListener('click', () => { state.showPreviewMode = !state.showPreviewMode; save(); renderAll(); }));
    $('combineByStatus').addEventListener('change', e => { state.combineByStatus = e.target.checked; save(); renderReport(); });
    $('backToFrontListBtn')?.addEventListener('click', () => { const project = getCurrentProject(); state.currentFrontId = null; state.showIssueForm = false; state.selectedEntryId = null; state.editingEntryId = null; save(); if(project && state.currentReportId){ setReportRoute(project, state.currentReportId); } renderAll(); });
    $('cancelEntryEditBtn').addEventListener('click', () => { resetEntryEditor(); save(); renderAll(); });
    $('addEntryBtn').addEventListener('click', () => {
      const frontId = Number($('selectFront').value);
      const status = $('statusSelect').value;
      const desc = $('entryDesc').value;
      const files = getEntryPhotoFiles();
      const finalize = (nextImages) => {
        if(state.editingEntryId != null){
          const existing = getEntryById(state.editingEntryId);
          if(existing){
            existing.status = status;
            existing.desc = desc;
            existing.images = nextImages.length ? nextImages : (existing.images || []);
            existing.ts = new Date().toISOString();
            save(); renderAll();
          }
        } else {
          addEntry(frontId, status, desc, nextImages);
        }
        resetEntryEditor();
        save(); renderAll();
      };
      Promise.all(files.map(file => optimizeImageFile(file)))
        .then(nextImages => {
          finalize(nextImages);
        })
        .catch(() => {
          alert('No se pudieron procesar una o más imágenes. Intenta con fotos más ligeras.');
        });
      if(!files.length){
        if(state.editingEntryId != null){
          const existing = getEntryById(state.editingEntryId);
          const nextImages = existing ? (existing.images || []) : [];
          finalize(nextImages);
        } else {
          finalize([]);
        }
      }
    });
    $('exportPdfBtn').addEventListener('click', () => {
      generateReportPdf().then(pdf => {
        pdf.save('reporte.pdf');
      });
    });
  }

  window.addEventListener('popstate', () => {
    syncViewWithCurrentRoute();
  });

  document.addEventListener('DOMContentLoaded', () => {
    load();
    bindEvents();
    updateSelectionScreenSections();
  });
})();
