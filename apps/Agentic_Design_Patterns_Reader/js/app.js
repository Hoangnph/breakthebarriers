document.addEventListener('DOMContentLoaded', () => {
    // ==========================================================================
    // 1. UNIFIED STATE ARCHITECTURE
    // ==========================================================================
    const NATIVE_WIDTH = 918;
    const NATIVE_HEIGHT = 1188;

    const state = {
        currentPage: 1,
        totalPages: 482,
        currentZoom: 1.0,
        currentLang: 'en',
        sidebarCollapsed: false,
        searchQuery: '',
        fitMode: 'page', // 'width' | 'page' | 'custom'
        lastTransitionTime: 0
    };

    // Hardcoded Fallback Chapter Directory for 100% CORS-safe offline (file://) support
    const CHAPTERS_FALLBACK = [
        {
            "title": "Front Matter",
            "title_vi": "Phần mở đầu",
            "pages": [
                {"page": 1, "title": "Cover", "title_vi": "Trang bìa"},
                {"page": 2, "title": "Title Page", "title_vi": "Trang tên sách"},
                {"page": 3, "title": "Dedication", "title_vi": "Lời đề tặng"},
                {"page": 4, "title": "Acknowledgement", "title_vi": "Lời cảm ơn"},
                {"page": 7, "title": "Foreword", "title_vi": "Lời tựa"},
                {"page": 8, "title": "A Thought Leader's Perspective", "title_vi": "Góc nhìn của chuyên gia: Quyền lực và Trách nhiệm"},
                {"page": 10, "title": "Preface", "title_vi": "Lời nói đầu"},
                {"page": 12, "title": "Introduction", "title_vi": "Giới thiệu"},
                {"page": 14, "title": "What makes an AI system an \"agent\"?", "title_vi": "Điều gì tạo nên một hệ thống AI \"Tác nhân\"?"}
            ]
        },
        {
            "title": "Part One",
            "title_vi": "Phần Một",
            "pages": [
                {"page": 21, "title": "Part One: Core Patterns", "title_vi": "Phần Một: Các mẫu cốt lõi"},
                {"page": 23, "title": "Chapter 1: Prompt Chaining", "title_vi": "Chương 1: Chuỗi nhắc (Prompt Chaining)"},
                {"page": 36, "title": "Chapter 2: Routing", "title_vi": "Chương 2: Định tuyến (Routing)"},
                {"page": 50, "title": "Chapter 3: Parallelization", "title_vi": "Chương 3: Song song hóa (Parallelization)"},
                {"page": 65, "title": "Chapter 4: Reflection", "title_vi": "Chương 4: Tự phản hồi/Phản tỉnh (Reflection)"},
                {"page": 79, "title": "Chapter 5: Tool Use", "title_vi": "Chương 5: Sử dụng công cụ (Tool Use)"},
                {"page": 100, "title": "Chapter 6: Planning", "title_vi": "Chương 6: Lập kế hoạch (Planning)"},
                {"page": 113, "title": "Chapter 7: Multi-Agent Collaboration", "title_vi": "Chương 7: Cộng tác đa tác nhân (Multi-Agent)"}
            ]
        },
        {
            "title": "Part Two",
            "title_vi": "Phần Hai",
            "pages": [
                {"page": 130, "title": "Part Two: Memory & Adaptation", "title_vi": "Phần Hai: Bộ nhớ & Thích ứng"},
                {"page": 132, "title": "Chapter 8: Memory Management", "title_vi": "Chương 8: Quản lý bộ nhớ (Memory)"},
                {"page": 154, "title": "Chapter 9: Learning and Adaptation", "title_vi": "Chương 9: Học tập và Thích ứng (Learning)"},
                {"page": 167, "title": "Chapter 10: Model Context Protocol", "title_vi": "Chương 10: Giao thức ngữ cảnh mô hình (MCP)"},
                {"page": 183, "title": "Chapter 11: Goal Setting and Monitoring", "title_vi": "Chương 11: Thiết lập mục tiêu và Giám sát"}
            ]
        },
        {
            "title": "Part Three",
            "title_vi": "Phần Ba",
            "pages": [
                {"page": 195, "title": "Part Three: Interaction & Exception Patterns", "title_vi": "Phần Ba: Mẫu tương tác & Ngoại lệ"},
                {"page": 196, "title": "Chapter 12: Exception Handling and Recovery", "title_vi": "Chương 12: Xử lý ngoại lệ và Phục hồi"},
                {"page": 204, "title": "Chapter 13: Human-in-the-Loop", "title_vi": "Chương 13: Con người tham gia giám sát (HITL)"},
                {"page": 213, "title": "Chapter 14: Knowledge Retrieval (RAG)", "title_vi": "Chương 14: Truy xuất tri thức (RAG)"}
            ]
        },
        {
            "title": "Part Four",
            "title_vi": "Phần Bốn",
            "pages": [
                {"page": 230, "title": "Part Four: Advanced Communication & Guardrails", "title_vi": "Phần Bốn: Giao tiếp nâng cao & Rào chắn"},
                {"page": 231, "title": "Chapter 15: Inter-Agent Communication", "title_vi": "Chương 15: Giao tiếp giữa các tác nhân (A2A)"},
                {"page": 246, "title": "Chapter 16: Resource-Aware Optimization", "title_vi": "Chương 16: Tối ưu hóa nhận biết tài nguyên"},
                {"page": 262, "title": "Chapter 17: Reasoning Techniques", "title_vi": "Chương 17: Kỹ thuật lập luận (Reasoning)"},
                {"page": 286, "title": "Chapter 18: Guardrails/Safety Patterns", "title_vi": "Chương 18: Rào chắn bảo vệ và Mẫu an toàn"},
                {"page": 306, "title": "Chapter 19: Evaluation and Monitoring", "title_vi": "Chương 19: Đánh giá và Giám sát"},
                {"page": 325, "title": "Chapter 20: Prioritization", "title_vi": "Chương 20: Phân bổ thứ tự ưu tiên"},
                {"page": 335, "title": "Chapter 21: Exploration and Discovery", "title_vi": "Chương 21: Khám phá và Phát hiện"}
            ]
        },
        {
            "title": "Appendix & Back Matter",
            "title_vi": "Phụ lục & Phần kết",
            "pages": [
                {"page": 348, "title": "Appendix: Introduction to Prompting", "title_vi": "Phụ lục: Giới thiệu về Prompting"},
                {"page": 349, "title": "Appendix A: Advanced Prompting Techniques", "title_vi": "Phụ lục A: Kỹ thuật viết prompt nâng cao"},
                {"page": 378, "title": "Appendix B: AI Agentic Interactions (GUI to Real World)", "title_vi": "Phụ lục B: Tương tác tác nhân AI (GUI đến thực tế)"},
                {"page": 385, "title": "Appendix C: Quick overview of Agentic Frameworks", "title_vi": "Phụ lục C: Tổng quan nhanh về các khung tác nhân"},
                {"page": 393, "title": "Appendix D: Building an Agent with AgentSpace", "title_vi": "Phụ lục D: Xây dựng tác nhân với AgentSpace"},
                {"page": 399, "title": "Appendix E: AI Agents on the CLI", "title_vi": "Phụ lục E: Tác nhân AI trên dòng lệnh (CLI)"},
                {"page": 404, "title": "Appendix G: Coding Agents", "title_vi": "Phụ lục G: Tác nhân lập trình (Coding Agents)"},
                {"page": 416, "title": "Conclusion", "title_vi": "Kết luận"},
                {"page": 421, "title": "Glossary", "title_vi": "Thuật ngữ giải nghĩa"},
                {"page": 437, "title": "Index of Terms", "title_vi": "Chỉ mục từ khóa"}
            ]
        }
    ];

    let bookStructure = CHAPTERS_FALLBACK;

    // ==========================================================================
    // 2. DOM ELEMENT BINDINGS
    // ==========================================================================
    const sidebar = document.getElementById('sidebar');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar');
    const toggleSidebarGlobalBtn = document.getElementById('toggle-sidebar-btn');
    const tocContainer = document.getElementById('toc-container');
    const tocSearch = document.getElementById('toc-search');
    const clearSearchBtn = document.getElementById('clear-search');
    const pageFrame = document.getElementById('page-frame');
    const pageWrapper = document.getElementById('page-wrapper');
    const viewerContainer = document.getElementById('viewer-container');
    const toggleLangBtn = document.getElementById('toggle-lang');
    const currentLangText = document.getElementById('current-lang-text');
    const btnTheme = document.getElementById('toggle-theme');
    
    // Zoom Elements
    const btnZoomIn = document.getElementById('zoom-in');
    const btnZoomOut = document.getElementById('zoom-out');
    const btnFitWidth = document.getElementById('fit-width');
    const btnFitPage = document.getElementById('fit-page');
    const zoomLevelText = document.getElementById('zoom-level');
    
    // Pagination Elements
    const btnPrev = document.getElementById('prev-page');
    const btnNext = document.getElementById('next-page');
    const inputPage = document.getElementById('page-input');
    const textTotalPages = document.getElementById('total-pages');

    // ==========================================================================
    // 3. PERSISTENCE LAYER & STATE SYNCING
    // ==========================================================================
    function loadSavedState() {
        state.currentPage = parseInt(localStorage.getItem('adp_page')) || 1;
        state.currentZoom = parseFloat(localStorage.getItem('adp_zoom')) || 1.0;
        state.currentLang = localStorage.getItem('adp_lang') || 'en';
        state.sidebarCollapsed = localStorage.getItem('adp_sidebar_collapsed') === 'true';
        state.fitMode = localStorage.getItem('adp_fit_mode') || 'page';

        // Apply theme early
        const savedTheme = localStorage.getItem('adp_theme') || 'light';
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-mode');
            document.body.classList.remove('light-mode');
            const icon = btnTheme.querySelector('i');
            if (icon) icon.className = 'fas fa-sun';
        } else {
            document.body.classList.add('light-mode');
            document.body.classList.remove('dark-mode');
            const icon = btnTheme.querySelector('i');
            if (icon) icon.className = 'fas fa-moon';
        }

        // Apply language text
        currentLangText.textContent = state.currentLang.toUpperCase();

        // Apply sidebar state
        if (state.sidebarCollapsed) {
            sidebar.classList.add('collapsed');
        } else {
            sidebar.classList.remove('collapsed');
        }
    }

    function saveState() {
        localStorage.setItem('adp_page', state.currentPage);
        localStorage.setItem('adp_zoom', state.currentZoom);
        localStorage.setItem('adp_lang', state.currentLang);
        localStorage.setItem('adp_sidebar_collapsed', state.sidebarCollapsed);
        localStorage.setItem('adp_fit_mode', state.fitMode);
        localStorage.setItem('adp_theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light');
    }

    // ==========================================================================
    // 4. THEME & STYLING LOGIC
    // ==========================================================================
    function toggleTheme() {
        const isDark = document.body.classList.toggle('dark-mode');
        document.body.classList.toggle('light-mode', !isDark);
        
        const icon = btnTheme.querySelector('i');
        if (icon) {
            icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
        }
        
        saveState();
        injectStyleToIframe();
    }

    // Automatically wrap lines if they exceed page boundary and shift down subsequent absolute elements to prevent overlap
    function adjustIframeLayout(iframeDoc) {
        const PAGE_WIDTH = 918;
        
        // Find all absolute positioned divs
        const divs = Array.from(iframeDoc.querySelectorAll('div')).filter(div => {
            const style = div.getAttribute('style') || '';
            return style.includes('position:absolute') || style.includes('position: absolute');
        });
        
        if (divs.length === 0) return;
        
        // 1. Initialize data-original-top for all divs if not already set to ensure shifts don't accumulate infinitely on subsequent runs
        divs.forEach(div => {
            if (!div.hasAttribute('data-original-top')) {
                div.setAttribute('data-original-top', div.style.top || '0px');
            }
        });
        
        // 2. Sort divs by their initial top position
        divs.sort((a, b) => {
            const topA = parseFloat(a.getAttribute('data-original-top')) || 0;
            const topB = parseFloat(b.getAttribute('data-original-top')) || 0;
            return topA - topB;
        });
        
        let accumulatedShift = 0;
        
        divs.forEach(div => {
            const originalTop = parseFloat(div.getAttribute('data-original-top')) || 0;
            
            // Apply accumulated shift from previous elements
            const newTop = originalTop + accumulatedShift;
            div.style.top = `${newTop}px`;
            
            // Enable wrapping if it overflows
            const left = parseFloat(div.style.left) || 0;
            const rightMargin = Math.max(left, 80);
            const maxWidth = PAGE_WIDTH - left - rightMargin;
            
            // Only apply wrapping adjustments to text divs that are not tiny markers/page numbers
            if (maxWidth > 120 && div.textContent.trim().length > 3) {
                const nobr = div.querySelector('nobr');
                
                // A. Temporarily reset wrapping styles and remove maxWidth to measure true unwrapped height
                div.style.maxWidth = '';
                div.style.setProperty('white-space', 'nowrap', 'important');
                if (nobr) {
                    nobr.style.setProperty('white-space', 'nowrap', 'important');
                }
                
                const unwrappedHeight = div.getBoundingClientRect().height || 18;
                
                // B. Enable wrapping and apply maxWidth constraint
                div.style.maxWidth = `${maxWidth}px`;
                div.style.setProperty('white-space', 'normal', 'important');
                div.style.wordBreak = 'normal';
                div.style.wordWrap = 'break-word';
                div.style.overflowWrap = 'break-word';
                if (nobr) {
                    nobr.style.setProperty('white-space', 'normal', 'important');
                }
                
                // C. Measure wrapped height after reflow
                const wrappedHeight = div.getBoundingClientRect().height || 18;
                
                // D. Update the accumulated shift if the text wrapped and increased in height
                if (wrappedHeight - unwrappedHeight > 2) {
                    const extraHeight = Math.ceil(wrappedHeight - unwrappedHeight);
                    accumulatedShift += extraHeight;
                    console.log(`[ADP Reader] Wrapped element (top: ${originalTop}px): "${div.textContent.trim().substring(0, 30)}..." | Height: ${unwrappedHeight.toFixed(1)}px -> ${wrappedHeight.toFixed(1)}px | Shift increased by ${extraHeight}px to ${accumulatedShift}px`);
                }
            }
        });
    }

    // Safely apply styles inside iframe, falling back to CORS-safe parent filter
    function injectStyleToIframe() {
        const isDarkMode = document.body.classList.contains('dark-mode');
        
        try {
            const iframeDoc = pageFrame.contentDocument || pageFrame.contentWindow.document;
            if (!iframeDoc) throw new Error('No contentDocument');
            
            // Success: Remove any cors-fallback classes from iframe
            pageFrame.classList.remove('cors-fallback');
            
            // Handle active stylesheet injection
            let style = iframeDoc.getElementById('adp-injected-style');
            if (!style) {
                style = iframeDoc.createElement('style');
                style.id = 'adp-injected-style';
                iframeDoc.head.appendChild(style);
            }
            
            const letterSpacingOverride = state.currentLang === 'vi' ? `
                body * { 
                    letter-spacing: normal !important; 
                    word-spacing: normal !important; 
                }
            ` : '';
            
            style.textContent = `
                body { 
                    margin: 0; 
                    padding: 0; 
                    background-color: ${isDarkMode ? '#121212' : '#ffffff'} !important; 
                    color: ${isDarkMode ? '#e2e8f0' : '#0f172a'} !important; 
                    transition: background-color 0.3s ease, color 0.3s ease;
                }
                
                /* Invert background color blocks generated by converter */
                div[style*="background-color"], p[style*="background-color"], span[style*="background-color"] { 
                    background-color: transparent !important; 
                }
                
                body * { 
                    background-color: transparent !important; 
                    color: ${isDarkMode ? '#e2e8f0' : '#0f172a'} !important; 
                    border-color: ${isDarkMode ? '#334155' : '#e2e8f0'} !important; 
                }
                
                ${letterSpacingOverride}
                
                img { 
                    filter: ${isDarkMode ? 'brightness(0.85) contrast(1.15) invert(0)' : 'none'}; 
                    -ms-interpolation-mode: bicubic; 
                }
                
                /* Selection Style */
                ::selection {
                    background: ${isDarkMode ? '#38bdf840' : '#3b82f630'} !important;
                }

                /* Allow nobr tags to wrap normally inside absolute text blocks */
                nobr {
                    white-space: normal !important;
                }
            `;
            
            // Adjust local image path references
            const imgs = iframeDoc.querySelectorAll('img, IMG');
            imgs.forEach(img => {
                const src = img.getAttribute('src');
                if (src && src.includes('../images/')) {
                    img.src = src.replace('../images/', '../../data/images/');
                }
            });

            // Bind wheel and touch listeners inside the iframe for seamless scrolling
            iframeDoc.addEventListener('wheel', handleWheel, { passive: true });
            iframeDoc.addEventListener('touchstart', handleTouchStart, { passive: true });
            iframeDoc.addEventListener('touchmove', handleTouchMove, { passive: false });

            // Clear any pending layout adjustment timers to avoid race conditions
            if (pageFrame.layoutTimers) {
                pageFrame.layoutTimers.forEach(t => clearTimeout(t));
            }

            // Automatically wrap overflow text lines and shift vertical layout down with progressive layout-settle delays
            const runLayout = () => {
                try {
                    adjustIframeLayout(iframeDoc);
                } catch (err) {
                    console.warn('[ADP Reader] Failed to adjust iframe layout:', err);
                }
            };

            pageFrame.layoutTimers = [
                setTimeout(runLayout, 50),
                setTimeout(runLayout, 200),
                setTimeout(runLayout, 500),
                setTimeout(runLayout, 1000)
            ];
            
        } catch (e) {
            // CORS-blocked (file:// protocol): Apply robust hardware-accelerated parent filters instead!
            pageFrame.classList.add('cors-fallback');
        }
    }

    // ==========================================================================
    // 5. VIEWPORT NAVIGATION & ZOOM MANAGEMENT
    // ==========================================================================
    function loadPage(page, startAtBottom = false) {
        if (page < 1) page = 1;
        if (page > state.totalPages) page = state.totalPages;
        
        state.currentPage = page;
        inputPage.value = state.currentPage;
        
        const folder = state.currentLang === 'vi' ? 'pages_vi' : 'pages';
        let src = `data/${folder}/Agentic_Design_Patterns-${state.currentPage}.html`;
        if (window.location.protocol.startsWith('http')) {
            src += `?t=${Date.now()}`;
        }
        pageFrame.src = src;
        
        updateTOCActiveState();
        updatePaginationButtons();
        saveState();
        
        // Scroll to top or bottom
        if (startAtBottom) {
            setTimeout(() => {
                viewerContainer.scrollTop = viewerContainer.scrollHeight;
            }, 60);
        } else {
            viewerContainer.scrollTop = 0;
        }
    }

    function updatePaginationButtons() {
        btnPrev.disabled = state.currentPage <= 1;
        btnNext.disabled = state.currentPage >= state.totalPages;
    }

    function applyZoom() {
        // Calculate new wrapper layout dimensions
        const newWidth = NATIVE_WIDTH * state.currentZoom;
        const newHeight = NATIVE_HEIGHT * state.currentZoom;
        
        pageWrapper.style.width = `${newWidth}px`;
        pageWrapper.style.height = `${newHeight}px`;
        
        // Scale the inner document natively
        pageFrame.style.transform = `scale(${state.currentZoom})`;
        
        // Update label
        zoomLevelText.textContent = `${Math.round(state.currentZoom * 100)}%`;
        
        // Update Fit Button Active Highlights
        btnFitWidth.classList.toggle('active', state.fitMode === 'width');
        btnFitPage.classList.toggle('active', state.fitMode === 'page');
        
        saveState();
    }

    function handleZoomIn() {
        state.fitMode = 'custom';
        state.currentZoom += 0.1;
        if (state.currentZoom > 3.0) state.currentZoom = 3.0;
        applyZoom();
    }

    function handleZoomOut() {
        state.fitMode = 'custom';
        state.currentZoom -= 0.1;
        if (state.currentZoom < 0.2) state.currentZoom = 0.2;
        applyZoom();
    }

    function handleFitWidth() {
        state.fitMode = 'width';
        const clientWidth = viewerContainer.clientWidth - 48; // Padding offset
        if (clientWidth > 0) {
            state.currentZoom = clientWidth / NATIVE_WIDTH;
            if (state.currentZoom < 0.2) state.currentZoom = 0.2;
            if (state.currentZoom > 3.0) state.currentZoom = 3.0;
            applyZoom();
        }
    }

    function handleFitPage() {
        state.fitMode = 'page';
        const clientWidth = viewerContainer.clientWidth - 48;
        const clientHeight = viewerContainer.clientHeight - 48; // Padding offset
        if (clientWidth > 0 && clientHeight > 0) {
            const zoomWidth = clientWidth / NATIVE_WIDTH;
            const zoomHeight = clientHeight / NATIVE_HEIGHT;
            state.currentZoom = Math.min(zoomWidth, zoomHeight);
            if (state.currentZoom < 0.2) state.currentZoom = 0.2;
            if (state.currentZoom > 3.0) state.currentZoom = 3.0;
            applyZoom();
        }
    }

    function applyFitMode() {
        if (state.fitMode === 'width') {
            handleFitWidth();
        } else if (state.fitMode === 'page') {
            handleFitPage();
        } else {
            applyZoom();
        }
    }

    // ==========================================================================
    // 6. COLLAPSIBLE SEARCHABLE TABLE OF CONTENTS RENDERER
    // ==========================================================================
    async function initTOC() {
        try {
            const url = window.location.protocol.startsWith('http') ? `data/chapters.json?t=${Date.now()}` : 'data/chapters.json';
            const res = await fetch(url);
            if (res.ok) {
                bookStructure = await res.json();
            }
        } catch (e) {
            console.warn('Unable to load chapters.json via fetch, using rich local fallback structure.', e);
        }
        
        renderTOC();
        updateTOCActiveState();
    }

    function renderTOC() {
        tocContainer.innerHTML = '';
        
        bookStructure.forEach((part, partIdx) => {
            const partGroup = document.createElement('div');
            partGroup.className = 'toc-part-group';
            partGroup.id = `part-group-${partIdx}`;
            
            // Check if this part contains the active page to keep expanded
            let hasActivePage = false;
            part.pages.forEach(p => {
                if (p.page === state.currentPage) hasActivePage = true;
            });
            
            if (hasActivePage) {
                partGroup.classList.add('expanded');
            }
            
            const header = document.createElement('div');
            header.className = 'toc-part-header';
            
            const partTitleText = state.currentLang === 'vi' ? part.title_vi : part.title;
            
            header.innerHTML = `
                <span class="part-title">${partTitleText}</span>
                <i class="chevron fas fa-chevron-right"></i>
            `;
            
            const pagesContainer = document.createElement('div');
            pagesContainer.className = 'toc-part-pages';
            
            part.pages.forEach(item => {
                const link = document.createElement('a');
                link.className = 'toc-page-link';
                link.href = '#';
                link.dataset.page = item.page;
                
                const localizedPageTitle = state.currentLang === 'vi' ? item.title_vi : item.title;
                
                link.innerHTML = `
                    <span style="font-weight: 700; min-width: 32px; color: var(--primary); font-size: 11px;">p.${item.page}</span>
                    <span class="link-label" style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${localizedPageTitle}</span>
                `;
                
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    loadPage(item.page);
                    
                    if (window.innerWidth <= 768) {
                        sidebar.classList.remove('open');
                    }
                });
                
                pagesContainer.appendChild(link);
            });
            
            header.addEventListener('click', () => {
                const wasExpanded = partGroup.classList.contains('expanded');
                
                // If searching, let headers act as normal collapses
                partGroup.classList.toggle('expanded');
            });
            
            partGroup.appendChild(header);
            partGroup.appendChild(pagesContainer);
            tocContainer.appendChild(partGroup);
        });
    }

    function updateTOCActiveState() {
        const links = tocContainer.querySelectorAll('.toc-page-link');
        let activeLink = null;
        
        links.forEach(link => {
            const pageVal = parseInt(link.dataset.page);
            if (pageVal === state.currentPage) {
                link.classList.add('active');
                activeLink = link;
            } else {
                link.classList.remove('active');
            }
        });
        
        // Auto-expand the parent part group of the active page if not expanded
        if (activeLink) {
            const parentGroup = activeLink.closest('.toc-part-group');
            if (parentGroup && !parentGroup.classList.contains('expanded') && !state.searchQuery) {
                parentGroup.classList.add('expanded');
            }
            
            // Scroll active element into viewport smoothly
            activeLink.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    // Highly responsive text query filtering with highlight tags
    function handleTOCSearch(e) {
        const query = e.target.value.toLowerCase().trim();
        state.searchQuery = query;
        
        clearSearchBtn.style.display = query ? 'flex' : 'none';
        
        const partGroups = tocContainer.querySelectorAll('.toc-part-group');
        
        partGroups.forEach((group, partIdx) => {
            const links = group.querySelectorAll('.toc-page-link');
            let matchedInGroup = false;
            
            links.forEach(link => {
                const pageNumStr = link.dataset.page;
                const labelSpan = link.querySelector('.link-label');
                const originalItem = bookStructure[partIdx].pages.find(p => p.page == pageNumStr);
                const originalLabel = state.currentLang === 'vi' ? originalItem.title_vi : originalItem.title;
                
                const matchesText = originalLabel.toLowerCase().includes(query);
                const matchesPage = pageNumStr.includes(query);
                
                if (matchesText || matchesPage) {
                    link.style.display = 'flex';
                    matchedInGroup = true;
                    
                    // Highlight matching substring
                    if (query && matchesText) {
                        const regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
                        labelSpan.innerHTML = originalLabel.replace(regex, '<mark>$1</mark>');
                    } else {
                        labelSpan.textContent = originalLabel;
                    }
                } else {
                    link.style.display = 'none';
                }
            });
            
            if (matchedInGroup) {
                group.style.display = 'block';
                if (query) {
                    group.classList.add('expanded'); // Auto-expand matching groups
                }
            } else {
                if (query) {
                    group.style.display = 'none';
                } else {
                    group.style.display = 'block';
                    
                    // Restore expanded state only for active page parent when clearing search
                    let containsActive = false;
                    bookStructure[partIdx].pages.forEach(p => {
                        if (p.page === state.currentPage) containsActive = true;
                    });
                    group.classList.toggle('expanded', containsActive);
                }
            }
        });
    }

    function clearSearch() {
        tocSearch.value = '';
        state.searchQuery = '';
        clearSearchBtn.style.display = 'none';
        
        // Re-render/Reset list representation
        const partGroups = tocContainer.querySelectorAll('.toc-part-group');
        partGroups.forEach((group, partIdx) => {
            group.style.display = 'block';
            
            // Clean highlight markup
            const links = group.querySelectorAll('.toc-page-link');
            links.forEach(link => {
                link.style.display = 'flex';
                const pageNumStr = link.dataset.page;
                const labelSpan = link.querySelector('.link-label');
                const originalItem = bookStructure[partIdx].pages.find(p => p.page == pageNumStr);
                labelSpan.textContent = state.currentLang === 'vi' ? originalItem.title_vi : originalItem.title;
            });
            
            // Reset collapse to active parent only
            let containsActive = false;
            bookStructure[partIdx].pages.forEach(p => {
                if (p.page === state.currentPage) containsActive = true;
            });
            group.classList.toggle('expanded', containsActive);
        });
        
        updateTOCActiveState();
        tocSearch.focus();
    }

    function escapeRegExp(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // ==========================================================================
    // SEAMLESS PAGE SCROLL TRANSITIONS GESTURE HANDLERS
    // ==========================================================================
    let scrollAccumulator = 0;
    let lastScrollTime = Date.now();
    let touchStartY = 0;
    let touchTransitioned = false;

    function handleWheel(e) {
        const now = Date.now();
        if (now - lastScrollTime > 400) scrollAccumulator = 0;
        lastScrollTime = now;
        
        const deltaY = e.deltaY;
        const isScrollable = viewerContainer.scrollHeight - viewerContainer.clientHeight > 15;
        const isAtBottom = viewerContainer.scrollTop + viewerContainer.clientHeight >= viewerContainer.scrollHeight - 15;
        const isAtTop = viewerContainer.scrollTop <= 15;
        const cooldown = 1000;
        
        if (deltaY > 0) {
            if (isAtBottom || !isScrollable) {
                if (scrollAccumulator < 0) scrollAccumulator = 0;
                scrollAccumulator += deltaY;
                if (scrollAccumulator >= 120 && (now - state.lastTransitionTime > cooldown)) {
                    if (state.currentPage < state.totalPages) {
                        state.lastTransitionTime = now;
                        scrollAccumulator = 0;
                        loadPage(state.currentPage + 1, false);
                    }
                }
            }
        } else if (deltaY < 0) {
            if (isAtTop || !isScrollable) {
                if (scrollAccumulator > 0) scrollAccumulator = 0;
                scrollAccumulator += deltaY;
                if (scrollAccumulator <= -120 && (now - state.lastTransitionTime > cooldown)) {
                    if (state.currentPage > 1) {
                        state.lastTransitionTime = now;
                        scrollAccumulator = 0;
                        loadPage(state.currentPage - 1, true);
                    }
                }
            }
        }
    }

    function handleTouchStart(e) {
        if (e.touches && e.touches.length > 0) {
            touchStartY = e.touches[0].clientY;
            touchTransitioned = false;
        }
    }

    function handleTouchMove(e) {
        if (touchTransitioned || !e.touches || e.touches.length === 0) return;
        const clientY = e.touches[0].clientY;
        const deltaY = touchStartY - clientY;
        
        const isScrollable = viewerContainer.scrollHeight - viewerContainer.clientHeight > 15;
        const isAtBottom = viewerContainer.scrollTop + viewerContainer.clientHeight >= viewerContainer.scrollHeight - 15;
        const isAtTop = viewerContainer.scrollTop <= 15;
        const now = Date.now();
        const cooldown = 1000;
        
        if (deltaY > 80) {
            if ((isAtBottom || !isScrollable) && (now - state.lastTransitionTime > cooldown) && state.currentPage < state.totalPages) {
                touchTransitioned = true;
                state.lastTransitionTime = now;
                loadPage(state.currentPage + 1, false);
            }
        } else if (deltaY < -80) {
            if ((isAtTop || !isScrollable) && (now - state.lastTransitionTime > cooldown) && state.currentPage > 1) {
                touchTransitioned = true;
                state.lastTransitionTime = now;
                loadPage(state.currentPage - 1, true);
            }
        }
    }

    // ==========================================================================
    // 7. EVENT BINDING & HANDLERS
    // ==========================================================================
    function setupEventListeners() {
        // Seamless Page Transitions: Bind wheel and touch events to the viewer container
        viewerContainer.addEventListener('wheel', handleWheel, { passive: true });
        viewerContainer.addEventListener('touchstart', handleTouchStart, { passive: true });
        viewerContainer.addEventListener('touchmove', handleTouchMove, { passive: false });

        // Theme
        btnTheme.addEventListener('click', toggleTheme);
        
        // Sidebar Toggle Buttons (Desktop & Mobile)
        const handleSidebarToggle = () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle('open');
            } else {
                state.sidebarCollapsed = !state.sidebarCollapsed;
                sidebar.classList.toggle('collapsed', state.sidebarCollapsed);
                saveState();
                
                // Resize adjustment delay to allow style transitions (transition is 0.25s / 250ms)
                setTimeout(applyFitMode, 260);
            }
        };

        if (toggleSidebarGlobalBtn) {
            toggleSidebarGlobalBtn.addEventListener('click', handleSidebarToggle);
        }
        if (toggleSidebarBtn) {
            toggleSidebarBtn.addEventListener('click', handleSidebarToggle);
        }
        
        // Mobile Sidebar backdrop click close
        viewerContainer.addEventListener('click', () => {
            if (sidebar.classList.contains('open')) {
                sidebar.classList.remove('open');
            }
        });

        // Language Switcher
        toggleLangBtn.addEventListener('click', () => {
            state.currentLang = state.currentLang === 'en' ? 'vi' : 'en';
            currentLangText.textContent = state.currentLang.toUpperCase();
            
            // Full re-render TOC with new language locale strings
            renderTOC();
            loadPage(state.currentPage);
        });

        // Zoom Listeners
        btnZoomIn.addEventListener('click', handleZoomIn);
        btnZoomOut.addEventListener('click', handleZoomOut);
        btnFitWidth.addEventListener('click', handleFitWidth);
        btnFitPage.addEventListener('click', handleFitPage);

        // Pagination Listeners
        btnPrev.addEventListener('click', () => loadPage(state.currentPage - 1));
        btnNext.addEventListener('click', () => loadPage(state.currentPage + 1));
        
        inputPage.addEventListener('change', (e) => {
            const pageVal = parseInt(e.target.value);
            if (!isNaN(pageVal) && pageVal >= 1 && pageVal <= state.totalPages) {
                loadPage(pageVal);
            } else {
                inputPage.value = state.currentPage;
            }
        });
        
        // Search Listeners
        tocSearch.addEventListener('input', handleTOCSearch);
        clearSearchBtn.addEventListener('click', clearSearch);
        
        // Iframe Event Listener for styling and relative links hook
        pageFrame.addEventListener('load', injectStyleToIframe);
        
        // Window Resize hook to keep viewport fitting intact
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                applyFitMode();
            }, 100);
        });

        // Global Keyboard Shortcut Bindings
        window.addEventListener('keydown', (e) => {
            // Ignore keypresses inside inputs
            if (document.activeElement === tocSearch || document.activeElement === inputPage) {
                if (e.key === 'Escape') {
                    tocSearch.blur();
                    clearSearch();
                }
                return;
            }

            switch (e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    loadPage(state.currentPage - 1);
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    loadPage(state.currentPage + 1);
                    break;
                case '+':
                case '=':
                    e.preventDefault();
                    handleZoomIn();
                    break;
                case '-':
                case '_':
                    e.preventDefault();
                    handleZoomOut();
                    break;
                case 'Escape':
                    e.preventDefault();
                    sidebar.classList.remove('open');
                    clearSearch();
                    break;
            }
        });
    }

    // ==========================================================================
    // 8. CRITICAL RUNTIME INITIALIZATION
    // ==========================================================================
    loadSavedState();
    setupEventListeners();
    initTOC().then(() => {
        loadPage(state.currentPage);
        
        // Trigger responsive layout alignment matching fitMode
        setTimeout(applyFitMode, 250);
    });
});
