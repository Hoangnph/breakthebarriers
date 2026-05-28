/* ==========================================================================
   Smart Documentations Backend - Core Interactive JavaScript
   Implements OpenAPI dynamic rendering, Live HTTP Try-Out client, 
   Service algorithm simulation, Terminal simulations, and test animations.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    
    // ==========================================================================
    // 1. PRIMARY STEPPER TABS LOGIC
    // ==========================================================================
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');

            // Deactivate all buttons and contents
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Activate current
            btn.classList.add('active');
            const targetContent = document.getElementById(targetTab);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });

    // ==========================================================================
    // 2. VIRTUAL ENVIRONMENT TERMINAL SIMULATOR
    // ==========================================================================
    const termTabs = document.querySelectorAll('.term-tab');
    const terminalScreen = document.getElementById('terminal-screen');

    const terminalCommands = {
        activate: [
            { type: 'cmd', text: 'source backend/.venv/bin/activate' },
            { type: 'success', text: '(.venv) autoeyes@macbook break_the_barriers % ' },
            { type: 'output', text: '# Môi trường ảo đã kích hoạt thành công.' },
            { type: 'output', text: '# Trình thông dịch hiện tại: backend/.venv/bin/python (v3.12.8)' }
        ],
        install: [
            { type: 'cmd', text: 'pip install -r backend/requirements.txt' },
            { type: 'output', text: 'Requirement already satisfied: fastapi==0.110.0 in ./backend/.venv/lib/python3.12/site-packages (0.110.0)' },
            { type: 'output', text: 'Requirement already satisfied: uvicorn==0.28.0 in ./backend/.venv/lib/python3.12/site-packages (0.28.0)' },
            { type: 'output', text: 'Requirement already satisfied: beautifulsoup4==4.12.3 in ./backend/.venv/lib/python3.12/site-packages (4.12.3)' },
            { type: 'output', text: 'Requirement already satisfied: pydantic==2.6.4 in ./backend/.venv/lib/python3.12/site-packages (2.6.4)' },
            { type: 'output', text: 'Requirement already satisfied: pytest==8.1.1 in ./backend/.venv/lib/python3.12/site-packages (8.1.1)' },
            { type: 'output', text: 'Requirement already satisfied: pytest-asyncio==0.23.6 in ./backend/.venv/lib/python3.12/site-packages (0.23.6)' },
            { type: 'output', text: 'Requirement already satisfied: httpx==0.27.0 in ./backend/.venv/lib/python3.12/site-packages (0.27.0)' },
            { type: 'output', text: 'Requirement already satisfied: sqlalchemy>=2.0.0 in ./backend/.venv/lib/python3.12/site-packages (2.0.28)' },
            { type: 'output', text: 'Requirement already satisfied: psycopg2-binary>=2.9.0 in ./backend/.venv/lib/python3.12/site-packages (2.9.9)' },
            { type: 'success', text: 'Successfully validated all dependencies in 0.15s.' }
        ],
        test: [
            { type: 'cmd', text: 'pytest backend/tests/ -v' },
            { type: 'output', text: '============================= test session starts ==============================' },
            { type: 'output', text: 'platform darwin -- Python 3.12.8, pytest-8.1.1, pluggy-1.4.0 -- backend/.venv/bin/python' },
            { type: 'output', text: 'cachedir: .pytest_cache' },
            { type: 'output', text: 'rootdir: /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend' },
            { type: 'output', text: 'plugins: anyio-4.3.0, asyncio-0.23.6' },
            { type: 'output', text: 'collected 17 items' },
            { type: 'output', text: 'tests/test_api.py::test_status PASSED                                    [  6%]' },
            { type: 'output', text: 'tests/test_api.py::test_list_documents PASSED                            [ 12%]' },
            { type: 'output', text: 'tests/test_api.py::test_upload_document_success PASSED                   [ 18%]' },
            { type: 'output', text: 'tests/test_api.py::test_upload_document_invalid PASSED                   [ 24%]' },
            { type: 'output', text: 'tests/test_api.py::test_extract_document_success PASSED                  [ 29%]' },
            { type: 'output', text: 'tests/test_api.py::test_extract_document_not_found PASSED                [ 35%]' },
            { type: 'output', text: 'tests/test_api.py::test_get_page_content_success PASSED                  [ 41%]' },
            { type: 'output', text: 'tests/test_api.py::test_translate_page_success PASSED                    [ 47%]' },
            { type: 'output', text: 'tests/test_api.py::test_async_endpoints PASSED                           [ 53%]' },
            { type: 'output', text: 'tests/test_api.py::test_translation_memory_apis PASSED                   [ 59%]' },
            { type: 'output', text: 'tests/test_api.py::test_delete_document PASSED                           [ 65%]' },
            { type: 'output', text: 'tests/test_services.py::test_extractor_sanitize_html PASSED              [ 71%]' },
            { type: 'output', text: 'tests/test_services.py::test_extractor_extract_spans PASSED              [ 76%]' },
            { type: 'output', text: 'tests/test_services.py::test_translator_reconstruct_context PASSED       [ 82%]' },
            { type: 'output', text: 'tests/test_services.py::test_translator_translate_text_glossary PASSED   [ 88%]' },
            { type: 'output', text: 'tests/test_services.py::test_compiler_inject_translation PASSED          [ 94%]' },
            { type: 'output', text: 'tests/test_services.py::test_compiler_verify_quality_gates PASSED         [100%]' },
            { type: 'success', text: '=========================== 17 passed in 0.35s ============================' }
        ],
        e2e: [
            { type: 'cmd', text: 'python run_e2e_automation_tests.py' },
            { type: 'output', text: '================================================================================' },
            { type: 'output', text: '        KHỞI CHẠY BỘ AUTOMATION TEST TOÀN DIỆN - SMART DOCUMENTATIONS          ' },
            { type: 'output', text: '================================================================================' },
            { type: 'output', text: '🚀 1. KIỂM TRA HỆ THỐNG & MÔI TRƯỜNG' },
            { type: 'output', text: 'Đang chạy Python: 3.12.8' },
            { type: 'output', text: 'DATABASE_URL cấu hình: postgresql://postgres:postgres@localhost:5432/break_the_barriers' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Kết nối thành công tới PostgreSQL Database thực tế!' },
            { type: 'output', text: '🚀 2. KHỞI CHẠY BỘ KIỂM THỬ BACKEND (TDD PYTEST)' },
            { type: 'output', text: 'collected 17 items' },
            { type: 'output', text: 'tests/test_api.py::test_status PASSED                                    [  6%]' },
            { type: 'output', text: 'tests/test_services.py::test_compiler_verify_quality_gates PASSED         [100%]' },
            { type: 'success', text: '✔ [THÀNH CÔNG] 17/17 Pytest Cases passed thành công trong 0.35s!' },
            { type: 'output', text: '🚀 3. XÁC THỰC DOM & ĐỒNG BỘ FRONTEND ASSETS' },
            { type: 'output', text: 'Rà soát tệp: index.html -> Cấu trúc HTML DOM hoàn hảo.' },
            { type: 'output', text: 'Rà soát tệp: docs/backend/index.html -> Cấu trúc HTML DOM hoàn hảo.' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Hamburger Menu & Navigation Drawer và Overlay được khai báo đầy đủ.' },
            { type: 'output', text: '🚀 4. END-TO-END AUTOMATION API FLOW VERIFICATION' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Bước 4.1: Kiểm tra trạng thái root thành công.' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Bước 4.3: Gọi API Upload tài liệu PDF hợp lệ thành công.' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Bước 4.4.1: Xác minh CSDL có 5 trang và 15 spans tọa độ được tạo lập thành công.' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Bước 4.7.1: Xác minh HTML biên dịch chứa mã thông dịch Tiếng Việt và script co dãn Font (Dynamic Font Shrink).' },
            { type: 'success', text: '✔ [THÀNH CÔNG] Bước 4.8: Cổng kiểm định DOM Quality Gate 2 tự động phát hiện và chặn thành công khi chênh lệch/thiếu thẻ Span bản dịch.' },
            { type: 'output', text: '--------------------------------------------------------------------------------' },
            { type: 'output', text: '📊 BÁO CÁO KẾT QUẢ AUTOMATION TESTING TOÀN DIỆN' },
            { type: 'success', text: ' - 1. Hệ thống & Kết nối Cơ sở Dữ liệu PostgreSQL                  ● PASSED' },
            { type: 'success', text: ' - 2. Bộ Kiểm thử tự động Pytest (17/17 tests)                     ● PASSED' },
            { type: 'success', text: ' - 3. Cấu trúc DOM & Liên kết Assets Tĩnh Frontend                  ● PASSED' },
            { type: 'success', text: ' - 4. Kiểm tra Chuỗi API Số hóa E2E & DOM Quality Gate 2            ● PASSED' },
            { type: 'success', text: '🎉 HOÀN HẢO! Hệ thống đạt chất lượng 100% (4/4 PASSED).' }
        ],
        run: [
            { type: 'cmd', text: 'python -m uvicorn backend.app.main:app --port 8005 --reload' },
            { type: 'output', text: 'INFO:     Will watch for changes in these directories: [\'/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers\']' },
            { type: 'output', text: 'INFO:     Uvicorn server running on http://127.0.0.1:8005 (Press CTRL+C to quit)' },
            { type: 'output', text: 'INFO:     Started reloader process [58931] using WatchFiles' },
            { type: 'output', text: 'INFO:     Started server process [58935], waiting for application startup.' },
            { type: 'output', text: 'INFO:     Application startup complete.' }
        ]
    };

    function renderTerminal(cmdKey) {
        terminalScreen.innerHTML = '';
        const lines = terminalCommands[cmdKey];
        if (!lines) return;

        lines.forEach((line, index) => {
            setTimeout(() => {
                const lineDiv = document.createElement('div');
                lineDiv.className = `term-line ${line.type}`;
                if (line.type === 'cmd') {
                    lineDiv.innerHTML = `<span class="prompt">autoeyes@macbook break_the_barriers % </span>${line.text}`;
                } else {
                    lineDiv.innerHTML = line.text;
                }
                terminalScreen.appendChild(lineDiv);
                terminalScreen.scrollTop = terminalScreen.scrollHeight;
            }, index * 100);
        });
    }

    termTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            termTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const cmdKey = tab.getAttribute('data-cmd');
            renderTerminal(cmdKey);
        });
    });

    // Initialize terminal with first command
    renderTerminal('activate');

    // ==========================================================================
    // 3. CORE SERVICES TABBING & SIMULATORS LOGIC
    // ==========================================================================
    const serviceTabBtns = document.querySelectorAll('.service-tab-btn');
    const serviceDetailPanes = document.querySelectorAll('.service-detail-pane');

    serviceTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetPane = btn.getAttribute('data-service');

            serviceTabBtns.forEach(b => b.classList.remove('active'));
            serviceDetailPanes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const pane = document.getElementById(targetPane);
            if (pane) {
                pane.classList.add('active');
            }
        });
    });

    // --- Extractor Service Simulator ---
    const runExtractorBtn = document.getElementById('run-extractor-sim');
    const extractorInput = document.getElementById('extractor-input-html');
    const extractorOutput = document.getElementById('extractor-output');

    if (runExtractorBtn && extractorInput && extractorOutput) {
        runExtractorBtn.addEventListener('click', () => {
            const rawHtml = extractorInput.value;
            
            // 1. Sanitize grey background #A0A0A0 -> #FFFFFF
            let sanitizedHtml = rawHtml.replace(/#A0A0A0/gi, '#FFFFFF');
            
            // 2. Check and inject meta charset in head
            let injectedCharset = false;
            if (!sanitizedHtml.toLowerCase().includes('charset=utf-8') && sanitizedHtml.toLowerCase().includes('<head>')) {
                sanitizedHtml = sanitizedHtml.replace(/(<head\b[^>]*>)/i, '$1\n  <meta charset="utf-8">');
                injectedCharset = true;
            }

            // 3. Extract coordinates
            const spans = [];
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = rawHtml;
            const spanNodes = tempDiv.querySelectorAll('span');
            
            spanNodes.forEach(span => {
                const id = span.id || 'unknown';
                const text = span.textContent || '';
                const style = span.getAttribute('style') || '';
                
                const leftMatch = style.match(/left:\s*([\d\.]+)px/i);
                const topMatch = style.match(/top:\s*([\d\.]+)px/i);
                
                if (leftMatch && topMatch) {
                    spans.push({
                        id: id,
                        text: text,
                        top: parseFloat(topMatch[1]),
                        left: parseFloat(leftMatch[1])
                    });
                }
            });

            // Format Output JSON
            const result = {
                sanitization: {
                    bg_color_replaced: rawHtml.toLowerCase().includes('#a0a0a0'),
                    charset_utf8_injected: injectedCharset
                },
                extracted_spans_count: spans.length,
                spans: spans,
                sanitized_html_preview: sanitizedHtml.trim().substring(0, 160) + '...'
            };

            extractorOutput.textContent = JSON.stringify(result, null, 2);
        });
    }

    // --- Translator Service Simulator ---
    const runTranslatorBtn = document.getElementById('run-translator-sim');
    const translatorInput = document.getElementById('translator-input-spans');
    const translatorOutput = document.getElementById('translator-output');

    if (runTranslatorBtn && translatorInput && translatorOutput) {
        runTranslatorBtn.addEventListener('click', () => {
            try {
                const spans = JSON.parse(translatorInput.value);
                
                // 1. Reconstruct context by threshold_y = 5.0px
                const sortedSpans = [...spans];
                sortedSpans.sort((a, b) => (a.top - b.top) || (a.left - b.left));
                
                const groups = [];
                let currentGroup = [];
                
                sortedSpans.forEach(span => {
                    if (currentGroup.length === 0) {
                        currentGroup.push(span);
                    } else {
                        if (Math.abs(span.top - currentGroup[0].top) < 5.0) {
                            currentGroup.push(span);
                        } else {
                            groups.push(currentGroup);
                            currentGroup = [span];
                        }
                    }
                });
                if (currentGroup.length > 0) {
                    groups.push(currentGroup);
                }

                const reconstructedBlocks = [];
                const glossary = { "programming": "Lập trình", "hello world": "Xin chào Thế giới" };
                const mockTranslations = {
                    "Introductory Programming": "Nhập môn Lập trình",
                    "Introductory [s:s2] Programming": "Nhập môn [s:s2] Lập trình",
                    "Second line": "Dòng chữ thứ hai",
                    "Hello World": "Xin chào Thế giới"
                };

                groups.forEach(group => {
                    group.sort((a, b) => a.left - b.left);
                    const textParts = [];
                    const spanIds = [];
                    
                    group.forEach((s, idx) => {
                        const sid = s.id || s.index || `s${idx}`;
                        spanIds.append ? spanIds.append(sid) : spanIds.push(sid);
                        
                        if (idx === 0) {
                            textParts.push(s.text);
                        } else {
                            textParts.push(`[s:${sid}] ${s.text}`);
                        }
                    });

                    const fullText = textParts.join(' ');
                    
                    // Simple Mock Translator logic with Glossary
                    let translatedText = mockTranslations[fullText] || `Dịch: ${fullText}`;
                    
                    // Glossary enforcement override
                    Object.keys(glossary).forEach(key => {
                        const regex = new RegExp(key, 'gi');
                        translatedText = translatedText.replace(regex, glossary[key]);
                    });

                    reconstructedBlocks.push({
                        raw_combined: fullText,
                        translated: translatedText,
                        span_ids: spanIds
                    });
                });

                translatorOutput.textContent = JSON.stringify({
                    status: "success",
                    groups_detected: groups.length,
                    reconstructed_blocks: reconstructedBlocks
                }, null, 2);

            } catch (err) {
                translatorOutput.textContent = JSON.stringify({
                    status: "error",
                    message: "Không thể phân tích dữ liệu JSON đầu vào. " + err.message
                }, null, 2);
            }
        });
    }

    // ==========================================================================
    // 4. FASTAPI OPENAPI DYNAMIC REFERENCE EXPLORER
    // ==========================================================================
    const apiRoutesMenu = document.getElementById('api-routes-menu');
    const endpointDetailPlaceholder = document.getElementById('endpoint-detail-placeholder');
    const endpointDetailView = document.getElementById('endpoint-detail-view');
    
    // DOM references for Detail View
    const viewMethod = document.getElementById('view-method');
    const viewPath = document.getElementById('view-path');
    const viewSummary = document.getElementById('view-summary');
    const viewDesc = document.getElementById('view-desc');
    const viewParamsBody = document.getElementById('view-params-body');
    const viewRequestBodySection = document.getElementById('view-request-body-section');
    const viewRequestBodyJson = document.getElementById('view-request-body-json');
    const viewPathParamsInputs = document.getElementById('view-path-params-inputs');
    const executeApiBtn = document.getElementById('execute-api-btn');
    const responseStatusDisplay = document.getElementById('response-status-display');
    const responseContentDisplay = document.getElementById('response-content-display');

    let openapiData = null;
    let selectedRoute = null;

    // Load static openapi.json exported by Python on venv
    async function loadOpenAPISchema() {
        try {
            const response = await fetch('openapi.json');
            if (!response.ok) {
                throw new Error("Cannot find openapi.json file");
            }
            openapiData = await response.json();
            renderRoutesMenu(openapiData);
        } catch (err) {
            console.error("OpenAPI loading failed, using fallback spec", err);
            // Dynamic fallback if openapi.json is missing or failed (YAGNI resilience)
            openapiData = getFallbackOpenAPISchema();
            renderRoutesMenu(openapiData);
        }
    }

    function renderRoutesMenu(spec) {
        if (!apiRoutesMenu) return;
        apiRoutesMenu.innerHTML = '';

        const paths = spec.paths;
        Object.keys(paths).forEach(pathKey => {
            const pathItem = paths[pathKey];
            Object.keys(pathItem).forEach(method => {
                if (method !== 'get' && method !== 'post') return; // Only display GET/POST
                
                const endpointSpec = pathItem[method];
                const routeItem = document.createElement('div');
                routeItem.className = 'route-item';
                routeItem.setAttribute('data-path', pathKey);
                routeItem.setAttribute('data-method', method);
                
                const methodBadge = document.createElement('span');
                methodBadge.className = `method-badge method-${method}`;
                methodBadge.textContent = method.toUpperCase();
                
                const pathSpan = document.createElement('span');
                pathSpan.textContent = pathKey;
                pathSpan.style.whiteSpace = 'nowrap';
                pathSpan.style.overflow = 'hidden';
                pathSpan.style.textOverflow = 'ellipsis';

                routeItem.appendChild(methodBadge);
                routeItem.appendChild(pathSpan);
                
                routeItem.addEventListener('click', () => {
                    document.querySelectorAll('.route-item').forEach(r => r.classList.remove('active'));
                    routeItem.classList.add('active');
                    showEndpointDetails(pathKey, method, endpointSpec);
                });

                apiRoutesMenu.appendChild(routeItem);
            });
        });
    }

    function showEndpointDetails(path, method, endpointSpec) {
        selectedRoute = { path, method, spec: endpointSpec };
        
        // Hide placeholder, show details card
        if (endpointDetailPlaceholder) endpointDetailPlaceholder.style.display = 'none';
        if (endpointDetailView) endpointDetailView.style.display = 'flex';

        // Set Basic Meta
        viewMethod.textContent = method.toUpperCase();
        viewMethod.className = `method-tag method-${method}`;
        viewPath.textContent = path;
        viewSummary.textContent = endpointSpec.summary || 'FastAPI Endpoint';
        viewDesc.textContent = endpointSpec.description || 'Không có mô tả chi tiết.';

        // Render Parameters Table
        viewParamsBody.innerHTML = '';
        viewPathParamsInputs.innerHTML = '';
        let hasParams = false;

        const params = endpointSpec.parameters || [];
        
        // 1. Path/Query parameters
        params.forEach(param => {
            hasParams = true;
            const tr = document.createElement('tr');
            
            const nameTd = document.createElement('td');
            nameTd.innerHTML = `<span class="param-name">${param.name} ${param.required ? '<span class="param-required-tag">*</span>' : ''}</span>`;
            
            const typeTd = document.createElement('td');
            typeTd.innerHTML = `<span class="param-type">${param.schema ? param.schema.type : 'string'}</span>`;
            
            const locTd = document.createElement('td');
            locTd.innerHTML = `<span class="param-loc">${param.in}</span>`;
            
            const descTd = document.createElement('td');
            descTd.className = 'param-desc';
            descTd.textContent = param.description || 'Không có mô tả.';
            
            tr.appendChild(nameTd);
            tr.appendChild(typeTd);
            tr.appendChild(locTd);
            tr.appendChild(descTd);
            viewParamsBody.appendChild(tr);

            // If it is a PATH parameter, create an input field in the live try-out console
            if (param.in === 'path') {
                const wrapper = document.createElement('div');
                wrapper.className = 'console-field-wrapper';
                
                const label = document.createElement('label');
                label.setAttribute('for', `console-input-${param.name}`);
                label.innerHTML = `${param.name} (path parameter):`;
                
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'console-input';
                input.id = `console-input-${param.name}`;
                input.value = param.name === 'doc_id' ? 'clean_code' : (param.name === 'page_num' ? '1' : '');
                
                wrapper.appendChild(label);
                wrapper.appendChild(input);
                viewPathParamsInputs.appendChild(wrapper);
            }
        });

        // 2. Request Body Parameter (Pydantic Schema)
        if (endpointSpec.requestBody) {
            hasParams = true;
            viewRequestBodySection.style.display = 'block';
            
            const tr = document.createElement('tr');
            const nameTd = document.createElement('td');
            nameTd.innerHTML = `<span class="param-name">Payload <span class="param-required-tag">*</span></span>`;
            
            const typeTd = document.createElement('td');
            typeTd.innerHTML = `<span class="param-type">object</span>`;
            
            const locTd = document.createElement('td');
            locTd.innerHTML = `<span class="param-loc">body</span>`;
            
            const descTd = document.createElement('td');
            descTd.className = 'param-desc';
            descTd.textContent = 'Mẫu dữ liệu Pydantic Schema gửi lên máy chủ.';
            
            tr.appendChild(nameTd);
            tr.appendChild(typeTd);
            tr.appendChild(locTd);
            tr.appendChild(descTd);
            viewParamsBody.appendChild(tr);

            // Populate Mock Request JSON
            const mockPayload = getMockRequestBody(path);
            viewRequestBodyJson.value = JSON.stringify(mockPayload, null, 2);
        } else {
            viewRequestBodySection.style.display = 'none';
        }

        if (!hasParams) {
            viewParamsBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">Endpoint này không yêu cầu tham số đầu vào.</td></tr>`;
        }

        // Render Input, Process, Output Flow details dynamically
        const flowInputEl = document.getElementById('view-flow-input');
        const flowProcessEl = document.getElementById('view-flow-process');
        const flowOutputEl = document.getElementById('view-flow-output');
        if (flowInputEl && flowProcessEl && flowOutputEl) {
            const flowData = getEndpointFlowData(path);
            flowInputEl.innerHTML = flowData.input;
            flowProcessEl.innerHTML = flowData.process;
            flowOutputEl.innerHTML = flowData.output;
        }

        // Reset Response screen
        responseStatusDisplay.textContent = 'STATUS: -';
        responseStatusDisplay.className = 'response-status-badge';
        responseContentDisplay.textContent = '// Sẵn sàng chạy thử nghiệm trực tiếp.';
    }

    function getEndpointFlowData(path) {
        // Default values
        let data = {
            input: "Không yêu cầu tham số đầu vào phức tạp.",
            process: "Xử lý yêu cầu cơ bản từ client và trả về phản hồi.",
            output: "Phản hồi JSON tiêu chuẩn."
        };

        if (path === '/') {
            data = {
                input: "<ul><li>Không yêu cầu tham số đầu vào.</li><li>Thực hiện qua phương thức <strong>GET</strong>.</li></ul>",
                process: "<ul><li>Hệ thống thực hiện kiểm tra tình trạng sức khỏe (Health Check) cơ bản của máy chủ FastAPI.</li><li>Xác nhận các cấu hình CORS và định tuyến hoạt động bình thường.</li></ul>",
                output: "<ul><li>Trả về mã trạng thái <strong>200 OK</strong>.</li><li>JSON chứa:<ul><li><code>status</code>: Trạng thái ('online').</li><li><code>service</code>: Tên dịch vụ.</li><li><code>docs_url</code>: Đường dẫn tài liệu OpenAPI Swagger gốc.</li></ul></li></ul>"
            };
        } else if (path === '/api/docs') {
            data = {
                input: "<ul><li>Yêu cầu phương thức <strong>GET</strong>.</li><li>Không cần tham số bổ sung.</li></ul>",
                process: "<ul><li>Hệ thống quét thư mục lưu trữ cục bộ <code>data/</code> hoặc kho lưu trữ mock dữ liệu phẳng.</li><li>Phân tích danh sách các tệp tài liệu PDF đã tải lên kèm theo metadata hiện tại của chúng.</li></ul>",
                output: "<ul><li>Mảng danh sách các tài liệu (JSON Array).</li><li>Mỗi phần tử chứa <code>DocumentMetadata</code>:<ul><li><code>id</code>: Mã định danh sách (như <em>clean_code</em>).</li><li><code>filename</code>: Tên tệp tin gốc.</li><li><code>total_pages</code>: Tổng số trang sách.</li><li><code>status</code>: Trạng thái xử lý (<em>raw, extracted, translated, compiled</em>).</li><li><code>created_at</code>: Thời gian khởi tạo tài liệu.</li></ul></li></ul>"
            };
        } else if (path === '/api/docs/upload') {
            data = {
                input: "<ul><li>Gửi qua <strong>POST Multipart Form-Data</strong>.</li><li>Tham số:<ul><li><code>file</code>: Tệp tin nhị phân bắt buộc có đuôi <code>.pdf</code>.</li></ul></li></ul>",
                process: "<ul><li><strong>Bước 1:</strong> Xác thực tệp tin tải lên (chỉ hỗ trợ định dạng PDF chuẩn, từ chối các tệp tin lạ).</li><li><strong>Bước 2:</strong> Tạo mã định danh <code>doc_id</code> duy nhất bằng cách chuẩn hóa tên tệp (chuyển chữ thường, thay khoảng trắng thành dấu gạch dưới).</li><li><strong>Bước 3:</strong> Tạo thư mục lưu trữ cách ly cho tài liệu trong hệ thống.</li></ul>",
                output: "<ul><li>Đối tượng <code>DocumentMetadata</code> cập nhật của tệp tin vừa tải lên.</li><li>Trạng thái mặc định ban đầu là <strong>\"raw\"</strong> (chờ xử lý trích xuất).</li><li>Tổng số trang ước tính ban đầu (mặc định 10 trang làm việc thử nghiệm).</li></ul>"
            };
        } else if (path.includes('extract')) {
            data = {
                input: "<ul><li>Tham số đường dẫn (Path parameter):<ul><li><code>doc_id</code> (Bắt buộc): Mã định danh tài liệu cần trích xuất (ví dụ: <em>clean_code</em>).</li></ul></li><li>Phương thức: <strong>POST</strong>.</li></ul>",
                process: "<ul><li><strong>Bước 1:</strong> Khởi tạo một <strong>FastAPI Background Task</strong> để trích xuất phi tuần tự, tránh chặn luồng xử lý chính.</li><li><strong>Bước 2:</strong> Kích hoạt bộ xử lý <code>pdftohtml</code> trích xuất PDF thành tệp HTML định vị tuyệt đối pixel.</li><li><strong>Bước 3 (Extractor Core):</strong> Lọc bỏ màu nền thô của canvas (<code>#A0A0A0</code> -> <code>#FFFFFF</code>) và tự động chèn thẻ meta charset UTF-8 chống lỗi font tiếng Việt.</li><li><strong>Bước 4:</strong> BeautifulSoup quét tọa độ <code>top</code>, <code>left</code> của các thẻ <code>span</code> lưu vào JSON.</li></ul>",
                output: "<ul><li>Đối tượng <code>ExtractionResult</code>:<ul><li><code>id</code>: Mã tài liệu.</li><li><code>pages_count</code>: Tổng số trang trích xuất thành công.</li><li><code>extracted_html_dir</code>: Đường dẫn đến thư mục chứa các tệp HTML thô đã xử lý.</li></ul></li></ul>"
            };
        } else if (path.includes('pages')) {
            data = {
                input: "<ul><li>Tham số đường dẫn (Path parameters):<ul><li><code>doc_id</code>: Mã định danh tài liệu.</li><li><code>page_num</code>: Số trang cần lấy nội dung (số nguyên >= 1).</li></ul></li><li>Tham số truy vấn (Query parameter):<ul><li><code>lang</code> (Tùy chọn): Ngôn ngữ hiển thị (<code>en</code> hoặc <code>vi</code>, mặc định <code>en</code>).</li></ul></li></ul>",
                process: "<ul><li><strong>Bước 1:</strong> Xác thực mã tài liệu tồn tại và trang nằm trong phạm vi cho phép.</li><li><strong>Bước 2:</strong> Tìm tệp tin trang HTML tương ứng đã trích xuất/dịch thuật trong bộ lưu trữ.</li><li><strong>Bước 3:</strong> Trả về trực tiếp mã nguồn HTML có định vị tuyệt đối của trang đó để frontend Reader tự động dựng lại giao diện pixel-perfect.</li></ul>",
                output: "<ul><li>JSON chứa thông tin phản hồi:<ul><li><code>doc_id</code>: Mã tài liệu.</li><li><code>page_num</code>: Trang đang truy cập.</li><li><code>lang</code>: Ngôn ngữ trả về.</li><li><code>html</code>: Chuỗi chứa toàn bộ mã nguồn HTML định vị tuyệt đối của trang sách.</li></ul></li></ul>"
            };
        } else if (path.includes('translate')) {
            data = {
                input: "<ul><li>Tham số đường dẫn: <code>doc_id</code>.</li><li>Payload Body (JSON):<ul><li><code>page_num</code> (Bắt buộc): Số trang muốn thực hiện dịch thuật.</li><li><code>target_lang</code> (Tùy chọn): Ngôn ngữ đích (mặc định <code>vi</code>).</li></ul></li></ul>",
                process: "<ul><li><strong>Bước 1 (Gom dòng):</strong> Gom nhóm các thẻ <code>span</code> nằm trên cùng một hàng ngang có chênh lệch tọa độ đứng <code>top <= 5.0px</code> để tái tạo câu hoàn chỉnh.</li><li><strong>Bước 2 (Sắp xếp):</strong> Sắp xếp các span trong cùng dòng từ trái qua phải theo tọa độ <code>left</code>.</li><li><strong>Bước 3 (Token Interpolation):</strong> Chèn mã thẻ ảo <code>[s:id]</code> nối các span lại thành một đoạn văn đầy đủ ngữ cảnh để gửi AI dịch chính xác mà không bị mất vị trí ban đầu.</li><li><strong>Bước 4 (Glossary):</strong> Áp dụng từ điển thuật ngữ công nghệ đè hậu xử lý.</li></ul>",
                output: "<ul><li>JSON phản hồi trạng thái:<ul><li><code>status</code>: Trạng thái (<strong>\"translated\"</strong>).</li><li><code>doc_id</code>: Mã tài liệu.</li><li><code>page_num</code>: Số trang đã dịch.</li><li><code>target_lang</code>: Ngôn ngữ đích đã dịch.</li></ul></li></ul>"
            };
        } else if (path.includes('compile')) {
            data = {
                input: "<ul><li>Tham số đường dẫn: <code>doc_id</code>.</li><li>Payload Body (JSON):<ul><li><code>page_num</code> (Bắt buộc): Số trang muốn đóng gói thành phẩm.</li></ul></li></ul>",
                process: "<ul><li><strong>Bước 1 (DOM Quality Gate 2):</strong> Kiểm tra tính toàn vẹn của DOM, so sánh số thẻ span trong mã gốc và bản dịch để tránh mất mát hoặc làm hỏng trang.</li><li><strong>Bước 2 (Tiêm bản dịch):</strong> Thay nội dung tiếng Việt đã dịch vào đúng các ID span tương ứng.</li><li><strong>Bước 3 (Dynamic Font Shrink):</strong> Nhúng một script Javascript thông minh ở cuối thẻ <code>&lt;/body&gt;</code>. Khi trang tải, script tự động co nhỏ font chữ (tỷ lệ 0.75 - 1.0) khi ký tự tiếng Việt bị dài hơn để chống tràn lề và đè chữ.</li></ul>",
                output: "<ul><li>JSON phản hồi trạng thái:<ul><li><code>status</code>: Trạng thái (<strong>\"compiled\"</strong>).</li><li><code>doc_id</code>: Mã định danh tài liệu.</li><li><code>page_num</code>: Số trang đã hoàn thành đóng gói.</li><li><code>html_path</code>: Đường dẫn lưu trữ tệp thành phẩm compiled tĩnh.</li></ul></li></ul>"
            };
        }

        return data;
    }

    function getMockRequestBody(path) {
        if (path.includes('translate')) {
            return {
                page_num: 1,
                target_lang: "vi"
            };
        }
        if (path.includes('compile')) {
            return {
                page_num: 1
            };
        }
        return {};
    }

    // ==========================================================================
    // 5. LIVE TRY-OUT EXECUTION CLIENT LOGIC
    // ==========================================================================
    if (executeApiBtn) {
        executeApiBtn.addEventListener('click', async () => {
            if (!selectedRoute) return;

            responseStatusDisplay.textContent = 'STATUS: SENDING...';
            responseStatusDisplay.className = 'response-status-badge';
            responseContentDisplay.textContent = '// Đang kết nối và truyền tin...';

            const { path, method } = selectedRoute;
            let finalUrl = `http://localhost:8005${path}`;
            
            // 1. Substitute Path Parameters
            const pathParams = path.match(/\{([^\}]+)\}/g) || [];
            let substitutedAll = true;
            
            pathParams.forEach(paramPlaceholder => {
                const paramName = paramPlaceholder.replace(/[\{\}]/g, '');
                const inputEl = document.getElementById(`console-input-${paramName}`);
                if (inputEl) {
                    finalUrl = finalUrl.replace(paramPlaceholder, encodeURIComponent(inputEl.value));
                } else {
                    substitutedAll = false;
                }
            });

            if (!substitutedAll) {
                responseStatusDisplay.textContent = 'STATUS: ERROR';
                responseStatusDisplay.className = 'response-status-badge error';
                responseContentDisplay.textContent = '// Lỗi: Thiếu tham số đường dẫn (Path parameters).';
                return;
            }

            // 2. Build Request Options
            const options = {
                method: method.toUpperCase(),
                headers: {}
            };

            if (selectedRoute.spec.requestBody) {
                try {
                    options.headers['Content-Type'] = 'application/json';
                    options.body = viewRequestBodyJson.value;
                    JSON.parse(options.body); // Validate JSON
                } catch (jsonErr) {
                    responseStatusDisplay.textContent = 'STATUS: BAD JSON';
                    responseStatusDisplay.className = 'response-status-badge error';
                    responseContentDisplay.textContent = `// Lỗi: Định dạng JSON Payload gửi đi không hợp lệ!\n${jsonErr.message}`;
                    return;
                }
            }

            // 3. Fire Fetch Request targeting the active server
            try {
                const startTime = performance.now();
                const res = await fetch(finalUrl, options);
                const endTime = performance.now();
                const duration = (endTime - startTime).toFixed(1);

                const statusText = `${res.status} ${res.statusText} (${duration}ms)`;
                responseStatusDisplay.textContent = `STATUS: ${statusText}`;
                
                if (res.ok) {
                    responseStatusDisplay.className = 'response-status-badge success';
                } else {
                    responseStatusDisplay.className = 'response-status-badge error';
                }

                const resJson = await res.json();
                responseContentDisplay.textContent = JSON.stringify(resJson, null, 2);

            } catch (netErr) {
                // Catch network error and fallback to high-fidelity mocks (YAGNI/Offline robustness)
                console.warn("Local server connection failed, falling back to mock response", netErr);
                
                setTimeout(() => {
                    const mockRes = getMockResponse(path, options.body);
                    responseStatusDisplay.textContent = 'STATUS: 200 OK (OFFLINE MOCK MODE)';
                    responseStatusDisplay.className = 'response-status-badge success';
                    
                    responseContentDisplay.textContent = `// LƯU Ý: Không thể kết nối tới server cục bộ tại http://localhost:8005.\n` +
                        `// Dưới đây là mô phỏng kết quả trả về từ API tĩnh:\n\n` + 
                        JSON.stringify(mockRes, null, 2);
                }, 600);
            }
        });
    }

    function getMockResponse(path, reqBody) {
        const dateStr = new Date().toISOString();
        let bodyParsed = {};
        try { if(reqBody) bodyParsed = JSON.parse(reqBody); } catch(e){}

        if (path === '/') {
            return {
                status: "online",
                service: "Smart Documentations Backend",
                docs_url: "/docs"
            };
        }
        if (path === '/api/docs') {
            return [
                {
                    id: "clean_code",
                    filename: "Clean_Code.pdf",
                    total_pages: 482,
                    status: "compiled",
                    created_at: dateStr
                }
            ];
        }
        if (path === '/api/docs/upload') {
            return {
                id: "uploaded_book",
                filename: "Uploaded_Book.pdf",
                total_pages: 10,
                status: "raw",
                created_at: dateStr
            };
        }
        if (path.includes('extract')) {
            return {
                id: "clean_code",
                pages_count: 10,
                extracted_html_dir: "data/extracted_html/clean_code"
            };
        }
        if (path.includes('pages')) {
            return {
                doc_id: "clean_code",
                page_num: 1,
                lang: "vi",
                html: `<div id="page-container">\n  <div class="pf w0 h0" data-page-no="1">\n    <div class="c x0 y0 w1 h1">\n      <span id="s1" style="position:absolute; left:100px; top:200px;">Xin chào Thế giới</span>\n    </div>\n  </div>\n</div>`
            };
        }
        if (path.includes('translate')) {
            return {
                status: "translated",
                doc_id: "clean_code",
                page_num: bodyParsed.page_num || 1,
                target_lang: bodyParsed.target_lang || "vi"
            };
        }
        if (path.includes('compile')) {
            return {
                status: "compiled",
                doc_id: "clean_code",
                page_num: bodyParsed.page_num || 1,
                html_path: `data/pages/clean_code/page_${bodyParsed.page_num || 1}.html`
            };
        }
        return { message: "Mock response generated" };
    }

    // ==========================================================================
    // 6. HEALTH CHECK (PING SERVER) LOGIC
    // ==========================================================================
    const liveServerDot = document.getElementById('live-server-dot');
    const liveServerText = document.getElementById('live-server-text');
    const recheckServerBtn = document.getElementById('recheck-server-btn');

    async function checkServerHealth() {
        if (!liveServerDot || !liveServerText) return;
        
        liveServerText.textContent = 'Đang kiểm tra kết nối...';
        liveServerDot.className = 'status-dot offline';
        liveServerDot.style.backgroundColor = '#e2e8f0';

        try {
            const res = await fetch('http://localhost:8005/', { method: 'GET' });
            if (res.ok) {
                liveServerDot.className = 'status-dot online';
                liveServerDot.style.backgroundColor = '#10b981';
                liveServerText.textContent = 'Máy chủ Hoạt động (Online)';
            } else {
                throw new Error("HTTP status abnormal");
            }
        } catch (err) {
            liveServerDot.className = 'status-dot offline';
            liveServerDot.style.backgroundColor = '#ef4444';
            liveServerText.textContent = 'Máy chủ Ngoại tuyến (Offline)';
        }
    }

    if (recheckServerBtn) {
        recheckServerBtn.addEventListener('click', checkServerHealth);
    }

    // Run health check initially
    checkServerHealth();

    // ==========================================================================
    // 7. PYTEST TEST RUNNER SCREEN ANIMATOR
    // ==========================================================================
    const triggerPytestAnim = document.getElementById('trigger-pytest-anim');
    const pytestScreen = document.getElementById('pytest-screen');

    if (triggerPytestAnim && pytestScreen) {
        triggerPytestAnim.addEventListener('click', () => {
            pytestScreen.innerHTML = '';
            
            const pytestOutputLines = [
                { text: '============================= test session starts ==============================\n', type: 'output' },
                { text: 'platform darwin -- Python 3.12.8, pytest-8.1.1, pluggy-1.4.0\n', type: 'output' },
                { text: 'rootdir: /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend\n', type: 'output' },
                { text: 'plugins: anyio-4.3.0, asyncio-0.23.6\n', type: 'output' },
                { text: 'collected 17 items\n\n', type: 'output' },
                { text: 'tests/test_api.py::test_status PASSED                                    [  6%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_list_documents PASSED                            [ 12%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_upload_document_success PASSED                   [ 18%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_upload_document_invalid PASSED                   [ 24%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_extract_document_success PASSED                  [ 29%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_extract_document_not_found PASSED                [ 35%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_get_page_content_success PASSED                  [ 41%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_translate_page_success PASSED                    [ 47%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_async_endpoints PASSED                           [ 53%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_translation_memory_apis PASSED                   [ 59%]\n', type: 'success' },
                { text: 'tests/test_api.py::test_delete_document PASSED                           [ 65%]\n', type: 'success' },
                { text: 'tests/test_services.py::test_extractor_sanitize_html PASSED              [ 71%]\n', type: 'success' },
                { text: 'tests/test_services.py::test_extractor_extract_spans PASSED              [ 76%]\n', type: 'success' },
                { text: 'tests/test_services.py::test_translator_reconstruct_context PASSED       [ 82%]\n', type: 'success' },
                { text: 'tests/test_services.py::test_translator_translate_text_glossary PASSED   [ 88%]\n', type: 'success' },
                { text: 'tests/test_services.py::test_compiler_inject_translation PASSED          [ 94%]\n', type: 'success' },
                { text: 'tests/test_services.py::test_compiler_verify_quality_gates PASSED         [100%]\n\n', type: 'success' },
                { text: '======================== 17 passed in 0.35s =========================\n', type: 'success' }
            ];

            pytestOutputLines.forEach((line, index) => {
                setTimeout(() => {
                    const lineSpan = document.createElement('span');
                    lineSpan.className = line.type === 'success' ? 'term-line success' : 'term-line output';
                    if (line.text.includes('17 passed')) {
                        lineSpan.className = 'term-line success bold';
                    }
                    lineSpan.innerHTML = line.text.replace(/\n/g, '<br>');
                    pytestScreen.appendChild(lineSpan);
                    pytestScreen.scrollTop = pytestScreen.scrollHeight;
                }, index * 80);
            });
        });
    }

    // ==========================================================================
    // 8. FALLBACK SPEC FOR RESILIENCE (YAGNI/OFFLINE)
    // ==========================================================================
    function getFallbackOpenAPISchema() {
        return {
            paths: {
                "/": {
                    "get": {
                        "summary": "Kiểm tra Trạng thái Backend",
                        "description": "Trả về thông tin kết nối và tài liệu API.",
                        "parameters": []
                    }
                },
                "/api/docs": {
                    "get": {
                        "summary": "Liệt kê Sách / Tài liệu",
                        "description": "Lấy danh sách tất cả các sách kỹ thuật có sẵn trong thư mục dữ liệu phẳng.",
                        "parameters": []
                    }
                },
                "/api/docs/upload": {
                    "post": {
                        "summary": "Tải Sách PDF lên",
                        "description": "Kiểm tra tính hợp lệ và chuẩn bị upload cho tệp PDF.",
                        "parameters": [],
                        "requestBody": {
                            "content": {
                                "application/json": {}
                            }
                        }
                    }
                },
                "/api/docs/{doc_id}/extract": {
                    "post": {
                        "summary": "Kích hoạt Trích xuất",
                        "description": "Chuyển đổi tài liệu thô PDF sang HTML định vị pixel tuyệt đối.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh duy nhất của tài liệu (ví dụ: clean_code)."
                            }
                        ]
                    }
                },
                "/api/docs/{doc_id}/pages/{page_num}": {
                    "get": {
                        "summary": "Lấy Nội dung Trang Sách",
                        "description": "Trả về mã nguồn HTML có định vị tọa độ tuyệt đối cho trang cụ thể.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh của tài liệu."
                            },
                            {
                                "name": "page_num",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "integer" },
                                "description": "Số trang cần truy vấn."
                            },
                            {
                                "name": "lang",
                                "in": "query",
                                "required": false,
                                "schema": { "type": "string" },
                                "description": "Ngôn ngữ văn bản (en | vi). Mặc định là en."
                            }
                        ]
                    }
                },
                "/api/docs/{doc_id}/translate": {
                    "post": {
                        "summary": "AI Dịch thuật Trang Sách",
                        "description": "Áp dụng công nghệ gom hàng ngang và gọi AI biên dịch ngôn ngữ chất lượng cao.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh tài liệu."
                            }
                        ],
                        "requestBody": {
                            "content": {
                                "application/json": {}
                            }
                        }
                    }
                },
                "/api/docs/{doc_id}/compile": {
                    "post": {
                        "summary": "Đóng gói Trang Biên dịch",
                        "description": "Tiêm bản dịch tiếng Việt, kiểm thử Quality Gate 2 và nhúng mã Dynamic Font Shrink chống tràn lề.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh tài liệu."
                            }
                        ],
                        "requestBody": {
                            "content": {
                                "application/json": {}
                            }
                        }
                    }
                },
                "/api/docs/{doc_id}": {
                    "delete": {
                        "summary": "Xóa Tài liệu",
                        "description": "Xóa vĩnh viễn tài liệu khỏi cơ sở dữ liệu và dọn dẹp toàn bộ tệp tin, asset hình ảnh liên quan trên ổ đĩa vật lý.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh tài liệu cần xóa."
                            }
                        ]
                    }
                },
                "/api/docs/{doc_id}/translations": {
                    "get": {
                        "summary": "Liệt kê Bộ nhớ dịch",
                        "description": "Lấy danh sách phân trang các bản ghi bộ nhớ dịch (translations) của tài liệu.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh tài liệu."
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": false,
                                "schema": { "type": "integer", "default": 50 },
                                "description": "Số lượng bản ghi tối đa trả về."
                            },
                            {
                                "name": "offset",
                                "in": "query",
                                "required": false,
                                "schema": { "type": "integer", "default": 0 },
                                "description": "Vị trí bắt đầu lấy bản ghi."
                            }
                        ]
                    }
                },
                "/api/docs/{doc_id}/translations/search": {
                    "get": {
                        "summary": "Tìm kiếm Bộ nhớ dịch",
                        "description": "Tìm kiếm toàn văn bản ghi dịch thuật dựa trên từ khóa truy vấn, không phân biệt hoa thường.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh tài liệu."
                            },
                            {
                                "name": "q",
                                "in": "query",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Từ khóa tìm kiếm."
                            }
                        ]
                    }
                },
                "/api/docs/{doc_id}/translations/{span_id}": {
                    "put": {
                        "summary": "Biên tập Bản dịch (Live Edit)",
                        "description": "Biên tập trực tiếp nội dung dịch của một span cụ thể. Hệ thống tự động biên dịch lại (Auto Re-compile) trang tương ứng ngay lập tức.",
                        "parameters": [
                            {
                                "name": "doc_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "Mã định danh tài liệu."
                            },
                            {
                                "name": "span_id",
                                "in": "path",
                                "required": true,
                                "schema": { "type": "string" },
                                "description": "ID thẻ span cần sửa đổi."
                            }
                        ],
                        "requestBody": {
                            "content": {
                                "application/json": {}
                            }
                        }
                    }
                }
            }
        };
    }

    // Fire initial OpenAPI Spec loading
    loadOpenAPISchema();

    // ==========================================================================
    // 9. RESPONSIVE HAMBURGER MENU DRAWER INTERACTION
    // ==========================================================================
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
            document.body.style.overflow = 'hidden'; // Prevent background scrolling
        } else {
            hamburgerBtn.classList.remove('active');
            navDrawer.classList.remove('active');
            drawerOverlay.classList.remove('active');
            document.body.style.overflow = ''; // Re-enable background scrolling
        }
    };

    if (hamburgerBtn) {
        hamburgerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleDrawer();
        });
    }

    if (drawerCloseBtn) {
        drawerCloseBtn.addEventListener('click', () => toggleDrawer(false));
    }

    if (drawerOverlay) {
        drawerOverlay.addEventListener('click', () => toggleDrawer(false));
    }

    drawerLinks.forEach(link => {
        link.addEventListener('click', () => toggleDrawer(false));
    });

    // ==========================================================================
    // 10. API ACCORDION TOGGLE INTERACTION
    // ==========================================================================
    const accordionCards = document.querySelectorAll('.api-accordion-card');

    accordionCards.forEach(card => {
        const trigger = card.querySelector('.accordion-trigger');
        if (trigger) {
            trigger.addEventListener('click', () => {
                const isCollapsed = card.classList.contains('collapsed');
                if (isCollapsed) {
                    card.classList.remove('collapsed');
                    card.classList.add('expanded');
                } else {
                    card.classList.remove('expanded');
                    card.classList.add('collapsed');
                }
            });
        }
    });
});
