// Discord Bot CMS Dashboard JavaScript

// API Configuration - UPDATE THIS WITH YOUR RAILWAY BACKEND URL
const API_BASE_URL = 'https://your-railway-app.railway.app'; // Replace with your actual Railway URL

// Helper function to build API URLs
function apiUrl(endpoint) {
    return `${API_BASE_URL}${endpoint}`;
}

// Global variables
let currentTab = 'overview';
let botStatus = 'offline';
let uptimeStart = Date.now();
let currentServerId = null;
let servers = [];

// Authentication variables
let authToken = null;
let refreshToken = null;
let isAuthenticated = false;
let currentUser = null;

// Error handling functions
function showError(message, details = null) {
    const errorDiv = document.getElementById('error-notification');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    }

    // Log to console for debugging
    console.error('Error:', message, details);

    // Also show in notification system if available
    if (typeof showNotification === 'function') {
        showNotification(`❌ ${message}`, 'error');
    }
}

function showSuccess(message) {
    const successDiv = document.getElementById('success-notification');
    if (successDiv) {
        successDiv.textContent = message;
        successDiv.style.display = 'block';
        setTimeout(() => {
            successDiv.style.display = 'none';
        }, 3000);
    }

    // Also show in notification system if available
    if (typeof showNotification === 'function') {
        showNotification(`✅ ${message}`, 'success');
    }
}

// Global error handler for unhandled errors
window.addEventListener('error', function(e) {
    showError(`JavaScript Error: ${e.message}`, {
        filename: e.filename,
        lineno: e.lineno,
        colno: e.colno,
        error: e.error
    });
});

// Global error handler for unhandled promise rejections
window.addEventListener('unhandledrejection', function(e) {
    showError(`Unhandled Promise Rejection: ${e.reason}`, e.reason);
});

// Authentication functions
function initAuth() {
    // Check for existing tokens in cookies
    authToken = getCookie('auth_token');
    refreshToken = getCookie('refresh_token');

    if (authToken) {
        // Validate token and set authenticated state
        validateToken();
    } else {
        // Show login screen
        showLoginScreen();
    }
}

function showLoginScreen() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('main-dashboard').style.display = 'none';
    isAuthenticated = false;
}

function hideLoginScreen() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('main-dashboard').style.display = 'flex';
    isAuthenticated = true;
}

async function login(event) {
    event.preventDefault();

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();

    if (!username || !password) {
        showLoginError('Please enter both username and password');
        return;
    }

    try {
        showLoginError(''); // Clear any previous errors

        const response = await fetch(apiUrl('/api/auth/login'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok && data.user) {
            // Tokens are stored in HTTP-only cookies by the backend
            // We don't have access to them in JavaScript for security
            currentUser = data.user;

            // Set cookies
            setCookie('auth_token', authToken, 1); // 1 hour
            if (refreshToken) {
                setCookie('refresh_token', refreshToken, 7); // 7 days
            }

            // Hide login screen and show dashboard
            hideLoginScreen();

            // Initialize dashboard
            initializeDashboard();

            showNotification('✅ Login successful!', 'success');
        } else {
            showLoginError(data.error || 'Login failed');
        }
    } catch (error) {
        console.error('Login error:', error);
        showLoginError('Network error. Please try again.');
    }
}

function showLoginError(message) {
    const errorElement = document.getElementById('login-error');
    if (message) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    } else {
        errorElement.style.display = 'none';
    }
}

async function logout() {
    try {
        // Call logout endpoint if available
        if (authToken) {
            await fetch(apiUrl('/api/auth/logout'), {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            });
        }
    } catch (error) {
        console.error('Logout error:', error);
    }

    // Clear tokens and cookies
    authToken = null;
    refreshToken = null;
    currentUser = null;
    isAuthenticated = false;

    // Clear cookies
    deleteCookie('auth_token');
    deleteCookie('refresh_token');

    // Show login screen
    showLoginScreen();

    showNotification('👋 Logged out successfully', 'info');
}

async function validateToken() {
    if (!authToken) {
        showLoginScreen();
        return;
    }

    try {
        const response = await fetch(apiUrl('/api/auth/validate'), {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            isAuthenticated = true;
            hideLoginScreen();
            initializeDashboard();
        } else {
            // Token invalid, try refresh
            await refreshAccessToken();
        }
    } catch (error) {
        console.error('Token validation error:', error);
        await refreshAccessToken();
    }
}

async function refreshAccessToken() {
    if (!refreshToken) {
        showLoginScreen();
        return;
    }

    try {
        const response = await fetch(apiUrl('/api/auth/refresh'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh_token: refreshToken })
        });

        const data = await response.json();

        if (response.ok && data.access_token) {
            authToken = data.access_token;
            setCookie('auth_token', authToken, 1);
            await validateToken();
        } else {
            // Refresh failed, show login
            showLoginScreen();
        }
    } catch (error) {
        console.error('Token refresh error:', error);
        showLoginScreen();
    }
}

// Cookie utility functions
function setCookie(name, value, hours) {
    const expires = new Date();
    expires.setTime(expires.getTime() + hours * 60 * 60 * 1000);
    document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Strict;Secure`;
}

function getCookie(name) {
    const nameEQ = name + '=';
    const ca = document.cookie.split(';');
    for (let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) === ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}

function deleteCookie(name) {
    document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=Strict;Secure`;
}

// Authenticated fetch wrapper
async function authenticatedFetch(url, options = {}) {
    if (!isAuthenticated || !authToken) {
        throw new Error('Not authenticated');
    }

    const headers = {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json',
        ...options.headers
    };

    const response = await fetch(url, { ...options, headers });

    // If unauthorized, try to refresh token
    if (response.status === 401) {
        await refreshAccessToken();
        if (isAuthenticated) {
            // Retry with new token
            headers.Authorization = `Bearer ${authToken}`;
            return fetch(url, { ...options, headers });
        }
    }

    return response;
}

// Utility functions
function showLoading(section) {
    const container = document.getElementById(`${section}-list`) || document.getElementById(section);
    if (container) {
        container.innerHTML = '<div class="loading">Loading...</div>';
    }
}

function hideLoading(section) {
    // Loading is hidden when content is replaced
}

function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container');
    if (!container) return;

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" class="notification-close">×</button>
    `;

    container.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// Tab switching functionality
function showTab(tabName) {
    // Hide all tabs
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => tab.classList.remove('active'));

    // Remove active class from all buttons
    const buttons = document.querySelectorAll('.tab-button');
    buttons.forEach(button => button.classList.remove('active'));

    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
    currentTab = tabName;

    // Load data for the tab
    loadTabData(tabName);
}

// Load data for specific tabs
async function loadTabData(tabName) {
    switch(tabName) {
        case 'overview':
            await loadOverviewData();
            break;
        case 'tasks':
            await loadTasks();
            break;
        case 'logs':
            await loadLogs();
            break;
        case 'commands':
            await loadCommands();
            break;
        case 'shop':
            await loadShopItems();
            break;
        case 'users':
            await loadUsers();
            // Initialize user selector when users tab is loaded
            initializeUserSelector();
            break;
        case 'settings':
            await loadSettings();
            break;
        case 'transactions':
            await loadTransactions();
            break;
    }
}

// Load overview data
async function loadOverviewData() {
    try {
        const response = await fetch(apiUrl('/api/status'));
        const data = await response.json();

        // Update dashboard content with overview data
        const dashboardContent = document.getElementById('dashboard-content');
        if (dashboardContent) {
            dashboardContent.innerHTML = `
                <div class="overview-stats">
                    <div class="stat-card">
                        <h3>Bot Status</h3>
                        <div class="status-indicator ${data.botOnline ? 'online' : 'offline'}">
                            ${data.botOnline ? '🟢 Online' : '🔴 Offline'}
                        </div>
                    </div>
                    <div class="stat-card">
                        <h3>Uptime</h3>
                        <div class="stat-value">${formatUptime(data.uptime)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Servers</h3>
                        <div class="stat-value">${data.servers || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Users</h3>
                        <div class="stat-value">${data.users || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Commands Used</h3>
                        <div class="stat-value">${data.commandsUsed || 0}</div>
                    </div>
                </div>
            `;
        }

        updateStatusDisplay(data.botOnline);
    } catch (error) {
        console.error('Error loading overview data:', error);
        const dashboardContent = document.getElementById('dashboard-content');
        if (dashboardContent) {
            dashboardContent.innerHTML = '<div class="error-state">Error loading dashboard data</div>';
        }
    }
}

// Load logs
async function loadLogs() {
    try {
        const logLevel = document.getElementById('log-level').value;
        const response = await fetch(apiUrl(`/api/logs?level=${logLevel}`));
        const logs = await response.json();

        const logContainer = document.getElementById('logs-content');
        logContainer.innerHTML = '';

        logs.forEach(log => {
            const logEntry = document.createElement('div');
            logEntry.className = `log-entry log-${log.level}`;
            logEntry.textContent = `[${log.timestamp}] ${log.level.toUpperCase()}: ${log.message}`;
            logContainer.appendChild(logEntry);
        });
    } catch (error) {
        console.error('Error loading logs:', error);
    }
}

// Load commands
async function loadCommands() {
    try {
        const response = await fetch(apiUrl('/api/commands'));
        const commands = await response.json();

        const commandList = document.getElementById('command-list');
        commandList.innerHTML = '';

        commands.forEach(cmd => {
            const cmdDiv = document.createElement('div');
            cmdDiv.className = 'command-item';
            cmdDiv.innerHTML = `
                <h4>${cmd.name}</h4>
                <p>${cmd.response}</p>
                <button onclick="deleteCommand('${cmd.name}')">Delete</button>
            `;
            commandList.appendChild(cmdDiv);
        });
    } catch (error) {
        console.error('Error loading commands:', error);
    }

    // Also load available bot commands
    loadAvailableCommands();
}

// Load available bot commands
function loadAvailableCommands() {
    const availableCommands = [
        // Slash Commands (Primary)
        { name: '/balance [user]', description: 'Check your balance or another user\'s balance', category: 'Currency' },
        { name: '/shop', description: 'Browse and purchase items from the shop', category: 'Shop' },
        { name: '/inventory [user]', description: 'View your inventory or another user\'s inventory', category: 'Shop' },
        { name: '/embed [title] [description] [color]', description: 'Create a rich embed message (Admin only)', category: 'Management' },
        { name: '/give_money user amount', description: 'Give currency to a user (Admin only)', category: 'Currency' },
        { name: '/take_money user amount', description: 'Take currency from a user (Admin only)', category: 'Currency' },
        { name: '/close_task name', description: 'Manually close a task (Admin only)', category: 'Management' },
        { name: '/announce channel message', description: 'Send an announcement to a channel (Admin only)', category: 'Management' },
        { name: '/add_command name response', description: 'Add a custom command (Admin only)', category: 'Management' },
        { name: '/remove_command name', description: 'Remove a custom command (Admin only)', category: 'Management' },

        // Traditional Prefix Commands
        { name: '/balance [@user]', description: 'Check your balance or another user\'s balance', category: 'Currency' },
        { name: '/give_money @user amount', description: 'Give currency to a user (Admin only)', category: 'Currency' },
        { name: '/take_money @user amount', description: 'Take currency from a user (Admin only)', category: 'Currency' },
        { name: '/shop', description: 'Browse and purchase items from the shop with buttons', category: 'Shop' },
        { name: '/buy item_id', description: 'Purchase a specific item from the shop', category: 'Shop' },
        { name: '/inventory [@user]', description: 'View your inventory or another user\'s inventory', category: 'Shop' },
        { name: '/embed [title] [description] [color] [fields]', description: 'Create a rich embed message (Admin only)', category: 'Management' },
        { name: '/announce #channel message', description: 'Send an announcement to a channel (Admin only)', category: 'Management' },
        { name: '/close_task task_name', description: 'Manually close a task (Admin only)', category: 'Management' },
        { name: '/add_command name response', description: 'Add a custom command (Admin only)', category: 'Management' },
        { name: '/remove_command name', description: 'Remove a custom command (Admin only)', category: 'Management' }
    ];

    const commandGrid = document.getElementById('available-commands');
    commandGrid.innerHTML = '';

    availableCommands.forEach(cmd => {
        const cmdDiv = document.createElement('div');
        cmdDiv.className = 'command-card';
        cmdDiv.innerHTML = `
            <div class="command-name">${cmd.name}</div>
            <div class="command-description">${cmd.description}</div>
            <div class="command-category">${cmd.category}</div>
        `;
        commandGrid.appendChild(cmdDiv);
    });
}

// Load settings
async function loadSettings() {
    try {
        const container = document.getElementById('settings-content');
        if (!container) return;

        let html = '<div class="settings-sections">';

        // Global Settings
        const globalResponse = await fetch(apiUrl('/api/settings'));
        const globalSettings = await globalResponse.json();

        html += `
            <div class="settings-section">
                <h3>Global Settings</h3>
                <div class="settings-grid">
        `;

        Object.entries(globalSettings).forEach(([key, value]) => {
            const displayName = key.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            html += `
                <div class="setting-item">
                    <label>
                        <input type="checkbox" id="${key}" ${value ? 'checked' : ''}>
                        ${displayName}
                    </label>
                </div>
            `;
        });

        html += '</div></div>';

        // Server-specific Settings
        if (currentServerId) {
            const serverResponse = await fetch(`/api/${currentServerId}/config`);
            const serverConfig = await serverResponse.json();

            html += `
                <div class="settings-section">
                    <h3>Server Settings</h3>
                    <div class="settings-grid">
                        <div class="setting-item">
                            <label>
                                <input type="checkbox" id="global_shop" ${serverConfig.global_shop ? 'checked' : ''}>
                                Global Shop (Show items in all channels)
                            </label>
                        </div>
                        <div class="setting-item">
                            <label>
                                <input type="checkbox" id="global_tasks" ${serverConfig.global_tasks ? 'checked' : ''}>
                                Global Tasks (Show tasks in all channels)
                            </label>
                        </div>
                    </div>
                </div>
            `;
        } else {
            html += '<p>Please select a server to view server-specific settings.</p>';
        }

        html += '</div>';
        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading settings:', error);
        const container = document.getElementById('settings-content');
        if (container) {
            container.innerHTML = '<div class="error-state">Error loading settings</div>';
        }
    }
}

// Update status display in UI
function updateStatusDisplay(isOnline) {
    const statusElement = document.getElementById('bot-status');
    if (isOnline) {
        statusElement.textContent = 'Bot Status: Online';
        statusElement.className = 'status online';
        botStatus = 'online';
    } else {
        statusElement.textContent = 'Bot Status: Offline';
        statusElement.className = 'status offline';
        botStatus = 'offline';
    }
}

// Format uptime
function formatUptime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Quick actions
async function restartBot() {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (confirm('Are you sure you want to restart the bot?')) {
        try {
            const response = await fetch(`/api/restart?server_id=${currentServerId}`, { method: 'POST' });
            if (response.ok) {
                alert('Bot restart initiated successfully');
                updateStatusDisplay(false);
                // Refresh status after a short delay
                setTimeout(() => {
                    loadOverviewData();
                }, 3000);
            } else {
                const error = await response.json();
                alert('Failed to restart bot: ' + (error.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error restarting bot:', error);
            alert('Error restarting bot');
        }
    }
}

async function clearLogs() {
    if (confirm('Are you sure you want to clear all logs?')) {
        try {
            const response = await fetch(apiUrl('/api/logs'), { method: 'DELETE' });
            if (response.ok) {
                alert('Logs cleared');
                loadLogs();
            } else {
                alert('Failed to clear logs');
            }
        } catch (error) {
            console.error('Error clearing logs:', error);
            alert('Error clearing logs');
        }
    }
}

async function exportData() {
    try {
        const response = await fetch(apiUrl('/api/export'));
        const data = await response.json();

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'bot-data-export.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Error exporting data:', error);
        alert('Error exporting data');
    }
}

// Command management
async function addCommand() {
    const name = document.getElementById('cmd-name').value.trim();
    const response = document.getElementById('cmd-response').value.trim();

    if (!name || !response) {
        alert('Please fill in both command name and response');
        return;
    }

    try {
        const result = await fetch(apiUrl('/api/commands'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, response })
        });

        if (result.ok) {
            alert('Command added successfully');
            document.getElementById('cmd-name').value = '';
            document.getElementById('cmd-response').value = '';
            loadCommands(); // Refresh the commands list
        } else {
            const error = await result.json();
            alert('Failed to add command: ' + (error.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error adding command:', error);
        alert('Error adding command');
    }
}

async function deleteCommand(name) {
    if (confirm(`Are you sure you want to delete the command "${name}"?`)) {
        try {
            const response = await fetch(`/api/commands/${name}`, { method: 'DELETE' });
            if (response.ok) {
                alert('Command deleted');
                loadCommands();
            } else {
                alert('Failed to delete command');
            }
        } catch (error) {
            console.error('Error deleting command:', error);
            alert('Error deleting command');
        }
    }
}

// Settings management
async function saveSettings() {
    const settings = {};
    const checkboxes = document.querySelectorAll('#settings input[type="checkbox"]');

    checkboxes.forEach(checkbox => {
        settings[checkbox.id] = checkbox.checked;
    });

    try {
        // Save global settings
        const globalResponse = await fetch(apiUrl('/api/settings'), {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        let serverResponse = null;
        if (currentServerId) {
            // Save server-specific settings
            const serverSettings = {};
            if (settings.global_shop !== undefined) serverSettings.global_shop = settings.global_shop;
            if (settings.global_tasks !== undefined) serverSettings.global_tasks = settings.global_tasks;

            serverResponse = await fetch(`/api/${currentServerId}/config`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(serverSettings)
            });
        }

        if (globalResponse.ok && (!serverResponse || serverResponse.ok)) {
            alert('Settings saved successfully');
        } else {
            alert('Failed to save some settings');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        alert('Error saving settings');
    }
}

// Load tasks with enhanced UI and real-time updates
async function loadTasks() {
    if (!currentServerId) {
        const tasksList = document.getElementById('tasks-list');
        if (tasksList) {
            tasksList.innerHTML = '<p>Please select a server first.</p>';
        }
        return;
    }

    try {
        showLoading('tasks');

        const response = await fetch(`/api/${currentServerId}/tasks`);
        const tasks = await response.json();

        const tasksList = document.getElementById('tasks-list');
        if (!tasksList) return;

        tasksList.innerHTML = '';

        if (tasks.length === 0) {
            tasksList.innerHTML = '<div class="empty-state">No tasks found for this server. <button onclick="showCreateTaskModal()" class="btn-primary">Create First Task</button></div>';
            hideLoading('tasks');
            return;
        }

        // Create tasks grid
        const tasksGrid = document.createElement('div');
        tasksGrid.className = 'tasks-grid';

        tasks.forEach(task => {
            const taskCard = createTaskCard(task);
            tasksGrid.appendChild(taskCard);
        });

        tasksList.appendChild(tasksGrid);
        hideLoading('tasks');

    } catch (error) {
        console.error('Error loading tasks:', error);
        const tasksList = document.getElementById('tasks-list');
        if (tasksList) {
            tasksList.innerHTML = '<div class="error-state">Error loading tasks. Please try again.</div>';
        }
        hideLoading('tasks');
    }
}

// Create task card with interactive elements
function createTaskCard(task) {
    const card = document.createElement('div');
    card.className = `task-card ${task.status}`;
    card.dataset.taskId = task.id;

    const durationText = task.duration_hours === -1 ? '♾️ No limit' : `⏰ ${task.duration_hours} hours`;
    const statusEmoji = {
        'active': '🟢',
        'pending': '🟡',
        'completed': '✅',
        'expired': '⏰',
        'cancelled': '❌'
    };

    const statusText = `${statusEmoji[task.status] || '⚪'} ${task.status.charAt(0).toUpperCase() + task.status.slice(1)}`;
    const claimsText = task.max_claims === -1 ?
        `👥 ${task.current_claims} claimed (unlimited)` :
        `👥 ${task.current_claims}/${task.max_claims} claimed`;

    let actionButtons = '';

    // Add appropriate action buttons based on task status and user permissions
    if (task.status === 'active') {
        actionButtons = `
            <button onclick="claimTask('${task.id}')" class="btn-primary btn-small" title="Claim this task">
                ✋ Claim Task
            </button>
        `;
    }

    // Admin actions (simplified - in real implementation would check permissions)
    actionButtons += `
        <button onclick="editTask('${task.id}')" class="btn-secondary btn-small" title="Edit task">
            ✏️ Edit
        </button>
        <button onclick="deleteTask('${task.id}')" class="btn-danger btn-small" title="Delete task">
            🗑️ Delete
        </button>
    `;

    card.innerHTML = `
        <div class="task-header">
            <div class="task-title-section">
                <h4 class="task-name">${escapeHtml(task.name)}</h4>
                <span class="task-status">${statusText}</span>
            </div>
            <div class="task-actions">
                ${actionButtons}
            </div>
        </div>

        <div class="task-description">
            <p>${escapeHtml(task.description)}</p>
        </div>

        <div class="task-details">
            <div class="task-reward">
                <span class="detail-label">💰 Reward:</span>
                <span class="detail-value">$${task.reward}</span>
            </div>
            <div class="task-duration">
                <span class="detail-label">Duration:</span>
                <span class="detail-value">${durationText}</span>
            </div>
            <div class="task-claims">
                <span class="detail-label">Claims:</span>
                <span class="detail-value">${claimsText}</span>
            </div>
        </div>

        ${task.url ? `
            <div class="task-link">
                <span class="detail-label">🔗 Link:</span>
                <a href="${task.url}" target="_blank" class="task-url">${task.url}</a>
            </div>
        ` : ''}

        <div class="task-meta">
            <span class="task-id">ID: <code>${task.id}</code></span>
            ${task.expires_at ? `<span class="task-expires">Expires: <t:${Math.floor(new Date(task.expires_at).getTime() / 1000)}:R></t>` : ''}
        </div>
    `;

    return card;
}

// Claim task via dashboard
async function claimTask(taskId) {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        showNotification('🔄 Claiming task...', 'info');

        // In a real implementation, this would use the Discord bot's API
        // For now, simulate the claim process
        const response = await fetch(`/api/${currentServerId}/tasks/${taskId}/claim`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: 'dashboard_user', // In real implementation, get from session
                channel_id: 'dashboard' // Indicate this came from dashboard
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to claim task');
        }

        const result = await response.json();

        showNotification('✅ Task claimed successfully!', 'success');

        // Refresh tasks to show updated status
        await loadTasks();

        // If there's a deadline, show reminder
        if (result.deadline) {
            const deadline = new Date(result.deadline);
            showNotification(`⏰ Task deadline: ${deadline.toLocaleString()}`, 'info');
        }

    } catch (error) {
        console.error('Error claiming task:', error);
        showNotification(`❌ Failed to claim task: ${error.message}`, 'error');
    }
}

// Complete task via dashboard
async function completeTask(taskId) {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    // Get completion details
    const proof = prompt('Please provide proof of completion (optional):');
    if (proof === null) return; // User cancelled

    try {
        showNotification('🔄 Completing task...', 'info');

        const response = await fetch(`/api/${currentServerId}/tasks/${taskId}/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: 'dashboard_user', // In real implementation, get from session
                proof: proof.trim(),
                channel_id: 'dashboard'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to complete task');
        }

        const result = await response.json();

        showNotification(`✅ Task completed! You earned $${result.reward}!`, 'success');

        // Refresh tasks and user data
        await loadTasks();
        if (currentTab === 'users') {
            await loadUsers();
        }

    } catch (error) {
        console.error('Error completing task:', error);
        showNotification(`❌ Failed to complete task: ${error.message}`, 'error');
    }
}

// Show create task modal
function showCreateTaskModal() {
    showModal(`
        <h2>Create New Task</h2>
        <form id="create-task-form" onsubmit="createTask(event)">
            <div class="form-group">
                <label>Name *</label>
                <input type="text" id="task-name" required maxlength="100" placeholder="Task name">
            </div>

            <div class="form-group">
                <label>Description *</label>
                <textarea id="task-description" required rows="3" maxlength="1000" placeholder="Task description"></textarea>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Reward *</label>
                    <input type="number" id="task-reward" required min="0" step="0.01" placeholder="0.00">
                </div>
                <div class="form-group">
                    <label>Duration (hours)</label>
                    <input type="number" id="task-duration" min="-1" value="24" placeholder="-1 for no limit">
                    <small>Use -1 for unlimited time</small>
                </div>
            </div>

            <div class="form-group">
                <label>URL (optional)</label>
                <input type="url" id="task-url" placeholder="https://example.com/task-link">
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Max Claims</label>
                    <input type="number" id="task-max-claims" min="-1" value="-1" placeholder="-1 for unlimited">
                </div>
                <div class="form-group">
                    <label>Channel ID *</label>
                    <input type="text" id="task-channel-id" required placeholder="Discord channel ID">
                </div>
            </div>

            <div class="form-group checkbox-group">
                <label>
                    <input type="checkbox" id="task-post-announcement" checked>
                    Post announcement when task is created
                </label>
            </div>

            <div class="form-actions">
                <button type="submit" class="btn-primary">Create Task</button>
                <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
            </div>
        </form>
    `);
}

// Create task
async function createTask(event) {
    event.preventDefault();

    const taskData = {
        name: document.getElementById('task-name').value.trim(),
        description: document.getElementById('task-description').value.trim(),
        reward: parseFloat(document.getElementById('task-reward').value),
        duration_hours: parseInt(document.getElementById('task-duration').value),
        url: document.getElementById('task-url').value.trim() || '',
        max_claims: parseInt(document.getElementById('task-max-claims').value),
        channel_id: document.getElementById('task-channel-id').value.trim(),
        post_announcement: document.getElementById('task-post-announcement').checked
    };

    // Validation
    if (taskData.reward < 0) {
        showNotification('Reward cannot be negative', 'error');
        return;
    }

    if (taskData.duration_hours < -1) {
        showNotification('Duration cannot be less than -1', 'error');
        return;
    }

    if (taskData.max_claims < -1) {
        showNotification('Max claims cannot be less than -1', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(taskData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create task');
        }

        const result = await response.json();

        closeModal();
        showNotification('✅ Task created successfully!', 'success');
        await loadTasks();

    } catch (error) {
        console.error('Error creating task:', error);
        showNotification(`❌ Failed to create task: ${error.message}`, 'error');
    }
}

// Edit task
async function editTask(taskId) {
    try {
        // Get current task data
        const response = await fetch(`/api/${currentServerId}/tasks`);
        const tasks = await response.json();
        const task = tasks.find(t => t.id == taskId);

        if (!task) {
            throw new Error('Task not found');
        }

        showModal(`
            <h2>Edit Task</h2>
            <form id="edit-task-form" onsubmit="updateTask(event, '${taskId}')">
                <div class="form-group">
                    <label>Name *</label>
                    <input type="text" id="edit-task-name" required maxlength="100" value="${escapeHtml(task.name)}">
                </div>

                <div class="form-group">
                    <label>Description *</label>
                    <textarea id="edit-task-description" required rows="3" maxlength="1000">${escapeHtml(task.description)}</textarea>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>Reward *</label>
                        <input type="number" id="edit-task-reward" required min="0" step="0.01" value="${task.reward}">
                    </div>
                    <div class="form-group">
                        <label>Duration (hours)</label>
                        <input type="number" id="edit-task-duration" min="-1" value="${task.duration_hours}" placeholder="-1 for no limit">
                    </div>
                </div>

                <div class="form-group">
                    <label>URL (optional)</label>
                    <input type="url" id="edit-task-url" value="${task.url || ''}">
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>Max Claims</label>
                        <input type="number" id="edit-task-max-claims" min="-1" value="${task.max_claims}">
                    </div>
                    <div class="form-group">
                        <label>Status</label>
                        <select id="edit-task-status">
                            <option value="active" ${task.status === 'active' ? 'selected' : ''}>Active</option>
                            <option value="pending" ${task.status === 'pending' ? 'selected' : ''}>Pending</option>
                            <option value="cancelled" ${task.status === 'cancelled' ? 'selected' : ''}>Cancelled</option>
                        </select>
                    </div>
                </div>

                <div class="form-actions">
                    <button type="submit" class="btn-primary">Update Task</button>
                    <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
                </div>
            </form>
        `);

    } catch (error) {
        console.error('Error loading task for edit:', error);
        showNotification('❌ Failed to load task for editing', 'error');
    }
}

// Update task
async function updateTask(event, taskId) {
    event.preventDefault();

    const updates = {
        name: document.getElementById('edit-task-name').value.trim(),
        description: document.getElementById('edit-task-description').value.trim(),
        reward: parseFloat(document.getElementById('edit-task-reward').value),
        duration_hours: parseInt(document.getElementById('edit-task-duration').value),
        url: document.getElementById('edit-task-url').value.trim(),
        max_claims: parseInt(document.getElementById('edit-task-max-claims').value),
        status: document.getElementById('edit-task-status').value
    };

    // Validation
    if (updates.reward < 0) {
        showNotification('Reward cannot be negative', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/tasks/${taskId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to update task');
        }

        const result = await response.json();

        closeModal();
        showNotification('✅ Task updated successfully!', 'success');
        await loadTasks();

    } catch (error) {
        console.error('Error updating task:', error);
        showNotification(`❌ Failed to update task: ${error.message}`, 'error');
    }
}

// Real-time task updates via SSE
function handleTaskUpdate(updateData) {
    console.log('Task update received:', updateData);

    // Update task status in UI if task tab is active
    if (currentTab === 'tasks' && updateData.task_id) {
        const taskCard = document.querySelector(`.task-card[data-task-id="${updateData.task_id}"]`);
        if (taskCard) {
            // Update status indicator
            const statusElement = taskCard.querySelector('.task-status');
            if (statusElement && updateData.status) {
                const statusEmoji = {
                    'active': '🟢',
                    'pending': '🟡',
                    'completed': '✅',
                    'expired': '⏰',
                    'cancelled': '❌'
                };
                statusElement.textContent = `${statusEmoji[updateData.status] || '⚪'} ${updateData.status.charAt(0).toUpperCase() + updateData.status.slice(1)}`;
            }

            // Update claims count if provided
            if (updateData.current_claims !== undefined) {
                const claimsElement = taskCard.querySelector('.task-claims .detail-value');
                if (claimsElement) {
                    const maxClaims = updateData.max_claims || -1;
                    const claimsText = maxClaims === -1 ?
                        `👥 ${updateData.current_claims} claimed (unlimited)` :
                        `👥 ${updateData.current_claims}/${maxClaims} claimed`;
                    claimsElement.textContent = claimsText;
                }
            }

            // Update card class for styling
            taskCard.className = `task-card ${updateData.status || 'active'}`;

            // Show notification for status changes
            if (updateData.status === 'completed') {
                showNotification(`✅ Task "${updateData.name || 'Unknown'}" has been completed!`, 'success');
            } else if (updateData.status === 'expired') {
                showNotification(`⏰ Task "${updateData.name || 'Unknown'}" has expired.`, 'warning');
            }
        }
    }

    // Update user balance if currency changed
    if (updateData.balance_change && currentTab === 'users') {
        // This would trigger a user data refresh
        loadUsers();
    }
}

// Global variables for user management
let selectedUser = null;
let currentServer = null;

// User selection functionality
function initUsersList() {
    // Add click event listeners to user table rows after they are loaded
    document.querySelectorAll('#users-table-body tr').forEach(row => {
        row.addEventListener('click', function(e) {
            const userId = this.dataset.userId;
            if (userId) {
                selectUser(userId);
            }
        });
    });
}

async function openUserProfileModal(userId, username) {
    try {
        // Fetch complete user data
        const response = await authenticatedFetch(`/api/${currentServerId}/users/${userId}`);
        const userData = await response.json();

        // Fetch user's tasks
        const tasksResponse = await authenticatedFetch(`/api/${currentServerId}/users/${userId}/tasks`);
        const userTasks = await tasksResponse.json();

        // Fetch user's inventory
        const inventoryResponse = await authenticatedFetch(`/api/${currentServerId}/inventory/${userId}`);
        const inventory = await inventoryResponse.json();

        // Fetch user's transactions
        const transactionsResponse = await authenticatedFetch(`/api/${currentServerId}/transactions?user_id=${userId}&limit=10`);
        const transactions = await transactionsResponse.json();

        // Build and show modal
        showUserProfileModal({
            user: userData,
            tasks: userTasks,
            inventory: inventory,
            transactions: transactions
        });
    } catch (error) {
        console.error('Error loading user profile:', error);
        showNotification('Failed to load user profile', 'error');
    }
}

function showUserProfileModal(data) {
    const modal = document.createElement('div');
    modal.className = 'modal user-profile-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>${data.user.username}'s Profile</h2>
                <span class="close-modal">&times;</span>
            </div>

            <div class="modal-body">
                <div class="profile-section">
                    <h3>Balance Information</h3>
                    <div class="balance-info">
                        <p><strong>Current Balance:</strong> ${data.user.balance} coins</p>
                        <p><strong>Total Earned:</strong> ${data.user.total_earned} coins</p>
                        <p><strong>Total Spent:</strong> ${data.user.total_spent} coins</p>
                        <p><strong>Last Daily:</strong> ${formatDate(data.user.last_daily)}</p>
                    </div>
                    <button onclick="showBalanceModal('${data.user.user_id}')" class="btn-primary">Modify Balance</button>
                </div>

                <div class="profile-section">
                    <h3>Inventory (${data.inventory.items?.length || 0} items)</h3>
                    <div class="inventory-list">
                        ${data.inventory.items?.map(item => `
                            <div class="inventory-item">
                                <span class="item-emoji">${item.emoji}</span>
                                <span class="item-name">${item.name}</span>
                                <span class="item-quantity">x${item.quantity}</span>
                            </div>
                        `).join('') || '<p>No items</p>'}
                    </div>
                </div>

                <div class="profile-section">
                    <h3>Active Tasks (${data.tasks?.length || 0})</h3>
                    <div class="tasks-list">
                        ${data.tasks?.map(task => `
                            <div class="task-item">
                                <span class="task-name">${task.name}</span>
                                <span class="task-status">${task.status}</span>
                            </div>
                        `).join('') || '<p>No active tasks</p>'}
                    </div>
                </div>

                <div class="profile-section">
                    <h3>Recent Transactions</h3>
                    <div class="transactions-list">
                        ${data.transactions?.transactions?.map(txn => `
                            <div class="transaction-item">
                                <span class="txn-type">${txn.type}</span>
                                <span class="txn-amount ${txn.amount > 0 ? 'positive' : 'negative'}">${txn.amount > 0 ? '+' : ''}${txn.amount}</span>
                                <span class="txn-date">${formatDate(txn.timestamp)}</span>
                            </div>
                        `).join('') || '<p>No transactions</p>'}
                    </div>
                </div>

                <div class="profile-actions">
                    <button onclick="deactivateUser('${data.user.user_id}')" class="btn-warning">Deactivate User</button>
                    <button onclick="exportUserData('${data.user.user_id}')" class="btn-secondary">Export User Data</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    modal.querySelector('.close-modal').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

function showBalanceModal(userId) {
    showModal(`
        <h2>Modify Balance</h2>
        <form id="balance-form" onsubmit="modifyBalance(event, '${userId}')">
            <div class="form-group">
                <label>Amount:</label>
                <input type="number" id="balance-amount" required step="0.01">
                <small>Use positive numbers to add, negative to subtract</small>
            </div>
            <div class="form-group">
                <label>Reason:</label>
                <input type="text" id="balance-reason" required maxlength="100">
            </div>
            <div class="form-actions">
                <button type="submit" class="btn-primary">Update Balance</button>
                <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
            </div>
        </form>
    `);
}

async function modifyBalance(event, userId) {
    event.preventDefault();

    const amount = parseFloat(document.getElementById('balance-amount').value);
    const reason = document.getElementById('balance-reason').value.trim();

    if (!reason) {
        showNotification('Reason is required', 'error');
        return;
    }

    try {
        const response = await authenticatedFetch(`/api/${currentServerId}/users/${userId}/balance`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: amount,
                reason: reason
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to modify balance');
        }

        const result = await response.json();
        showNotification(`Balance updated successfully! New balance: ${result.balance_after}`, 'success');
        closeModal();

        // Refresh user list
        await loadUsers();

    } catch (error) {
        console.error('Error modifying balance:', error);
        showNotification(`Failed to modify balance: ${error.message}`, 'error');
    }
}

async function deactivateUser(userId) {
    if (!confirm('Are you sure you want to deactivate this user? This will prevent them from using the bot.')) {
        return;
    }

    try {
        const response = await authenticatedFetch(`/api/${currentServerId}/users/${userId}/deactivate`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to deactivate user');
        }

        showNotification('User deactivated successfully', 'success');
        await loadUsers();

    } catch (error) {
        console.error('Error deactivating user:', error);
        showNotification(`Failed to deactivate user: ${error.message}`, 'error');
    }
}

function formatDate(dateString) {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Global variables for lazy loading
let usersLazyLoader = null;
let currentUserPage = 1;
let hasMoreUsers = true;
let isLoadingUsers = false;
let allUsersData = []; // Cache for user selector

// Load users with lazy loading
async function loadUsers() {
    if (!currentServerId) {
        console.log('No server selected');
        return;
    }

    try {
        showLoading('users');

        // Reset pagination state
        currentUserPage = 1;
        hasMoreUsers = true;
        allUsersData = [];

        // Load first page
        const response = await fetch(`/api/${currentServerId}/users?page=1&per_page=50`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.users || data.users.length === 0) {
            document.getElementById('users-list').innerHTML =
                '<div class="empty-state">No users found in this server</div>';
            hideLoading('users');
            return;
        }

        // Cache all users for selector (load in background)
        loadAllUsersForSelector();

        // Display first page
        displayUserTable(data.users, data.total_balance || 0, false);

        // Initialize lazy loading
        hasMoreUsers = data.has_more;
        if (hasMoreUsers) {
            initializeUserLazyLoading();
        }

        // Initialize user selection functionality
        initUsersList();

        hideLoading('users');

    } catch (error) {
        console.error('Error loading users:', error);
        document.getElementById('users-list').innerHTML =
            `<div class="error-state">Error loading users: ${error.message}</div>`;
        hideLoading('users');
    }
}

// Load all users for selector dropdown (in background)
async function loadAllUsersForSelector() {
    try {
        const response = await fetch(`/api/${currentServerId}/users?page=1&per_page=1000`);
        if (response.ok) {
            const data = await response.json();
            allUsersData = data.users || [];
            updateUserSelector(allUsersData);
        }
    } catch (error) {
        console.error('Error loading users for selector:', error);
        // Fallback to current page users
        const currentUsers = Array.from(document.querySelectorAll('#users-list tr[data-user-id]'))
            .map(row => ({
                id: row.dataset.userId,
                display_name: row.querySelector('.user-name')?.textContent || 'Unknown',
                balance: parseInt(row.querySelector('.balance-amount')?.textContent || '0')
            }));
        updateUserSelector(currentUsers);
    }
}

// Initialize lazy loading for users
function initializeUserLazyLoading() {
    if (usersLazyLoader) {
        usersLazyLoader.disconnect();
    }

    usersLazyLoader = new IntersectionObserver(
        (entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && hasMoreUsers && !isLoadingUsers) {
                    loadNextUserPage();
                }
            });
        },
        {
            root: document.getElementById('users-list'),
            rootMargin: '100px',
            threshold: 0.1
        }
    );

    // Add sentinel element
    const sentinel = document.createElement('div');
    sentinel.id = 'users-sentinel';
    sentinel.className = 'loading-sentinel';
    sentinel.innerHTML = '<div class="loading-more">Loading more users...</div>';
    document.getElementById('users-list').appendChild(sentinel);

    usersLazyLoader.observe(sentinel);
}

// Load next page of users
async function loadNextUserPage() {
    if (isLoadingUsers || !hasMoreUsers) return;

    isLoadingUsers = true;
    currentUserPage++;

    try {
        const sentinel = document.getElementById('users-sentinel');
        if (sentinel) {
            sentinel.innerHTML = '<div class="loading-more">Loading more users...</div>';
        }

        const response = await fetch(`/api/${currentServerId}/users?page=${currentUserPage}&per_page=50`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.users && data.users.length > 0) {
            // Append new users to table
            appendUsersToTable(data.users);
            hasMoreUsers = data.has_more;
        } else {
            hasMoreUsers = false;
        }

        // Update sentinel
        if (!hasMoreUsers) {
            if (sentinel) {
                sentinel.innerHTML = '<div class="no-more">All users loaded</div>';
            }
        } else {
            if (sentinel) {
                sentinel.innerHTML = '<div class="loading-more">Scroll for more users...</div>';
            }
        }

    } catch (error) {
        console.error('Error loading next user page:', error);
        const sentinel = document.getElementById('users-sentinel');
        if (sentinel) {
            sentinel.innerHTML = '<div class="error-more">Failed to load more users</div>';
        }
    } finally {
        isLoadingUsers = false;
    }
}

// Append users to existing table
function appendUsersToTable(users) {
    const tbody = document.querySelector('#users-list tbody');
    if (!tbody) return;

    users.forEach(user => {
        const row = createUserTableRow(user);
        tbody.appendChild(row);
    });
}

// Create user table row helper function
function createUserTableRow(user) {
    const avatarUrl = user.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';
    const displayName = user.display_name || user.username || user.id;
    const balance = user.balance || 0;
    const earned = user.total_earned || 0;
    const spent = user.total_spent || 0;

    const row = document.createElement('tr');
    row.setAttribute('data-user-id', user.id);
    row.innerHTML = `
        <td>
            <div class="user-info">
                <img src="${avatarUrl}" alt="Avatar" class="user-avatar">
                <div class="user-details">
                    <div class="user-name">${displayName}</div>
                    <div class="user-id">${user.id}</div>
                </div>
            </div>
        </td>
        <td><span class="balance-amount">${balance}</span></td>
        <td>${earned}</td>
        <td>${spent}</td>
        <td>
            <button onclick="selectUser('${user.id}')" class="btn-small btn-primary">Select</button>
            <button onclick="viewUserTransactions('${user.id}')" class="btn-small btn-secondary">History</button>
        </td>
    `;

    return row;
}

function displayUserTable(users, totalBalance, append = false) {
    const container = document.getElementById('users-list');

    if (!append) {
        // Create initial table structure
        let html = `
            <div class="users-header">
                <h3>Server Members</h3>
                <div class="stats-summary">
                    <span>Total Balance: ${totalBalance}</span>
                </div>
            </div>
            <div class="table-container">
                <table class="users-table">
                    <thead>
                        <tr>
                            <th>User</th>
                            <th>Balance</th>
                            <th>Total Earned</th>
                            <th>Total Spent</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="users-table-body">
        `;

        users.forEach(user => {
            const row = createUserTableRow(user);
            html += row.innerHTML;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        container.innerHTML = html;
    } else {
        // Append to existing table
        const tbody = document.getElementById('users-table-body');
        if (tbody) {
            users.forEach(user => {
                const row = createUserTableRow(user);
                tbody.appendChild(row);
            });
        }
    }
}

function updateUserSelector(users) {
    const selector = document.getElementById('user-selector');
    if (!selector) {
        console.warn('User selector element not found');
        return;
    }

    // Clear existing options
    selector.innerHTML = '<option value="">-- Select User --</option>';

    // Add users to dropdown
    users.forEach(user => {
        const option = document.createElement('option');
        option.value = user.id;
        option.textContent = `${user.display_name || user.username || user.id} (${user.balance || 0})`;
        selector.appendChild(option);
    });

    console.log(`User selector updated with ${users.length} users`);
}

function selectUser(userId) {
    const userRow = document.querySelector(`tr[data-user-id="${userId}"]`);
    if (!userRow) return;

    // Remove previous selection
    document.querySelectorAll('.users-table tr.selected').forEach(row => {
        row.classList.remove('selected');
    });

    // Highlight selected row
    userRow.classList.add('selected');

    // Store selected user data
    const userName = userRow.querySelector('.user-name').textContent;
    const userBalance = parseInt(userRow.querySelector('.balance-amount').textContent);

    selectedUser = {
        id: userId,
        name: userName,
        balance: userBalance
    };

    // Update user selector dropdown if exists
    const selector = document.getElementById('user-selector');
    if (selector) {
        selector.value = userId;
    }

    // Show user management panel
    showUserManagementPanel();

    showNotification(`Selected user: ${userName}`, 'info');
}

function showUserManagementPanel() {
    if (!selectedUser) return;

    let panel = document.getElementById('user-management-panel');

    if (!panel) {
        // Create panel if it doesn't exist
        panel = document.createElement('div');
        panel.id = 'user-management-panel';
        panel.className = 'management-panel';
        document.getElementById('users').appendChild(panel);
    }

    panel.innerHTML = `
        <div class="panel-header">
            <h3>Manage: ${selectedUser.name}</h3>
            <button onclick="clearUserSelection()" class="btn-close">×</button>
        </div>
        <div class="panel-content">
            <div class="balance-display">
                <label>Current Balance:</label>
                <span class="balance-value">${selectedUser.balance}</span>
            </div>

            <div class="action-section">
                <h4>Quick Actions</h4>
                <div class="quick-actions">
                    <button onclick="quickBalanceChange(100)" class="btn-action">+100</button>
                    <button onclick="quickBalanceChange(500)" class="btn-action">+500</button>
                    <button onclick="quickBalanceChange(1000)" class="btn-action">+1000</button>
                    <button onclick="quickBalanceChange(-100)" class="btn-action btn-danger">-100</button>
                    <button onclick="quickBalanceChange(-500)" class="btn-action btn-danger">-500</button>
                </div>
            </div>

            <div class="action-section">
                <h4>Custom Amount</h4>
                <div class="custom-balance-form">
                    <input type="number" id="custom-amount" placeholder="Amount" class="form-control">
                    <input type="text" id="balance-reason" placeholder="Reason (required)" class="form-control">
                    <div class="button-group">
                        <button onclick="customBalanceAdd()" class="btn-primary">Add</button>
                        <button onclick="customBalanceSubtract()" class="btn-warning">Subtract</button>
                        <button onclick="customBalanceSet()" class="btn-secondary">Set To</button>
                    </div>
                </div>
            </div>

            <div class="action-section">
                <h4>Other Actions</h4>
                <button onclick="viewUserTransactions('${selectedUser.id}')" class="btn-secondary">View Transactions</button>
                <button onclick="clearUserInventory('${selectedUser.id}')" class="btn-danger">Clear Inventory</button>
            </div>
        </div>
    `;

    panel.style.display = 'block';
}

function clearUserSelection() {
    selectedUser = null;

    const panel = document.getElementById('user-management-panel');
    if (panel) {
        panel.style.display = 'none';
    }

    document.querySelectorAll('.users-table tr.selected').forEach(row => {
        row.classList.remove('selected');
    });
}

async function quickBalanceChange(amount) {
    if (!selectedUser) {
        showNotification('Please select a user first', 'error');
        return;
    }

    const reason = prompt(`Enter reason for ${amount > 0 ? 'adding' : 'removing'} ${Math.abs(amount)}:`);
    if (!reason || reason.trim() === '') {
        showNotification('Reason is required', 'error');
        return;
    }

    await modifyUserBalance(amount, false, reason.trim());
}

async function customBalanceAdd() {
    const amount = parseInt(document.getElementById('custom-amount').value);
    const reason = document.getElementById('balance-reason').value.trim();

    if (isNaN(amount) || amount <= 0) {
        showNotification('Please enter a valid positive amount', 'error');
        return;
    }

    if (!reason) {
        showNotification('Reason is required', 'error');
        return;
    }

    await modifyUserBalance(amount, false, reason);
}

async function customBalanceSubtract() {
    const amount = parseInt(document.getElementById('custom-amount').value);
    const reason = document.getElementById('balance-reason').value.trim();

    if (isNaN(amount) || amount <= 0) {
        showNotification('Please enter a valid positive amount', 'error');
        return;
    }

    if (!reason) {
        showNotification('Reason is required', 'error');
        return;
    }

    await modifyUserBalance(-amount, false, reason);
}

async function customBalanceSet() {
    const amount = parseInt(document.getElementById('custom-amount').value);
    const reason = document.getElementById('balance-reason').value.trim();

    if (isNaN(amount) || amount < 0) {
        showNotification('Please enter a valid amount', 'error');
        return;
    }

    if (!reason) {
        showNotification('Reason is required', 'error');
        return;
    }

    await modifyUserBalance(amount, true, reason);
}

async function modifyUserBalance(amount, setBalance = false, reason = '') {
    if (!selectedUser) {
        showNotification('Please select a user first', 'error');
        return;
    }

    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        // Get admin token from localStorage or prompt user
        let adminToken = localStorage.getItem(`admin_token_${currentServerId}`);

        if (!adminToken) {
            adminToken = prompt('Please enter your admin token for this server:');
            if (!adminToken || adminToken.trim() === '') {
                showNotification('Admin token is required', 'error');
                return;
            }
            // Store token for future use
            localStorage.setItem(`admin_token_${currentServerId}`, adminToken.trim());
        }

        const response = await fetch(`/api/${currentServerId}/users/${selectedUser.id}/balance`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: amount,
                set: setBalance,
                reason: reason,
                admin_token: adminToken
            })
        });

        const result = await response.json();

        if (result.success) {
            const action = setBalance ? 'set to' : (amount > 0 ? 'increased by' : 'decreased by');
            showNotification(
                `Balance ${action} ${Math.abs(amount)}. New balance: ${result.balance_after}`,
                'success'
            );

            // Reload users to show updated balance
            await loadUsers();

            // Reselect the user
            selectUser(selectedUser.id);
        } else {
            showNotification(result.error || 'Failed to modify balance', 'error');

            // If token is invalid, clear it and retry once
            if (result.error && result.error.includes('token')) {
                localStorage.removeItem(`admin_token_${currentServerId}`);
                if (confirm('Invalid admin token. Would you like to try again with a new token?')) {
                    return modifyUserBalance(amount, setBalance, reason);
                }
            }
        }
    } catch (error) {
        console.error('Error modifying balance:', error);
        showNotification('Error modifying balance', 'error');
    }
}

// Global variable for selected user
let selectedUserId = null;

// Populate user selector dropdown
function populateUserSelector(users) {
    const dropdown = document.getElementById('user-selector-dropdown');
    dropdown.innerHTML = '';

    users.forEach(user => {
        const option = document.createElement('div');
        option.className = 'user-option';
        option.dataset.userId = user.id;

        const avatarUrl = user.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';

        option.innerHTML = `
            <img src="${avatarUrl}" alt="${user.display_name}" class="user-option-avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
            <div class="user-option-info">
                <div class="user-option-name">${user.display_name}</div>
                <div class="user-option-tag">${user.username}#${user.discriminator}</div>
            </div>
            <div class="user-option-balance">$${user.balance || 0}</div>
        `;

        option.addEventListener('click', () => selectUser(user));
        dropdown.appendChild(option);
    });
}

// Initialize custom user selector
function initializeUserSelector() {
    // User selector elements don't exist in current HTML, skip initialization
    console.log('User selector initialization skipped - elements not present in HTML');
}

// Select a user from the dropdown (removed - not used in current HTML)

// Display users in Discord-style format
function displayUsers(users) {
    const userList = document.getElementById('user-list');
    userList.innerHTML = '';

    users.forEach(user => {
        const userDiv = document.createElement('div');
        userDiv.className = 'user-card';

        const avatarUrl = user.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';
        const displayName = user.display_name || user.username;
        const balance = user.balance || 0;
        const inventoryCount = Object.keys(user.inventory || {}).length;
        const rolesText = user.roles && user.roles.length > 0 ? user.roles.slice(0, 3).join(', ') : 'No roles';

        userDiv.innerHTML = `
            <div class="user-avatar">
                <img src="${avatarUrl}" alt="${displayName}'s avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
            </div>
            <div class="user-info">
                <div class="user-header">
                    <h4 class="user-name">${displayName}</h4>
                    <span class="user-tag">${user.username}#${user.discriminator}</span>
                </div>
                <div class="user-details">
                    <div class="user-balance">💰 $${balance}</div>
                    <div class="user-inventory">📦 ${inventoryCount} items</div>
                    <div class="user-roles">🏷️ ${rolesText}</div>
                </div>
            </div>
            <div class="user-actions">
                <button onclick="quickBalanceChange('${user.id}', 100)" class="quick-add">+💰</button>
                <button onclick="quickBalanceChange('${user.id}', -100)" class="quick-subtract">-💰</button>
                <button onclick="viewUserDetails('${user.id}')" class="view-details">👁️</button>
            </div>
        `;

        userList.appendChild(userDiv);
    });
}

// Quick balance change
async function quickBalanceChange(userId, amount) {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    // NEW: Prompt for reason
    const reason = prompt('Enter reason for balance modification:');
    if (!reason || reason.trim() === '') {
        alert('Reason is required');
        return;
    }

    const confirmMsg = amount > 0 ?
        `Add $${amount} to this user's balance?` :
        `Subtract $${Math.abs(amount)} from this user's balance?`;

    if (confirm(confirmMsg)) {
        try {
            const response = await fetch(`/api/${currentServerId}/users/${userId}/balance`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    amount: amount,
                    reason: reason.trim()
                })
            });

            if (response.ok) {
                alert('Balance updated successfully!');
                loadUsers(); // Refresh the user list
            } else {
                alert('Failed to update balance');
            }
        } catch (error) {
            console.error('Error updating balance:', error);
            alert('Error updating balance');
        }
    }
}

// === SHOP MANAGEMENT FUNCTIONS ===

// Load shop items with enhanced UI
async function loadShop() {
    if (!currentServerId) {
        document.getElementById('shop-list').innerHTML = '<p>Please select a server first.</p>';
        return;
    }

    try {
        showLoading('shop');

        // Load shop items and statistics
        const [itemsResponse, statsResponse] = await Promise.all([
            fetch(`/api/${currentServerId}/shop`),
            fetch(`/api/${currentServerId}/shop/statistics`)
        ]);

        const itemsData = await itemsResponse.json();
        const statsData = await statsResponse.json();

        // Update statistics display
        updateShopStats(statsData.statistics);

        const shopContainer = document.getElementById('shop-list');
        shopContainer.innerHTML = '';

        if (!itemsData.items || Object.keys(itemsData.items).length === 0) {
            shopContainer.innerHTML = '<div class="empty-state">No shop items found for this server. <button onclick="showAddItemModal()" class="btn-primary">Add First Item</button></div>';
            hideLoading('shop');
            return;
        }

        // Create shop items grid
        const itemsGrid = document.createElement('div');
        itemsGrid.className = 'shop-items-grid';

        Object.entries(itemsData.items).forEach(([itemId, item]) => {
            const itemCard = createShopItemCard(itemId, item);
            itemsGrid.appendChild(itemCard);
        });

        shopContainer.appendChild(itemsGrid);
        hideLoading('shop');

    } catch (error) {
        console.error('Error loading shop:', error);
        document.getElementById('shop-list').innerHTML = '<div class="error-state">Error loading shop items. Please try again.</div>';
        hideLoading('shop');
    }
}

// Create shop item card
function createShopItemCard(itemId, item) {
    const card = document.createElement('div');
    card.className = `shop-item-card ${!item.is_active ? 'inactive' : ''}`;
    card.dataset.itemId = itemId;

    const stockText = item.stock === -1 ? '♾️ Unlimited' : `📦 ${item.stock} available`;
    const categoryText = item.category ? item.category.charAt(0).toUpperCase() + item.category.slice(1) : 'General';

    card.innerHTML = `
        <div class="item-header">
            <span class="item-emoji">${item.emoji || '🛍️'}</span>
            <div class="item-title-section">
                <h4 class="item-name">${escapeHtml(item.name)}</h4>
                <span class="item-category">${categoryText}</span>
            </div>
            <div class="item-actions">
                <button onclick="editShopItem('${itemId}')" class="btn-small" title="Edit">✏️</button>
                <button onclick="deleteShopItem('${itemId}')" class="btn-small btn-danger" title="Delete">🗑️</button>
            </div>
        </div>

        <div class="item-description">
            <p>${escapeHtml(item.description)}</p>
        </div>

        <div class="item-details">
            <div class="item-price">
                <span class="price-label">Price:</span>
                <span class="price-value">$${item.price}</span>
            </div>
            <div class="item-stock">
                <span class="stock-label">Stock:</span>
                <span class="stock-value">${stockText}</span>
            </div>
        </div>

        <div class="item-meta">
            <span class="item-id">ID: <code>${itemId}</code></span>
            ${!item.is_active ? '<span class="inactive-badge">Inactive</span>' : ''}
        </div>
    `;

    return card;
}

// Update shop statistics display
function updateShopStats(stats) {
    if (!stats) return;

    const totalItemsEl = document.getElementById('total-shop-items');
    const activeItemsEl = document.getElementById('active-shop-items');
    const salesEl = document.getElementById('total-shop-sales');
    const revenueEl = document.getElementById('shop-revenue');

    if (totalItemsEl) totalItemsEl.textContent = stats.total_items || 0;
    if (activeItemsEl) activeItemsEl.textContent = stats.active_items || 0;
    if (salesEl) salesEl.textContent = stats.total_sales || 0;
    if (revenueEl) revenueEl.textContent = `$${stats.total_revenue || 0}`;

    // Show stats section
    const statsSection = document.getElementById('shop-stats');
    if (statsSection) {
        statsSection.style.display = 'block';
    }
}

// Filter shop items
function filterShopItems() {
    const categoryFilter = document.getElementById('category-filter').value;
    const activeOnly = document.getElementById('active-only-filter').checked;
    const inStockOnly = document.getElementById('in-stock-only-filter').checked;
    const searchTerm = document.getElementById('shop-search').value.toLowerCase();

    const itemCards = document.querySelectorAll('.shop-item-card');

    itemCards.forEach(card => {
        const itemId = card.dataset.itemId;
        const itemName = card.querySelector('.item-name').textContent.toLowerCase();
        const itemDesc = card.querySelector('.item-description p').textContent.toLowerCase();
        const isActive = !card.classList.contains('inactive');
        const stockText = card.querySelector('.stock-value').textContent;

        // Category filter
        if (categoryFilter && categoryFilter !== 'all') {
            const itemCategory = card.querySelector('.item-category').textContent.toLowerCase();
            if (itemCategory !== categoryFilter.toLowerCase()) {
                card.style.display = 'none';
                return;
            }
        }

        // Active only filter
        if (activeOnly && !isActive) {
            card.style.display = 'none';
            return;
        }

        // In stock only filter
        if (inStockOnly && stockText.includes('0 available') && !stockText.includes('Unlimited')) {
            card.style.display = 'none';
            return;
        }

        // Search filter
        if (searchTerm) {
            if (!itemName.includes(searchTerm) && !itemDesc.includes(searchTerm) && !itemId.includes(searchTerm)) {
                card.style.display = 'none';
                return;
            }
        }

        card.style.display = 'block';
    });
}

// Show add item modal
function showAddItemModal() {
    showModal(`
        <h2>Add New Shop Item</h2>
        <form id="add-item-form" onsubmit="addShopItem(event)">
            <div class="form-row">
                <div class="form-group">
                    <label>Item ID *</label>
                    <input type="text" id="item-id" required placeholder="unique_item_id" pattern="[a-zA-Z0-9_]+" title="Only letters, numbers, and underscores allowed">
                    <small>Unique identifier (no spaces, only letters/numbers/underscores)</small>
                </div>
                <div class="form-group">
                    <label>Emoji</label>
                    <input type="text" id="item-emoji" placeholder="🛍️" maxlength="10">
                </div>
            </div>

            <div class="form-group">
                <label>Name *</label>
                <input type="text" id="item-name" required placeholder="Item Name" maxlength="100">
            </div>

            <div class="form-group">
                <label>Description *</label>
                <textarea id="item-description" required rows="3" placeholder="Item description" maxlength="500"></textarea>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Price *</label>
                    <input type="number" id="item-price" required min="0" step="0.01" placeholder="0.00">
                </div>
                <div class="form-group">
                    <label>Stock</label>
                    <input type="number" id="item-stock" min="-1" value="-1" placeholder="-1 for unlimited">
                    <small>Use -1 for unlimited stock</small>
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Category</label>
                    <select id="item-category">
                        <option value="general">General</option>
                        <option value="consumable">Consumable</option>
                        <option value="role">Role</option>
                        <option value="collectible">Collectible</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Role Requirement</label>
                    <input type="text" id="item-role-req" placeholder="Role name (optional)">
                    <small>Users must have this role to purchase</small>
                </div>
            </div>

            <div class="form-actions">
                <button type="submit" class="btn-primary">Add Item</button>
                <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
            </div>
        </form>
    `);
}

// Add shop item
async function addShopItem(event) {
    event.preventDefault();

    const itemData = {
        item_id: document.getElementById('item-id').value.trim(),
        name: document.getElementById('item-name').value.trim(),
        description: document.getElementById('item-description').value.trim(),
        price: parseFloat(document.getElementById('item-price').value),
        stock: parseInt(document.getElementById('item-stock').value),
        category: document.getElementById('item-category').value,
        emoji: document.getElementById('item-emoji').value.trim() || '🛍️',
        role_requirement: document.getElementById('item-role-req').value.trim() || null
    };

    // Validation
    if (itemData.price < 0) {
        showNotification('Price cannot be negative', 'error');
        return;
    }

    if (itemData.stock < -1) {
        showNotification('Stock cannot be less than -1', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/shop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(itemData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to add item');
        }

        const result = await response.json();

        closeModal();
        showNotification('✅ Item added successfully!', 'success');
        await loadShop();

    } catch (error) {
        console.error('Error adding shop item:', error);
        showNotification(`❌ Failed to add item: ${error.message}`, 'error');
    }
}

// Edit shop item
async function editShopItem(itemId) {
    try {
        // Get current item data
        const response = await fetch(`/api/${currentServerId}/shop/${itemId}`);
        if (!response.ok) {
            throw new Error('Item not found');
        }

        const item = await response.json();

        showModal(`
            <h2>Edit Shop Item</h2>
            <form id="edit-item-form" onsubmit="updateShopItem(event, '${itemId}')">
                <div class="form-row">
                    <div class="form-group">
                        <label>Item ID</label>
                        <input type="text" value="${itemId}" disabled>
                        <small>Cannot change item ID</small>
                    </div>
                    <div class="form-group">
                        <label>Emoji</label>
                        <input type="text" id="edit-item-emoji" value="${item.emoji || '🛍️'}" maxlength="10">
                    </div>
                </div>

                <div class="form-group">
                    <label>Name *</label>
                    <input type="text" id="edit-item-name" required value="${escapeHtml(item.name)}" maxlength="100">
                </div>

                <div class="form-group">
                    <label>Description *</label>
                    <textarea id="edit-item-description" required rows="3" maxlength="500">${escapeHtml(item.description)}</textarea>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>Price *</label>
                        <input type="number" id="edit-item-price" required min="0" step="0.01" value="${item.price}">
                    </div>
                    <div class="form-group">
                        <label>Stock</label>
                        <input type="number" id="edit-item-stock" min="-1" value="${item.stock}" placeholder="-1 for unlimited">
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label>Category</label>
                        <select id="edit-item-category">
                            <option value="general" ${item.category === 'general' ? 'selected' : ''}>General</option>
                            <option value="consumable" ${item.category === 'consumable' ? 'selected' : ''}>Consumable</option>
                            <option value="role" ${item.category === 'role' ? 'selected' : ''}>Role</option>
                            <option value="collectible" ${item.category === 'collectible' ? 'selected' : ''}>Collectible</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Role Requirement</label>
                        <input type="text" id="edit-item-role-req" value="${item.role_requirement || ''}" placeholder="Role name (optional)">
                    </div>
                </div>

                <div class="form-group checkbox-group">
                    <label>
                        <input type="checkbox" id="edit-item-active" ${item.is_active !== false ? 'checked' : ''}>
                        Item is active
                    </label>
                </div>

                <div class="form-actions">
                    <button type="submit" class="btn-primary">Save Changes</button>
                    <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
                </div>
            </form>
        `);

    } catch (error) {
        console.error('Error loading item for edit:', error);
        showNotification('❌ Failed to load item for editing', 'error');
    }
}

// Update shop item
async function updateShopItem(event, itemId) {
    event.preventDefault();

    const updates = {
        name: document.getElementById('edit-item-name').value.trim(),
        description: document.getElementById('edit-item-description').value.trim(),
        price: parseFloat(document.getElementById('edit-item-price').value),
        stock: parseInt(document.getElementById('edit-item-stock').value),
        category: document.getElementById('edit-item-category').value,
        emoji: document.getElementById('edit-item-emoji').value.trim(),
        role_requirement: document.getElementById('edit-item-role-req').value.trim() || null,
        is_active: document.getElementById('edit-item-active').checked
    };

    // Validation
    if (updates.price < 0) {
        showNotification('Price cannot be negative', 'error');
        return;
    }

    if (updates.stock < -1) {
        showNotification('Stock cannot be less than -1', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/shop/${itemId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to update item');
        }

        const result = await response.json();

        closeModal();
        showNotification('✅ Item updated successfully!', 'success');
        await loadShop();

    } catch (error) {
        console.error('Error updating shop item:', error);
        showNotification(`❌ Failed to update item: ${error.message}`, 'error');
    }
}

// Delete shop item
async function deleteShopItem(itemId) {
    if (!confirm(`Are you sure you want to delete the shop item "${itemId}"? This action cannot be undone.`)) {
        return;
    }

    // Ask about archiving
    const archive = confirm('Would you like to archive this item instead of permanently deleting it? Archived items can be restored later.');

    try {
        const response = await fetch(`/api/${currentServerId}/shop/${itemId}?archive=${archive}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to delete item');
        }

        showNotification(`✅ Item ${archive ? 'archived' : 'deleted'} successfully!`, 'success');
        await loadShop();

    } catch (error) {
        console.error('Error deleting shop item:', error);
        showNotification(`❌ Failed to delete item: ${error.message}`, 'error');
    }
}

// View shop statistics
async function viewShopStatistics() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/shop/statistics`);
        const data = await response.json();

        const stats = data.statistics;

        showModal(`
            <h2>Shop Statistics</h2>
            <div class="stats-modal">
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>Total Items</h3>
                        <div class="stat-value">${stats.total_items || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Active Items</h3>
                        <div class="stat-value">${stats.active_items || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Total Sales</h3>
                        <div class="stat-value">${stats.total_sales || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Revenue</h3>
                        <div class="stat-value">$${stats.total_revenue || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Items Sold</h3>
                        <div class="stat-value">${stats.total_quantity_sold || 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Avg Price</h3>
                        <div class="stat-value">$${stats.average_price ? stats.average_price.toFixed(2) : '0.00'}</div>
                    </div>
                </div>

                ${stats.top_items && stats.top_items.length > 0 ? `
                    <div class="top-items-section">
                        <h3>🏆 Top Selling Items</h3>
                        <div class="top-items-list">
                            ${stats.top_items.slice(0, 5).map(item => `
                                <div class="top-item">
                                    <span class="item-emoji">${item.emoji || '🛍️'}</span>
                                    <span class="item-name">${escapeHtml(item.name)}</span>
                                    <span class="item-sales">${item.sales_count} sold</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}

                ${stats.category_breakdown ? `
                    <div class="category-breakdown">
                        <h3>📂 Items by Category</h3>
                        <div class="category-list">
                            ${Object.entries(stats.category_breakdown).map(([category, count]) => `
                                <div class="category-item">
                                    <span class="category-name">${category.charAt(0).toUpperCase() + category.slice(1)}</span>
                                    <span class="category-count">${count} items</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>

            <div class="modal-actions">
                <button onclick="closeModal()" class="btn-secondary">Close</button>
            </div>
        `);

    } catch (error) {
        console.error('Error loading shop statistics:', error);
        showNotification('❌ Failed to load statistics', 'error');
    }
}

// Validate shop integrity
async function validateShopIntegrity() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        showNotification('🔍 Validating shop data...', 'info');

        const response = await fetch(`/api/${currentServerId}/shop/validate`, {
            method: 'POST'
        });

        const result = await response.json();

        let message = '✅ Shop validation complete!\n\n';

        if (result.errors && result.errors.length > 0) {
            message += `❌ Errors found: ${result.errors.length}\n`;
            result.errors.slice(0, 5).forEach(error => {
                message += `• ${error}\n`;
            });
        }

        if (result.warnings && result.warnings.length > 0) {
            message += `⚠️ Warnings: ${result.warnings.length}\n`;
            result.warnings.slice(0, 5).forEach(warning => {
                message += `• ${warning}\n`;
            });
        }

        if ((!result.errors || result.errors.length === 0) &&
            (!result.warnings || result.warnings.length === 0)) {
            message += 'No issues found!';
        }

        showModal(`
            <h2>Shop Validation Results</h2>
            <div class="validation-results">
                <pre>${message}</pre>
            </div>
            <div class="modal-actions">
                <button onclick="closeModal()" class="btn-secondary">Close</button>
            </div>
        `);

    } catch (error) {
        console.error('Error validating shop:', error);
        showNotification('❌ Failed to validate shop', 'error');
    }
}

// Legacy function for backward compatibility
async function loadShopItems() {
    await loadShop();
}

// Add shop item
async function addShopItem() {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    const itemId = document.getElementById('shop-item-id').value.trim();
    const name = document.getElementById('shop-item-name').value.trim();
    const price = parseFloat(document.getElementById('shop-item-price').value) || 0;
    const description = document.getElementById('shop-item-description').value.trim();

    if (!itemId || !name || !description) {
        alert('Please fill in all fields');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/shop`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ id: itemId, name, price, description })
        });

        if (response.ok) {
            alert('Shop item added successfully!');
            document.getElementById('shop-item-id').value = '';
            document.getElementById('shop-item-name').value = '';
            document.getElementById('shop-item-price').value = '';
            document.getElementById('shop-item-description').value = '';
            loadShopItems();
        } else {
            const error = await response.json();
            alert('Failed to add shop item: ' + (error.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error adding shop item:', error);
        alert('Error adding shop item');
    }
}

// Delete shop item
async function deleteShopItem(itemId) {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (confirm(`Are you sure you want to delete the shop item "${itemId}"?`)) {
        try {
            const response = await fetch(`/api/${currentServerId}/shop/${itemId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                alert('Shop item deleted successfully!');
                loadShopItems();
            } else {
                alert('Failed to delete shop item');
            }
        } catch (error) {
            console.error('Error deleting shop item:', error);
            alert('Error deleting shop item');
        }
    }
}

// Edit shop item (placeholder for now)
function editShopItem(itemId) {
    alert(`Edit functionality for ${itemId} - Coming soon!`);
}

// View user details
function viewUserDetails(userId) {
    const user = allUsers.find(u => u.id === userId);
    if (user) {
        const inventory = Object.entries(user.inventory || {});
        const inventoryText = inventory.length > 0 ?
            inventory.map(([item, qty]) => `${item}: ${qty}`).join('\n') :
            'No items';

        alert(`${user.display_name} (${user.username}#${user.discriminator})\n\n` +
              `Balance: $${user.balance || 0}\n` +
              `Inventory:\n${inventoryText}\n\n` +
              `Roles: ${user.roles?.join(', ') || 'None'}\n` +
              `Joined: ${user.joined_at ? new Date(user.joined_at).toLocaleDateString() : 'Unknown'}`);
    }
}

// Search users
function setupUserSearch() {
    const searchInput = document.getElementById('user-search');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const filteredUsers = allUsers.filter(user =>
                user.username.toLowerCase().includes(searchTerm) ||
                user.display_name.toLowerCase().includes(searchTerm) ||
                (user.roles && user.roles.some(role => role.toLowerCase().includes(searchTerm)))
            );
            displayUsers(filteredUsers);
        });
    }
}

// Create task
async function createTask() {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    const name = document.getElementById('task-name').value.trim();
    const url = document.getElementById('task-url').value.trim();
    const description = document.getElementById('task-description').value.trim();
    const reward = parseFloat(document.getElementById('task-reward').value) || 0;
    const durationType = document.getElementById('task-duration-type').value;
    const durationValue = parseInt(document.getElementById('task-duration-value').value) || 24;

    if (!name || !description) {
        alert('Please fill in task name and description');
        return;
    }

    // Calculate duration in hours
    let duration_hours = null;
    if (durationType === 'forever') {
        duration_hours = -1; // Special value for forever
    } else {
        switch (durationType) {
            case 'hours':
                duration_hours = durationValue;
                break;
            case 'days':
                duration_hours = durationValue * 24;
                break;
            case 'weeks':
                duration_hours = durationValue * 24 * 7;
                break;
        }
    }

    try {
        const result = await fetch(`/api/${currentServerId}/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, url, description, reward, duration_hours })
        });

        if (result.ok) {
            alert('Task created successfully');
            document.getElementById('task-name').value = '';
            document.getElementById('task-url').value = '';
            document.getElementById('task-description').value = '';
            document.getElementById('task-reward').value = '';
            document.getElementById('task-duration-type').value = 'hours';
            document.getElementById('task-duration-value').value = '24';
            loadTasks();
        } else {
            const error = await result.json();
            alert('Failed to create task: ' + error.error);
        }
    } catch (error) {
        console.error('Error creating task:', error);
        alert('Error creating task');
    }
}

// Delete task
async function deleteTask(taskId) {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (confirm('Are you sure you want to delete this task?')) {
        try {
            // Updated URL to include server_id - cache refresh v2
            const response = await fetch(`/api/${currentServerId}/tasks/${taskId}`, { method: 'DELETE' });
            if (response.ok) {
                alert('Task deleted successfully');
                loadTasks();
            } else {
                const errorData = await response.json();
                alert('Failed to delete task: ' + (errorData.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error deleting task:', error);
            alert('Error deleting task: ' + error.message);
        }
    }
}

// Refresh logs
function refreshLogs() {
    loadLogs();
}

async function updateBotStatus() {
    const statusType = document.getElementById('bot-status-type').value;
    const statusMessage = document.getElementById('bot-status-message').value.trim();
    const presence = document.getElementById('bot-presence').value;
    const streamingUrl = document.getElementById('streaming-url').value.trim();

    try {
        const response = await fetch(apiUrl('/api/bot/status'), {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                status_type: statusType,
                status_message: statusMessage
            })
        });

        const result = await response.json();

        if (response.ok) {
            alert('✅ ' + result.message);
            // Refresh the status display
            loadOverviewData();
        } else {
            alert('❌ Error: ' + (result.error || 'Failed to update status'));
        }
    } catch (error) {
        console.error('Error updating bot status:', error);
        alert('❌ Failed to update bot status. Check console for details.');
    }
}

// Load servers list
async function loadServers() {
    try {
        const response = await fetch(apiUrl('/api/servers'));
        const data = await response.json();
        servers = data.servers || [];

        const serverSelect = document.getElementById('server-select');
        serverSelect.innerHTML = '<option value="">Select a server...</option>';

        servers.forEach(server => {
            const option = document.createElement('option');
            option.value = server.id;
            option.textContent = `${server.name} (${server.member_count} members)`;
            serverSelect.appendChild(option);
        });

        // Auto-select first server if available
        if (servers.length > 0 && !currentServerId) {
            currentServerId = servers[0].id;
            serverSelect.value = currentServerId;
            onServerChange();
        }
    } catch (error) {
        console.error('Error loading servers:', error);
    }
}

// Handle server selection change
function onServerChange() {
    const serverSelect = document.getElementById('server-select');
    const selectedServerId = serverSelect.value;

    if (selectedServerId && selectedServerId !== currentServerId) {
        currentServerId = selectedServerId;
        console.log(`Switched to server: ${currentServerId}`);

        // Show restart button only for EVL server (1123738140050464878)
        const restartBtn = document.getElementById('restart-btn');
        if (restartBtn) {
            if (selectedServerId === '1123738140050464878') {
                restartBtn.style.display = 'block';
            } else {
                restartBtn.style.display = 'none';
            }
        }

        // Reload current tab data with new server
        if (currentTab !== 'overview' && currentTab !== 'logs' && currentTab !== 'commands') {
            loadTabData(currentTab);
        }
    } else if (!selectedServerId) {
        currentServerId = null;
        console.log('No server selected');

        // Hide restart button when no server is selected
        const restartBtn = document.getElementById('restart-btn');
        if (restartBtn) {
            restartBtn.style.display = 'none';
        }
    }
}

// Global variables for SSE with enhanced reconnection
let eventSource = null;
let reconnectDelay = 1000;
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let isReconnecting = false;
let lastHeartbeat = Date.now();
let heartbeatInterval = null;
let connectionStatus = 'disconnected'; // 'connected', 'connecting', 'disconnected', 'error'

// SSE Connection Status Management
function updateConnectionStatus(status, message = '') {
    connectionStatus = status;
    const statusElement = document.getElementById('sse-status');
    if (statusElement) {
        statusElement.className = `sse-status status-${status}`;
        statusElement.textContent = message || getStatusText(status);
    }

    // Update connection indicator
    const indicator = document.getElementById('connection-indicator');
    if (indicator) {
        indicator.className = `connection-indicator ${status}`;
    }

    console.log(`SSE Status: ${status}${message ? ' - ' + message : ''}`);
}

function getStatusText(status) {
    switch(status) {
        case 'connected': return '🟢 Connected';
        case 'connecting': return '🟡 Connecting...';
        case 'disconnected': return '🔴 Disconnected';
        case 'error': return '❌ Connection Error';
        default: return '⚪ Unknown';
    }
}

// Initialize real-time updates with enhanced reconnection
function initRealtimeUpdates() {
    if (isReconnecting) {
        console.log('Already attempting to reconnect, skipping...');
        return;
    }

    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    updateConnectionStatus('connecting', `Attempting to connect... (${reconnectAttempts + 1}/${maxReconnectAttempts})`);

    // Build SSE URL with authentication and filters
    let sseUrl = apiUrl('/api/stream');
    const params = new URLSearchParams();

    // Add server filter if selected
    if (currentServerId) {
        params.append('guilds', currentServerId);
    }

    // Add event type filters based on current tab
    const eventFilters = getEventFiltersForTab(currentTab);
    if (eventFilters.length > 0) {
        params.append('events', eventFilters.join(','));
    }

    if (params.toString()) {
        sseUrl += '?' + params.toString();
    }

    try {
        // Create EventSource with authentication headers
        eventSource = new EventSource(sseUrl);

        // Connection opened
        eventSource.onopen = (event) => {
            console.log('SSE connection opened');
            updateConnectionStatus('connected');
            reconnectAttempts = 0;
            reconnectDelay = 1000;
            isReconnecting = false;

            // Start heartbeat monitoring
            startHeartbeatMonitoring();
        };

        // Message received
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Handle heartbeat
                if (data.type === 'heartbeat') {
                    lastHeartbeat = Date.now();
                    return;
                }

                // Handle connection info
                if (data.type === 'connected') {
                    console.log('SSE connected with client ID:', data.client_id);
                    return;
                }

                console.log('Received SSE update:', data);

                // Handle different update types
                handleSSEEvent(data);

                // Reset reconnect delay on successful message
                reconnectDelay = 1000;

            } catch (error) {
                console.error('Error parsing SSE event data:', error, 'Raw data:', event.data);
                // Continue with other event handling even if this event failed
            }
        };

        // Connection error
        eventSource.onerror = (event) => {
            console.error('SSE connection error:', event);
            updateConnectionStatus('error', 'Connection failed');

            // Stop heartbeat monitoring
            stopHeartbeatMonitoring();

            // Close current connection
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }

            // Attempt reconnection
            attemptReconnection();
        };

    } catch (error) {
        console.error('Failed to create EventSource:', error);
        updateConnectionStatus('error', 'Failed to initialize connection');
        attemptReconnection();
    }
}

// Get event filters based on current tab
function getEventFiltersForTab(tabName) {
    const filters = [];

    switch(tabName) {
        case 'tasks':
            filters.push('task_update', 'guild_update');
            break;
        case 'users':
            filters.push('balance_update', 'inventory_update', 'guild_update');
            break;
        case 'shop':
            filters.push('shop_update', 'inventory_update', 'guild_update');
            break;
        case 'transactions':
            filters.push('balance_update', 'inventory_update', 'guild_update');
            break;
        default:
            filters.push('guild_update');
    }

    return filters;
}

// Handle SSE events
function handleSSEEvent(data) {
    console.log('SSE Event:', data);

    switch (data.type) {
        case 'task_created':
            handleTaskCreated(data);
            break;
        case 'task_updated':
            handleTaskUpdated(data);
            break;
        case 'task_deleted':
            handleTaskDeleted(data);
            break;
        case 'shop_item_created':
            handleShopItemCreated(data);
            break;
        case 'shop_item_deleted':
            handleShopItemDeleted(data);
            break;
        case 'user_updated':
            handleUserUpdated(data);
            break;
        case 'embed_created':
            handleEmbedCreated(data);
            break;
        case 'announcement_posted':
            handleAnnouncementPosted(data);
            break;
        case 'guild_update':
            if (currentServerId && data.guild_id === currentServerId) {
                // Refresh appropriate tab based on data_type
                if (data.data_type === 'currency' && currentTab === 'users') {
                    loadUsers();
                } else if (data.data_type === 'currency' && currentTab === 'shop') {
                    loadShop();
                } else if (data.data_type === 'tasks' && currentTab === 'tasks') {
                    loadTasks();
                } else if (data.data_type === 'transactions' && currentTab === 'transactions') {
                    loadTransactions();
                }
            }
            break;
        case 'task_update':
            // Handle task-specific updates
            if (currentServerId && data.guild_id === currentServerId) {
                handleTaskUpdate(data);
            }
            break;
        case 'balance_update':
            // Handle balance updates
            if (currentServerId && data.guild_id === currentServerId) {
                if (currentTab === 'users') {
                    loadUsers();
                }
                if (currentTab === 'transactions') {
                    loadTransactions();
                }
            }
            break;
        case 'shop_update':
            if (currentServerId && data.guild_id === currentServerId && currentTab === 'shop') {
                // Handle specific shop updates
                if (data.action === 'item_added' || data.action === 'item_updated' || data.action === 'item_deleted') {
                    console.log('Shop item changed, refreshing shop...');
                    loadShop();
                }
            }
            break;
        case 'inventory_update':
            if (currentServerId && data.guild_id === currentServerId) {
                // Handle inventory updates
                if (currentTab === 'users') {
                    loadUsers(); // Refresh user balances
                }
                if (currentTab === 'transactions') {
                    loadTransactions(); // Refresh transaction history
                }
            }
            break;
        case 'batch':
            // Handle batched events
            console.log(`Processing batch of ${data.events.length} events for ${data.event_type}`);
            data.events.forEach(event => handleSSEEvent(event));
            break;
        default:
            console.log('Unhandled SSE event:', data.type);
    }
}

function handleTaskCreated(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Add task to UI without full refresh
    addTaskToList(data.task);
}

function handleTaskUpdated(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Update task in UI without full refresh
    updateTaskInList(data.task_id, data.task);
}

function handleTaskDeleted(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Remove task from UI
    removeTaskFromList(data.task_id);
}

function handleShopItemCreated(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Add shop item to UI without full refresh
    addShopItemToList(data.item);
}

function handleShopItemDeleted(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Remove shop item from UI
    removeShopItemFromList(data.item_id);
}

function handleUserUpdated(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Update user in UI without full refresh
    updateUserInList(data.user_id, data.user);
}

function handleEmbedCreated(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Add embed to UI without full refresh
    addEmbedToList(data.embed);
}

function handleAnnouncementPosted(data) {
    if (data.guild_id !== getCurrentServerId()) return;
    // Add announcement to UI without full refresh
    addAnnouncementToList(data.announcement);
}

function getCurrentServerId() {
    return currentServerId;
}

// Helper functions for UI updates (placeholders for now)
function addTaskToList(task) {
    console.log('Adding task to list:', task);
    // TODO: Implement actual UI update
}

function updateTaskInList(taskId, task) {
    console.log('Updating task in list:', taskId, task);
    // TODO: Implement actual UI update
}

function removeTaskFromList(taskId) {
    console.log('Removing task from list:', taskId);
    // TODO: Implement actual UI update
}

function addShopItemToList(item) {
    console.log('Adding shop item to list:', item);
    // TODO: Implement actual UI update
}

function removeShopItemFromList(itemId) {
    console.log('Removing shop item from list:', itemId);
    // TODO: Implement actual UI update
}

function updateUserInList(userId, user) {
    console.log('Updating user in list:', userId, user);
    // TODO: Implement actual UI update
}

function addEmbedToList(embed) {
    console.log('Adding embed to list:', embed);
    // TODO: Implement actual UI update
}

function addAnnouncementToList(announcement) {
    console.log('Adding announcement to list:', announcement);
    // TODO: Implement actual UI update
}

// Attempt reconnection with exponential backoff
function attemptReconnection() {
    if (isReconnecting) return;

    isReconnecting = true;
    reconnectAttempts++;

    if (reconnectAttempts >= maxReconnectAttempts) {
        updateConnectionStatus('error', `Max reconnection attempts (${maxReconnectAttempts}) reached`);
        showNotification('⚠️ Real-time updates unavailable. Please refresh the page.', 'warning');
        isReconnecting = false;
        return;
    }

    // Exponential backoff with jitter
    const jitter = Math.random() * 1000;
    const delay = Math.min(reconnectDelay + jitter, 30000);

    console.log(`Attempting SSE reconnection in ${Math.round(delay/1000)}s (attempt ${reconnectAttempts}/${maxReconnectAttempts})`);

    setTimeout(() => {
        isReconnecting = false;
        initRealtimeUpdates();
    }, delay);

    // Increase delay for next attempt
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
}

// Start heartbeat monitoring
function startHeartbeatMonitoring() {
    stopHeartbeatMonitoring(); // Clear any existing interval

    heartbeatInterval = setInterval(() => {
        const timeSinceLastHeartbeat = Date.now() - lastHeartbeat;

        // If no heartbeat for 60 seconds, consider connection stale
        if (timeSinceLastHeartbeat > 60000) {
            console.warn('SSE heartbeat timeout, reconnecting...');
            updateConnectionStatus('error', 'Heartbeat timeout');
            if (eventSource) {
                eventSource.close();
            }
        }
    }, 30000); // Check every 30 seconds
}

// Stop heartbeat monitoring
function stopHeartbeatMonitoring() {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }
}

// Manual reconnection
function reconnectSSE() {
    console.log('Manual SSE reconnection requested');
    reconnectAttempts = 0; // Reset attempt counter
    reconnectDelay = 1000; // Reset delay
    initRealtimeUpdates();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
    stopHeartbeatMonitoring();
});

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Initialize authentication first
    initAuth();

    // Set up login form
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', login);
    }

    // Set up duration selector
    setupDurationSelector();

    // Set up user search
    setupUserSearch();
});

// Initialize dashboard after authentication
function initializeDashboard() {
    loadServers();
    loadOverviewData();

    // Set up server selector
    const serverSelect = document.getElementById('server-select');
    if (serverSelect) {
        serverSelect.addEventListener('change', onServerChange);
    }

    // Initialize real-time updates
    initRealtimeUpdates();

    // Auto-refresh overview every 30 seconds
    setInterval(() => {
        if (currentTab === 'overview') {
            loadOverviewData();
        }
    }, 30000);
}

// Command templates
function loadTemplate(templateName) {
    const templates = {
        'give_money': {
            name: 'givemoney',
            response: '💰 **ADMIN COMMAND**: /give_money @user amount\n\nGives currency to a user. Requires admin permissions.'
        },
        'take_money': {
            name: 'takemoney',
            response: '💰 **ADMIN COMMAND**: /take_money @user amount\n\nTakes currency from a user. Requires admin permissions.'
        },
        'balance': {
            name: 'bal',
            response: '💰 **BALANCE CHECK**: /balance [@user]\n\nShows your current balance or another user\'s balance.'
        },
        'shop': {
            name: 'store',
            response: '🛒 **ITEM SHOP**: /shop\n\nBrowse and purchase items from the shop using your currency!'
        },
        'inventory': {
            name: 'inv',
            response: '📦 **INVENTORY**: /inventory [@user]\n\nView your purchased items or check another user\'s inventory.'
        },
        'embed': {
            name: 'createembed',
            response: '📄 **ADMIN COMMAND**: /embed title:"Title" description:"Description"\n\nCreates a rich embed message. Requires admin permissions.'
        },
        'announce': {
            name: 'announcement',
            response: '📢 **ADMIN COMMAND**: /announce #channel message\n\nSends an announcement to a specific channel. Requires admin permissions.'
        },
        'close_task': {
            name: 'closetask',
            response: '✅ **ADMIN COMMAND**: /close_task task_name\n\nManually closes a task and distributes rewards. Requires admin permissions.'
        },
        'welcome': {
            name: 'welcome',
            response: '👋 **Welcome to our server!**\n\nPlease read the rules in #rules and introduce yourself in #introductions.\n\nEnjoy your stay! 🎉'
        },
        'rules': {
            name: 'rules',
            response: '📋 **SERVER RULES**\n\n1. Be respectful to all members\n2. No spam or excessive caps\n3. Keep content appropriate\n4. Use appropriate channels\n5. No self-promotion without permission\n\nBreaking rules may result in warnings, mutes, or bans.'
        }
    };

    const template = templates[templateName];
    if (template) {
        document.getElementById('cmd-name').value = template.name;
        document.getElementById('cmd-response').value = template.response;
    }
}

// Set up duration selector functionality
function setupDurationSelector() {
    const durationTypeSelect = document.getElementById('task-duration-type');
    const durationValueInput = document.getElementById('task-duration-value');

    if (durationTypeSelect && durationValueInput) {
        durationTypeSelect.addEventListener('change', function() {
            if (this.value === 'forever') {
                durationValueInput.disabled = true;
                durationValueInput.value = '';
            } else {
                durationValueInput.disabled = false;
                if (!durationValueInput.value) {
                    durationValueInput.value = '24';
                }
            }
        });
    }
}

// User management functions

// Bulk actions
async function resetAllBalances() {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (!confirm('Are you sure you want to reset ALL user balances to $0? This cannot be undone!')) {
        return;
    }

    try {
        // This would need a new backend endpoint for bulk operations
        alert('Bulk balance reset - This feature requires backend implementation');
    } catch (error) {
        console.error('Error resetting balances:', error);
        alert('Error resetting balances');
    }
}

async function giveAllUsers(amount) {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (!confirm(`Are you sure you want to give $${amount} to ALL users?`)) {
        return;
    }

    try {
        // This would need a new backend endpoint for bulk operations
        alert('Bulk currency distribution - This feature requires backend implementation');
    } catch (error) {
        console.error('Error giving currency:', error);
        alert('Error giving currency');
    }
}

async function clearAllInventories() {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (!confirm('Are you sure you want to clear ALL user inventories? This cannot be undone!')) {
        return;
    }

    try {
        // This would need a new backend endpoint for bulk operations
        alert('Bulk inventory clear - This feature requires backend implementation');
    } catch (error) {
        console.error('Error clearing inventories:', error);
        alert('Error clearing inventories');
    }
}

// Individual user actions
async function modifyUserBalance(operation, amount) {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    const finalAmount = operation === 'add' ? amount : -amount;
    const actionText = operation === 'add' ? 'add' : 'subtract';

    if (!confirm(`Are you sure you want to ${actionText} $${amount} from this user's balance?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/users/${selectedUserId}/balance`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ amount: finalAmount })
        });

        if (response.ok) {
            alert('Balance updated successfully!');
            loadUsers(); // Refresh the user list
        } else {
            alert('Failed to update balance');
        }
    } catch (error) {
        console.error('Error updating balance:', error);
        alert('Error updating balance');
    }
}

async function setUserBalance(amount) {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    // NEW: Prompt for reason
    const reason = prompt('Enter reason for balance modification:');
    if (!reason || reason.trim() === '') {
        alert('Reason is required');
        return;
    }

    if (!confirm(`Are you sure you want to set this user's balance to $${amount}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/users/${selectedUserId}/balance`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                amount: amount,
                set: true,
                reason: reason.trim()
            })
        });

        if (response.ok) {
            alert('Balance set successfully!');
            loadUsers(); // Refresh the user list
        } else {
            alert('Failed to set balance');
        }
    } catch (error) {
        console.error('Error setting balance:', error);
        alert('Error setting balance');
    }
}

async function setCustomBalance() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    const amount = parseFloat(document.getElementById('custom-balance').value);

    if (isNaN(amount)) {
        alert('Please enter a valid amount');
        return;
    }

    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    // NEW: Prompt for reason
    const reason = prompt('Enter reason for balance modification:');
    if (!reason || reason.trim() === '') {
        alert('Reason is required');
        return;
    }

    if (!confirm(`Are you sure you want to set this user's balance to $${amount}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/users/${selectedUserId}/balance`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                amount: amount,
                set: true,
                reason: reason.trim()
            })
        });

        if (response.ok) {
            alert('Balance set successfully!');
            document.getElementById('custom-balance').value = '';
            loadUsers(); // Refresh the user list
        } else {
            alert('Failed to set balance');
        }
    } catch (error) {
        console.error('Error setting balance:', error);
        alert('Error setting balance');
    }
}

async function clearUserInventory() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (!confirm('Are you sure you want to clear this user\'s inventory? This cannot be undone!')) {
        return;
    }

    try {
        // This would need a new backend endpoint for inventory management
        alert('Clear inventory - This feature requires backend implementation');
    } catch (error) {
        console.error('Error clearing inventory:', error);
        alert('Error clearing inventory');
    }
}

async function giveUserItem() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    const itemName = document.getElementById('item-name').value.trim();
    const quantity = parseInt(document.getElementById('item-quantity').value) || 1;

    if (!itemName) {
        alert('Please enter an item name');
        return;
    }

    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    if (!confirm(`Are you sure you want to give ${quantity}x "${itemName}" to this user?`)) {
        return;
    }

    try {
        // This would need a new backend endpoint for inventory management
        alert('Give item - This feature requires backend implementation');
        document.getElementById('item-name').value = '';
        document.getElementById('item-quantity').value = '1';
    } catch (error) {
        console.error('Error giving item:', error);
        alert('Error giving item');
    }
}

// Moderation functions (placeholders for now)
function kickUser() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    alert('Kick user - This feature requires Discord API integration and admin permissions');
}

function banUser() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    alert('Ban user - This feature requires Discord API integration and admin permissions');
}

function muteUser() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    alert('Mute user - This feature requires Discord API integration and admin permissions');
}

function unmuteUser() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    alert('Unmute user - This feature requires Discord API integration and admin permissions');
}

// Info functions
function viewUserDetails() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    const user = allUsers.find(u => u.id === selectedUserId);
    if (user) {
        const inventory = Object.entries(user.inventory || {});
        const inventoryText = inventory.length > 0 ?
            inventory.map(([item, qty]) => `${item}: ${qty}`).join('\n') :
            'No items';

        alert(`${user.display_name} (${user.username}#${user.discriminator})\n\n` +
              `Balance: $${user.balance || 0}\n` +
              `Total Earned: $${user.total_earned || 0}\n` +
              `Total Spent: $${user.total_spent || 0}\n\n` +
              `Inventory:\n${inventoryText}\n\n` +
              `Roles: ${user.roles?.join(', ') || 'None'}\n` +
              `Joined: ${user.joined_at ? new Date(user.joined_at).toLocaleDateString() : 'Unknown'}`);
    }
}

function viewUserTransactions() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    alert('View transactions - This feature requires transaction logging implementation');
}

function exportUserData() {
    if (!selectedUserId) {
        alert('Please select a user first');
        return;
    }

    const user = allUsers.find(u => u.id === selectedUserId);
    if (user) {
        const userData = {
            id: user.id,
            username: user.username,
            discriminator: user.discriminator,
            display_name: user.display_name,
            balance: user.balance || 0,
            total_earned: user.total_earned || 0,
            total_spent: user.total_spent || 0,
            inventory: user.inventory || {},
            roles: user.roles || [],
            joined_at: user.joined_at,
            exported_at: new Date().toISOString()
        };

        const blob = new Blob([JSON.stringify(userData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `user-${user.username}-data.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// Load transactions
async function loadTransactions() {
    if (!currentServerId) {
        document.getElementById('transactions-list').innerHTML = '<p>Please select a server first.</p>';
        return;
    }

    try {
        // Load both transactions and statistics
        const [txnResponse, statsResponse] = await Promise.all([
            fetch(`/api/${currentServerId}/transactions`),
            fetch(`/api/${currentServerId}/transactions/statistics`)
        ]);

        const txnData = await txnResponse.json();
        const statsData = await statsResponse.json();

        const container = document.getElementById('transactions-list');
        if (!container) return;

        // Show statistics
        updateTransactionStats(statsData);

        if (!txnData.transactions || txnData.transactions.length === 0) {
            container.innerHTML = '<div class="empty-state">No transactions yet</div>';
            return;
        }

        // Sort by timestamp (newest first)
        const sorted = txnData.transactions.sort((a, b) =>
            new Date(b.timestamp) - new Date(a.timestamp)
        );

        let html = `
            <div class="table-controls">
                <input type="text" id="txn-search" placeholder="Search by user ID or description..." class="search-input">
                <select id="txn-filter" class="filter-select">
                    <option value="all">All Transactions</option>
                    <option value="positive">Gains Only</option>
                    <option value="negative">Losses Only</option>
                    <option value="daily">Daily Rewards</option>
                    <option value="shop">Shop Purchases</option>
                    <option value="admin">Admin Actions</option>
                    <option value="transfer_send">Transfers Sent</option>
                    <option value="transfer_receive">Transfers Received</option>
                    <option value="task">Task Rewards</option>
                </select>
                <span class="total-transactions">Total: ${sorted.length} transactions</span>
            </div>
            <div class="transactions-table">
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>User</th>
                            <th>Amount</th>
                            <th>Before</th>
                            <th>After</th>
                            <th>Description</th>
                            <th>Source</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="txn-table-body">
        `;

        sorted.forEach(txn => {
            const amount = txn.amount || 0;
            const amountClass = amount >= 0 ? 'positive' : 'negative';
            const amountSign = amount >= 0 ? '+' : '';
            const timestamp = new Date(txn.timestamp).toLocaleString();
            const source = txn.source || 'discord';
            const userDisplay = txn.display_name || txn.username || txn.user_id;

            html += `
                <tr data-user-id="${txn.user_id}" data-type="${getTxnType(txn)}" onclick="showTransactionDetail('${txn.id}')">
                    <td>${timestamp}</td>
                    <td>
                        <div class="user-cell">
                            ${txn.avatar_url ? `<img src="${txn.avatar_url}" class="user-avatar-small" alt="Avatar">` : ''}
                            <span>${userDisplay}</span>
                        </div>
                    </td>
                    <td class="${amountClass}">${amountSign}$${Math.abs(amount)}</td>
                    <td>$${txn.balance_before || 0}</td>
                    <td>$${txn.balance_after || 0}</td>
                    <td>${txn.description || 'N/A'}</td>
                    <td><span class="source-badge source-${source}">${source}</span></td>
                    <td><button onclick="event.stopPropagation(); showTransactionDetail('${txn.id}')" class="btn-small">👁️</button></td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        container.innerHTML = html;

        // Add search and filter functionality
        document.getElementById('txn-search').addEventListener('input', filterTransactions);
        document.getElementById('txn-filter').addEventListener('change', filterTransactions);

        // Populate user filter dropdown
        populateUserFilter(txnData.transactions);

    } catch (error) {
        console.error('Error loading transactions:', error);
        document.getElementById('transactions-list').innerHTML = '<p>Error loading transactions.</p>';
    }
}

function getTxnType(txn) {
    const desc = (txn.description || '').toLowerCase();
    if (desc.includes('daily')) return 'daily';
    if (desc.includes('purchase') || desc.includes('bought')) return 'shop';
    if (desc.includes('admin') || txn.source === 'cms') return 'admin';
    if (txn.amount > 0) return 'positive';
    if (txn.amount < 0) return 'negative';
    return 'all';
}

function filterTransactions() {
    const searchTerm = document.getElementById('txn-search').value.toLowerCase();
    const filterType = document.getElementById('txn-filter').value;

    const rows = document.querySelectorAll('#txn-table-body tr');
    let visibleCount = 0;

    rows.forEach(row => {
        const userId = row.dataset.userId;
        const txnType = row.dataset.type;
        const description = row.cells[5].textContent.toLowerCase();

        const matchesSearch = !searchTerm ||
            userId.includes(searchTerm) ||
            description.includes(searchTerm);

        const matchesFilter = filterType === 'all' || txnType === filterType;

        if (matchesSearch && matchesFilter) {
            row.style.display = '';
            visibleCount++;
        } else {
            row.style.display = 'none';
        }
    });

    document.querySelector('.total-transactions').textContent =
        `Showing: ${visibleCount} transactions`;
}

// Announcements Tab Content
async function loadAnnouncementsTab() {
    const content = document.getElementById('tab-content');
    content.innerHTML = `
        <div class="announcements-container">
            <div class="announcements-header">
                <h2>Announcements</h2>
                <div class="announcements-actions">
                    <button onclick="showCreateAnnouncementModal()" class="btn-primary">
                        📢 Create Announcement
                    </button>
                </div>
            </div>

            <div class="announcements-list" id="announcements-list">
                <div class="loading">Loading announcements...</div>
            </div>
        </div>
    `;

    await loadAnnouncements();
}

async function loadAnnouncements() {
    try {
        const response = await fetch(`/api/${currentServerId}/announcements`);
        const data = await response.json();

        const listContainer = document.getElementById('announcements-list');

        if (!data.announcements || Object.keys(data.announcements).length === 0) {
            listContainer.innerHTML = '<div class="empty-state">No announcements yet. Create one to get started!</div>';
            return;
        }

        // Convert to array and sort by date
        const announcements = Object.values(data.announcements).sort((a, b) =>
            new Date(b.created_at) - new Date(a.created_at)
        );

        listContainer.innerHTML = announcements.map(ann => `
            <div class="announcement-card" data-id="${ann.id}">
                <div class="announcement-header">
                    <div class="announcement-title">
                        <span class="announcement-type ${ann.type}">${getAnnouncementTypeEmoji(ann.type)}</span>
                        <h3>${escapeHtml(ann.title)}</h3>
                        ${ann.pinned ? '<span class="pinned-badge">📌 Pinned</span>' : ''}
                    </div>
                    <div class="announcement-actions">
                        <button onclick="editAnnouncement('${ann.id}')" class="btn-small" title="Edit">✏️</button>
                        ${!ann.pinned
                            ? `<button onclick="pinAnnouncement('${ann.id}')" class="btn-small" title="Pin">📌</button>`
                            : `<button onclick="unpinAnnouncement('${ann.id}')" class="btn-small" title="Unpin">📍</button>`
                        }
                        <button onclick="deleteAnnouncement('${ann.id}')" class="btn-small btn-danger" title="Delete">🗑️</button>
                    </div>
                </div>

                <div class="announcement-content">
                    <p>${escapeHtml(ann.content)}</p>
                </div>

                <div class="announcement-meta">
                    <span>Posted by ${escapeHtml(ann.author_name)}</span>
                    <span>${formatDate(ann.created_at)}</span>
                    <span>Channel: <a href="https://discord.com/channels/${currentServerId}/${ann.channel_id}" target="_blank">#${ann.channel_id}</a></span>
                    ${ann.message_id ? `<span>Message: <a href="https://discord.com/channels/${currentServerId}/${ann.channel_id}/${ann.message_id}" target="_blank">${ann.message_id}</a></span>` : ''}
                </div>

                ${data.task_announcements && Object.values(data.task_announcements).find(ta => ta.announcement_id === ann.id)
                    ? `<div class="task-link">🔗 Linked to Task ID: ${Object.keys(data.task_announcements).find(tid => data.task_announcements[tid].announcement_id === ann.id)}</div>`
                    : ''
                }
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load announcements:', error);
        document.getElementById('announcements-list').innerHTML =
            '<div class="error">Failed to load announcements. Please try again.</div>';
    }
}

function showCreateAnnouncementModal() {
    // Get available channels
    fetch(`/api/${currentServerId}/users`)
        .then(res => res.json())
        .then(data => {
            const guild = servers.find(s => s.id === currentServerId);

            showModal(`
                <h2>Create Announcement</h2>
                <form id="create-announcement-form" onsubmit="createAnnouncement(event)">
                    <div class="form-group">
                        <label>Title *</label>
                        <input type="text" id="ann-title" required maxlength="100"
                               placeholder="Announcement title">
                    </div>

                    <div class="form-group">
                        <label>Content *</label>
                        <textarea id="ann-content" required rows="5" maxlength="2000"
                                  placeholder="Announcement content"></textarea>
                        <small>Supports Discord markdown formatting</small>
                    </div>

                    <div class="form-group">
                        <label>Type</label>
                        <select id="ann-type">
                            <option value="general">General</option>
                            <option value="update">Update</option>
                            <option value="event">Event</option>
                            <option value="important">Important</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Channel *</label>
                        <input type="text" id="ann-channel" required
                               placeholder="Channel ID (e.g., 123456789)">
                        <small>Enter the Discord channel ID where the announcement will be posted</small>
                    </div>

                    <div class="form-group">
                        <label>Embed Color</label>
                        <input type="color" id="ann-color" value="#5865F2">
                    </div>

                    <div class="form-group checkbox-group">
                        <label>
                            <input type="checkbox" id="ann-mention-everyone">
                            Mention @everyone
                        </label>
                    </div>

                    <div class="form-group checkbox-group">
                        <label>
                            <input type="checkbox" id="ann-pin">
                            Pin announcement
                        </label>
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn-primary">Create Announcement</button>
                        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
                    </div>
                </form>
            `);
        });
}

async function createAnnouncement(event) {
    event.preventDefault();

    const title = document.getElementById('ann-title').value;
    const content = document.getElementById('ann-content').value;
    const type = document.getElementById('ann-type').value;
    const channelId = document.getElementById('ann-channel').value;
    const color = document.getElementById('ann-color').value;
    const mentionEveryone = document.getElementById('ann-mention-everyone').checked;
    const pin = document.getElementById('ann-pin').checked;

    try {
        const response = await fetch(`/api/${currentServerId}/announcements`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title,
                content,
                type,
                channel_id: channelId,
                author_id: 'web_dashboard',
                author_name: 'Dashboard Admin',
                embed_color: color,
                mentions: {
                    everyone: mentionEveryone,
                    roles: [],
                    users: []
                },
                auto_pin: pin
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create announcement');
        }

        const announcement = await response.json();

        closeModal();
        showNotification('✅ Announcement created successfully!', 'success');
        await loadAnnouncements();

    } catch (error) {
        console.error('Failed to create announcement:', error);
        showNotification(`❌ Failed to create announcement: ${error.message}`, 'error');
    }
}

async function editAnnouncement(announcementId) {
    try {
        // Load current announcement data
        const response = await fetch(`/api/${currentServerId}/announcements`);
        const data = await response.json();
        const announcement = data.announcements[announcementId];

        if (!announcement) {
            throw new Error('Announcement not found');
        }

        showModal(`
            <h2>Edit Announcement</h2>
            <form id="edit-announcement-form" onsubmit="submitAnnouncementEdit(event, '${announcementId}')">
                <div class="form-group">
                    <label>Title *</label>
                    <input type="text" id="edit-ann-title" required maxlength="100"
                           value="${escapeHtml(announcement.title)}">
                </div>

                <div class="form-group">
                    <label>Content *</label>
                    <textarea id="edit-ann-content" required rows="5" maxlength="2000">${escapeHtml(announcement.content)}</textarea>
                </div>

                <div class="form-group">
                    <label>Embed Color</label>
                    <input type="color" id="edit-ann-color" value="${announcement.embed.color}">
                </div>

                <div class="form-actions">
                    <button type="submit" class="btn-primary">Save Changes</button>
                    <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
                </div>
            </form>
        `);

    } catch (error) {
        showNotification(`❌ Failed to load announcement: ${error.message}`, 'error');
    }
}

async function submitAnnouncementEdit(event, announcementId) {
    event.preventDefault();

    const title = document.getElementById('edit-ann-title').value;
    const content = document.getElementById('edit-ann-content').value;
    const color = document.getElementById('edit-ann-color').value;

    try {
        const response = await fetch(`/api/${currentServerId}/announcements/${announcementId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, content, embed_color: color })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to update announcement');
        }

        closeModal();
        showNotification('✅ Announcement updated successfully!', 'success');
        await loadAnnouncements();

    } catch (error) {
        console.error('Failed to update announcement:', error);
        showNotification(`❌ Failed to update announcement: ${error.message}`, 'error');
    }
}

async function deleteAnnouncement(announcementId) {
    if (!confirm('Are you sure you want to delete this announcement? This will also delete the Discord message.')) {
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/announcements/${announcementId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ delete_discord_message: true })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to delete announcement');
        }

        showNotification('✅ Announcement deleted successfully!', 'success');
        await loadAnnouncements();

    } catch (error) {
        console.error('Failed to delete announcement:', error);
        showNotification(`❌ Failed to delete announcement: ${error.message}`, 'error');
    }
}

async function pinAnnouncement(announcementId) {
    try {
        const response = await fetch(`/api/${currentServerId}/announcements/${announcementId}/pin`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to pin announcement');
        }

        showNotification('✅ Announcement pinned successfully!', 'success');
        await loadAnnouncements();

    } catch (error) {
        console.error('Failed to pin announcement:', error);
        showNotification(`❌ Failed to pin announcement: ${error.message}`, 'error');
    }
}

async function unpinAnnouncement(announcementId) {
    try {
        const response = await fetch(`/api/${currentServerId}/announcements/${announcementId}/unpin`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to unpin announcement');
        }

        showNotification('✅ Announcement unpinned successfully!', 'success');
        await loadAnnouncements();

    } catch (error) {
        console.error('Failed to unpin announcement:', error);
        showNotification(`❌ Failed to unpin announcement: ${error.message}`, 'error');
    }
}

function getAnnouncementTypeEmoji(type) {
    const emojis = {
        'general': '📢',
        'update': '🔔',
        'event': '🎉',
        'important': '⚠️',
        'task': '📋'
    };
    return emojis[type] || '📢';
}

// Helper functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Modal functions (assuming these exist in the main script)
function showModal(content) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="modal-close" onclick="closeModal()">&times;</span>
                <div id="modal-body"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById('modal-body').innerHTML = content;
    modal.style.display = 'block';
}

function closeModal() {
    const modal = document.getElementById('modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Add announcements tab to navigation
function initializeTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            // Remove active class from all tabs
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const tabName = tab.dataset.tab;

            // Load appropriate content
            switch(tabName) {
                case 'dashboard':
                    await loadDashboardTab();
                    break;
                case 'users':
                    await loadUsersTab();
                    break;
                case 'shop':
                    await loadShopTab();
                    break;
                case 'tasks':
                    await loadTasksTab();
                    break;
                case 'announcements':
                    await loadAnnouncementsTab();
                    break;
                case 'transactions':
                    await loadTransactionsTab();
                    break;
                case 'settings':
                    await loadSettingsTab();
                    break;
                case 'logs':
                    await loadLogsTab();
                    break;
            }
        });
    });
}

// Integration with task creation
async function createTaskWithAnnouncement(taskData, announceTask) {
    try {
        // Create task first
        const taskResponse = await fetch(`/api/${currentServerId}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(taskData)
        });

        if (!taskResponse.ok) {
            throw new Error('Failed to create task');
        }

        const task = await taskResponse.json();

        // Create announcement if requested
        if (announceTask) {
            const annResponse = await fetch(`/api/${currentServerId}/announcements/task/${task.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: taskData.channel_id,
                    author_id: 'web_dashboard',
                    author_name: 'Dashboard Admin',
                    auto_pin: true
                })
            });

            if (!annResponse.ok) {
                console.error('Task created but announcement failed');
            }
        }

        return task;

    } catch (error) {
        throw error;
    }
}

async function exportTransactions() {
    if (!currentServerId) {
        alert('Please select a server first');
        return;
    }

    try {
        window.location.href = `/api/${currentServerId}/transactions/export`;
        alert('Exporting transactions...');
    } catch (error) {
        console.error('Error exporting transactions:', error);
        alert('Failed to export transactions');
    }
}

// Transaction UI enhancement functions
let currentPage = 1;
let totalPages = 1;
let currentFilters = {};

function showTransactionFilters() {
    const filtersSection = document.getElementById('transaction-filters');
    const statsSection = document.getElementById('transaction-stats');

    if (filtersSection) {
        filtersSection.style.display = 'block';
        // Show stats when filters are shown
        if (statsSection) {
            statsSection.style.display = 'block';
        }
    }
}

function hideTransactionFilters() {
    const filtersSection = document.getElementById('transaction-filters');
    if (filtersSection) {
        filtersSection.style.display = 'none';
    }
}

async function applyFilters() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;
    const userId = document.getElementById('user-filter').value;
    const type = document.getElementById('type-filter').value;
    const minAmount = document.getElementById('min-amount').value;
    const maxAmount = document.getElementById('max-amount').value;

    // Build query parameters
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', new Date(startDate).toISOString());
    if (endDate) params.append('end_date', new Date(endDate).toISOString());
    if (userId) params.append('user_id', userId);
    if (type && type !== 'all') params.append('type', type);
    if (minAmount) params.append('min_amount', minAmount);
    if (maxAmount) params.append('max_amount', maxAmount);

    try {
        const response = await fetch(`/api/${currentServerId}/transactions?${params}`);
        const data = await response.json();

        if (!data.transactions || data.transactions.length === 0) {
            document.getElementById('transactions-list').innerHTML = '<div class="empty-state">No transactions match your filters</div>';
            return;
        }

        // Update the table with filtered results
        updateTransactionTable(data.transactions);

    } catch (error) {
        console.error('Error applying filters:', error);
        showNotification('Error applying filters', 'error');
    }
}

function clearFilters() {
    // Reset all filter inputs
    document.getElementById('start-date').value = '';
    document.getElementById('end-date').value = '';
    document.getElementById('user-filter').value = '';
    document.getElementById('type-filter').value = 'all';
    document.getElementById('min-amount').value = '';
    document.getElementById('max-amount').value = '';

    // Reload all transactions
    loadTransactions();
}

function updateTransactionStats(statsData) {
    const statsSection = document.getElementById('transaction-stats');
    if (!statsSection || !statsData) return;

    document.getElementById('total-transactions').textContent = statsData.total_transactions || 0;
    document.getElementById('total-volume').textContent = `$${statsData.total_volume || 0}`;
    document.getElementById('most-active-user').textContent = statsData.most_active_user || '-';
    document.getElementById('avg-transaction').textContent = `$${statsData.avg_transaction || 0}`;

    statsSection.style.display = 'block';
}

function populateUserFilter(transactions) {
    const userFilter = document.getElementById('user-filter');
    if (!userFilter) return;

    // Get unique users from transactions
    const users = new Map();

    transactions.forEach(txn => {
        if (!users.has(txn.user_id)) {
            users.set(txn.user_id, {
                id: txn.user_id,
                display_name: txn.display_name || txn.username || txn.user_id,
                avatar_url: txn.avatar_url
            });
        }
    });

    // Clear existing options except "All Users"
    userFilter.innerHTML = '<option value="">All Users</option>';

    // Add user options
    users.forEach(user => {
        const option = document.createElement('option');
        option.value = user.id;
        option.textContent = user.display_name;
        userFilter.appendChild(option);
    });
}

function updateTransactionTable(transactions) {
    const container = document.getElementById('transactions-list');

    if (!transactions || transactions.length === 0) {
        container.innerHTML = '<div class="empty-state">No transactions found</div>';
        return;
    }

    // Sort by timestamp (newest first)
    const sorted = transactions.sort((a, b) =>
        new Date(b.timestamp) - new Date(a.timestamp)
    );

    // Pagination setup
    const itemsPerPage = 50;
    totalPages = Math.ceil(sorted.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const pageTransactions = sorted.slice(startIndex, endIndex);

    let html = `
        <div class="table-controls">
            <input type="text" id="txn-search" placeholder="Search by user ID or description..." class="search-input">
            <select id="txn-filter" class="filter-select">
                <option value="all">All Transactions</option>
                <option value="positive">Gains Only</option>
                <option value="negative">Losses Only</option>
                <option value="daily">Daily Rewards</option>
                <option value="shop">Shop Purchases</option>
                <option value="admin">Admin Actions</option>
                <option value="transfer_send">Transfers Sent</option>
                <option value="transfer_receive">Transfers Received</option>
                <option value="task">Task Rewards</option>
            </select>
            <span class="total-transactions">Showing ${startIndex + 1}-${Math.min(endIndex, sorted.length)} of ${sorted.length} transactions</span>
        </div>
    `;

    // Add pagination controls if needed
    if (totalPages > 1) {
        html += `<div class="pagination-controls">${generatePaginationControls()}</div>`;
    }

    html += `
        <div class="transactions-table">
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>User</th>
                        <th>Amount</th>
                        <th>Before</th>
                        <th>After</th>
                        <th>Description</th>
                        <th>Source</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="txn-table-body">
    `;

    pageTransactions.forEach(txn => {
        const amount = txn.amount || 0;
        const amountClass = amount >= 0 ? 'positive' : 'negative';
        const amountSign = amount >= 0 ? '+' : '';
        const timestamp = new Date(txn.timestamp).toLocaleString();
        const source = txn.source || 'discord';
        const userDisplay = txn.display_name || txn.username || txn.user_id;

        html += `
            <tr data-user-id="${txn.user_id}" data-type="${getTxnType(txn)}" onclick="showTransactionDetail('${txn.id}')">
                <td>${timestamp}</td>
                <td>
                    <div class="user-cell">
                        ${txn.avatar_url ? `<img src="${txn.avatar_url}" class="user-avatar-small" alt="Avatar">` : ''}
                        <span>${userDisplay}</span>
                    </div>
                </td>
                <td class="${amountClass}">${amountSign}$${Math.abs(amount)}</td>
                <td>$${txn.balance_before || 0}</td>
                <td>$${txn.balance_after || 0}</td>
                <td>${txn.description || 'N/A'}</td>
                <td><span class="source-badge source-${source}">${source}</span></td>
                <td><button onclick="event.stopPropagation(); showTransactionDetail('${txn.id}')" class="btn-small">👁️</button></td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    // Add pagination controls at bottom if needed
    if (totalPages > 1) {
        html += `<div class="pagination-controls">${generatePaginationControls()}</div>`;
    }

    container.innerHTML = html;

    // Re-attach event listeners
    document.getElementById('txn-search').addEventListener('input', filterTransactions);
    document.getElementById('txn-filter').addEventListener('change', filterTransactions);
}

function generatePaginationControls() {
    let html = '<div class="pagination">';

    // Previous button
    if (currentPage > 1) {
        html += `<button onclick="changePage(${currentPage - 1})" class="btn-small">« Previous</button>`;
    }

    // Page numbers
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);

    if (startPage > 1) {
        html += `<button onclick="changePage(1)" class="btn-small">1</button>`;
        if (startPage > 2) {
            html += '<span>...</span>';
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        const activeClass = i === currentPage ? ' active' : '';
        html += `<button onclick="changePage(${i})" class="btn-small${activeClass}">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += '<span>...</span>';
        }
        html += `<button onclick="changePage(${totalPages})" class="btn-small">${totalPages}</button>`;
    }

    // Next button
    if (currentPage < totalPages) {
        html += `<button onclick="changePage(${currentPage + 1})" class="btn-small">Next »</button>`;
    }

    html += '</div>';
    return html;
}

function changePage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    loadTransactions(); // Reload with new page
}

async function showTransactionDetail(transactionId) {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/transactions/${transactionId}`);
        const txn = await response.json();

        if (!txn || response.status === 404) {
            showNotification('Transaction not found', 'error');
            return;
        }

        const amount = txn.amount || 0;
        const amountClass = amount >= 0 ? 'positive' : 'negative';
        const amountSign = amount >= 0 ? '+' : '';
        const timestamp = new Date(txn.timestamp).toLocaleString();
        const source = txn.source || 'discord';
        const userDisplay = txn.username || txn.display_name || txn.user_id;

        showModal(`
            <h2>Transaction Details</h2>
            <div class="transaction-detail">
                <div class="detail-row">
                    <strong>Transaction ID:</strong>
                    <code>${txn.id}</code>
                </div>
                <div class="detail-row">
                    <strong>Timestamp:</strong>
                    <span>${timestamp}</span>
                </div>
                <div class="detail-row">
                    <strong>User:</strong>
                    <span>${userDisplay} (${txn.user_id})</span>
                </div>
                <div class="detail-row">
                    <strong>Amount:</strong>
                    <span class="${amountClass}">${amountSign}$${Math.abs(amount)}</span>
                </div>
                <div class="detail-row">
                    <strong>Balance Before:</strong>
                    <span>$${txn.balance_before || 0}</span>
                </div>
                <div class="detail-row">
                    <strong>Balance After:</strong>
                    <span>$${txn.balance_after || 0}</span>
                </div>
                <div class="detail-row">
                    <strong>Description:</strong>
                    <span>${txn.description || 'N/A'}</span>
                </div>
                <div class="detail-row">
                    <strong>Source:</strong>
                    <span class="source-badge source-${source}">${source}</span>
                </div>
                ${txn.metadata ? `
                    <div class="detail-row">
                        <strong>Metadata:</strong>
                        <pre class="metadata">${JSON.stringify(txn.metadata, null, 2)}</pre>
                    </div>
                ` : ''}
            </div>
            <div class="modal-actions">
                <button onclick="closeModal()" class="btn-secondary">Close</button>
            </div>
        `);

    } catch (error) {
        console.error('Error loading transaction detail:', error);
        showNotification('Error loading transaction details', 'error');
    }
}

async function archiveOldTransactions() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    // Show confirmation modal with options
    showModal(`
        <h2>Archive Old Transactions</h2>
        <p>This will move transactions older than the specified number of days to an archive file.</p>
        <p><strong>Warning:</strong> Archived transactions will be removed from the main database but can be restored from the archive files if needed.</p>

        <div class="archive-options">
            <div class="form-group">
                <label>Days to keep (transactions older than this will be archived):</label>
                <input type="number" id="archive-days" value="90" min="1" max="365" class="form-control">
            </div>
            <div class="form-group checkbox-group">
                <label>
                    <input type="checkbox" id="archive-enabled" checked>
                    Create archive file (uncheck to permanently delete)
                </label>
            </div>
        </div>

        <div class="modal-actions">
            <button onclick="confirmArchive()" class="btn-warning">Archive Transactions</button>
            <button onclick="closeModal()" class="btn-secondary">Cancel</button>
        </div>
    `);
}

async function confirmArchive() {
    const daysToKeep = parseInt(document.getElementById('archive-days').value);
    const archiveEnabled = document.getElementById('archive-enabled').checked;

    if (isNaN(daysToKeep) || daysToKeep < 1) {
        showNotification('Please enter a valid number of days', 'error');
        return;
    }

    if (!confirm(`Are you sure you want to archive transactions older than ${daysToKeep} days? ${archiveEnabled ? 'They will be moved to an archive file.' : 'They will be permanently deleted.'}`)) {
        return;
    }

    closeModal();
    showNotification('Archiving transactions...', 'info');

    try {
        const response = await fetch(`/api/${currentServerId}/transactions/archive`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                days_to_keep: daysToKeep,
                archive: archiveEnabled
            })
        });

        const result = await response.json();

        if (result.success) {
            showNotification(
                `Successfully archived ${result.archived_count} transactions. ${result.remaining_count} transactions remain.`,
                'success'
            );

            // Refresh the transaction list
            loadTransactions();
        } else {
            showNotification(result.error || 'Failed to archive transactions', 'error');
        }

    } catch (error) {
        console.error('Error archiving transactions:', error);
        showNotification('Error archiving transactions', 'error');
    }
}

// === EMBEDS MANAGEMENT FUNCTIONS ===

// Load embeds
async function loadEmbeds() {
    if (!currentServerId) {
        document.getElementById('embeds-list').innerHTML = '<p>Please select a server first.</p>';
        return;
    }

    try {
        showLoading('embeds');

        const response = await fetch(`/api/${currentServerId}/embeds`);
        const data = await response.json();

        const embedsContainer = document.getElementById('embeds-list');
        embedsContainer.innerHTML = '';

        if (!data.embeds || Object.keys(data.embeds).length === 0) {
            embedsContainer.innerHTML = '<div class="empty-state">No embeds found for this server. <button onclick="showCreateEmbedModal()" class="btn-primary">Create First Embed</button></div>';
            hideLoading('embeds');
            return;
        }

        const embedsGrid = document.createElement('div');
        embedsGrid.className = 'embeds-grid';

        Object.entries(data.embeds).forEach(([embedId, embed]) => {
            const embedCard = createEmbedCard(embedId, embed);
            embedsGrid.appendChild(embedCard);
        });

        embedsContainer.appendChild(embedsGrid);
        hideLoading('embeds');

    } catch (error) {
        console.error('Error loading embeds:', error);
        document.getElementById('embeds-list').innerHTML = '<div class="error-state">Error loading embeds. Please try again.</div>';
        hideLoading('embeds');
    }
}

// Create embed card
function createEmbedCard(embedId, embed) {
    const card = document.createElement('div');
    card.className = 'embed-card';

    const title = embed.title || 'Untitled Embed';
    const description = embed.description || 'No description';
    const type = embed.type || 'general';
    const createdAt = embed.created_at ? new Date(embed.created_at).toLocaleDateString() : 'Unknown';

    card.innerHTML = `
        <div class="embed-card-header">
            <div class="embed-card-title">${escapeHtml(title)}</div>
            <span class="embed-card-type">${type}</span>
        </div>
        <div class="embed-card-description">${escapeHtml(description.substring(0, 100))}${description.length > 100 ? '...' : ''}</div>
        <div class="embed-card-footer">
            <span>Created: ${createdAt}</span>
            <div class="embed-card-actions">
                <button onclick="editEmbed('${embedId}')" class="btn-small" title="Edit">✏️</button>
                <button onclick="duplicateEmbed('${embedId}')" class="btn-small" title="Duplicate">📋</button>
                <button onclick="deleteEmbed('${embedId}')" class="btn-small btn-danger" title="Delete">🗑️</button>
            </div>
        </div>
    `;

    return card;
}

// Show create embed modal
function showCreateEmbedModal() {
    showModal(`
        <div class="modal-large">
            <h2>Create New Embed</h2>
            <div class="embed-editor">
                <div class="embed-form">
                    <div class="form-group">
                        <label>Embed ID *</label>
                        <input type="text" id="embed-id" required placeholder="unique_embed_id" pattern="[a-zA-Z0-9_]+" title="Only letters, numbers, and underscores allowed">
                        <small>Unique identifier (no spaces, only letters/numbers/underscores)</small>
                    </div>

                    <div class="form-group">
                        <label>Title</label>
                        <input type="text" id="embed-title" placeholder="Embed Title" maxlength="256">
                        <span class="char-count" id="title-count">0/256</span>
                    </div>

                    <div class="form-group">
                        <label>Description</label>
                        <textarea id="embed-description" rows="3" placeholder="Embed description" maxlength="4096"></textarea>
                        <span class="char-count" id="desc-count">0/4096</span>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Author Name</label>
                            <input type="text" id="embed-author-name" placeholder="Author name" maxlength="256">
                        </div>
                        <div class="form-group">
                            <label>Author Icon URL</label>
                            <input type="url" id="embed-author-icon" placeholder="https://example.com/icon.png">
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="color-input-group">
                            <label>Embed Color</label>
                            <input type="color" id="embed-color" value="#5865F2">
                            <input type="text" id="embed-color-hex" value="#5865F2" readonly>
                        </div>
                        <div class="form-group">
                            <label>Thumbnail URL</label>
                            <input type="url" id="embed-thumbnail" placeholder="https://example.com/thumbnail.png">
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Image URL</label>
                        <input type="url" id="embed-image" placeholder="https://example.com/image.png">
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label>Footer Text</label>
                            <input type="text" id="embed-footer-text" placeholder="Footer text" maxlength="2048">
                        </div>
                        <div class="form-group">
                            <label>Footer Icon URL</label>
                            <input type="url" id="embed-footer-icon" placeholder="https://example.com/icon.png">
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Fields</label>
                        <div id="embed-fields-container">
                            <div class="embed-field-item">
                                <div class="field-header">
                                    <span>Field 1</span>
                                    <button onclick="removeEmbedField(this)" class="btn-small btn-danger">Remove</button>
                                </div>
                                <input type="text" placeholder="Field name" maxlength="256">
                                <textarea rows="2" placeholder="Field value" maxlength="1024"></textarea>
                                <label><input type="checkbox"> Inline</label>
                            </div>
                        </div>
                        <button onclick="addEmbedField()" class="btn-secondary btn-small">Add Field</button>
                    </div>

                    <div class="form-group">
                        <label>Type</label>
                        <select id="embed-type">
                            <option value="general">General</option>
                            <option value="announcement">Announcement</option>
                            <option value="task">Task</option>
                            <option value="shop">Shop</option>
                            <option value="welcome">Welcome</option>
                        </select>
                    </div>
                </div>

                <div class="discord-embed-preview">
                    <h3>Preview</h3>
                    <div id="embed-preview">
                        <div class="preview-embed">
                            <div id="preview-author" style="display: none;">
                                <img id="preview-author-icon" src="" alt="Author">
                                <span id="preview-author-name"></span>
                            </div>
                            <div id="preview-title"></div>
                            <div id="preview-description"></div>
                            <div id="preview-fields"></div>
                            <div id="preview-thumbnail" style="display: none;">
                                <img id="preview-thumbnail-img" src="" alt="Thumbnail">
                            </div>
                            <div id="preview-image" style="display: none;">
                                <img id="preview-image-img" src="" alt="Image">
                            </div>
                            <div id="preview-footer" style="display: none;">
                                <img id="preview-footer-icon" src="" alt="Footer">
                                <span id="preview-footer-text"></span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="form-actions">
                <button onclick="createEmbed()" class="btn-primary">Create Embed</button>
                <button onclick="closeModal()" class="btn-secondary">Cancel</button>
            </div>
        </div>
    `);

    // Add event listeners for live preview
    setupEmbedPreview();
}

// Setup embed preview
function setupEmbedPreview() {
    const inputs = [
        'embed-title', 'embed-description', 'embed-author-name', 'embed-author-icon',
        'embed-color', 'embed-thumbnail', 'embed-image', 'embed-footer-text', 'embed-footer-icon'
    ];

    inputs.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', updateEmbedPreview);
        }
    });

    // Color picker sync
    document.getElementById('embed-color').addEventListener('input', function() {
        document.getElementById('embed-color-hex').value = this.value;
        updateEmbedPreview();
    });

    // Character counters
    document.getElementById('embed-title').addEventListener('input', function() {
        document.getElementById('title-count').textContent = `${this.value.length}/256`;
    });

    document.getElementById('embed-description').addEventListener('input', function() {
        document.getElementById('desc-count').textContent = `${this.value.length}/4096`;
    });

    // Initial preview update
    updateEmbedPreview();
}

// Update embed preview
function updateEmbedPreview() {
    const title = document.getElementById('embed-title').value;
    const description = document.getElementById('embed-description').value;
    const authorName = document.getElementById('embed-author-name').value;
    const authorIcon = document.getElementById('embed-author-icon').value;
    const color = document.getElementById('embed-color').value;
    const thumbnail = document.getElementById('embed-thumbnail').value;
    const image = document.getElementById('embed-image').value;
    const footerText = document.getElementById('embed-footer-text').value;
    const footerIcon = document.getElementById('embed-footer-icon').value;

    // Update preview elements
    const previewEmbed = document.querySelector('.preview-embed');
    if (previewEmbed) {
        previewEmbed.style.borderLeftColor = color;
    }

    const previewTitle = document.getElementById('preview-title');
    if (previewTitle) {
        previewTitle.textContent = title;
        previewTitle.style.display = title ? 'block' : 'none';
    }

    const previewDesc = document.getElementById('preview-description');
    if (previewDesc) {
        previewDesc.textContent = description;
        previewDesc.style.display = description ? 'block' : 'none';
    }

    const previewAuthor = document.getElementById('preview-author');
    if (previewAuthor) {
        const authorNameEl = document.getElementById('preview-author-name');
        const authorIconEl = document.getElementById('preview-author-icon');

        if (authorName) {
            authorNameEl.textContent = authorName;
            if (authorIcon) {
                authorIconEl.src = authorIcon;
                authorIconEl.style.display = 'inline';
            } else {
                authorIconEl.style.display = 'none';
            }
            previewAuthor.style.display = 'flex';
        } else {
            previewAuthor.style.display = 'none';
        }
    }

    const previewThumbnail = document.getElementById('preview-thumbnail');
    if (previewThumbnail) {
        const thumbnailImg = document.getElementById('preview-thumbnail-img');
        if (thumbnail) {
            thumbnailImg.src = thumbnail;
            previewThumbnail.style.display = 'block';
        } else {
            previewThumbnail.style.display = 'none';
        }
    }

    const previewImage = document.getElementById('preview-image');
    if (previewImage) {
        const imageImg = document.getElementById('preview-image-img');
        if (image) {
            imageImg.src = image;
            previewImage.style.display = 'block';
        } else {
            previewImage.style.display = 'none';
        }
    }

    const previewFooter = document.getElementById('preview-footer');
    if (previewFooter) {
        const footerTextEl = document.getElementById('preview-footer-text');
        const footerIconEl = document.getElementById('preview-footer-icon');

        if (footerText) {
            footerTextEl.textContent = footerText;
            if (footerIcon) {
                footerIconEl.src = footerIcon;
                footerIconEl.style.display = 'inline';
            } else {
                footerIconEl.style.display = 'none';
            }
            previewFooter.style.display = 'flex';
        } else {
            previewFooter.style.display = 'none';
        }
    }

    // Update fields preview
    updateFieldsPreview();
}

// Update fields preview
function updateFieldsPreview() {
    const fieldsContainer = document.getElementById('embed-fields-container');
    const previewFields = document.getElementById('preview-fields');

    if (!fieldsContainer || !previewFields) return;

    const fieldItems = fieldsContainer.querySelectorAll('.embed-field-item');
    let fieldsHtml = '';

    fieldItems.forEach(item => {
        const inputs = item.querySelectorAll('input, textarea');
        const name = inputs[0]?.value || '';
        const value = inputs[1]?.value || '';
        const inline = inputs[2]?.checked || false;

        if (name && value) {
            fieldsHtml += `
                <div class="preview-embed-field ${inline ? 'inline' : ''}">
                    <div class="preview-embed-field-name">${escapeHtml(name)}</div>
                    <div class="preview-embed-field-value">${escapeHtml(value)}</div>
                </div>
            `;
        }
    });

    previewFields.innerHTML = fieldsHtml;
    previewFields.style.display = fieldsHtml ? 'grid' : 'none';
}

// Add embed field
function addEmbedField() {
    const container = document.getElementById('embed-fields-container');
    const fieldCount = container.children.length + 1;

    const fieldItem = document.createElement('div');
    fieldItem.className = 'embed-field-item';
    fieldItem.innerHTML = `
        <div class="field-header">
            <span>Field ${fieldCount}</span>
            <button onclick="removeEmbedField(this)" class="btn-small btn-danger">Remove</button>
        </div>
        <input type="text" placeholder="Field name" maxlength="256">
        <textarea rows="2" placeholder="Field value" maxlength="1024"></textarea>
        <label><input type="checkbox"> Inline</label>
    `;

    // Add event listeners for live preview
    const inputs = fieldItem.querySelectorAll('input, textarea');
    inputs.forEach(input => {
        input.addEventListener('input', updateFieldsPreview);
    });

    container.appendChild(fieldItem);
}

// Remove embed field
function removeEmbedField(button) {
    const fieldItem = button.closest('.embed-field-item');
    fieldItem.remove();
    updateFieldsPreview();
}

// Create embed
async function createEmbed() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    const embedId = document.getElementById('embed-id').value.trim();
    if (!embedId) {
        showNotification('Embed ID is required', 'error');
        return;
    }

    // Collect embed data
    const embedData = {
        id: embedId,
        title: document.getElementById('embed-title').value.trim(),
        description: document.getElementById('embed-description').value.trim(),
        color: parseInt(document.getElementById('embed-color').value.replace('#', ''), 16),
        type: document.getElementById('embed-type').value,
        author: {
            name: document.getElementById('embed-author-name').value.trim(),
            icon_url: document.getElementById('embed-author-icon').value.trim()
        },
        thumbnail: {
            url: document.getElementById('embed-thumbnail').value.trim()
        },
        image: {
            url: document.getElementById('embed-image').value.trim()
        },
        footer: {
            text: document.getElementById('embed-footer-text').value.trim(),
            icon_url: document.getElementById('embed-footer-icon').value.trim()
        },
        fields: []
    };

    // Collect fields
    const fieldItems = document.getElementById('embed-fields-container').querySelectorAll('.embed-field-item');
    fieldItems.forEach(item => {
        const inputs = item.querySelectorAll('input, textarea');
        const name = inputs[0].value.trim();
        const value = inputs[1].value.trim();
        const inline = inputs[2].checked;

        if (name && value) {
            embedData.fields.push({
                name: name,
                value: value,
                inline: inline
            });
        }
    });

    // Clean up empty objects
    Object.keys(embedData).forEach(key => {
        if (typeof embedData[key] === 'object' && embedData[key] !== null) {
            const obj = embedData[key];
            if (Object.values(obj).every(val => !val || val === '')) {
                delete embedData[key];
            }
        }
    });

    try {
        const response = await fetch(`/api/${currentServerId}/embeds`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(embedData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create embed');
        }

        const result = await response.json();

        closeModal();
        showNotification('✅ Embed created successfully!', 'success');
        await loadEmbeds();

    } catch (error) {
        console.error('Error creating embed:', error);
        showNotification(`❌ Failed to create embed: ${error.message}`, 'error');
    }
}

// Edit embed
async function editEmbed(embedId) {
    try {
        const response = await fetch(`/api/${currentServerId}/embeds/${embedId}`);
        const embed = await response.json();

        // Populate the create modal with existing data
        showCreateEmbedModal();

        // Fill in the form
        document.getElementById('embed-id').value = embedId;
        document.getElementById('embed-id').disabled = true;
        document.getElementById('embed-title').value = embed.title || '';
        document.getElementById('embed-description').value = embed.description || '';
        document.getElementById('embed-author-name').value = embed.author?.name || '';
        document.getElementById('embed-author-icon').value = embed.author?.icon_url || '';
        document.getElementById('embed-color').value = embed.color ? `#${embed.color.toString(16).padStart(6, '0')}` : '#5865F2';
        document.getElementById('embed-thumbnail').value = embed.thumbnail?.url || '';
        document.getElementById('embed-image').value = embed.image?.url || '';
        document.getElementById('embed-footer-text').value = embed.footer?.text || '';
        document.getElementById('embed-footer-icon').value = embed.footer?.icon_url || '';
        document.getElementById('embed-type').value = embed.type || 'general';

        // Clear existing fields and add the embed's fields
        const fieldsContainer = document.getElementById('embed-fields-container');
        fieldsContainer.innerHTML = '';

        if (embed.fields && embed.fields.length > 0) {
            embed.fields.forEach((field, index) => {
                addEmbedField();
                const fieldItems = fieldsContainer.querySelectorAll('.embed-field-item');
                const lastField = fieldItems[fieldItems.length - 1];
                const inputs = lastField.querySelectorAll('input, textarea');
                inputs[0].value = field.name || '';
                inputs[1].value = field.value || '';
                inputs[2].checked = field.inline || false;
            });
        } else {
            // Add one empty field
            addEmbedField();
        }

        // Change button text
        const submitBtn = document.querySelector('.modal-content .btn-primary');
        if (submitBtn) {
            submitBtn.textContent = 'Update Embed';
            submitBtn.onclick = () => updateEmbed(embedId);
        }

        // Update modal title
        const modalTitle = document.querySelector('.modal-content h2');
        if (modalTitle) {
            modalTitle.textContent = 'Edit Embed';
        }

    } catch (error) {
        console.error('Error loading embed for edit:', error);
        showNotification('❌ Failed to load embed for editing', 'error');
    }
}

// Update embed
async function updateEmbed(embedId) {
    // Similar to createEmbed but with PUT method
    const embedData = {
        title: document.getElementById('embed-title').value.trim(),
        description: document.getElementById('embed-description').value.trim(),
        color: parseInt(document.getElementById('embed-color').value.replace('#', ''), 16),
        type: document.getElementById('embed-type').value,
        author: {
            name: document.getElementById('embed-author-name').value.trim(),
            icon_url: document.getElementById('embed-author-icon').value.trim()
        },
        thumbnail: {
            url: document.getElementById('embed-thumbnail').value.trim()
        },
        image: {
            url: document.getElementById('embed-image').value.trim()
        },
        footer: {
            text: document.getElementById('embed-footer-text').value.trim(),
            icon_url: document.getElementById('embed-footer-icon').value.trim()
        },
        fields: []
    };

    // Collect fields
    const fieldItems = document.getElementById('embed-fields-container').querySelectorAll('.embed-field-item');
    fieldItems.forEach(item => {
        const inputs = item.querySelectorAll('input, textarea');
        const name = inputs[0].value.trim();
        const value = inputs[1].value.trim();
        const inline = inputs[2].checked;

        if (name && value) {
            embedData.fields.push({
                name: name,
                value: value,
                inline: inline
            });
        }
    });

    // Clean up empty objects
    Object.keys(embedData).forEach(key => {
        if (typeof embedData[key] === 'object' && embedData[key] !== null) {
            const obj = embedData[key];
            if (Object.values(obj).every(val => !val || val === '')) {
                delete embedData[key];
            }
        }
    });

    try {
        const response = await fetch(`/api/${currentServerId}/embeds/${embedId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(embedData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to update embed');
        }

        closeModal();
        showNotification('✅ Embed updated successfully!', 'success');
        await loadEmbeds();

    } catch (error) {
        console.error('Error updating embed:', error);
        showNotification(`❌ Failed to update embed: ${error.message}`, 'error');
    }
}

// Duplicate embed
async function duplicateEmbed(embedId) {
    try {
        const response = await fetch(`/api/${currentServerId}/embeds/${embedId}`);
        const embed = await response.json();

        // Create a copy with new ID
        const newEmbedId = `${embedId}_copy`;
        const embedData = { ...embed, id: newEmbedId };

        const createResponse = await fetch(`/api/${currentServerId}/embeds`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(embedData)
        });

        if (!createResponse.ok) {
            const error = await createResponse.json();
            throw new Error(error.error || 'Failed to duplicate embed');
        }

        showNotification('✅ Embed duplicated successfully!', 'success');
        await loadEmbeds();

    } catch (error) {
        console.error('Error duplicating embed:', error);
        showNotification(`❌ Failed to duplicate embed: ${error.message}`, 'error');
    }
}

// Delete embed
async function deleteEmbed(embedId) {
    if (!confirm(`Are you sure you want to delete the embed "${embedId}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/${currentServerId}/embeds/${embedId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to delete embed');
        }

        showNotification('✅ Embed deleted successfully!', 'success');
        await loadEmbeds();

    } catch (error) {
        console.error('Error deleting embed:', error);
        showNotification(`❌ Failed to delete embed: ${error.message}`, 'error');
    }
}

// Refresh embeds
async function refreshEmbeds() {
    await loadEmbeds();
}

// === SERVER CONFIGURATION FUNCTIONS ===

// Load server settings
async function loadServerSettings() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        showNotification('Loading server configuration...', 'info');

        const response = await fetch(`/api/${currentServerId}/config`);
        const config = await response.json();

        const configContent = document.getElementById('config-content');
        if (!configContent) return;

        // Build the configuration form
        let html = `
            <div class="config-sections">
                <div class="config-section">
                    <h3>🤖 Bot Configuration</h3>
                    <div class="config-grid">
                        <div class="config-item">
                            <label for="prefix">Command Prefix</label>
                            <input type="text" id="prefix" value="${config.prefix || '!'}" maxlength="5" placeholder="!">
                            <small>The prefix for bot commands (e.g., !balance)</small>
                        </div>

                        <div class="config-item">
                            <label for="currency_name">Currency Name</label>
                            <input type="text" id="currency_name" value="${config.currency_name || 'Coins'}" maxlength="50" placeholder="Coins">
                            <small>The name of the currency (e.g., Coins, Points)</small>
                        </div>

                        <div class="config-item">
                            <label for="currency_symbol">Currency Symbol</label>
                            <input type="text" id="currency_symbol" value="${config.currency_symbol || '💰'}" maxlength="10" placeholder="💰">
                            <small>The symbol for the currency (e.g., 💰, $)</small>
                        </div>
                    </div>
                </div>

                <div class="config-section">
                    <h3>👥 Role Permissions</h3>
                    <div class="config-grid">
                        <div class="config-item">
                            <label for="admin_roles">Admin Roles</label>
                            <textarea id="admin_roles" rows="3" placeholder="Admin Role Name&#10;Moderator Role Name">${(config.admin_roles || []).join('\n')}</textarea>
                            <small>Role names that have admin permissions (one per line)</small>
                        </div>

                        <div class="config-item">
                            <label for="moderator_roles">Moderator Roles</label>
                            <textarea id="moderator_roles" rows="3" placeholder="Moderator Role Name&#10;Helper Role Name">${(config.moderator_roles || []).join('\n')}</textarea>
                            <small>Role names that have moderator permissions (one per line)</small>
                        </div>
                    </div>
                </div>

                <div class="config-section">
                    <h3>📢 Channel Configuration</h3>
                    <div class="config-grid">
                        <div class="config-item">
                            <label for="log_channel">Log Channel ID</label>
                            <input type="text" id="log_channel" value="${config.log_channel || ''}" placeholder="123456789012345678">
                            <small>Discord channel ID for logging bot actions</small>
                        </div>

                        <div class="config-item">
                            <label for="welcome_channel">Welcome Channel ID</label>
                            <input type="text" id="welcome_channel" value="${config.welcome_channel || ''}" placeholder="123456789012345678">
                            <small>Discord channel ID for welcome messages</small>
                        </div>

                        <div class="config-item">
                            <label for="task_channel_id">Task Channel ID</label>
                            <input type="text" id="task_channel_id" value="${config.task_channel_id || ''}" placeholder="123456789012345678">
                            <small>Discord channel ID for task announcements</small>
                        </div>

                        <div class="config-item">
                            <label for="shop_channel_id">Shop Channel ID</label>
                            <input type="text" id="shop_channel_id" value="${config.shop_channel_id || ''}" placeholder="123456789012345678">
                            <small>Discord channel ID for shop interactions</small>
                        </div>
                    </div>
                </div>

                <div class="config-section">
                    <h3>⚙️ Feature Settings</h3>
                    <div class="config-grid">
                        <div class="config-item checkbox-item">
                            <label>
                                <input type="checkbox" id="global_shop" ${config.global_shop ? 'checked' : ''}>
                                Global Shop
                            </label>
                            <small>Allow shop items to be used in all channels</small>
                        </div>

                        <div class="config-item checkbox-item">
                            <label>
                                <input type="checkbox" id="global_tasks" ${config.global_tasks ? 'checked' : ''}>
                                Global Tasks
                            </label>
                            <small>Allow task commands to be used in all channels</small>
                        </div>

                        <div class="config-item checkbox-item">
                            <label>
                                <input type="checkbox" id="daily_rewards_enabled" ${config.daily_rewards_enabled !== false ? 'checked' : ''}>
                                Daily Rewards
                            </label>
                            <small>Enable daily reward system</small>
                        </div>

                        <div class="config-item checkbox-item">
                            <label>
                                <input type="checkbox" id="shop_enabled" ${config.shop_enabled !== false ? 'checked' : ''}>
                                Shop System
                            </label>
                            <small>Enable shop functionality</small>
                        </div>
                    </div>
                </div>
            </div>
        `;

        configContent.innerHTML = html;

        // Show bot status section
        const botStatusSection = document.getElementById('bot-status-section');
        if (botStatusSection) {
            botStatusSection.style.display = 'block';
            updateBotStatusDisplay();
        }

        showNotification('✅ Server configuration loaded!', 'success');

    } catch (error) {
        console.error('Error loading server settings:', error);
        const configContent = document.getElementById('config-content');
        if (configContent) {
            configContent.innerHTML = '<div class="error-state">Error loading server configuration</div>';
        }
        showNotification('❌ Failed to load server configuration', 'error');
    }
}

// Save server settings
async function saveServerSettings() {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        showNotification('Saving server configuration...', 'info');

        // Collect form data
        const configData = {
            prefix: document.getElementById('prefix').value.trim(),
            currency_name: document.getElementById('currency_name').value.trim(),
            currency_symbol: document.getElementById('currency_symbol').value.trim(),
            admin_roles: document.getElementById('admin_roles').value.split('\n').map(r => r.trim()).filter(r => r),
            moderator_roles: document.getElementById('moderator_roles').value.split('\n').map(r => r.trim()).filter(r => r),
            log_channel: document.getElementById('log_channel').value.trim(),
            welcome_channel: document.getElementById('welcome_channel').value.trim(),
            task_channel_id: document.getElementById('task_channel_id').value.trim(),
            shop_channel_id: document.getElementById('shop_channel_id').value.trim(),
            global_shop: document.getElementById('global_shop').checked,
            global_tasks: document.getElementById('global_tasks').checked,
            daily_rewards_enabled: document.getElementById('daily_rewards_enabled').checked,
            shop_enabled: document.getElementById('shop_enabled').checked
        };

        // Validation
        if (!configData.currency_name) {
            showNotification('Currency name is required', 'error');
            return;
        }

        if (!configData.currency_symbol) {
            showNotification('Currency symbol is required', 'error');
            return;
        }

        const response = await fetch(`/api/${currentServerId}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save configuration');
        }

        const result = await response.json();

        showNotification('✅ Server configuration saved successfully!', 'success');

        // Reload settings to confirm changes
        await loadServerSettings();

    } catch (error) {
        console.error('Error saving server settings:', error);
        showNotification(`❌ Failed to save configuration: ${error.message}`, 'error');
    }
}

// Set bot status
async function setBotStatus(status) {
    if (!currentServerId) {
        showNotification('Please select a server first', 'error');
        return;
    }

    try {
        showNotification(`Setting bot status to ${status}...`, 'info');

        const response = await fetch(`/api/${currentServerId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: status })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to update bot status');
        }

        const result = await response.json();

        showNotification(`✅ Bot status set to ${status}!`, 'success');

        // Update the status display
        updateBotStatusDisplay();

    } catch (error) {
        console.error('Error setting bot status:', error);
        showNotification(`❌ Failed to set bot status: ${error.message}`, 'error');
    }
}

// Update bot status display
async function updateBotStatusDisplay() {
    try {
        const response = await fetch(apiUrl('/api/status'));
        const data = await response.json();

        const statusElement = document.getElementById('current-bot-status');
        if (statusElement) {
            const status = data.bot_status || 'unknown';
            statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            statusElement.className = `status-value status-${status}`;
        }

        // Update status buttons
        const statusButtons = document.querySelectorAll('.status-actions button');
        statusButtons.forEach(button => {
            const buttonStatus = button.onclick.toString().match(/'(\w+)'/)[1];
            button.classList.toggle('btn-success', buttonStatus === data.bot_status);
            button.classList.toggle('btn-secondary', buttonStatus !== data.bot_status);
        });

    } catch (error) {
        console.error('Error updating bot status display:', error);
        const statusElement = document.getElementById('current-bot-status');
        if (statusElement) {
            statusElement.textContent = 'Unknown';
            statusElement.className = 'status-value status-unknown';
        }
    }
}

async function createAnnouncement(event) {
    event.preventDefault(); // CRITICAL

    const form = event.target;
    const formData = new FormData(form);

    // Get selected roles for mentions
    const selectedRoles = Array.from(document.querySelectorAll('input[name="mention_roles"]:checked'))
        .map(checkbox => checkbox.value);

    const announcementData = {
        title: formData.get('title'),
        content: formData.get('content'),
        channel_id: formData.get('channel_id'),
        color: formData.get('color') || '#3498db',
        image_url: formData.get('image_url') || null,
        thumbnail_url: formData.get('thumbnail_url') || null,
        footer: formData.get('footer') || null,
        mention_roles: selectedRoles,
        pin: formData.get('pin') === 'on'
    };

    // Validate
    if (!announcementData.title || !announcementData.content) {
        showNotification('Title and content are required', 'error');
        return;
    }

    if (!announcementData.channel_id) {
        showNotification('Please select a channel', 'error');
        return;
    }

    // Validate URLs if provided
    if (announcementData.image_url && !isValidUrl(announcementData.image_url)) {
        showNotification('Invalid image URL', 'error');
        return;
    }

    try {
        const response = await authenticatedFetch(`/api/${currentServer}/announcements`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(announcementData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create announcement');
        }

        const result = await response.json();

        showNotification('Announcement posted successfully!', 'success');
        closeModal();
        loadAnnouncements(); // Reload announcements list

    } catch (error) {
        console.error('Error creating announcement:', error);
        showNotification(error.message || 'Failed to create announcement', 'error');
    }
}

function isValidUrl(string) {
    try {
        new URL(string);
        return true;
    } catch (_) {
        return false;
    }
}

// Initialize announcements tab
function initAnnouncementsTab() {
    const createForm = document.getElementById('announcement-create-form');
    if (createForm) {
        createForm.addEventListener('submit', createAnnouncement);
    }

    loadAnnouncements();
}

// Add config to tab loading
function loadTabData(tabName) {
    switch(tabName) {
        case 'dashboard':
            loadOverviewData();
            break;
        case 'users':
            loadUsers();
            break;
        case 'shop':
            loadShop();
            break;
        case 'tasks':
            loadTasks();
            break;
        case 'announcements':
            loadAnnouncementsTab();
            break;
        case 'embeds':
            loadEmbeds();
            break;
        case 'transactions':
            loadTransactions();
            break;
        case 'config':
            loadServerSettings();
            break;
        case 'settings':
            loadSettings();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}
