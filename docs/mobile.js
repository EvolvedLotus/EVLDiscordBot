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
        // Only initialize mobile features if on mobile device
        if (window.innerWidth <= 768) {
            createMobileElements();
            attachMobileListeners();
        }

        // Re-initialize on window resize
        let resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                if (window.innerWidth <= 768) {
                    if (!document.getElementById('mobile-menu-toggle')) {
                        createMobileElements();
                        attachMobileListeners();
                    }
                } else {
                    removeMobileElements();
                }
            }, 250);
        });
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

        // Create overlay
        const overlay = document.createElement('div');
        overlay.id = 'mobile-overlay';
        overlay.className = 'mobile-overlay';

        // Add to body
        document.body.appendChild(toggleBtn);
        document.body.appendChild(overlay);
    }

    function attachMobileListeners() {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        const overlay = document.getElementById('mobile-overlay');
        const sidebar = document.querySelector('.sidebar');

        if (!toggleBtn || !overlay || !sidebar) {
            return;
        }

        // Toggle menu on button click
        toggleBtn.addEventListener('click', function () {
            sidebar.classList.toggle('mobile-open');
            overlay.classList.toggle('active');
            toggleBtn.innerHTML = sidebar.classList.contains('mobile-open') ? '✕' : '☰';
        });

        // Close menu when clicking overlay
        overlay.addEventListener('click', function () {
            sidebar.classList.remove('mobile-open');
            overlay.classList.remove('active');
            toggleBtn.innerHTML = '☰';
        });

        // Close menu when clicking a nav button
        const navButtons = sidebar.querySelectorAll('.tab-button');
        navButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (window.innerWidth <= 768) {
                    sidebar.classList.remove('mobile-open');
                    overlay.classList.remove('active');
                    toggleBtn.innerHTML = '☰';
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
        }
    }
})();
