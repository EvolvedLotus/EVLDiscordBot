// API Configuration - Supports both development and production
function getApiBaseUrl() {
    const hostname = window.location.hostname;

    // Production: GitHub Pages
    if (hostname === 'evolvedlotus.github.io') {
        return 'https://your-railway-app.railway.app'; // Replace with your actual Railway app URL
    }

    // Local development: Try common ports
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        // Try to detect if backend is running on port 5000 (Flask default)
        // If not available, fallback to port 3000
        return 'http://localhost:5000';
    }

    // Railway/Netlify deployment
    if (window.API_BASE_URL) {
        return window.API_BASE_URL;
    }

    // Fallback
    return 'http://localhost:5000';
}

const API_BASE_URL = getApiBaseUrl();

// Debug logging
console.log('=== SCRIPT.JS LOADING ===');
console.log('Current URL:', window.location.href);
console.log('DOM State:', document.readyState);
console.log('API Base URL:', API_BASE_URL);

// Helper function to make API calls with proper CORS support
async function apiCall(endpoint, options = {}) {
    try {
        // Default options with CORS support
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            mode: 'cors'
        };

        // Merge options
        const fetchOptions = { ...defaultOptions, ...options };

        // Make request
        const response = await fetch(`${API_BASE_URL}${endpoint}`, fetchOptions);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}

// Login functionality
async function login(event) {
    // Prevent default at the very start
    if (event) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
    }

    console.log('=== LOGIN FUNCTION EXECUTING ===');

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    console.log('Username:', username);
    console.log('Attempting login...');

    // Validate inputs
    if (!username || !password) {
        alert('Please enter both username and password');
        return;
    }

    try {
        const loginUrl = `${API_BASE_URL}/api/auth/login`;
        console.log('Login URL:', loginUrl);

        const response = await fetch(loginUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            mode: 'cors',
            body: JSON.stringify({
                username: username,
                password: password
            })
        });

        console.log('Response status:', response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Login failed: ${response.status}`);
        }

        const data = await response.json();
        console.log('Login successful:', data);

        // Hide login screen, show dashboard
        document.getElementById('login-screen').style.display = 'none';
        document.getElementById('main-dashboard').style.display = 'block';

        // Load initial data
        await loadServers();

    } catch (error) {
        console.error('Login error:', error);
        alert(`Login failed: ${error.message}`);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, attaching login handler');

    const loginForm = document.getElementById('login-form');
    const loginBtn = document.getElementById('login-btn');

    console.log('Login form found:', !!loginForm);
    console.log('Login button found:', !!loginBtn);

    if (loginForm) {
        // Remove any existing listeners first
        loginForm.removeEventListener('submit', login);
        // Add the listener
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            e.stopPropagation();
            login(e);
        });
        console.log('Login form handler attached successfully');
    }

    // Also attach to button click as backup
    if (loginBtn) {
        loginBtn.removeEventListener('click', login);
        loginBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            login(e);
        });
        console.log('Login button handler attached successfully');
    }
});

// Load servers function
async function loadServers() {
    try {
        console.log('Loading servers...');
        const response = await apiCall('/api/servers');
        console.log('Servers loaded:', response);
        // TODO: Populate server selector
    } catch (error) {
        console.error('Error loading servers:', error);
    }
}
