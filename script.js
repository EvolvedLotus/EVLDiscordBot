// ========== API CONFIGURATION ==========
function getApiBaseUrl() {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;

    console.log('🌐 Detecting API URL for:', hostname);

    // Production: GitHub Pages
    if (hostname === 'evolvedlotus.github.io') {
        return 'https://evldiscordbot-production.up.railway.app';
    }

    // Development: Localhost
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'http://localhost:5000';
    }

    // Fallback to production
    return 'https://evldiscordbot-production.up.railway.app';
}

const API_BASE_URL = getApiBaseUrl();
console.log('✅ API Base URL:', API_BASE_URL);

// ========== UNIVERSAL FETCH WRAPPER WITH CORS ==========
async function apiCall(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    // Default options with CORS credentials
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',  // CRITICAL: Include cookies/session
        mode: 'cors',             // CRITICAL: Enable CORS
    };

    // Merge options
    const fetchOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...(options.headers || {})
        }
    };

    console.log('📡 API Call:', {
        url,
        method: fetchOptions.method,
        credentials: fetchOptions.credentials
    });

    try {
        const response = await fetch(url, fetchOptions);

        console.log('📥 Response:', {
            status: response.status,
            ok: response.ok
        });

        // Handle non-JSON responses
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }

        return response;

    } catch (error) {
        console.error('❌ API Call Failed:', error);
        throw error;
    }
}

// ========== LOGIN FUNCTION ==========
async function login(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
    }

    console.log('🔐 === LOGIN ATTEMPT ===');

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    console.log('Username:', username);

    if (!username || !password) {
        alert('Please enter both username and password');
        return;
    }

    try {
        const data = await apiCall('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({
                username: username,
                password: password
            })
        });

        console.log('✅ Login successful:', data);

        // Store token if provided (optional, sessions use cookies)
        if (data.token) {
            localStorage.setItem('authToken', data.token);
        }

        // Hide login screen, show dashboard
        document.getElementById('login-screen').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        // Load initial data
        await loadServers();

    } catch (error) {
        console.error('❌ Login failed:', error);
        alert(`Login failed: ${error.message || 'Unknown error'}`);
    }
}

// ========== DOM READY INITIALIZATION ==========
document.addEventListener('DOMContentLoaded', function() {
    console.log('📄 DOM Content Loaded');

    // Attach login form handler
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        // Remove existing listener (if any)
        loginForm.removeEventListener('submit', login);

        // Add new listener
        loginForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            e.stopPropagation();
            await login(e);
        });

        console.log('✅ Login form handler attached');
    } else {
        console.error('❌ Login form not found!');
    }

    // Also attach to button as backup
    const loginBtn = document.getElementById('login-btn');
    if (loginBtn) {
        loginBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            e.stopPropagation();
            await login(e);
        });
        console.log('✅ Login button handler attached');
    }
});

// Load servers function
async function loadServers() {
    try {
        const data = await apiCall('/api/servers');
        console.log('Servers loaded:', data);
        // TODO: Populate server selector
    } catch (error) {
        console.error('Failed to load servers:', error);
    }
}
