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
        document.getElementById('main-dashboard').style.display = 'flex';

        // Load initial data
        await loadDashboardData();

    } catch (error) {
        console.error('❌ Login failed:', error);
        alert(`Login failed: ${error.message || 'Unknown error'}`);
        isAuthenticated = false;
    }
}

// ========== DOM READY INITIALIZATION ==========
document.addEventListener('DOMContentLoaded', function () {
    console.log('📄 DOM Content Loaded');

    // Attach login form handler
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        // Remove existing listener (if any)
        loginForm.removeEventListener('submit', login);

        // Add new listener
        loginForm.addEventListener('submit', async function (e) {
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
        loginBtn.addEventListener('click', async function (e) {
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
    document.getElementById('main-dashboard').style.display = 'none';
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

// ========== TAB NAVIGATION ==========
function showTab(tabName) {
    console.log('Switching to tab:', tabName);

    // Hide all tab contents
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });

    // Remove active class from all tab buttons
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab
    const selectedTab = document.getElementById(tabName);
    if (selectedTab) {
        selectedTab.classList.add('active');
        selectedTab.style.display = 'block';
    }

    // Add active class to clicked button
    const activeButton = document.querySelector(`[data-tab="${tabName}"]`);
    if (activeButton) {
        activeButton.classList.add('active');
    }

    // Load tab-specific data
    loadTabData(tabName);
}

function loadTabData(tabName) {
    if (!currentServerId) {
        console.warn('No server selected');
        return;
    }

    switch (tabName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'users':
            loadUsersTab();
            break;
        case 'shop':
            loadShop();
            break;
        case 'tasks':
            loadTasks();
            break;
        case 'announcements':
            loadAnnouncements();
            break;
        case 'transactions':
            loadTransactions();
            break;
        case 'server-settings':
            loadServerSettingsTab();
            break;
        case 'permissions':
            loadPermissionsTab();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}

// ========== TAB LOADING FUNCTIONS ==========
async function loadDashboard() {
    try {
        await loadDashboardStats();
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }
}

async function loadUsersTab() {
    const usersList = document.getElementById('users-list');
    if (!usersList) return;

    try {
        usersList.innerHTML = '<div class="loading">Loading users...</div>';
        const data = await apiCall(`/api/${currentServerId}/users?page=1&limit=100`);

        if (data && data.users && data.users.length > 0) {
            let html = '<div class="table-container"><table><thead><tr>';
            html += '<th>User</th><th>Balance</th><th>Level</th><th>XP</th><th>Actions</th>';
            html += '</tr></thead><tbody>';

            data.users.forEach(user => {
                html += `<tr>
                    <td>
                        <div class="user-info">
                            <div class="user-details">
                                <div class="user-name">${user.username || 'Unknown'}</div>
                                <div class="user-id">${user.user_id}</div>
                            </div>
                        </div>
                    </td>
                    <td class="balance-amount">$${(user.balance || 0).toLocaleString()}</td>
                    <td>${user.level || 0}</td>
                    <td>${user.xp || 0}</td>
                    <td>
                        <button class="btn-small btn-primary" onclick="editUser('${user.user_id}')">Edit</button>
                    </td>
                </tr>`;
            });

            html += '</tbody></table></div>';
            usersList.innerHTML = html;
        } else {
            usersList.innerHTML = '<div class="empty-state">No users found</div>';
        }
    } catch (error) {
        console.error('Failed to load users:', error);
        usersList.innerHTML = '<div class="error-state">Failed to load users</div>';
    }
}

async function loadShop() {
    const shopList = document.getElementById('shop-list');
    if (!shopList) return;

    shopList.innerHTML = '<div class="loading">Shop management coming soon...</div>';
}

async function loadTasks() {
    const tasksList = document.getElementById('tasks-list');
    if (!tasksList) return;

    tasksList.innerHTML = '<div class="loading">Task management coming soon...</div>';
}

async function loadAnnouncements() {
    const announcementsContent = document.getElementById('tab-content');
    if (!announcementsContent) return;

    announcementsContent.innerHTML = '<div class="loading">Announcements coming soon...</div>';
}

async function loadTransactions() {
    const transactionsList = document.getElementById('transactions-list');
    if (!transactionsList) return;

    transactionsList.innerHTML = '<div class="loading">Transactions coming soon...</div>';
}

async function loadServerSettingsTab() {
    const settingsContent = document.getElementById('server-settings-content');
    if (!settingsContent) return;

    settingsContent.innerHTML = '<div class="loading">Server settings loaded. Configure your server here.</div>';
}

async function loadPermissionsTab() {
    const permissionsContent = document.getElementById('permissions-content');
    if (!permissionsContent) return;

    permissionsContent.innerHTML = '<div class="loading">Permissions management coming soon...</div>';
}

async function loadLogs() {
    const logsContent = document.getElementById('logs-content');
    if (!logsContent) return;

    logsContent.innerHTML = '<div class="loading">Logs coming soon...</div>';
}

// ========== USER MANAGEMENT ==========
function editUser(userId) {
    showNotification(`Edit user ${userId} - Feature coming soon`, 'info');
}

// ========== PLACEHOLDER FUNCTIONS ==========
function restartBot() {
    showNotification('Restart bot feature coming soon', 'info');
}

function showAddItemModal() {
    showNotification('Add shop item - Feature coming soon', 'info');
}

function viewShopStatistics() {
    showNotification('Shop statistics - Feature coming soon', 'info');
}

function validateShopIntegrity() {
    showNotification('Shop validation - Feature coming soon', 'info');
}

function filterShopItems() {
    console.log('Filtering shop items...');
}

function showCreateTaskModal() {
    showNotification('Create task - Feature coming soon', 'info');
}

function showCreateEmbedModal() {
    showNotification('Create embed - Feature coming soon', 'info');
}

function refreshEmbeds() {
    showNotification('Refresh embeds - Feature coming soon', 'info');
}

function showTransactionFilters() {
    const filters = document.getElementById('transaction-filters');
    if (filters) {
        filters.style.display = filters.style.display === 'none' ? 'block' : 'none';
    }
}

function hideTransactionFilters() {
    const filters = document.getElementById('transaction-filters');
    if (filters) filters.style.display = 'none';
}

function archiveOldTransactions() {
    showNotification('Archive transactions - Feature coming soon', 'info');
}

function exportTransactions() {
    showNotification('Export transactions - Feature coming soon', 'info');
}

function applyFilters() {
    showNotification('Applying filters...', 'info');
}

function clearFilters() {
    showNotification('Filters cleared', 'info');
}

function saveServerSettings() {
    showNotification('Save server settings - Feature coming soon', 'info');
}

function saveSettings() {
    showNotification('Save settings - Feature coming soon', 'info');
}

function updateBotStatus() {
    showNotification('Update bot status - Feature coming soon', 'info');
}

function saveChannelSetting(type) {
    showNotification(`Save ${type} channel - Feature coming soon`, 'info');
}

function saveCurrencySettings() {
    showNotification('Save currency settings - Feature coming soon', 'info');
}

function saveFeatureToggle(feature) {
    showNotification(`Save ${feature} toggle - Feature coming soon`, 'info');
}

function saveBotBehavior() {
    showNotification('Save bot behavior - Feature coming soon', 'info');
}

function saveAdminRoles() {
    showNotification('Save admin roles - Feature coming soon', 'info');
}

function saveModRoles() {
    showNotification('Save moderator roles - Feature coming soon', 'info');
}

function assignRoleToUser() {
    showNotification('Assign role - Feature coming soon', 'info');
}

function removeRoleFromUser() {
    showNotification('Remove role - Feature coming soon', 'info');
}

function kickUser() {
    showNotification('Kick user - Feature coming soon', 'info');
}

function banUser() {
    showNotification('Ban user - Feature coming soon', 'info');
}

function unbanUser() {
    showNotification('Unban user - Feature coming soon', 'info');
}

function timeoutUser() {
    showNotification('Timeout user - Feature coming soon', 'info');
}

function loadCommandPermissions() {
    showNotification('Load command permissions - Feature coming soon', 'info');
}

function syncRoles() {
    showNotification('Sync roles - Feature coming soon', 'info');
}

function clearLogs() {
    showNotification('Clear logs - Feature coming soon', 'info');
}
