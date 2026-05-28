/* ==========================================================================
   Page Preview & Translation Manager Script - break_the_barriers
   Implements 3s polling loop, selective DOM rendering, concurrent async AJAX API,
   sandboxed iframe rendering, and seamless document workflow transitions.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    console.log("%cSmart Docs Page Preview Manager Active!", "color: #f59e0b; font-size: 14px; font-weight: bold;");

    const API_BASE = 'http://localhost:8005';
    const urlParams = new URLSearchParams(window.location.search);
    const docId = urlParams.get('doc_id');

    if (!docId) {
        console.error("Missing doc_id on URL parameters, redirecting to Dashboard...");
        window.location.href = 'index.html';
        return;
    }

    // Cache state to prevent redundant iframe/card re-renders
    let pageStatesCache = {}; // { page_num: { status, has_original, has_translated } }
    let pageDimensionsCache = {}; // { page_num: { width, height } }
    let documentMetadata = null;
    let pollingInterval = null;
    
    // View Switcher & Details Mode States
    let currentViewMode = localStorage.getItem('preview_view_mode') || 'grid';
    let activePageNum = parseInt(urlParams.get('page')) || null;
    let viewportState = 'html'; // 'original' | 'html' | 'translated'
    let pagesDataStore = []; // Unified data array for sidebar and active rendering

    if (urlParams.get('page')) {
        currentViewMode = 'details';
    }

    // DOM References
    const titleDocName = document.getElementById('title-doc-name');
    const toolbarDocFilename = document.getElementById('toolbar-doc-filename');
    const metaTotalPages = document.getElementById('meta-total-pages');
    const metaTranslatedPages = document.getElementById('meta-translated-pages');
    const metaDocStatus = document.getElementById('meta-doc-status');
    const pagesGrid = document.getElementById('pages-grid');
    const detailsWorkspace = document.getElementById('details-workspace');
    const workspaceSidebar = document.getElementById('workspace-sidebar');

    const btnViewGrid = document.getElementById('btn-view-grid');
    const btnViewDetails = document.getElementById('btn-view-details');
    
    const largePreviewIframe = document.getElementById('large-preview-iframe');
    const viewportActivePageLabel = document.getElementById('viewport-active-page-label');
    const viewportActiveStatusBadge = document.getElementById('viewport-active-status-badge');
    const viewportActions = document.getElementById('viewport-actions');
    const btnStateOriginal = document.getElementById('btn-state-original');
    const btnStateHtml = document.getElementById('btn-state-html');
    const btnStateTranslated = document.getElementById('btn-state-translated');

    const btnBackDashboard = document.getElementById('btn-back-dashboard');
    const btnOpenReaderGlobal = document.getElementById('btn-open-reader-global');
    const btnTranslateRemaining = document.getElementById('btn-translate-remaining');

    // Navigation triggers
    if (btnBackDashboard) {
        btnBackDashboard.addEventListener('click', () => {
            window.location.href = 'index.html';
        });
    }

    if (btnOpenReaderGlobal) {
        btnOpenReaderGlobal.addEventListener('click', () => {
            window.location.href = `reader.html?doc_id=${docId}`;
        });
    }

    // Fetch document metadata details (first time)
    const fetchDocMetadata = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/docs`);
            if (!res.ok) throw new Error('Không thể tải metadata từ backend.');
            const docs = await res.json();
            const doc = docs.find(d => d.id === docId);

            if (!doc) {
                showToast('Lỗi', `Không tìm thấy tài liệu ID: ${docId}`, 'error');
                setTimeout(() => { window.location.href = 'index.html'; }, 2000);
                return;
            }

            documentMetadata = doc;
            titleDocName.innerText = doc.filename;
            toolbarDocFilename.innerText = doc.filename;
            metaTotalPages.innerHTML = `<i class="fas fa-book-open"></i> ${doc.total_pages} trang`;
            metaDocStatus.innerHTML = `<i class="fas fa-info-circle"></i> Trạng thái: ${getStatusLabel(doc.status)}`;

            if (doc.status === 'compiled') {
                btnOpenReaderGlobal.style.display = 'inline-flex';
            }
        } catch (err) {
            console.error('Error fetching document metadata:', err);
            showToast('Lỗi', 'Không thể kết nối với máy chủ API.', 'error');
        }
    };

    // Main API retrieval function for individual pages
    const fetchPagesData = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/docs/${docId}/pages`);
            if (!res.ok) throw new Error('Không thể lấy danh sách trang.');
            const pages = await res.json();

            updatePagesUI(pages);
        } catch (err) {
            console.error('Error fetching pages:', err);
        }
    };

    // Update grid UI selectively based on changes
    const updatePagesUI = (pages) => {
        pagesDataStore = pages; // Cache globally for active details lookup

        if (pages.length === 0) {
            pagesGrid.innerHTML = `
                <div class="empty-pages-view">
                    <i class="fas fa-file-excel"></i>
                    <h3>Chưa trích xuất được cấu trúc trang</h3>
                    <p>Hãy chắc chắn tài liệu đã được bắt đầu trích xuất (status > raw).</p>
                </div>
            `;
            return;
        }

        // Remove empty state placeholder
        const emptyView = document.getElementById('empty-pages-view');
        if (emptyView) emptyView.remove();

        let translatedCount = 0;
        let hasRawPages = false;

        // Render immersive grid cards
        pages.forEach(page => {
            const pageNum = page.page_num;
            const status = page.status;
            
            if (status === 'compiled') {
                translatedCount++;
            }
            if (status === 'raw' || status === 'failed') {
                hasRawPages = true;
            }

            // Check if grid card exists, if not create it
            let card = document.getElementById(`page-card-${pageNum}`);
            const isNew = !card;

            if (isNew) {
                card = document.createElement('div');
                card.id = `page-card-${pageNum}`;
                card.className = 'page-card';
                card.dataset.pageNum = pageNum;
                pagesGrid.appendChild(card);
            }

            // Detect real status changes to avoid layout/iframe flash
            const cached = pageStatesCache[pageNum];
            const hasChanged = !cached || cached.status !== status || cached.has_original !== page.has_original;

            if (hasChanged) {
                // Update local cache
                pageStatesCache[pageNum] = {
                    status: status,
                    has_original: page.has_original,
                    has_translated: page.has_translated
                };

                // Render dynamic inner content
                renderCardContent(card, page);

                // Auto-Compile logic:
                if (status === 'translated') {
                    console.log(`[AutoCompile] Page ${pageNum} is translated. Launching LSE Compile background worker...`);
                    triggerCompilePage(pageNum, true); // silent background call
                }
            }
        });

        // Populate Left Sidebar with Mini page cards (if details view active or to keep in sync)
        renderSidebarPages(pages);

        // Populate or Update Active Viewport details
        updateActivePageViewport();

        // Update overall counters in toolbar
        if (metaTranslatedPages) {
            metaTranslatedPages.innerHTML = `<i class="fas fa-check-circle"></i> Đã dịch: ${translatedCount}/${pages.length}`;
        }

        // Enable or disable global action based on raw pages availability
        if (btnTranslateRemaining) {
            if (hasRawPages) {
                btnTranslateRemaining.disabled = false;
                btnTranslateRemaining.innerHTML = `<i class="fas fa-magic"></i> Dịch toàn bộ trang còn lại`;
            } else {
                btnTranslateRemaining.disabled = true;
                btnTranslateRemaining.innerHTML = `<i class="fas fa-check-double"></i> Đã dịch tất cả các trang`;
            }
        }
    };

    // Render left sidebar page listing dynamically
    const renderSidebarPages = (pages) => {
        pages.forEach(page => {
            const pageNum = page.page_num;
            const status = page.status;
            let item = document.getElementById(`sidebar-item-${pageNum}`);
            const isNew = !item;

            if (isNew) {
                item = document.createElement('div');
                item.id = `sidebar-item-${pageNum}`;
                item.className = 'sidebar-page-item';
                item.dataset.pageNum = pageNum;
                item.addEventListener('click', () => {
                    selectActivePage(pageNum);
                });
                workspaceSidebar.appendChild(item);
            }

            const cached = pageStatesCache[pageNum];
            const hasChanged = isNew || !cached || cached.status !== status || cached.has_original !== page.has_original;

            if (hasChanged) {
                renderSidebarItemContent(item, page);
            }

            // Sync active styling
            if (pageNum === activePageNum) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    };

    // Render inner content of mini sidebar card
    const renderSidebarItemContent = (item, page) => {
        const pageNum = page.page_num;
        const status = page.status;

        let thumbnailHTML = '';
        if (page.has_original) {
            thumbnailHTML = `
                <div class="mini-thumbnail-container">
                    <iframe class="mini-thumbnail-iframe" src="${API_BASE}/api/docs/${docId}/pages/${pageNum}?lang=en&raw=true" sandbox="allow-same-origin allow-scripts"></iframe>
                </div>
            `;
        } else {
            thumbnailHTML = `
                <div class="mini-thumbnail-container">
                    <div class="mini-thumbnail-placeholder">
                        <i class="far fa-file-pdf"></i>
                    </div>
                </div>
            `;
        }

        let dotClass = 'status-raw';
        let statusLabel = 'Chưa dịch';
        if (status === 'translating') { dotClass = 'status-translating'; statusLabel = 'Đang dịch'; }
        else if (status === 'translated') { dotClass = 'status-translated'; statusLabel = 'Đang tổng hợp'; }
        else if (status === 'compiling') { dotClass = 'status-compiling'; statusLabel = 'Đang biên dịch'; }
        else if (status === 'compiled') { dotClass = 'status-compiled'; statusLabel = 'Đã hoàn tất'; }
        else if (status === 'failed') { dotClass = 'status-failed'; statusLabel = 'Thất bại'; }

        item.innerHTML = `
            ${thumbnailHTML}
            <div class="page-info">
                <div class="page-title">Trang ${pageNum}</div>
                <div class="page-meta-row">
                    <span class="page-status-label">${statusLabel}</span>
                    <span class="page-status-dot ${dotClass}-dot" title="${statusLabel}"></span>
                </div>
            </div>
        `;
    };

    // Handle user page selection inside sidebar
    window.selectActivePage = (pageNum) => {
        if (activePageNum === pageNum) return;
        activePageNum = pageNum;
        
        // Fast UI feedback
        const items = workspaceSidebar.querySelectorAll('.sidebar-page-item');
        items.forEach(item => {
            if (parseInt(item.dataset.pageNum) === pageNum) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        updateActivePageViewport(true); // Force reload active viewport
    };

    // Update active viewport preview and interactive actions
    let lastLoadedIframeUrl = '';
    const updateActivePageViewport = (forceIframeLoad = false) => {
        if (pagesDataStore.length === 0) return;
        
        // Auto-select first page if none is currently active
        if (!activePageNum) {
            activePageNum = pagesDataStore[0].page_num;
        }

        const page = pagesDataStore.find(p => p.page_num === activePageNum);
        if (!page) return;

        // Render page title and detailed status badge
        if (viewportActivePageLabel) {
            viewportActivePageLabel.innerText = `Trang ${activePageNum}`;
        }
        
        const status = page.status;
        let badgeLabel = 'Chưa Dịch';
        let badgeClass = 'status-raw';
        let badgeIcon = 'fa-file-signature';

        if (status === 'translating') {
            badgeLabel = 'Đang dịch...';
            badgeClass = 'status-translating';
            badgeIcon = 'fa-spinner fa-spin';
        } else if (status === 'translated') {
            badgeLabel = 'Đang tổng hợp';
            badgeClass = 'status-translated';
            badgeIcon = 'fa-cogs';
        } else if (status === 'compiling') {
            badgeLabel = 'Đang biên dịch...';
            badgeClass = 'status-compiling';
            badgeIcon = 'fa-spinner fa-spin';
        } else if (status === 'compiled') {
            badgeLabel = 'Đã hoàn tất';
            badgeClass = 'status-compiled';
            badgeIcon = 'fa-check';
        } else if (status === 'failed') {
            badgeLabel = 'Thất bại';
            badgeClass = 'status-failed';
            badgeIcon = 'fa-exclamation-triangle';
        }

        if (viewportActiveStatusBadge) {
            viewportActiveStatusBadge.className = `status-badge ${badgeClass}`;
            viewportActiveStatusBadge.innerHTML = `<i class="fas ${badgeIcon}"></i> ${badgeLabel}`;
        }

        // Viewport State switcher options
        if (btnStateTranslated) {
            if (status === 'compiled') {
                btnStateTranslated.disabled = false;
                btnStateTranslated.style.opacity = '1';
                btnStateTranslated.style.cursor = 'pointer';
                btnStateTranslated.title = 'Xem trang đã dịch song ngữ';
            } else {
                if (viewportState === 'translated') {
                    viewportState = 'html'; // Fallback
                }
                btnStateTranslated.disabled = true;
                btnStateTranslated.style.opacity = '0.35';
                btnStateTranslated.style.cursor = 'not-allowed';
                btnStateTranslated.title = 'Bản dịch tiếng Việt chưa hoàn thiện.';
            }
        }

        // Sync active class across state buttons
        if (btnStateOriginal) btnStateOriginal.classList.toggle('active', viewportState === 'original');
        if (btnStateHtml) btnStateHtml.classList.toggle('active', viewportState === 'html');
        if (btnStateTranslated) btnStateTranslated.classList.toggle('active', viewportState === 'translated');

        // Load sandboxed iframe URL depending on selected State
        let iframeUrl = '';
        if (viewportState === 'original') {
            iframeUrl = `${API_BASE}/api/docs/${docId}/pdf?page=${activePageNum}`;
        } else if (viewportState === 'html') {
            iframeUrl = page.has_original ? `${API_BASE}/api/docs/${docId}/pages/${activePageNum}?lang=en&raw=true` : 'about:blank';
        } else if (viewportState === 'translated') {
            iframeUrl = page.has_translated ? `${API_BASE}/api/docs/${docId}/pages/${activePageNum}?lang=vi&raw=true` : 'about:blank';
        }

        // Retrieve dimensions from cache with default fallback (Portrait 900x1260)
        const dims = pageDimensionsCache[activePageNum] || { width: 900, height: 1260 };
        const container = document.getElementById('large-preview-container');
        const scaleFactor = 324 / dims.width;

        // Configure sandboxing, sizing, and styling dynamically to allow browser PDF plugins vs HTML
        if (largePreviewIframe) {
            if (viewportState === 'original') {
                largePreviewIframe.removeAttribute('sandbox');
                largePreviewIframe.classList.add('is-pdf');
                
                // Set absolute dimensions for the PDF container to fit the exact page ratio
                largePreviewIframe.style.width = '100%';
                largePreviewIframe.style.height = '100%';
                largePreviewIframe.style.transform = 'none';
            } else {
                largePreviewIframe.setAttribute('sandbox', 'allow-same-origin allow-scripts');
                largePreviewIframe.classList.remove('is-pdf');

                largePreviewIframe.style.width = `${dims.width}px`;
                largePreviewIframe.style.height = `${dims.height}px`;
                largePreviewIframe.style.transform = `scale(${scaleFactor})`;
            }

            if (container) {
                container.style.height = `${dims.height * scaleFactor}px`;
            }

            if (forceIframeLoad || lastLoadedIframeUrl !== iframeUrl) {
                largePreviewIframe.src = iframeUrl;
                lastLoadedIframeUrl = iframeUrl;
            }
        }

        // Dynamic footer action selection
        let actionBtnHTML = '';
        if (status === 'raw' || status === 'failed') {
            actionBtnHTML = `
                <button class="btn-page-action btn-translate" onclick="triggerTranslatePage(${activePageNum})">
                    <i class="fas fa-language"></i> Dịch Trang ${activePageNum} Ngay
                </button>
            `;
        } else if (status === 'translating') {
            actionBtnHTML = `
                <button class="btn-page-action btn-loading" disabled>
                    <i class="fas fa-spinner fa-spin"></i> Đang dịch...
                </button>
            `;
        } else if (status === 'translated') {
            actionBtnHTML = `
                <button class="btn-page-action btn-compile" onclick="triggerCompilePage(${activePageNum})">
                    <i class="fas fa-cogs"></i> Biên dịch Trang ${activePageNum}
                </button>
            `;
        } else if (status === 'compiling') {
            actionBtnHTML = `
                <button class="btn-page-action btn-loading" disabled>
                    <i class="fas fa-spinner fa-spin"></i> Đang biên dịch...
                </button>
            `;
        } else if (status === 'compiled') {
            actionBtnHTML = `
                <button class="btn-page-action btn-view" onclick="openReaderPage(${activePageNum})">
                    <i class="fas fa-book-reader"></i> Xem Trang ${activePageNum} Song Ngữ
                </button>
            `;
        }
        
        if (viewportActions) {
            viewportActions.innerHTML = actionBtnHTML;
        }
    };


    // Render inner content of page card
    const renderCardContent = (card, page) => {
        const pageNum = page.page_num;
        const status = page.status;
        
        let iframeHTML = '';
        if (page.has_original) {
            // High-fidelity micro-scaled original HTML in sandboxed iframe
            iframeHTML = `
                <div class="preview-frame-container">
                    <iframe class="preview-iframe" src="${API_BASE}/api/docs/${docId}/pages/${pageNum}?lang=en&raw=true" sandbox="allow-same-origin allow-scripts"></iframe>
                </div>
            `;
        } else {
            iframeHTML = `
                <div class="preview-frame-container">
                    <div class="preview-placeholder">
                        <i class="far fa-file-pdf"></i>
                        <span>Không có preview</span>
                    </div>
                </div>
            `;
        }

        let badgeLabel = 'Chưa Dịch';
        let badgeClass = 'status-raw';
        let badgeIcon = 'fa-file-signature';

        if (status === 'translating') {
            badgeLabel = 'Đang dịch...';
            badgeClass = 'status-translating';
            badgeIcon = 'fa-spinner fa-spin';
        } else if (status === 'translated') {
            badgeLabel = 'Đang tổng hợp';
            badgeClass = 'status-translated';
            badgeIcon = 'fa-cogs';
        } else if (status === 'compiling') {
            badgeLabel = 'Đang biên dịch...';
            badgeClass = 'status-compiling';
            badgeIcon = 'fa-spinner fa-spin';
        } else if (status === 'compiled') {
            badgeLabel = 'Đã hoàn tất';
            badgeClass = 'status-compiled';
            badgeIcon = 'fa-check';
        } else if (status === 'failed') {
            badgeLabel = 'Thất bại';
            badgeClass = 'status-failed';
            badgeIcon = 'fa-exclamation-triangle';
        }

        // Action button selection
        let actionBtnHTML = '';
        if (status === 'raw' || status === 'failed') {
            actionBtnHTML = `
                <button class="btn-page-action btn-translate" onclick="triggerTranslatePage(${pageNum})">
                    <i class="fas fa-language"></i> Dịch ngay
                </button>
            `;
        } else if (status === 'translating') {
            actionBtnHTML = `
                <button class="btn-page-action btn-loading" disabled>
                    <i class="fas fa-spinner fa-spin"></i> Đang dịch...
                </button>
            `;
        } else if (status === 'translated') {
            actionBtnHTML = `
                <button class="btn-page-action btn-compile" onclick="triggerCompilePage(${pageNum})">
                    <i class="fas fa-cogs"></i> Biên dịch
                </button>
            `;
        } else if (status === 'compiling') {
            actionBtnHTML = `
                <button class="btn-page-action btn-loading" disabled>
                    <i class="fas fa-spinner fa-spin"></i> Đang biên dịch...
                </button>
            `;
        } else if (status === 'compiled') {
            actionBtnHTML = `
                <button class="btn-page-action btn-view" onclick="openReaderPage(${pageNum})">
                    <i class="fas fa-book-reader"></i> Xem kết quả
                </button>
            `;
        }

        card.innerHTML = `
            <!-- Full card background iframe -->
            ${iframeHTML}
            
            <!-- Immersive corner tags -->
            <div class="page-badge-top-left">Trang ${pageNum}</div>
            <div class="page-badge-top-right ${badgeClass}-dot" title="${badgeLabel}">
                <i class="fas ${badgeIcon}"></i>
            </div>
            
            <!-- Glassmorphic Hover Overlay containing detailed states -->
            <div class="page-card-overlay">
                <div class="overlay-content">
                    <span class="status-badge ${badgeClass}">
                        <i class="fas ${badgeIcon}"></i> ${badgeLabel}
                    </span>
                    <div class="overlay-actions">
                        ${actionBtnHTML}
                    </div>
                </div>
            </div>
        `;
    };

    // Trigger individual page translation
    window.triggerTranslatePage = async (pageNum) => {
        try {
            const selectTargetLang = document.getElementById('select-target-lang');
            const targetLang = selectTargetLang ? selectTargetLang.value : 'vi';
            
            showToast('Tiến Trình', `Đang bắt đầu dịch Trang ${pageNum} sang ${getTargetLangName(targetLang)} qua Gemini AI...`, 'info');
            
            // Set temporary state locally to make interface immediately reactive under 100ms
            const card = document.getElementById(`page-card-${pageNum}`);
            if (card) {
                const badge = card.querySelector('.status-badge');
                if (badge) {
                    badge.className = 'status-badge status-translating';
                    badge.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang dịch...';
                }
                const btn = card.querySelector('.btn-page-action');
                if (btn) {
                    btn.className = 'btn-page-action btn-loading';
                    btn.disabled = true;
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang dịch...';
                }
            }

            const res = await fetch(`${API_BASE}/api/docs/${docId}/translate?async_mode=true`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ page_num: pageNum, target_lang: targetLang })
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Không thể bắt đầu dịch.');
            }

            // Immediate quick refresh
            await fetchPagesData();
        } catch (err) {
            showToast('Lỗi Dịch Thuật', err.message, 'error');
            await fetchPagesData();
        }
    };

    // Trigger LSE Compilation for a single page
    window.triggerCompilePage = async (pageNum, silent = false) => {
        try {
            if (!silent) {
                showToast('Tiến Trình', `Đang biên dịch Layout Shift Engine cho Trang ${pageNum}...`, 'info');
            }

            const res = await fetch(`${API_BASE}/api/docs/${docId}/compile?async_mode=true`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ page_num: pageNum })
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Không thể biên dịch.');
            }

            // Quick refresh
            await fetchPagesData();
        } catch (err) {
            console.error('Error compiling:', err);
            if (!silent) {
                showToast('Lỗi Biên Dịch', err.message, 'error');
            }
            await fetchPagesData();
        }
    };

    // Launch Reader at specific page
    window.openReaderPage = (pageNum) => {
        window.location.href = `reader.html?doc_id=${docId}&page=${pageNum}`;
    };

    // Translate all remaining raw pages concurrently
    btnTranslateRemaining.addEventListener('click', async () => {
        try {
            const selectTargetLang = document.getElementById('select-target-lang');
            const targetLang = selectTargetLang ? selectTargetLang.value : 'vi';
            
            btnTranslateRemaining.disabled = true;
            btnTranslateRemaining.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Đang gửi yêu cầu dịch thuật...`;

            // Identify all pages with 'raw' or 'failed' status
            const rawPages = Object.entries(pageStatesCache)
                .filter(([_, data]) => data.status === 'raw' || data.status === 'failed')
                .map(([pageNum, _]) => parseInt(pageNum));

            if (rawPages.length === 0) {
                showToast('Thông báo', 'Không còn trang nào chưa dịch.', 'info');
                return;
            }

            showToast('Tiến Trình', `Khởi chạy dịch song hành ${rawPages.length} trang sang ${getTargetLangName(targetLang)} trong nền...`, 'success');

            const promises = rawPages.map(page => 
                fetch(`${API_BASE}/api/docs/${docId}/translate?async_mode=true`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ page_num: page, target_lang: targetLang })
                })
            );

            await Promise.all(promises);
            showToast('Gửi Thành Công', 'Các luồng dịch đã khởi động. Vui lòng theo dõi tiến trình trực quan!', 'success');

            // Immediate quick refresh
            await fetchPagesData();
        } catch (err) {
            showToast('Lỗi Dịch Hàng Loạt', err.message, 'error');
            await fetchPagesData();
        }
    });

    // Helper function for user-friendly target language names
    const getTargetLangName = (code) => {
        const names = {
            'vi': 'Tiếng Việt',
            'en': 'Tiếng Anh',
            'zh': 'Tiếng Trung',
            'ja': 'Tiếng Nhật',
            'ko': 'Tiếng Hàn',
            'fr': 'Tiếng Pháp',
            'de': 'Tiếng Đức'
        };
        return names[code] || code;
    };

    // Helper functions for statuses labels
    const getStatusLabel = (status) => {
        const labels = {
            'raw': 'Nguyên Bản',
            'extracting': 'Đang Trích Xuất',
            'extracted': 'Đã Trích Xuất',
            'translating': 'Đang Dịch AI',
            'translated': 'Đã Dịch',
            'compiling': 'Đang Biên Dịch',
            'compiled': 'Sẵn Sàng',
            'failed': 'Thất Bại'
        };
        return labels[status] || status;
    };

    // Premium Toast Notifications System
    const showToast = (title, message, type = 'info') => {
        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        
        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        if (type === 'error') icon = 'fa-exclamation-triangle';

        toast.innerHTML = `
            <i class="fas ${icon} toast-icon"></i>
            <div>
                <h5 style="margin: 0; font-weight: 800; font-size: 0.9rem;">${title}</h5>
                <p style="margin: 0.15rem 0 0; font-size: 0.75rem; color: #94a3b8; line-height: 1.3;">${message}</p>
            </div>
        `;
        document.body.appendChild(toast);

        // Toast styles programmatically
        Object.assign(toast.style, {
            borderLeft: `4px solid ${type === 'success' ? 'var(--accent-emerald)' : type === 'error' ? 'var(--accent-red)' : 'var(--accent-blue)'}`,
        });

        const iconEl = toast.querySelector('.toast-icon');
        iconEl.style.fontSize = '1.4rem';
        iconEl.style.color = type === 'success' ? 'var(--accent-emerald)' : type === 'error' ? 'var(--accent-red)' : 'var(--accent-blue)';

        // Animate In
        setTimeout(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateY(0)';
        }, 10);

        // Animate Out
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    };

    // View Switcher controls
    const toggleViewMode = (mode) => {
        currentViewMode = mode;
        localStorage.setItem('preview_view_mode', mode);

        if (mode === 'grid') {
            if (btnViewGrid) btnViewGrid.classList.add('active');
            if (btnViewDetails) btnViewDetails.classList.remove('active');
            if (pagesGrid) pagesGrid.style.display = 'grid';
            if (detailsWorkspace) detailsWorkspace.style.display = 'none';
        } else {
            if (btnViewDetails) btnViewDetails.classList.add('active');
            if (btnViewGrid) btnViewGrid.classList.remove('active');
            if (pagesGrid) pagesGrid.style.display = 'none';
            if (detailsWorkspace) detailsWorkspace.style.display = 'flex';
            
            // Render active page immediately when entering details mode
            updateActivePageViewport(true);
        }
    };

    if (btnViewGrid) {
        btnViewGrid.addEventListener('click', () => toggleViewMode('grid'));
    }

    if (btnViewDetails) {
        btnViewDetails.addEventListener('click', () => toggleViewMode('details'));
    }

    // Viewport State switch triggers
    if (btnStateOriginal) {
        btnStateOriginal.addEventListener('click', () => {
            if (viewportState === 'original') return;
            viewportState = 'original';
            updateActivePageViewport(true); // force iframe load
        });
    }

    if (btnStateHtml) {
        btnStateHtml.addEventListener('click', () => {
            if (viewportState === 'html') return;
            viewportState = 'html';
            updateActivePageViewport(true); // force iframe load
        });
    }

    if (btnStateTranslated) {
        btnStateTranslated.addEventListener('click', () => {
            if (btnStateTranslated.disabled) return;
            if (viewportState === 'translated') return;
            viewportState = 'translated';
            updateActivePageViewport(true); // force iframe load
        });
    }

    // Listen for dynamic page dimensions from iframes to auto-scale layout perfectly
    window.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'page_size') {
            const { width, height, page_num } = event.data;
            console.log(`[Autoscale] Received dynamic dimensions for Page ${page_num}: ${width}x${height}`);

            // Cache dimensions for future page toggling and original view sync
            pageDimensionsCache[page_num] = { width, height };

            // 1. Scale Card Grid Iframe (if present)
            const cardFrame = document.querySelector(`#page-card-${page_num} .preview-iframe`);
            if (cardFrame) {
                cardFrame.style.width = `${width}px`;
                cardFrame.style.height = `${height}px`;
                cardFrame.style.transform = `scale(${162 / width})`;
            }

            // 2. Scale Sidebar Mini Thumbnail Iframe (if present)
            const sidebarFrame = document.querySelector(`#sidebar-item-${page_num} .mini-thumbnail-iframe`);
            if (sidebarFrame) {
                sidebarFrame.style.width = `${width}px`;
                sidebarFrame.style.height = `${height}px`;
                sidebarFrame.style.transform = `scale(${45 / width})`;
            }

            // 3. Scale Active Viewport Iframe (if active)
            if (activePageNum === page_num && largePreviewIframe) {
                const container = document.getElementById('large-preview-container');
                const scaleFactor = 324 / width;
                if (viewportState === 'original') {
                    largePreviewIframe.style.width = '100%';
                    largePreviewIframe.style.height = '100%';
                    largePreviewIframe.style.transform = 'none';
                } else {
                    largePreviewIframe.style.width = `${width}px`;
                    largePreviewIframe.style.height = `${height}px`;
                    largePreviewIframe.style.transform = `scale(${scaleFactor})`;
                }
                if (container) {
                    container.style.height = `${height * scaleFactor}px`;
                }
            }
        }
    });

    // Core Initialization
    const init = async () => {
        await fetchDocMetadata();
        await fetchPagesData();
        
        // Sync & toggle view mode on initial load
        toggleViewMode(currentViewMode);

        // Active 3-second real-time polling loop
        pollingInterval = setInterval(async () => {
            await fetchPagesData();
        }, 3000);
    };

    init();

    // Cleanup interval on page unload
    window.addEventListener('beforeunload', () => {
        if (pollingInterval) clearInterval(pollingInterval);
    });
});
