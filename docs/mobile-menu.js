// Mobile menu toggle functionality
function toggleMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('mobile-overlay');
    const toggle = document.getElementById('mobile-menu-toggle');

    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
    toggle.classList.toggle('active');
}

function closeMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('mobile-overlay');
    const toggle = document.getElementById('mobile-menu-toggle');

    sidebar.classList.remove('open');
    overlay.classList.remove('active');
    toggle.classList.remove('active');
}

// Close mobile menu when clicking on a tab
document.addEventListener('DOMContentLoaded', function () {
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => {
        button.addEventListener('click', function () {
            if (window.innerWidth <= 768) {
                closeMobileMenu();
            }
        });
    });
});
