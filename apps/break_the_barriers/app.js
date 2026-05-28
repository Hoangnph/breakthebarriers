/* ==========================================================================
   Smart Documentations Dashboard - Core JavaScript
   Implements premium page micro-interactions, AJAX API client, polling logic,
   drag & drop uploaders, cascading deletions, and TM Editor Modal.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // ---------------------------------------------------------
    // Log Initialization message
    // ---------------------------------------------------------
    console.log("%cSmart Documentations Dashboard Active!", "color: #a855f7; font-size: 14px; font-weight: bold;");
    console.log("Environment: Full-Stack Integrated Client");
    console.log("Design Standards: TDD, YAGNI, DRY, UX-first");

    const API_BASE = 'http://localhost:8005';
    let pollingInterval = null;
    let activeTMDocId = null;

    // ---------------------------------------------------------
    // Interactive Module Card Highlights & Launch Actions
    // ---------------------------------------------------------
    const moduleCards = document.querySelectorAll('.module-card');
    moduleCards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const cardGlow = card.querySelector('.card-glow');
            if (cardGlow) {
                cardGlow.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(139, 92, 246, 0.15) 0%, transparent 60%)`;
            }
        });
    });

    const launchReaderBtn = document.getElementById('launch-reader-btn');
    if (launchReaderBtn) {
        launchReaderBtn.addEventListener('click', () => {
            const workspace = document.getElementById('workspace');
            if (workspace) {
                workspace.scrollIntoView({ behavior: 'smooth' });
                showNotification('Trình đọc Song ngữ', 'Hãy chọn một tài liệu đã biên dịch từ danh sách kệ sách bên dưới để bắt đầu đọc!', 'info');
            }
        });
    }

    const launchAiBtn = document.getElementById('launch-ai-btn');
    if (launchAiBtn) {
        launchAiBtn.addEventListener('click', () => {
            const workspace = document.getElementById('workspace');
            if (workspace) {
                workspace.scrollIntoView({ behavior: 'smooth' });
                showNotification('AI Smart Engine', 'Kéo thả hoặc chạm vào vùng upload để tải tệp PDF lên bắt đầu chuỗi số hóa thông minh!', 'success');
            }
        });
    }

    // ---------------------------------------------------------
    // Responsive Hamburger Menu Drawer Interaction Logic
    // ---------------------------------------------------------
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const navDrawer = document.getElementById('nav-drawer');
    const drawerOverlay = document.getElementById('drawer-overlay');
    const drawerCloseBtn = document.getElementById('drawer-close-btn');
    const drawerLinks = document.querySelectorAll('.drawer-link:not(.disabled)');

    const toggleDrawer = (forceState) => {
        const shouldActive = typeof forceState === 'boolean' ? forceState : !navDrawer.classList.contains('active');
        if (shouldActive) {
            hamburgerBtn.classList.add('active');
            navDrawer.classList.add('active');
            drawerOverlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        } else {
            hamburgerBtn.classList.remove('active');
            navDrawer.classList.remove('active');
            drawerOverlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    };

    if (hamburgerBtn) {
        hamburgerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleDrawer();
        });
    }
    if (drawerCloseBtn) drawerCloseBtn.addEventListener('click', () => toggleDrawer(false));
    if (drawerOverlay) drawerOverlay.addEventListener('click', () => toggleDrawer(false));
    drawerLinks.forEach(link => {
        link.addEventListener('click', () => toggleDrawer(false));
    });

    // ---------------------------------------------------------
    // Drag & Drop Uploader Integration
    // ---------------------------------------------------------
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const uploadProgressContainer = document.getElementById('upload-progress-container');
    const uploadProgressFill = document.getElementById('upload-progress-fill');
    const uploadProgressText = document.getElementById('upload-progress-text');

    if (dropzone && fileInput) {
        // Trigger file input dialog on tap
        dropzone.addEventListener('click', (e) => {
            if (e.target.closest('#upload-progress-container')) return;
            fileInput.click();
        });

        // Drag events
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
            }, false);
        });

        // Drop handler
        dropzone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                handleFileUpload(files[0]);
            }
        });

        // Input change handler
        fileInput.addEventListener('change', (e) => {
            const files = e.target.files;
            if (files.length > 0) {
                handleFileUpload(files[0]);
            }
        });
    }

    const handleFileUpload = async (file) => {
        if (file.type !== 'application/pdf' && !file.name.endsWith('.pdf')) {
            showNotification('Lỗi', 'Chỉ chấp nhận tệp định dạng PDF nguyên bản!', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        uploadProgressContainer.style.display = 'block';
        uploadProgressFill.style.width = '0%';
        uploadProgressText.innerText = 'Đang chuẩn bị tải lên...';

        try {
            // Simulated visual progress for premium look
            let prog = 0;
            const progressTimer = setInterval(() => {
                prog = Math.min(prog + 15, 90);
                uploadProgressFill.style.width = `${prog}%`;
                uploadProgressText.innerText = `Đang tải lên: ${prog}%`;
            }, 100);

            const res = await fetch(`${API_BASE}/api/docs/upload`, {
                method: 'POST',
                body: formData
            });

            clearInterval(progressTimer);

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Không thể tải lên tệp PDF.');
            }

            const docData = await res.json();
            uploadProgressFill.style.width = '100%';
            uploadProgressText.innerText = 'Tải lên hoàn tất 100%!';
            showNotification('Thành công', `Tải lên tệp ${file.name} thành công.`, 'success');

            setTimeout(() => {
                uploadProgressContainer.style.display = 'none';
            }, 1500);

            // Refresh document list and trigger extraction automatically
            await fetchDocuments();
            await triggerExtraction(docData.id);

        } catch (err) {
            uploadProgressContainer.style.display = 'none';
            showNotification('Lỗi Tải Lên', err.message, 'error');
        }
    };

    // ---------------------------------------------------------
    // Document Shelf Manager & Polling Engine
    // ---------------------------------------------------------
    const documentShelf = document.getElementById('document-shelf');
    const emptyShelfView = document.getElementById('empty-shelf-view');
    const docCountEl = document.getElementById('doc-count');
    const btnRefreshShelf = document.getElementById('btn-refresh-shelf');

    if (btnRefreshShelf) {
        btnRefreshShelf.addEventListener('click', async () => {
            btnRefreshShelf.querySelector('i').classList.add('fa-spin');
            await fetchDocuments();
            setTimeout(() => {
                btnRefreshShelf.querySelector('i').classList.remove('fa-spin');
            }, 500);
        });
    }

    const fetchDocuments = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/docs`);
            if (!res.ok) throw new Error('Không thể tải danh sách tài liệu.');
            const docs = await res.json();

            // Set document count
            if (docCountEl) docCountEl.innerText = docs.length;

            if (docs.length === 0) {
                documentShelf.innerHTML = '';
                documentShelf.appendChild(emptyShelfView);
                stopPolling();
                return;
            }

            // Remove empty view if populated
            if (documentShelf.contains(emptyShelfView)) {
                documentShelf.removeChild(emptyShelfView);
            }

            // Keep track of any active document doing background tasks
            let hasActiveTasks = false;

            // Render/Update cards
            const currentCards = Array.from(documentShelf.querySelectorAll('.doc-card'));
            const docIds = docs.map(d => d.id);

            // Remove deleted document cards
            currentCards.forEach(card => {
                if (!docIds.includes(card.dataset.id)) {
                    card.remove();
                }
            });

            docs.forEach(doc => {
                let card = documentShelf.querySelector(`.doc-card[data-id="${doc.id}"]`);
                const isNew = !card;

                if (isNew) {
                    card = document.createElement('div');
                    card.className = 'doc-card';
                    card.dataset.id = doc.id;
                }

                // Check active states
                if (['extracting', 'translating', 'compiling'].includes(doc.status)) {
                    hasActiveTasks = true;
                }

                const statusLabel = getStatusLabel(doc.status);
                const progressWidth = getProgressPercent(doc.status);

                // Actions buttons template based on current state
                let actionButtonsHTML = '';
                if (doc.status === 'raw' || doc.status === 'failed') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action btn-doc-primary" onclick="triggerExtraction('${doc.id}')">
                            <i class="fas fa-file-export"></i> Trích xuất
                        </button>
                    `;
                } else if (doc.status === 'extracted') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action btn-doc-primary" onclick="triggerTranslation('${doc.id}', ${doc.total_pages})">
                            <i class="fas fa-language"></i> Dịch Thuật AI
                        </button>
                        <button class="btn-doc-action" onclick="openPreview('${doc.id}')" style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: #cbd5e1; cursor: pointer;">
                            <i class="fas fa-eye"></i> Xem Trang
                        </button>
                    `;
                } else if (doc.status === 'translating') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action" disabled>
                            <i class="fas fa-spinner fa-spin"></i> Đang dịch...
                        </button>
                        <button class="btn-doc-action" onclick="openPreview('${doc.id}')" style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: #cbd5e1; cursor: pointer;">
                            <i class="fas fa-eye"></i> Xem Trang
                        </button>
                    `;
                } else if (doc.status === 'translated') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action btn-doc-primary" onclick="triggerCompilation('${doc.id}', ${doc.total_pages})">
                            <i class="fas fa-cogs"></i> Biên Dịch LSE
                        </button>
                        <button class="btn-doc-action" onclick="openPreview('${doc.id}')" style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: #cbd5e1; cursor: pointer;">
                            <i class="fas fa-eye"></i> Xem Trang
                        </button>
                    `;
                } else if (doc.status === 'compiling') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action" disabled>
                            <i class="fas fa-spinner fa-spin"></i> Đang biên dịch...
                        </button>
                        <button class="btn-doc-action" onclick="openPreview('${doc.id}')" style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: #cbd5e1; cursor: pointer;">
                            <i class="fas fa-eye"></i> Xem Trang
                        </button>
                    `;
                } else if (doc.status === 'compiled') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action btn-doc-primary" onclick="openReader('${doc.id}')">
                            <i class="fas fa-book-open"></i> Đọc Sách
                        </button>
                        <button class="btn-doc-action" onclick="openPreview('${doc.id}')" style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); color: #cbd5e1; cursor: pointer;">
                            <i class="fas fa-eye"></i> Xem Trang
                        </button>
                        <button class="btn-doc-action" onclick="openTMEditor('${doc.id}')">
                            <i class="fas fa-database"></i> Tra Bộ Nhớ
                        </button>
                    `;
                } else if (doc.status === 'extracting') {
                    actionButtonsHTML = `
                        <button class="btn-doc-action" disabled>
                            <i class="fas fa-spinner fa-spin"></i> Đang tách...
                        </button>
                    `;
                }

                card.innerHTML = `
                    <div class="doc-info">
                        <div class="doc-title-wrapper">
                            <i class="fas fa-file-pdf doc-icon"></i>
                            <div>
                                <h4 class="doc-title" title="${doc.filename}">${doc.filename}</h4>
                                <span class="doc-pages">${doc.total_pages > 0 ? doc.total_pages + ' trang' : 'Chờ phân tích'}</span>
                            </div>
                        </div>
                        <span class="doc-status-badge status-${doc.status}">${statusLabel}</span>
                    </div>
                    <div class="doc-progress">
                        <div class="doc-progress-bar">
                            <div class="doc-progress-fill ${doc.status}" style="width: ${progressWidth}%"></div>
                        </div>
                    </div>
                    <div class="doc-actions">
                        <div class="doc-buttons">
                            ${actionButtonsHTML}
                        </div>
                        <button class="btn-doc-delete" onclick="deleteDocument('${doc.id}')" title="Xóa tài liệu">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                `;

                if (isNew) {
                    documentShelf.appendChild(card);
                }
            });

            // Handle Polling State Transitions
            if (hasActiveTasks) {
                startPolling();
            } else {
                stopPolling();
            }

        } catch (err) {
            console.error('Error fetching shelf:', err);
        }
    };

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

    const getProgressPercent = (status) => {
        const percents = {
            'raw': 5,
            'extracting': 25,
            'extracted': 40,
            'translating': 65,
            'translated': 80,
            'compiling': 90,
            'compiled': 100,
            'failed': 100
        };
        return percents[status] || 0;
    };

    const startPolling = () => {
        if (pollingInterval) return;
        console.log("Starting 3-second background polling loop...");
        pollingInterval = setInterval(fetchDocuments, 3000);
    };

    const stopPolling = () => {
        if (!pollingInterval) return;
        console.log("All documents settled. Stopping polling loop.");
        clearInterval(pollingInterval);
        pollingInterval = null;
    };

    // ---------------------------------------------------------
    // Document Action Handlers (API Integrations)
    // ---------------------------------------------------------
    window.triggerExtraction = async (docId) => {
        try {
            const res = await fetch(`${API_BASE}/api/docs/${docId}/extract?async_mode=true`, { method: 'POST' });
            if (!res.ok) throw new Error('Không thể khởi chạy tiến trình trích xuất.');
            showNotification('Tiến Trình', 'Bắt đầu trích xuất cấu trúc trang PDF...', 'info');
            await fetchDocuments();
        } catch (err) {
            showNotification('Lỗi', err.message, 'error');
        }
    };

    window.triggerTranslation = async (docId, totalPages = 1) => {
        try {
            showNotification('Tiến Trình', `Bắt đầu gửi dữ liệu dịch tới Gemini AI cho tất cả ${totalPages} trang...`, 'info');
            
            // Loop and translate all pages concurrently in the background using async_mode=true
            const promises = [];
            for (let page = 1; page <= totalPages; page++) {
                promises.push(
                    fetch(`${API_BASE}/api/docs/${docId}/translate?async_mode=true`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ page_num: page, target_lang: 'vi' }),
                        mode: 'cors'
                    })
                );
            }
            
            await Promise.all(promises);
            await fetchDocuments();
        } catch (err) {
            showNotification('Lỗi', err.message, 'error');
        }
    };

    window.triggerCompilation = async (docId, totalPages = 1) => {
        try {
            showNotification('Tiến Trình', `Bắt đầu biên dịch Layout Shift Engine cho tất cả ${totalPages} trang...`, 'info');
            
            // Loop and compile all pages concurrently in the background using async_mode=true
            const promises = [];
            for (let page = 1; page <= totalPages; page++) {
                promises.push(
                    fetch(`${API_BASE}/api/docs/${docId}/compile?async_mode=true`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ page_num: page }),
                        mode: 'cors'
                    })
                );
            }
            
            await Promise.all(promises);
            await fetchDocuments();
        } catch (err) {
            showNotification('Lỗi', err.message, 'error');
        }
    };

    window.deleteDocument = async (docId) => {
        if (!confirm('Bạn có chắc chắn muốn xóa tài liệu này cùng tất cả dữ liệu số hóa liên quan?')) return;
        try {
            const res = await fetch(`${API_BASE}/api/docs/${docId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Không thể xóa tài liệu.');
            showNotification('Xóa Thành Công', 'Tài liệu đã được dọn sạch khỏi cơ sở dữ liệu và đĩa.', 'success');
            await fetchDocuments();
        } catch (err) {
            showNotification('Lỗi', err.message, 'error');
        }
    };

    window.openReader = (docId) => {
        window.location.href = `reader.html?doc_id=${docId}`;
    };

    window.openPreview = (docId) => {
        window.location.href = `preview.html?doc_id=${docId}`;
    };

    // ---------------------------------------------------------
    // TM Search & Editor Modal Functions
    // ---------------------------------------------------------
    const tmModal = document.getElementById('tm-modal');
    const tmModalCloseBtn = document.getElementById('tm-modal-close-btn');
    const tmSearchInput = document.getElementById('tm-search-input');
    const tmResultsList = document.getElementById('tm-results-list');
    const tmMatchCount = document.getElementById('tm-match-count');
    const tmSaveBtn = document.getElementById('tm-save-btn');

    let debounceTimer = null;
    let modifiedTranslations = {}; // { span_id: new_translation }

    window.openTMEditor = async (docId) => {
        activeTMDocId = docId;
        modifiedTranslations = {};
        if (tmSearchInput) tmSearchInput.value = '';
        if (tmSaveBtn) tmSaveBtn.style.display = 'none';
        
        // Initial load of first 10 translations
        await loadTranslations();
        if (tmModal) tmModal.classList.add('active');
    };

    const loadTranslations = async (query = '') => {
        if (!activeTMDocId) return;
        tmResultsList.innerHTML = `<div class="tm-no-results"><i class="fas fa-spinner fa-spin"></i> Đang tải dữ liệu bộ nhớ...</div>`;
        
        try {
            let url = `${API_BASE}/api/docs/${activeTMDocId}/translations`;
            if (query.trim()) {
                url = `${API_BASE}/api/docs/${activeTMDocId}/translations/search?query=${encodeURIComponent(query)}`;
            }

            const res = await fetch(url);
            if (!res.ok) throw new Error('Không thể tải bộ nhớ dịch thuật.');
            const items = await res.json();

            tmMatchCount.innerText = items.length;

            if (items.length === 0) {
                tmResultsList.innerHTML = `<div class="tm-no-results">Không tìm thấy cụm từ dịch thuật nào khớp với yêu cầu tìm kiếm.</div>`;
                return;
            }

            tmResultsList.innerHTML = '';
            items.forEach(item => {
                const row = document.createElement('div');
                row.className = 'tm-row';
                row.innerHTML = `
                    <div class="tm-field">
                        <span class="tm-label">Nguyên bản tiếng Anh (Page ${item.page_num})</span>
                        <div class="tm-text-en">${escapeHTML(item.original_text)}</div>
                    </div>
                    <div class="tm-field">
                        <span class="tm-label">Bản dịch tiếng Việt (Span ID: ${item.span_id})</span>
                        <textarea class="tm-input-vi" data-span-id="${item.span_id}" data-page-num="${item.page_num}">${escapeHTML(item.translated_text || '')}</textarea>
                    </div>
                `;

                // Handle edit changes
                const textarea = row.querySelector('.tm-input-vi');
                textarea.addEventListener('input', (e) => {
                    const spanId = e.target.dataset.spanId;
                    const val = e.target.value;
                    modifiedTranslations[spanId] = {
                        text: val,
                        page_num: parseInt(e.target.dataset.pageNum)
                    };
                    if (tmSaveBtn) tmSaveBtn.style.display = 'block';
                });

                tmResultsList.appendChild(row);
            });

        } catch (err) {
            tmResultsList.innerHTML = `<div class="tm-no-results text-red">Lỗi: ${err.message}</div>`;
        }
    };

    if (tmSearchInput) {
        tmSearchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                loadTranslations(e.target.value);
            }, 300);
        });
    }

    if (tmModalCloseBtn) {
        tmModalCloseBtn.addEventListener('click', () => {
            if (Object.keys(modifiedTranslations).length > 0) {
                if (!confirm('Bạn có thay đổi chưa lưu trong bộ nhớ dịch thuật. Bạn có muốn hủy bỏ?')) return;
            }
            tmModal.classList.remove('active');
            activeTMDocId = null;
        });
    }

    if (tmSaveBtn) {
        tmSaveBtn.addEventListener('click', async () => {
            if (!activeTMDocId) return;
            tmSaveBtn.disabled = true;
            tmSaveBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Đang lưu...`;

            try {
                const entries = Object.entries(modifiedTranslations);
                let savedCount = 0;
                const pagesToRecompile = new Set();

                for (const [spanId, item] of entries) {
                    const res = await fetch(`${API_BASE}/api/docs/${activeTMDocId}/translations/${spanId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ translated_text: item.text })
                    });
                    if (res.ok) {
                        savedCount++;
                        pagesToRecompile.add(item.page_num);
                    }
                }

                showNotification('Lưu Thành Công', `Đã lưu thành công ${savedCount} thay đổi dịch thuật vào CSDL.`, 'success');

                // Hot re-compile all affected pages
                for (const pageNum of pagesToRecompile) {
                    await fetch(`${API_BASE}/api/docs/${activeTMDocId}/compile`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ page_num: pageNum })
                    });
                }

                showNotification('Hot Re-compile', `Đã hoàn tất cập nhật trực tiếp trang HTML.`, 'info');
                
                // Clear state
                modifiedTranslations = {};
                tmSaveBtn.style.display = 'none';
                tmModal.classList.remove('active');
                
                // Refresh main page status
                await fetchDocuments();

            } catch (err) {
                showNotification('Lỗi khi lưu', err.message, 'error');
            } finally {
                tmSaveBtn.disabled = false;
                tmSaveBtn.innerHTML = `<i class="fas fa-save"></i> Lưu Thay Đổi`;
            }
        });
    }

    // Escape HTML helper
    const escapeHTML = (str) => {
        return str.replace(/[&<>'"]/g, 
            tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
        );
    };

    // ---------------------------------------------------------
    // Premium Toast Notifications
    // ---------------------------------------------------------
    const showNotification = (title, message, type = 'info') => {
        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        
        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        if (type === 'error') icon = 'fa-exclamation-triangle';

        toast.innerHTML = `
            <i class="fas ${icon} toast-icon"></i>
            <div>
                <h5>${title}</h5>
                <p>${message}</p>
            </div>
        `;
        document.body.appendChild(toast);

        // Styling Toast programmatically to prevent CSS file bloat
        Object.assign(toast.style, {
            position: 'fixed',
            bottom: '2rem',
            right: '2rem',
            background: 'rgba(13, 20, 38, 0.85)',
            borderLeft: `4px solid ${type === 'success' ? 'var(--accent-emerald)' : type === 'error' ? '#ef4444' : 'var(--accent-blue)'}`,
            borderTop: '1px solid var(--border-color)',
            borderRight: '1px solid var(--border-color)',
            borderBottom: '1px solid var(--border-color)',
            padding: '1rem 1.5rem',
            borderRadius: '12px',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
            backdropFilter: 'blur(10px)',
            zIndex: '99999',
            opacity: '0',
            transform: 'translateY(20px)',
            transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
            maxWidth: '350px'
        });

        const iconEl = toast.querySelector('.toast-icon');
        iconEl.style.fontSize = '1.5rem';
        iconEl.style.color = type === 'success' ? 'var(--accent-emerald)' : type === 'error' ? '#ef4444' : 'var(--accent-blue)';

        const h5 = toast.querySelector('h5');
        h5.style.fontWeight = '700';
        h5.style.fontSize = '0.9rem';
        h5.style.marginBottom = '0.15rem';

        const p = toast.querySelector('p');
        p.style.fontSize = '0.75rem';
        p.style.color = 'var(--text-secondary)';
        p.style.lineHeight = '1.3';

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

    // ---------------------------------------------------------
    // Initial Load
    // ---------------------------------------------------------
    fetchDocuments();
});

