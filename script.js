// API Configuration
const API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8080'
    : (window.API_BASE_URL || 'https://evldiscordbot-production.up.railway.app');

let currentServerId = '';
let currentUser = null;

// Helper function to build API URLs
function apiUrl(endpoint) {
    return `${API_BASE_URL}${endpoint}`;
}

// Generic API call function with auth
async function apiCall(endpoint, options = {}) {
    options.credentials = 'include';
    options.headers = options.headers || {};
    options.headers['Content-Type'] = 'application/json';

    try {
        const response = await fetch(apiUrl(endpoint), options);

        if (response.status === 401) {
            // Unauthorized - redirect to login
            showLoginScreen();
            return null;
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `API Error: ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error('API Call Error:', error);
        throw error;
    }
}

// Show notification toast
function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Trigger reflow
    toast.offsetHeight;

    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Auth & Initialization
document.addEventListener('DOMContentLoaded', async () => {
    console.log('App initialized');

    // Event Listeners
    const loginBtn = document.getElementById('login-btn');
    if (loginBtn) {
        loginBtn.addEventListener('click', handleLogin);
    }

    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleLogin(e);
        });
    }

    // Check session
    await checkAuth();
});

async function checkAuth() {
    try {
        const data = await apiCall('/api/auth/me');
        if (data && data.authenticated) {
            currentUser = data.user;
            showDashboard();
            loadServers();
        } else {
            showLoginScreen();
        }
    } catch (e) {
        showLoginScreen();
    }
}

async function handleLogin(e) {
    if (e) e.preventDefault();

    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const errorDiv = document.getElementById('login-error');

    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    if (!username || !password) {
        if (errorDiv) {
            errorDiv.textContent = 'Please enter username and password';
            errorDiv.style.display = 'block';
        }
        return;
    }

    try {
        const response = await fetch(apiUrl('/api/auth/login'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
            credentials: 'include'
        });

        const data = await response.json();

        if (response.ok && data.success) {
            currentUser = data.user;
            showDashboard();
            loadServers();
        } else {
            if (errorDiv) {
                errorDiv.textContent = data.error || 'Login failed';
                errorDiv.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Login error:', error);
        if (errorDiv) {
            errorDiv.textContent = 'Network error. Please check console.';
            errorDiv.style.display = 'block';
        }
    }
}

function showLoginScreen() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('main-dashboard').style.display = 'none';
}

function showDashboard() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('main-dashboard').style.display = 'flex';
    loadDashboard(); // Load initial dashboard data
}

async function loadServers() {
    try {
        const data = await apiCall('/api/servers');
        const select = document.getElementById('server-select');

        if (data && data.servers) {
            select.innerHTML = '<option value="">Select Server</option>';
            data.servers.forEach(server => {
                const option = document.createElement('option');
                option.value = server.id;
                option.textContent = server.name;
                select.appendChild(option);
            });

            // Select first server by default if available
            if (data.servers.length > 0) {
                select.value = data.servers[0].id;
                currentServerId = data.servers[0].id;
                onServerChange(); // Trigger load
            }
        }
    } catch (error) {
        console.error('Failed to load servers:', error);
    }
}

function onServerChange() {
    const select = document.getElementById('server-select');
    currentServerId = select.value;

    if (currentServerId) {
        // Refresh current tab
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const tabId = activeTab.id;
            loadTabContent(tabId);
        }
    }
}

function showTab(tabId) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Deactivate buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab
    const selectedTab = document.getElementById(tabId);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    // Activate button
    const selectedBtn = document.querySelector(`.tab-button[data-tab="${tabId}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('active');
    }

    loadTabContent(tabId);
}

function loadTabContent(tabId) {
    if (!currentServerId) return;

    switch (tabId) {
        case 'dashboard': loadDashboard(); break;
        case 'users': loadUsers(); break;
        case 'shop': loadShop(); break;
        case 'tasks': loadTasks(); break;
        case 'announcements': loadAnnouncements(); break;
        case 'embeds': loadEmbeds(); break;
        case 'transactions': loadTransactions(); break;
        case 'server-settings': loadServerSettingsTab(); break;
        case 'permissions': loadPermissionsTab(); break;
        case 'roles-tab': loadRolesTab(); break;
        case 'moderation-tab': loadModerationTab(); break;
        case 'config': loadServerSettings(); break;
        case 'logs': loadLogs(); break;
    }
}

// --- Feature Loaders ---

async function loadDashboard() {
    if (!currentServerId) return;
    const content = document.getElementById('dashboard-content');
    content.innerHTML = '<div class="loading">Loading dashboard...</div>';

    try {
        const statusData = await apiCall('/api/status');
        const serverConfig = await apiCall(`/api/${currentServerId}/config`);

        content.innerHTML = `
            <div class="dashboard-grid">
                <div class="stat-card">
                    <h3>Bot Status</h3>
                    <div class="stat-value ${statusData.bot_status}">${statusData.bot_status.toUpperCase()}</div>
                    <div class="stat-sub">Uptime: ${statusData.uptime}</div>
                </div>
                <div class="stat-card">
                    <h3>Server Name</h3>
                    <div class="stat-value">${serverConfig.server_name || 'Unknown'}</div>
                </div>
                <div class="stat-card">
                    <h3>Currency</h3>
                    <div class="stat-value">${serverConfig.currency_symbol} ${serverConfig.currency_name}</div>
                </div>
            </div>
        `;
    } catch (error) {
        content.innerHTML = `<div class="error">Failed to load dashboard: ${error.message}</div>`;
    }
}

async function loadUsers() {
    if (!currentServerId) return;
    const list = document.getElementById('users-list');
    list.innerHTML = '<div class="loading">Loading users...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/users`);
        if (data.users && data.users.length > 0) {
            let html = '<table class="data-table"><thead><tr><th>User</th><th>Balance</th><th>Level</th><th>XP</th><th>Actions</th></tr></thead><tbody>';
            data.users.forEach(user => {
                html += `
                    <tr>
                        <td>${user.username || user.user_id}</td>
                        <td>${user.balance}</td>
                        <td>${user.level}</td>
                        <td>${user.xp}</td>
                        <td>
                            <button onclick="manageUser('${user.user_id}')" class="btn-small btn-primary">Manage</button>
                        </td>
                    </tr>
                `;
            });
            html += '</tbody></table>';
            list.innerHTML = html;
        } else {
            list.innerHTML = '<p>No users found.</p>';
        }
    } catch (error) {
        list.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

async function loadShop() {
    if (!currentServerId) return;
    const list = document.getElementById('shop-list');
    list.innerHTML = '<div class="loading">Loading shop...</div>';
    try {
        const data = await apiCall(`/api/${currentServerId}/shop`);
        if (data.items && data.items.length > 0) {
            let html = '<div class="shop-grid">';
            data.items.forEach(item => {
                html += `
                    <div class="shop-card">
                        <h4>${item.name}</h4>
                        <p>${item.description || ''}</p>
                        <div class="price">${item.price} coins</div>
                        <div class="stock">Stock: ${item.stock === -1 ? '∞' : item.stock}</div>
                    </div>
                `;
            });
            html += '</div>';
            list.innerHTML = html;
        } else {
            list.innerHTML = '<p>No items in shop.</p>';
        }
    } catch (error) {
        list.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

async function loadTasks() {
    if (!currentServerId) return;
    const list = document.getElementById('tasks-list');
    list.innerHTML = '<div class="loading">Loading tasks...</div>';
    try {
        const data = await apiCall(`/api/${currentServerId}/tasks`);
        if (data.tasks && Object.keys(data.tasks).length > 0) {
            let html = '<div class="tasks-grid">';
            Object.values(data.tasks).forEach(task => {
                html += `
                    <div class="task-card">
                        <h4>${task.name}</h4>
                        <p>${task.description}</p>
                        <div class="reward">Reward: ${task.reward}</div>
                    </div>
                `;
            });
            html += '</div>';
            list.innerHTML = html;
        } else {
            list.innerHTML = '<p>No tasks found.</p>';
        }
    } catch (error) {
        list.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

async function loadServerSettings() {
    if (!currentServerId) return;
    // Implement loading of server config for the Config tab
    try {
        const config = await apiCall(`/api/${currentServerId}/config`);
        // Populate form fields
        if (document.getElementById('bot-status-message')) {
            document.getElementById('bot-status-message').value = config.bot_status_message || '';
        }
        if (document.getElementById('bot-status-type')) {
            document.getElementById('bot-status-type').value = config.bot_status_type || 'playing';
        }
    } catch (error) {
        console.error('Error loading config:', error);
    }
}

async function updateBotStatus() {
    if (!currentServerId) return;
    const message = document.getElementById('bot-status-message').value;
    const type = document.getElementById('bot-status-type').value;
    const presence = document.getElementById('bot-presence').value;
    const url = document.getElementById('streaming-url').value;

    try {
        await apiCall(`/api/${currentServerId}/bot_status`, {
            method: 'POST',
            body: JSON.stringify({
                message,
                type,
                presence,
                streaming_url: url
            })
        });
        showNotification('Bot status updated!', 'success');
    } catch (error) {
        showNotification('Failed to update status', 'error');
    }
}

// Placeholder functions for missing implementations
async function loadAnnouncements() { document.getElementById('tab-content').innerHTML = 'Announcements not implemented yet.'; }
async function loadEmbeds() { document.getElementById('embeds-list').innerHTML = 'Embeds not implemented yet.'; }
async function loadTransactions() { document.getElementById('transactions-list').innerHTML = 'Transactions not implemented yet.'; }
async function loadServerSettingsTab() { document.getElementById('server-settings-content').innerHTML = 'Server Settings not implemented yet.'; }
async function loadLogs() { document.getElementById('logs-content').innerHTML = 'Logs not implemented yet.'; }

// --- Restored Functions ---

async function loadRolesTab() {
    console.log('Loading roles...');
    try {
        const data = await apiCall(`/api/${currentServerId}/roles`);
        const rolesList = document.getElementById('roles-list');

        if (!rolesList) return;

        if (data && data.roles && data.roles.length > 0) {
            let html = '<div class="roles-grid">';
            data.roles.forEach(role => {
                const colorStyle = role.color ? `style="border-left: 4px solid #${role.color.toString(16).padStart(6, '0')}"` : '';
                const memberBadge = role.member_count ? `<span class="badge badge-info">${role.member_count} members</span>` : '';
                const mentionableBadge = role.mentionable ? '<span class="badge badge-success">Mentionable</span>' : '<span class="badge badge-secondary">Not Mentionable</span>';

                html += `
                    <div class="role-card" ${colorStyle}>
                        <div class="role-header">
                            <h4 class="role-name">${role.name}</h4>
                            <div class="role-badges">
                                ${memberBadge}
                                ${mentionableBadge}
                            </div>
                        </div>
                        <div class="role-info">
                            <div class="role-detail">
                                <span class="label">ID:</span>
                                <span class="value">${role.id}</span>
                            </div>
                            <div class="role-detail">
                                <span class="label">Position:</span>
                                <span class="value">${role.position}</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            rolesList.innerHTML = html;
        } else {
            rolesList.innerHTML = '<p class="text-center">No roles found. Make sure the bot is running.</p>';
        }
    } catch (error) {
        console.error('Failed to load roles:', error);
        showNotification('Failed to load roles', 'error');
    }
}

async function loadModerationTab() {
    console.log('Loading moderation settings...');
    const moderationContent = document.getElementById('moderation-content');

    if (!moderationContent) return;

    try {
        // Load channels for moderation options
        const channels = await apiCall(`/api/${currentServerId}/channels`);

        let html = '<div class="moderation-grid">';

        // Moderation Actions
        html += `
            <div class="card">
                <h3>⚡ Quick Actions</h3>
                <div class="quick-actions">
                    <button class="btn-action warning" onclick="clearCache()">Clear Cache</button>
                    <button class="btn-action info" onclick="syncData()">Sync Data</button>
                    <button class="btn-action success" onclick="validateIntegrity()">Validate Integrity</button>
                </div>
            </div>

            <div class="card">
                <h3>🚫 Strikes & Warnings</h3>
                <p>Manage user violations and automated moderation responses.</p>
                <button class="btn btn-primary" onclick="showStrikeManager()">Manage Strikes</button>
            </div>

            <div class="card">
                <h3>⏰ Scheduled Jobs</h3>
                <p>Automate moderation tasks like unbans and cleanups.</p>
                <button class="btn btn-primary" onclick="showScheduledJobs()">View Jobs</button>
            </div>
        `;

        html += '</div>';

        moderationContent.innerHTML = html;
    } catch (error) {
        console.error('Failed to load moderation settings:', error);
        showNotification('Failed to load moderation settings', 'error');
    }
}

async function loadPermissionsTab() {
    console.log('Loading permissions...');
    const permissionsContent = document.getElementById('permissions-content');

    if (!permissionsContent) return;

    try {
        // Load roles and channels for permissions setup
        const [roles, channels] = await Promise.all([
            apiCall(`/api/${currentServerId}/roles`),
            apiCall(`/api/${currentServerId}/channels`)
        ]);

        let html = '<div class="permissions-setup">';

        if (roles && roles.roles && roles.roles.length > 0) {
            html += `
                <div class="section-card">
                    <h3>👥 Role Permissions</h3>
                    <p>Configure which roles have access to specific features.</p>
                    <div class="role-permissions-list">
            `;

            roles.roles.slice(0, 5).forEach(role => {
                const colorStyle = role.color ? `style="background: #${role.color.toString(16).padStart(6, '0')}"` : '';
                html += `
                    <div class="role-item">
                        <div class="role-info">
                            <div class="role-header">
                                <span class="role-name">${role.name}</span>
                                <span class="role-member-count">${role.member_count || 0} members</span>
                            </div>
                        </div>
                        <div class="role-perm-controls">
                            <div class="perm-checkbox">
                                <input type="checkbox" id="admin-${role.id}" ${role.permissions & 8 ? 'checked' : ''}>
                                <label for="admin-${role.id}">Administrator</label>
                            </div>
                            <div class="perm-checkbox">
                                <input type="checkbox" id="manage-${role.id}" ${role.permissions & 32 ? 'checked' : ''}>
                                <label for="manage-${role.id}">Manage Server</label>
                            </div>
                            <div class="perm-checkbox">
                                <input type="checkbox" id="moderate-${role.id}" ${role.permissions & 8192 ? 'checked' : ''}>
                                <label for="moderate-${role.id}">Moderate Members</label>
                            </div>
                        </div>
                    </div>
                `;
            });

            html += `
                    </div>
                </div>
            `;
        }

        html += `
            <div class="section-card">
                <h3>💬 Channel Permissions</h3>
                <p>Control bot access and user permissions in different channels.</p>
                <button class="btn btn-primary" onclick="configureChannelPermissions()">Configure Channels</button>
            </div>
        `;

        html += '</div>';

        permissionsContent.innerHTML = html;
    } catch (error) {
        console.error('Failed to load permissions:', error);
        showNotification('Failed to load permissions', 'error');
    }
}
