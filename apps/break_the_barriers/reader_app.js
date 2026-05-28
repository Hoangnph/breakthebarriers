/* ==========================================================================
   Smart Reader Client Engine - reader_app.js
   Triển khai 3 giải thuật lõi: Touch Gesture Engine, Autoscale Engine, LSE & Font Shrink.
   Tích hợp AJAX polling, safe-area-insets, and Bilingual Overlay tooltip.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    console.log("%cSmart Reader Client Engine Active!", "color: #10b981; font-size: 14px; font-weight: bold;");

    const API_BASE = 'http://localhost:8005';
    
    // ---------------------------------------------------------
    // Khởi tạo các trạng thái mặc định (State management)
    // ---------------------------------------------------------
    const urlParams = new URLSearchParams(window.location.search);
    const docId = urlParams.get('doc_id');
    
    if (!docId) {
        console.error("Thiếu tham số doc_id trên URL, chuyển hướng về dashboard...");
        window.location.href = 'index.html';
        return;
    }

    let activePageNum = 1;
    let totalPages = 0;
    let zoomFactor = 1.0;
    let currentLang = 'vi'; // Mặc định hiển thị bản dịch tiếng Việt
    let currentTheme = 'dark'; // Mặc định HSL dark-first theme
    
    // Cache cục bộ chứa các span dịch thuật phục vụ Bilingual Overlay
    let translationsCache = {}; // { spanId: { en: "English text", vi: "Bản dịch" } }
    
    // Dynamic page dimensions
    let activePageWidth = 900;
    let activePageHeight = 1260;

    // ---------------------------------------------------------
    // Tham chiếu các phần tử DOM quan trọng
    // ---------------------------------------------------------
    const container = document.getElementById('reader-container');
    const card = document.getElementById('active-page-card');
    const wrapper = document.getElementById('flip-book-wrapper');
    const iframe = document.getElementById('reader-iframe');
    
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const navDrawer = document.getElementById('nav-drawer');
    const drawerOverlay = document.getElementById('drawer-overlay');
    const drawerCloseBtn = document.getElementById('drawer-close-btn');
    const tocList = document.getElementById('toc-list');
    
    const zoomInBtn = document.getElementById('zoom-in');
    const zoomOutBtn = document.getElementById('zoom-out');
    const zoomPercent = document.getElementById('zoom-percent');
    
    const btnBack = document.getElementById('btn-back');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    
    const themeButtons = document.querySelectorAll('.theme-btn');
    const modeButtons = document.querySelectorAll('.mode-btn');

    // ---------------------------------------------------------
    // 1. Thuật toán Autoscale Engine & Responsive Iframe
    // ---------------------------------------------------------
    const autoScale = () => {
        if (!container || !card || !wrapper) return;
        
        const viewportWidth = container.clientWidth;
        const viewportHeight = container.clientHeight;
        
        // Để lại khoảng đệm an toàn 48px (24px mỗi bên) trên thiết bị di động
        const targetWidth = viewportWidth - 48;
        const targetHeight = viewportHeight - 48;
        
        const canonicalWidth = activePageWidth;
        const canonicalHeight = activePageHeight;
        
        const scaleX = targetWidth / canonicalWidth;
        const scaleY = targetHeight / canonicalHeight;
        
        // Co dãn đồng đều để vừa khít cả chiều rộng và chiều cao màn hình
        const scaleFactor = Math.min(scaleX, scaleY);
        
        // Giới hạn scaleFactor tối đa 1.5 và tối thiểu 0.2 tránh vỡ nét chữ
        const baseScale = Math.max(0.2, Math.min(1.5, scaleFactor));
        
        // Kết hợp với zoomFactor thủ công do người dùng điều khiển
        const combinedScale = baseScale * zoomFactor;
        
        // Áp dụng transform cho card chứa iframe
        card.style.transform = `scale(${combinedScale})`;
        card.style.transformOrigin = 'center center';
        
        // Đồng bộ kích thước của wrapper bao ngoài để tránh hiện tượng mất thanh cuộn hoặc che khuất
        wrapper.style.width = `${canonicalWidth * combinedScale}px`;
        wrapper.style.height = `${canonicalHeight * combinedScale}px`;
        
        console.log(`[AutoScale] viewport: ${viewportWidth}x${viewportHeight}, scale kết hợp: ${combinedScale.toFixed(2)}`);
    };

    // Đăng ký sự kiện resize tự động co dãn màn hình
    window.addEventListener('resize', autoScale);

    // Listen for dynamic page size from child iframe to auto-scale landscape/portrait correctly
    window.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'page_size') {
            const { width, height, page_num } = event.data;
            if (page_num === activePageNum) {
                console.log(`[Autoscale] Reader detected page dimensions: ${width}x${height}`);
                activePageWidth = width;
                activePageHeight = height;
                autoScale();
            }
        }
    });

    // ---------------------------------------------------------
    // 2. Thuật toán Touch Gesture Engine & Hoạt cảnh 3D
    // ---------------------------------------------------------
    let touchStartX = 0;
    let touchStartY = 0;

    const handleTouchStart = (e) => {
        const touch = e.touches[0] || e.changedTouches[0];
        touchStartX = touch.screenX;
        touchStartY = touch.screenY;
    };

    const handleTouchEnd = (e) => {
        const touch = e.touches[0] || e.changedTouches[0];
        const touchEndX = touch.screenX;
        const touchEndY = touch.screenY;
        
        const deltaX = touchEndX - touchStartX;
        const deltaY = touchEndY - touchStartY;
        
        const absX = Math.abs(deltaX);
        const absY = Math.abs(deltaY);
        
        // Lật trang vuốt chạm di động nếu vuốt ngang tối thiểu 80px và gấp đôi chiều dọc
        if (absX > 80 && absX > 2 * absY) {
            if (deltaX < 0) {
                nextPage();
            } else {
                prevPage();
            }
        }
    };

    // Ràng buộc sự kiện chạm vuốt lên một cửa sổ tài liệu (cả parent và iframe)
    const bindTouchEvents = (targetDoc) => {
        if (!targetDoc) return;
        targetDoc.removeEventListener('touchstart', handleTouchStart);
        targetDoc.removeEventListener('touchend', handleTouchEnd);
        
        targetDoc.addEventListener('touchstart', handleTouchStart, { passive: true });
        targetDoc.addEventListener('touchend', handleTouchEnd, { passive: true });
    };

    // Tạo hiệu ứng lật trang 3D xoay trục Y mượt mà dưới 150ms
    const animateAndChangePage = (direction, action) => {
        if (!card) {
            action();
            return;
        }
        
        const animationClass = direction === 'next' ? 'flip-next' : 'flip-prev';
        card.classList.add(animationClass);
        
        // Thời gian xoay lật 140ms (phù hợp đặc tả < 150ms)
        setTimeout(() => {
            action();
            card.classList.remove(animationClass);
        }, 140);
    };

    // ---------------------------------------------------------
    // 3. Thuật toán LSE & Font Shrink (Xử lý dồn đè dòng tuyệt đối)
    // ---------------------------------------------------------
    const runPageLayoutCorrection = (iframeDoc) => {
        const spans = Array.from(iframeDoc.querySelectorAll('span'));
        if (spans.length === 0) return;
        
        console.log(`[LSE & FontShrink] Đang hiệu chỉnh bố cục cho ${spans.length} spans...`);
        
        // Giai đoạn 3.1: Sao lưu trạng thái gốc ban đầu (Baseline Recovery)
        spans.forEach(span => {
            if (!span.hasAttribute('data-orig-top')) {
                const origTop = parseFloat(span.style.top) || 0;
                span.setAttribute('data-orig-top', origTop);
            }
            if (!span.hasAttribute('data-orig-font-size')) {
                const computedStyle = iframeDoc.defaultView.getComputedStyle(span);
                const origFontSize = computedStyle.fontSize || '16px';
                span.setAttribute('data-orig-font-size', origFontSize);
            }
        });
        
        // Giai đoạn 3.2: Dynamic Font Shrink (Tự động co kích cỡ chữ chống tràn trang)
        // Canvas chiều rộng giới hạn chuẩn 900px
        const canvasWidthLimit = 900;
        
        spans.forEach(span => {
            // Phục hồi font size gốc trước khi tính toán co dãn
            span.style.fontSize = span.getAttribute('data-orig-font-size');
            
            const leftCoord = parseFloat(span.style.left) || 0;
            const rect = span.getBoundingClientRect();
            // Nếu bounding rect rỗng (do chưa render), tính gần đúng theo độ dài chuỗi ký tự
            const spanWidth = rect.width || (span.textContent.length * 8);
            const rightCoord = leftCoord + spanWidth;
            
            if (rightCoord > canvasWidthLimit) {
                const spaceAvailable = canvasWidthLimit - leftCoord;
                if (spaceAvailable > 0) {
                    const ratio = spaceAvailable / spanWidth;
                    // Giới hạn tỉ lệ co rút tối thiểu là 0.75 (75% font size gốc) theo Giai đoạn 5 spec
                    const shrinkFactor = Math.max(0.75, Math.min(1.0, ratio));
                    const origFontSizeVal = parseFloat(span.getAttribute('data-orig-font-size'));
                    span.style.fontSize = `${origFontSizeVal * shrinkFactor}px`;
                    console.log(`[FontShrink] Span #${span.id} tràn biên (${rightCoord.toFixed(1)}px). Co xuống: ${(shrinkFactor*100).toFixed(0)}%`);
                }
            }
        });
        
        // Giai đoạn 3.3: Layout Shift Engine (LSE - Tịnh tiến tọa độ dọc)
        // Gom nhóm các spans nằm cùng hàng ngang (Y-threshold < 5px)
        const rows = [];
        spans.forEach(span => {
            const origTop = parseFloat(span.getAttribute('data-orig-top'));
            
            let foundRow = rows.find(r => Math.abs(r.avgTop - origTop) < 5);
            if (foundRow) {
                foundRow.spans.push(span);
                // Cập nhật lại tọa độ Y trung bình của hàng
                const sum = foundRow.spans.reduce((acc, s) => acc + parseFloat(s.getAttribute('data-orig-top')), 0);
                foundRow.avgTop = sum / foundRow.spans.length;
            } else {
                rows.push({
                    avgTop: origTop,
                    spans: [span]
                });
            }
        });
        
        // Sắp xếp các hàng từ trên xuống dưới
        rows.sort((a, b) => a.avgTop - b.avgTop);
        
        let accumulatedShift = 0;
        
        rows.forEach(row => {
            // Tịnh tiến tọa độ của tất cả các spans thuộc hàng này
            row.spans.forEach(span => {
                const origTop = parseFloat(span.getAttribute('data-orig-top'));
                const newTop = origTop + accumulatedShift;
                span.style.top = `${newTop}px`;
            });
            
            // Đo mức độ dồn dòng thực tế (chiều cao nở ra) của hàng này
            let maxRowExpansion = 0;
            row.spans.forEach(span => {
                const computedStyle = iframeDoc.defaultView.getComputedStyle(span);
                const fontSize = parseFloat(computedStyle.fontSize) || 16;
                const singleLineHeight = fontSize * 1.4; // Chiều cao chuẩn 1 dòng đơn
                
                const actualHeight = span.offsetHeight || span.getBoundingClientRect().height;
                
                // Nếu chiều cao thực tế lớn hơn 1.5 lần font-size, nghĩa là span bị xuống dòng
                if (actualHeight > fontSize * 1.5) {
                    const expansion = actualHeight - singleLineHeight;
                    if (expansion > maxRowExpansion) {
                        maxRowExpansion = expansion;
                    }
                }
            });
            
            // Cộng dồn độ giãn của hàng này vào accumulatedShift để đẩy tất cả các hàng phía dưới xuống
            accumulatedShift += maxRowExpansion;
        });
        
        if (accumulatedShift > 0) {
            console.log(`[LSE] Đã tịnh tiến chống chồng chữ thành công. Tổng dịch chuyển dọc tích lũy: ${accumulatedShift.toFixed(1)}px`);
        }
    };

    // ---------------------------------------------------------
    // 4. Bilingual Overlay Tooltip Engine (Song ngữ song hành)
    // ---------------------------------------------------------
    const applyBilingualOverlay = (iframeDoc) => {
        // Khởi tạo/Tìm tooltip popup glassmorphic duy nhất trong iframe
        let tooltip = iframeDoc.getElementById('bilingual-tooltip');
        if (!tooltip) {
            tooltip = iframeDoc.createElement('div');
            tooltip.id = 'bilingual-tooltip';
            tooltip.className = 'bilingual-tooltip';
            iframeDoc.body.appendChild(tooltip);
        }
        
        // Nhúng stylesheet tạo giao diện tooltip
        const styleId = 'bilingual-tooltip-style';
        let style = iframeDoc.getElementById(styleId);
        if (!style) {
            style = iframeDoc.createElement('style');
            style.id = styleId;
            style.textContent = `
                .bilingual-tooltip {
                    position: absolute;
                    background: rgba(13, 20, 38, 0.96) !important;
                    border: 1px solid rgba(255, 255, 255, 0.1) !important;
                    color: #ffffff !important;
                    padding: 0.6rem 0.9rem !important;
                    border-radius: 8px !important;
                    font-size: 0.8rem !important;
                    line-height: 1.4 !important;
                    font-family: 'Inter', system-ui, sans-serif !important;
                    z-index: 100000 !important;
                    max-width: 320px !important;
                    pointer-events: none !important;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4) !important;
                    backdrop-filter: blur(10px) !important;
                    -webkit-backdrop-filter: blur(10px) !important;
                    opacity: 0;
                    transform: translateY(5px);
                    transition: opacity 0.2s ease, transform 0.2s ease;
                }
                .bilingual-tooltip.visible {
                    opacity: 1 !important;
                    transform: translateY(0) !important;
                }
                span.bilingual-hover-target {
                    border-bottom: 1.5px dashed #a855f7 !important; /* Dấu gạch chân chấm tím thanh lịch */
                    cursor: help !important;
                    transition: background-color 0.2s ease;
                }
                span.bilingual-hover-target:hover {
                    background-color: rgba(168, 85, 247, 0.08) !important;
                }
            `;
            iframeDoc.head.appendChild(style);
        }
        
        // Ràng buộc sự kiện di chuột cho từng span
        const spans = iframeDoc.querySelectorAll('span');
        let boundCount = 0;
        
        spans.forEach(span => {
            const spanId = span.id;
            if (spanId && translationsCache[spanId]) {
                const englishText = translationsCache[spanId].en;
                
                span.classList.add('bilingual-hover-target');
                boundCount++;
                
                span.addEventListener('mouseenter', () => {
                    tooltip.textContent = englishText;
                    tooltip.classList.add('visible');
                    
                    const rect = span.getBoundingClientRect();
                    const scrollTop = iframeDoc.documentElement.scrollTop || iframeDoc.body.scrollTop;
                    const scrollLeft = iframeDoc.documentElement.scrollLeft || iframeDoc.body.scrollLeft;
                    
                    // Định vị tooltip ngay bên trên span được hover
                    const x = rect.left + scrollLeft + (rect.width / 2);
                    const y = rect.top + scrollTop - 10;
                    
                    tooltip.style.left = `${x}px`;
                    tooltip.style.top = `${y}px`;
                    tooltip.style.transform = 'translate(-50%, -100%)';
                });
                
                span.addEventListener('mouseleave', () => {
                    tooltip.classList.remove('visible');
                });
            }
        });
        
        console.log(`[Bilingual] Đã kích hoạt tooltip song hành cho ${boundCount}/${spans.length} spans.`);
    };

    // ---------------------------------------------------------
    // 5. Đồng bộ Giao diện Theme trong Iframe
    // ---------------------------------------------------------
    const applyThemeToIframe = (iframeDoc) => {
        const existingStyle = iframeDoc.getElementById('reader-theme-style');
        if (existingStyle) existingStyle.remove();
        
        const style = iframeDoc.createElement('style');
        style.id = 'reader-theme-style';
        
        let bg, text;
        if (currentTheme === 'dark') {
            bg = '#070b15';
            text = '#f8fafc';
        } else if (currentTheme === 'light') {
            bg = '#ffffff';
            text = '#0f172a';
        } else if (currentTheme === 'sepia') {
            bg = '#f4ecd8';
            text = '#433422';
        }
        
        style.textContent = `
            html, body {
                background-color: ${bg} !important;
                color: ${text} !important;
                transition: background-color 0.3s ease, color 0.3s ease;
            }
            span {
                color: ${text} !important;
            }
        `;
        iframeDoc.head.appendChild(style);
    };

    // ---------------------------------------------------------
    // 6. Quy trình AJAX Tải trang & Quản lý vòng đời trang sách
    // ---------------------------------------------------------
    const loadPageContent = async (pageNum) => {
        if (!docId) return;
        
        // Trong chế độ song ngữ (bilingual), ta tải bản gốc việt ngữ đã biên dịch (vi),
        // và tiêm các tooltips tiếng anh vào client-side.
        const fetchLang = currentLang === 'bilingual' ? 'vi' : currentLang;
        
        try {
            const url = `${API_BASE}/api/docs/${docId}/pages/${pageNum}?lang=${fetchLang}`;
            const res = await fetch(url);
            if (!res.ok) throw new Error(`Không thể nạp nội dung trang ${pageNum} từ máy chủ.`);
            
            const data = await res.json();
            const htmlContent = data.html;
            
            // Thực hiện ghi tài liệu trực tiếp vào Sandboxed Iframe
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            iframeDoc.open();
            iframeDoc.write(htmlContent);
            iframeDoc.close();
            
            // Lần lượt áp dụng các Interactive Engines và hiệu chỉnh sau khi DOM tải xong
            applyThemeToIframe(iframeDoc);
            runPageLayoutCorrection(iframeDoc);
            bindTouchEvents(iframeDoc);
            
            if (currentLang === 'bilingual') {
                applyBilingualOverlay(iframeDoc);
            }
            
            // Cập nhật thanh tiến trình và bộ đếm trang
            updateProgress();
            
        } catch (err) {
            console.error('[LoadPageError]', err);
            // Hiển thị panel thông báo lỗi sang trọng bên trong iframe nếu tải thất bại
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            iframeDoc.open();
            iframeDoc.write(`
                <html>
                <head>
                    <style>
                        body {
                            background-color: #070b15;
                            color: #ffffff;
                            font-family: 'Inter', sans-serif;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                            text-align: center;
                        }
                        .error-card {
                            background: rgba(255, 255, 255, 0.05);
                            border: 1px solid rgba(255, 255, 255, 0.1);
                            padding: 2.5rem;
                            border-radius: 16px;
                            max-width: 80%;
                            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                            backdrop-filter: blur(10px);
                        }
                        h3 { color: #ef4444; margin-top: 0; font-size: 1.3rem; }
                        p { color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin: 0.5rem 0 1.5rem; }
                        .retry-btn {
                            background: #3b82f6;
                            border: none;
                            color: white;
                            padding: 0.6rem 1.5rem;
                            border-radius: 8px;
                            font-weight: 600;
                            cursor: pointer;
                            transition: background 0.2s ease;
                        }
                        .retry-btn:hover { background: #2563eb; }
                    </style>
                </head>
                <body>
                    <div class="error-card">
                        <h3>Lỗi Truy Tải Trang Sách</h3>
                        <p>${err.message}</p>
                        <button class="retry-btn" onclick="window.parent.location.reload()">Thử lại toàn bộ</button>
                    </div>
                </body>
                </html>
            `);
            iframeDoc.close();
        }
    };

    const loadPage = (pageNum) => {
        if (pageNum < 1 || pageNum > totalPages) return;
        
        activePageNum = pageNum;
        updateActiveTOCItem();
        loadPageContent(pageNum);
    };

    const nextPage = () => {
        if (activePageNum < totalPages) {
            animateAndChangePage('next', () => {
                loadPage(activePageNum + 1);
            });
        }
    };

    const prevPage = () => {
        if (activePageNum > 1) {
            animateAndChangePage('prev', () => {
                loadPage(activePageNum - 1);
            });
        }
    };

    // ---------------------------------------------------------
    // 7. Đồng bộ hóa TOC Drawer & Metadata sách
    // ---------------------------------------------------------
    const fetchDocumentMetadata = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/docs`);
            if (!res.ok) throw new Error('Không thể đồng bộ danh sách tài liệu từ cổng 8005.');
            
            const docs = await res.json();
            const doc = docs.find(d => d.id === docId);
            
            if (!doc) {
                throw new Error(`Không tìm thấy tài liệu nào khớp với ID: ${docId}`);
            }
            
            totalPages = doc.total_pages;
            document.getElementById('reader-doc-title').innerText = doc.filename;
            document.getElementById('drawer-doc-id').innerText = `Document ID: ${doc.id}`;
            
            // Nạp song song cache dịch thuật từ cơ sở dữ liệu để phục vụ tooltip
            await loadTranslationsCache();
            
            // Xây dựng thanh mục lục TOC động
            populateTOC();
            
            // Tải trang sách đầu tiên hoặc trang yêu cầu từ URL
            const startPage = parseInt(urlParams.get('page')) || 1;
            loadPage(startPage);
            
            // Kích hoạt Autoscale khớp màn hình ban đầu
            setTimeout(autoScale, 150);
            
        } catch (err) {
            console.error('[MetadataError]', err);
            document.getElementById('reader-doc-title').innerText = 'Lỗi Tải Sách';
            alert(`Lỗi khởi tạo Smart Reader: ${err.message}`);
        }
    };

    const loadTranslationsCache = async () => {
        try {
            const url = `${API_BASE}/api/docs/${docId}/translations?limit=10000`;
            const res = await fetch(url);
            if (res.ok) {
                const items = await res.json();
                translationsCache = {};
                items.forEach(item => {
                    translationsCache[item.span_id] = {
                        en: item.original_text,
                        vi: item.translated_text || ''
                    };
                });
                console.log(`[Cache] Đã lưu trữ ${items.length} cụm từ dịch thuật vào bộ nhớ cache local.`);
            }
        } catch (err) {
            console.error('Không thể đồng bộ cache dịch thuật:', err);
        }
    };

    const populateTOC = () => {
        if (!tocList) return;
        tocList.innerHTML = '';
        
        for (let i = 1; i <= totalPages; i++) {
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'toc-item';
            item.dataset.pageNum = i;
            item.innerHTML = `<i class="fas fa-file-alt"></i> Trang ${i}`;
            
            item.addEventListener('click', (e) => {
                e.preventDefault();
                loadPage(i);
                toggleDrawer(false); // Tự đóng drawer khi chọn trang trên mobile
            });
            
            tocList.appendChild(item);
        }
    };

    const updateActiveTOCItem = () => {
        const items = document.querySelectorAll('.toc-item');
        items.forEach(item => {
            const pageNum = parseInt(item.dataset.pageNum);
            if (pageNum === activePageNum) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    };

    const updateProgress = () => {
        const progressFill = document.getElementById('progress-fill');
        const pageCounter = document.getElementById('page-counter');
        
        if (pageCounter) {
            pageCounter.innerText = `Trang ${activePageNum} / ${totalPages}`;
        }
        
        if (progressFill && totalPages > 0) {
            const percent = (activePageNum / totalPages) * 100;
            progressFill.style.width = `${percent}%`;
        }
    };

    // ---------------------------------------------------------
    // 8. Ràng buộc các sự kiện tương tác Header/Footer Controls
    // ---------------------------------------------------------
    
    // Nút Quay lại Dashboard
    if (btnBack) {
        btnBack.addEventListener('click', () => {
            window.location.href = 'index.html';
        });
    }

    // Nút Quản lý trang dịch trong Drawer TOC
    const btnGoPreview = document.getElementById('btn-go-preview');
    if (btnGoPreview) {
        btnGoPreview.addEventListener('click', (e) => {
            e.preventDefault();
            window.location.href = `preview.html?doc_id=${docId}`;
        });
    }

    // Các nút lật trang ở footer
    if (btnPrev) btnPrev.addEventListener('click', prevPage);
    if (btnNext) btnNext.addEventListener('click', nextPage);

    // Ràng buộc Drawer TOC Hamburger
    const toggleDrawer = (forceState) => {
        const shouldActive = typeof forceState === 'boolean' ? forceState : !navDrawer.classList.contains('active');
        if (shouldActive) {
            hamburgerBtn.classList.add('active');
            navDrawer.classList.add('active');
            drawerOverlay.classList.add('active');
        } else {
            hamburgerBtn.classList.remove('active');
            navDrawer.classList.remove('active');
            drawerOverlay.classList.remove('active');
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

    // Bộ điều khiển Zoom Percent thủ công
    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => {
            zoomFactor = Math.min(2.0, zoomFactor + 0.1);
            zoomPercent.innerText = `${Math.round(zoomFactor * 100)}%`;
            autoScale();
        });
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => {
            zoomFactor = Math.max(0.5, zoomFactor - 0.1);
            zoomPercent.innerText = `${Math.round(zoomFactor * 100)}%`;
            autoScale();
        });
    }

    // Gắn sự kiện chuyển đổi Themes (Tối / Sáng / Sepia)
    themeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const theme = btn.dataset.theme;
            currentTheme = theme;
            
            // Cập nhật theme class trên body
            document.body.className = `theme-${theme}`;
            
            themeButtons.forEach(b => {
                if (b.dataset.theme === theme) b.classList.add('active');
                else b.classList.remove('active');
            });
            
            // Truyền theme mới vào iframe
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDoc) {
                applyThemeToIframe(iframeDoc);
            }
        });
    });

    // Gắn sự kiện chuyển đổi ngôn ngữ (VI / EN / Song ngữ)
    modeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const mode = btn.dataset.mode;
            currentLang = mode;
            
            modeButtons.forEach(b => {
                if (b.dataset.mode === mode) b.classList.add('active');
                else b.classList.remove('active');
            });
            
            // Nạp lại trang theo chế độ ngôn ngữ đã chọn
            loadPage(activePageNum);
        });
    });

    // ---------------------------------------------------------
    // Khởi động dòng chảy chính (Initialization flow)
    // ---------------------------------------------------------
    fetchDocumentMetadata();
});
