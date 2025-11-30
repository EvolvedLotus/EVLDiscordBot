// Mobile Menu Functionality for EVL Discord Bot CMS
// Add this script to index.html with: <script src="./mobile.js"></script>

(function () {
    'use strict';

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobile);
    } else {
        initMobile();
    }

    function initMobile() {
        // Initial check
        checkMobileState();

        // Re-initialize on window resize
        let resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(checkMobileState, 250);
        });

        // Observe dashboard visibility changes
        const dashboard = document.getElementById('main-dashboard');
        const loginScreen = document.getElementById('login-screen');

        // Observer for dashboard
        if (dashboard) {
            const observer = new MutationObserver(function (mutations) {
                checkMobileState();
            });
            observer.observe(dashboard, { attributes: true, attributeFilter: ['style', 'class'] });
        }

        // Observer for login screen (to detect when it hides)
        if (loginScreen) {
            const loginObserver = new MutationObserver(function (mutations) {
                checkMobileState();
            });
            loginObserver.observe(loginScreen, { attributes: true, attributeFilter: ['style', 'class'] });
        }

        // Periodic check fallback (every 1s) to ensure button appears
        setInterval(checkMobileState, 1000);
    }

    function checkMobileState() {
        const isMobile = window.innerWidth <= 1024; // Increased breakpoint to include tablets
        const dashboard = document.getElementById('main-dashboard');
        const loginScreen = document.getElementById('login-screen');

        // Check if dashboard is visible OR login screen is hidden (implies dashboard active)
        const isDashboardVisible = (dashboard && dashboard.style.display !== 'none') ||
            (loginScreen && loginScreen.style.display === 'none');

        if (isMobile && isDashboardVisible) {
            if (!document.getElementById('mobile-menu-toggle')) {
                createMobileElements();
                attachMobileListeners();
            }
        } else {
            // Only remove if we are on desktop AND dashboard is visible
            // If we are on mobile but dashboard hidden (login screen), we also remove
            if (!isMobile || !isDashboardVisible) {
                removeMobileElements();
            }
        }
    }

    function createMobileElements() {
        // Check if elements already exist
        if (document.getElementById('mobile-menu-toggle')) {
            return;
        }

        // Create mobile menu toggle button
        const toggleBtn = document.createElement('button');
        toggleBtn.id = 'mobile-menu-toggle';
        toggleBtn.className = 'mobile-menu-toggle';
        toggleBtn.innerHTML = '☰';
        toggleBtn.setAttribute('aria-label', 'Toggle Menu');
        toggleBtn.title = 'Open Menu';

        // Create overlay
        const overlay = document.createElement('div');
        overlay.id = 'mobile-overlay';
        overlay.className = 'mobile-overlay';

        // Add to body
        document.body.appendChild(toggleBtn);
        document.body.appendChild(overlay);

        // Force sidebar styles if needed
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.classList.add('mobile-ready');
        }
    }

    function attachMobileListeners() {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        const overlay = document.getElementById('mobile-overlay');
        const sidebar = document.querySelector('.sidebar');

        if (!toggleBtn || !overlay || !sidebar) {
            return;
        }

        // Remove old listeners to avoid duplicates (cloning trick)
        const newBtn = toggleBtn.cloneNode(true);
        toggleBtn.parentNode.replaceChild(newBtn, toggleBtn);

        const newOverlay = overlay.cloneNode(true);
        overlay.parentNode.replaceChild(newOverlay, overlay);

        // Re-select
        const activeBtn = document.getElementById('mobile-menu-toggle');
        const activeOverlay = document.getElementById('mobile-overlay');

        // Toggle menu on button click
        activeBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            sidebar.classList.toggle('mobile-open');
            activeOverlay.classList.toggle('active');
            activeBtn.innerHTML = sidebar.classList.contains('mobile-open') ? '✕' : '☰';
        });

        // Close menu when clicking overlay
        activeOverlay.addEventListener('click', function () {
            sidebar.classList.remove('mobile-open');
            activeOverlay.classList.remove('active');
            activeBtn.innerHTML = '☰';
        });

        // Close menu when clicking a nav button
        const navButtons = sidebar.querySelectorAll('.tab-button');
        navButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (window.innerWidth <= 1024) {
                    sidebar.classList.remove('mobile-open');
                    activeOverlay.classList.remove('active');
                    activeBtn.innerHTML = '☰';
                }
            });
        });
    }

    function removeMobileElements() {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        const overlay = document.getElementById('mobile-overlay');
        const sidebar = document.querySelector('.sidebar');

        if (toggleBtn) {
            toggleBtn.remove();
        }
        if (overlay) {
            overlay.remove();
        }
        if (sidebar) {
            sidebar.classList.remove('mobile-open');
            sidebar.classList.remove('mobile-ready');
        }
    }
})();
