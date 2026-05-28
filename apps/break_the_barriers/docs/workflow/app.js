/* ==========================================================================
   Agentic Design Patterns Reader - Workflow Interactive Logic
   Handles Stepper states, Sandbox interactive demos, and Technical code tabs.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // ---------------------------------------------------------
    // Stepper Stepper Navigation
    // ---------------------------------------------------------
    const stepCards = document.querySelectorAll('.step-card');
    const detailContents = document.querySelectorAll('.detail-content');
    const detailPanel = document.querySelector('.detail-panel');

    const stepColors = {
        'step-1': '#3b82f6', // blue
        'step-2': '#8b5cf6', // purple
        'step-3': '#10b981', // emerald
        'step-4': '#ec4899', // pink
        'step-5': '#f59e0b'  // orange
    };

    const stepGlows = {
        'step-1': 'rgba(59, 130, 246, 0.2)',
        'step-2': 'rgba(139, 92, 246, 0.2)',
        'step-3': 'rgba(16, 185, 129, 0.2)',
        'step-4': 'rgba(236, 72, 153, 0.2)',
        'step-5': 'rgba(245, 158, 11, 0.2)'
    };

    const switchStep = (stepId) => {
        // Deactivate all cards and contents
        stepCards.forEach(card => card.classList.remove('active'));
        detailContents.forEach(content => content.classList.remove('active'));

        // Activate matching card and content
        const activeCard = document.querySelector(`[data-step="${stepId}"]`);
        const activeContent = document.getElementById(stepId);

        if (activeCard && activeContent) {
            activeCard.classList.add('active');
            activeContent.classList.add('active');

            // Apply theme accent color dynamically to panel borders and glowing shadows
            const accentColor = stepColors[stepId] || '#3b82f6';
            const glowColor = stepGlows[stepId] || 'rgba(59, 130, 246, 0.2)';
            
            detailPanel.style.setProperty('--active-accent', accentColor);
            detailPanel.style.setProperty('--active-accent-glow', glowColor);
        }
    };

    stepCards.forEach(card => {
        card.addEventListener('click', () => {
            const stepId = card.getAttribute('data-step');
            switchStep(stepId);
        });
    });

    // Initialize with first step
    switchStep('step-1');

    // ---------------------------------------------------------
    // Code Specifications Tabs
    // ---------------------------------------------------------
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const tabContainer = document.querySelector('.tab-container');

    const tabColors = {
        'tab-pdf': '#3b82f6',
        'tab-layout': '#8b5cf6',
        'tab-trans': '#10b981',
        'tab-reader': '#ec4899',
        'tab-device': '#f59e0b',
        'tab-hfe-safeguard': '#a78bfa',
        'tab-automation-e2e': '#00e5ff'
    };

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');

            // Deactivate all tabs
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Activate matching tab
            btn.classList.add('active');
            const targetContent = document.getElementById(tabId);
            if (targetContent) {
                targetContent.classList.add('active');
            }

            // Apply active indicator border color
            const accent = tabColors[tabId] || '#3b82f6';
            tabContainer.style.setProperty('--active-tab-accent', accent);
        });
    });

    // ---------------------------------------------------------
    // Interactive Sandbox Demos
    // ---------------------------------------------------------

    // Sandbox 1: Simulated Upload
    const dropzone = document.getElementById('sandbox-dropzone');
    const uploadBtn = document.getElementById('sandbox-upload-btn');
    const uploadStatus = document.getElementById('upload-status');

    const handleMockUpload = () => {
        uploadStatus.innerHTML = '<i class="fas fa-spinner fa-spin" style="color:#3b82f6;"></i> Đang đọc tài liệu PDF...';
        uploadBtn.disabled = true;

        setTimeout(() => {
            uploadStatus.innerHTML = '<i class="fas fa-check-circle" style="color:#10b981; font-size:1.5rem;"></i><span style="font-weight:600; color:#10b981;">Tải lên thành công!</span><br><span style="font-size:0.85rem; color:#9ca3af;">Đã phát hiện: 482 trang, 127 hình ảnh</span>';
            
            // Add premium pulse animation
            dropzone.style.borderColor = '#10b981';
            dropzone.style.background = 'rgba(16, 185, 129, 0.05)';

            // Trigger step 2 auto-transition shortly after success
            setTimeout(() => {
                switchStep('step-2');
            }, 1200);
        }, 1500);
    };

    if (dropzone) {
        dropzone.addEventListener('click', handleMockUpload);
    }
    if (uploadBtn) {
        uploadBtn.addEventListener('click', handleMockUpload);
    }

    // Sandbox 3: Interactive Shift Translation Selector (Multi-language)
    const langTabs = document.querySelectorAll('.lang-tab');
    const langScreens = document.querySelectorAll('.lang-screen');

    langTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const langId = tab.getAttribute('data-lang');

            langTabs.forEach(t => t.classList.remove('active'));
            langScreens.forEach(s => s.classList.remove('active'));

            tab.classList.add('active');
            const targetScreen = document.getElementById(`lang-${langId}`);
            if (targetScreen) {
                targetScreen.classList.add('active');
            }
        });
    });

    // Sandbox 4: Shelf Document selector
    const shelfCards = document.querySelectorAll('.mock-doc-card');
    const shelfBtn = document.getElementById('sandbox-shelf-btn');

    shelfCards.forEach(card => {
        card.addEventListener('click', () => {
            shelfCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');

            const title = card.querySelector('h4').textContent;
            shelfBtn.innerHTML = `<i class="fas fa-book-open"></i> Mở trình đọc: ${title}`;
            shelfBtn.style.background = 'linear-gradient(135deg, #ec4899, #8b5cf6)';
            shelfBtn.style.boxShadow = '0 4px 15px rgba(236, 72, 153, 0.4)';
        });
    });

    if (shelfBtn) {
        shelfBtn.addEventListener('click', () => {
            // Smoothly navigate back to main application!
            window.location.href = '../../index.html';
        });
    }

    // Sandbox 5: Device Selector Sandbox
    const deviceTabs = document.querySelectorAll('.device-tab');
    const deviceScreens = document.querySelectorAll('.device-screen');

    deviceTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const deviceId = tab.getAttribute('data-device');

            deviceTabs.forEach(t => t.classList.remove('active'));
            deviceScreens.forEach(s => s.classList.remove('active'));

            tab.classList.add('active');
            const targetScreen = document.getElementById(`screen-${deviceId}`);
            if (targetScreen) {
                targetScreen.classList.add('active');
            }
        });
    });

    // ==========================================================================
    // RESPONSIVE HAMBURGER MENU DRAWER INTERACTION
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
});
