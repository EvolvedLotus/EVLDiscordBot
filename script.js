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
            ok: response.ok,
            headers: Object.fromEntries(response.headers.entries())
        });

        // Check for authentication errors
        if (response.status === 401) {
            // Clear authentication state
            isAuthenticated = false;
            console.warn('🔐 Authentication required');

            // Create a more specific error for 401
            throw new Error('Authentication required. Please login again.');
        }

        // Handle non-JSON responses
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }

        return response;

    } catch (error) {
        console.error('❌ API Call Failed:', error);

        // Re-throw with more context
        if (error.message && error.message.includes('Authentication')) {
            throw error;
        }

        throw new Error(error.message || 'Network error occurred');
    }
}

let isAuthenticated = false;

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
        const response = await apiCall('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({
                username: username,
                password: password
            })
        });

        console.log('✅ Login successful:', response);

        // Mark as authenticated for subsequent requests
        isAuthenticated = true;

        // Hide login screen, show dashboard
        document.getElementById('login-screen').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        // Load initial data
        await loadDashboardData();

    } catch (error) {
        console.error('❌ Login failed:', error);
        alert(`Login failed: ${error.message || 'Unknown error'}`);
        isAuthenticated = false;
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

// ========== DASHBOARD DATA LOADING ==========
let currentServerId = null;
let userData = null;

// Load initial dashboard data after login
async function loadDashboardData() {
    try {
        console.log('🔄 Loading dashboard data...');

        // Load servers first
        await loadServers();

        // Load initial dashboard stats
        await loadDashboardStats();

        console.log('✅ Dashboard data loaded successfully');

    } catch (error) {
        console.error('❌ Failed to load dashboard data:', error);
        if (error.message && error.message.includes('Authentication')) {
            // Authentication failed, redirect to login
            showLoginScreen();
            alert('Your session has expired. Please login again.');
        }
    }
}

// Load servers and populate selector
async function loadServers() {
    try {
        const data = await apiCall('/api/servers');
        console.log('Servers loaded:', data);

        if (data && data.servers) {
            populateServerSelector(data.servers);

            // Auto-select first server if available
            if (data.servers.length > 0 && !currentServerId) {
                selectServer(data.servers[0].id);
            }
        }

        return data;
    } catch (error) {
        console.error('Failed to load servers:', error);
        throw error;
    }
}

// Populate server selector dropdown
function populateServerSelector(servers) {
    const selector = document.getElementById('server-select');
    if (!selector) return;

    selector.innerHTML = '<option value="">-- Select Server --</option>';

    servers.forEach(server => {
        const option = document.createElement('option');
        option.value = server.id;
        option.textContent = `${server.name} (${server.member_count} members)`;
        selector.appendChild(option);
    });
}

// Handle server selection change
function onServerChange() {
    const selector = document.getElementById('server-select');
    if (!selector) return;

    const selectedServerId = selector.value;
    if (selectedServerId && selectedServerId !== currentServerId) {
        selectServer(selectedServerId);
    }
}

// Select a specific server
async function selectServer(serverId) {
    currentServerId = serverId;
    console.log('Selected server:', serverId);

    // Load server-specific data
    await loadServerData(serverId);
}

// Load server-specific data
async function loadServerData(serverId) {
    try {
        console.log('Loading data for server:', serverId);

        // Load users
        await loadUsers(serverId);

        // Load other server data as needed
        // await loadTasks(serverId);
        // await loadShop(serverId);

    } catch (error) {
        console.error('Failed to load server data:', error);
        throw error;
    }
}

// Load users for current server
async function loadUsers(serverId) {
    try {
        const data = await apiCall(`/api/${serverId}/users?page=1&limit=100`);
        console.log('Users loaded:', data);

        // Update UI if needed
        updateUserCount(data.users ? data.users.length : 0);

        return data;
    } catch (error) {
        console.error('Failed to load users:', error);
        throw error;
    }
}

// Load dashboard statistics
async function loadDashboardStats() {
    try {
        const data = await apiCall('/api/status');
        console.log('Dashboard stats:', data);

        // Update dashboard content
        updateDashboardDisplay(data);

        return data;
    } catch (error) {
        console.error('Failed to load dashboard stats:', error);
        throw error;
    }
}

// Update dashboard display with stats
function updateDashboardDisplay(data) {
    const content = document.getElementById('dashboard-content');
    if (!content) return;

    content.innerHTML = `
        <div class="dashboard-stats">
            <div class="stat-card">
                <h3>🤖 Bot Status</h3>
                <div class="status-indicator ${data.bot_status === 'online' ? 'online' : 'offline'}">
                    ${data.bot_status === 'online' ? '🟢 Online' : '🔴 Offline'}
                </div>
            </div>
            <div class="stat-card">
                <h3>⏱️ Uptime</h3>
                <div class="stat-value">${data.uptime || 'N/A'}</div>
            </div>
            <div class="stat-card">
                <h3>🏠 Servers</h3>
                <div class="stat-value">${data.servers || 0}</div>
            </div>
            <div class="stat-card">
                <h3>👥 Total Users</h3>
                <div class="stat-value">${data.users || 0}</div>
            </div>
        </div>
    `;
}

// Update user count in UI
function updateUserCount(count) {
    // Update any UI elements that show user count
    console.log('User count for server:', count);
}

// Show login screen (for when authentication fails)
function showLoginScreen() {
    isAuthenticated = false;
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('dashboard').style.display = 'none';
}

// Utility functions
function showNotification(message, type = 'info', duration = 5000) {
    const container = document.getElementById('notification-container');
    if (!container) return;

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" class="notification-close">×</button>
    `;

    container.appendChild(notification);

    // Auto-remove after duration
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, duration);
}
