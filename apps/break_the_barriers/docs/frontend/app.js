/* ==========================================================================
   Interactive Plan - Core JavaScript
   Implements Stepper Tabs, Interactive Checklists, and Duration Adjusters.
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    
    // ==========================================================================
    // 1. STEPPER TABS SWITCHING LOGIC
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
    // 2. INTERACTIVE CHECKLIST & PROGRESS BAR
    // ==========================================================================
    const checkboxes = document.querySelectorAll('.task-check');
    const progressFill = document.getElementById('progress-fill');
    const progressPercent = document.getElementById('progress-percent');

    function updateProgress() {
        let totalWeight = 0;
        let completedWeight = 0;

        checkboxes.forEach(cb => {
            const weight = parseFloat(cb.getAttribute('data-weight')) || 10;
            totalWeight += weight;
            if (cb.checked) {
                completedWeight += weight;
            }
        });

        const percentage = totalWeight > 0 ? Math.round((completedWeight / totalWeight) * 100) : 0;
        
        // Update DOM Elements
        progressPercent.textContent = `${percentage}%`;
        progressFill.style.width = `${percentage}%`;

        // Save progress to LocalStorage for persistence
        const checkedStates = Array.from(checkboxes).map(cb => cb.checked);
        localStorage.setItem('plan_checked_states', JSON.stringify(checkedStates));
    }

    // Load saved checklist states
    function loadSavedProgress() {
        const savedStates = localStorage.getItem('plan_checked_states');
        if (savedStates) {
            try {
                const checkedStates = JSON.parse(savedStates);
                checkboxes.forEach((cb, idx) => {
                    if (idx < checkedStates.length) {
                        cb.checked = checkedStates[idx];
                    }
                });
            } catch (err) {
                console.error("Error loading checklist states:", err);
            }
        }
        updateProgress();
    }

    // Bind event listeners to checkboxes
    checkboxes.forEach(cb => {
        cb.addEventListener('change', updateProgress);
    });

    // ==========================================================================
    // 3. DURATION ADJUSTER LOGIC
    // ==========================================================================
    const sliders = document.querySelectorAll('.days-slider');
    const totalDaysText = document.getElementById('total-days');

    function calculateTotalDuration() {
        let grandTotal = 0;
        
        sliders.forEach(slider => {
            const phaseId = slider.getAttribute('data-phase');
            const days = parseInt(slider.value) || 1;
            grandTotal += days;

            // Update label for this specific phase
            const daysValLabel = document.getElementById(`days-val-${phaseId}`);
            if (daysValLabel) {
                daysValLabel.textContent = `${days} ngày`;
            }
        });

        totalDaysText.textContent = `${grandTotal} ngày`;
    }

    // Bind inputs to sliders
    sliders.forEach(slider => {
        slider.addEventListener('input', calculateTotalDuration);
    });

    // ==========================================================================
    // 4. EXPORT PLAN CONFIGURATION TO JSON
    // ==========================================================================
    const exportBtn = document.getElementById('export-plan-btn');
    const exportBox = document.getElementById('export-box');
    const jsonOutputText = document.getElementById('json-output-text');

    exportBtn.addEventListener('click', () => {
        const phaseConfig = {};
        let grandTotal = 0;

        sliders.forEach(slider => {
            const phaseId = slider.getAttribute('data-phase');
            const days = parseInt(slider.value) || 1;
            phaseConfig[`phase_${phaseId}`] = {
                expected_days: days,
                priority: phaseId <= 2 ? "High" : (phaseId <= 4 ? "Medium" : "Low")
            };
            grandTotal += days;
        });

        const planJSON = {
            project: "break_the_barriers",
            target_platform: "Mobile-First Ebook Reader & Translator",
            architecture: "3-Layer Decoupled (Offline Prep / Shared Assets / Touch Client)",
            total_duration_days: grandTotal,
            phases: phaseConfig,
            customized_timestamp: new Date().toISOString()
        };

        // Output formatted JSON
        jsonOutputText.value = JSON.stringify(planJSON, null, 2);
        
        // Show box with animation
        exportBox.style.display = 'block';
        jsonOutputText.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    // Initialize all controls
    loadSavedProgress();
    calculateTotalDuration();

    // ==========================================================================
    // 5. RESPONSIVE HAMBURGER MENU DRAWER INTERACTION
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
