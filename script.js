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
let currentServerId = null;
let userData = null;

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

    // Update selector
    const selector = document.getElementById('server-select');
    if (selector) {
        selector.value = serverId;
    }

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
        case 'embeds':
            loadEmbeds();
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
            html += '<th>User</th><th>Balance</th><th>Total Earned</th><th>Total Spent</th><th>Last Daily</th><th>Actions</th>';
            html += '</tr></thead><tbody>';

            data.users.forEach(user => {
                const lastDaily = user.last_daily ? new Date(user.last_daily).toLocaleDateString() : 'Never';
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
                    <td>$${(user.total_earned || 0).toLocaleString()}</td>
                    <td>$${(user.total_spent || 0).toLocaleString()}</td>
                    <td>${lastDaily}</td>
                    <td>
                        <button class="btn-small btn-primary" onclick="editUserBalance('${user.user_id}', ${user.balance})">Edit Balance</button>
                    </td>
                </tr>`;
            });

            html += '</tbody></table></div>';

            // Add pagination info
            if (data.pages > 1) {
                html += `<div class="pagination-info">Page ${data.page} of ${data.pages} (${data.total} total users)</div>`;
            }

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

    try {
        shopList.innerHTML = '<div class="loading">Loading shop items...</div>';
        const data = await apiCall(`/api/${currentServerId}/shop`);

        if (data && data.items && data.items.length > 0) {
            let html = '<div class="table-container"><table><thead><tr>';
            html += '<th>Item</th><th>Price</th><th>Category</th><th>Stock</th><th>Status</th><th>Actions</th>';
            html += '</tr></thead><tbody>';

            data.items.forEach(item => {
                const stockDisplay = item.stock === -1 ? '∞ Unlimited' : item.stock;
                const statusBadge = item.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-secondary">Inactive</span>';

                html += `<tr>
                    <td>
                        <div>${item.emoji || '📦'} ${item.name}</div>
                        <div class="item-description">${item.description || ''}</div>
                    </td>
                    <td class="balance-amount">$${item.price.toLocaleString()}</td>
                    <td>${item.category}</td>
                    <td>${stockDisplay}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <button class="btn-small btn-primary" onclick="editShopItem('${item.item_id}')">Edit</button>
                        <button class="btn-small btn-danger" onclick="deleteShopItem('${item.item_id}')">Delete</button>
                    </td>
                </tr>`;
            });

            html += '</tbody></table></div>';
            shopList.innerHTML = html;
        } else {
            shopList.innerHTML = '<div class="empty-state">No shop items found. Click "Add Item" to create one.</div>';
        }
    } catch (error) {
        console.error('Failed to load shop:', error);
        shopList.innerHTML = '<div class="error-state">Failed to load shop items</div>';
    }
}

async function loadTasks() {
    const tasksList = document.getElementById('tasks-list');
    if (!tasksList) return;

    try {
        tasksList.innerHTML = '<div class="loading">Loading tasks...</div>';
        const data = await apiCall(`/api/${currentServerId}/tasks`);

        if (data && data.tasks && data.tasks.length > 0) {
            let html = '<div class="table-container"><table><thead><tr>';
            html += '<th>Task</th><th>Reward</th><th>Duration</th><th>Claims</th><th>Status</th><th>Expires</th><th>Actions</th>';
            html += '</tr></thead><tbody>';

            data.tasks.forEach(task => {
                const expiresAt = task.expires_at ? new Date(task.expires_at).toLocaleString() : 'No expiration';
                const claimsDisplay = task.max_claims === -1 ? `${task.current_claims} / ∞` : `${task.current_claims} / ${task.max_claims}`;
                const statusBadge = task.status === 'active' ? '<span class="badge badge-success">Active</span>' :
                    task.status === 'completed' ? '<span class="badge badge-primary">Completed</span>' :
                        task.status === 'expired' ? '<span class="badge badge-warning">Expired</span>' :
                            '<span class="badge badge-secondary">Cancelled</span>';

                html += `<tr>
                    <td>
                        <div><strong>${task.name}</strong></div>
                        <div class="task-description">${task.description || ''}</div>
                    </td>
                    <td class="balance-amount">$${task.reward.toLocaleString()}</td>
                    <td>${task.duration_hours}h</td>
                    <td>${claimsDisplay}</td>
                    <td>${statusBadge}</td>
                    <td>${expiresAt}</td>
                    <td>
                        <button class="btn-small btn-primary" onclick="editTask(${task.task_id})">Edit</button>
                        <button class="btn-small btn-danger" onclick="deleteTask(${task.task_id})">Delete</button>
                    </td>
                </tr>`;
            });

            html += '</tbody></table></div>';
            tasksList.innerHTML = html;
        } else {
            tasksList.innerHTML = '<div class="empty-state">No tasks found. Click "Add Task" to create one.</div>';
        }
    } catch (error) {
        console.error('Failed to load tasks:', error);
        tasksList.innerHTML = '<div class="error-state">Failed to load tasks</div>';
    }
}

async function loadAnnouncements() {
    const announcementsContent = document.getElementById('tab-content');
    if (!announcementsContent) return;

    try {
        announcementsContent.innerHTML = '<div class="loading">Loading announcements...</div>';
        const data = await apiCall(`/api/${currentServerId}/announcements`);

        if (data && data.announcements && data.announcements.length > 0) {
            let html = '<div class="announcements-list">';

            data.announcements.forEach(announcement => {
                const createdAt = new Date(announcement.created_at).toLocaleString();
                const pinnedBadge = announcement.is_pinned ? '<span class="pinned-badge">📌 Pinned</span>' : '';

                html += `<div class="announcement-card">
                    <div class="announcement-header">
                        <div class="announcement-title">
                            <h3>${announcement.title || 'Announcement'}</h3>
                            ${pinnedBadge}
                        </div>
                        <div class="announcement-actions">
                            <button class="btn-small" onclick="editAnnouncement('${announcement.announcement_id}')">Edit</button>
                            <button class="btn-small btn-danger" onclick="deleteAnnouncement('${announcement.announcement_id}')">Delete</button>
                        </div>
                    </div>
                    <div class="announcement-content">
                        <p>${announcement.content}</p>
                    </div>
                    <div class="announcement-meta">
                        <span>Created: ${createdAt}</span>
                        <span>By: ${announcement.created_by || 'Unknown'}</span>
                    </div>
                </div>`;
            });

            html += '</div>';
            announcementsContent.innerHTML = html;
        } else {
            announcementsContent.innerHTML = '<div class="empty-state">No announcements found.</div>';
        }
    } catch (error) {
        console.error('Failed to load announcements:', error);
        announcementsContent.innerHTML = '<div class="error-state">Failed to load announcements</div>';
    }
}

async function loadTransactions() {
    const transactionsList = document.getElementById('transactions-list');
    if (!transactionsList) return;

    try {
        transactionsList.innerHTML = '<div class="loading">Loading transactions...</div>';
        const data = await apiCall(`/api/${currentServerId}/transactions`);

        if (data && data.transactions && data.transactions.length > 0) {
            let html = '<div class="table-container"><table><thead><tr>';
            html += '<th>Date</th><th>User</th><th>Type</th><th>Amount</th><th>Balance After</th><th>Description</th>';
            html += '</tr></thead><tbody>';

            data.transactions.forEach(txn => {
                const timestamp = new Date(txn.timestamp).toLocaleString();
                const amountClass = txn.amount >= 0 ? 'positive' : 'negative';
                const amountSign = txn.amount >= 0 ? '+' : '';

                html += `<tr>
                    <td>${timestamp}</td>
                    <td>${txn.user_id}</td>
                    <td>${txn.transaction_type}</td>
                    <td class="${amountClass}">${amountSign}$${Math.abs(txn.amount).toLocaleString()}</td>
                    <td>$${txn.balance_after.toLocaleString()}</td>
                    <td>${txn.description || ''}</td>
                </tr>`;
            });

            html += '</tbody></table></div>';
            transactionsList.innerHTML = html;
        } else {
            transactionsList.innerHTML = '<div class="empty-state">No transactions found</div>';
        }
    } catch (error) {
        console.error('Failed to load transactions:', error);
        transactionsList.innerHTML = '<div class="error-state">Failed to load transactions</div>';
    }
}

async function loadEmbeds() {
    const embedsList = document.getElementById('embeds-list');
    if (!embedsList) return;

    try {
        embedsList.innerHTML = '<div class="loading">Loading embeds...</div>';
        const data = await apiCall(`/api/${currentServerId}/embeds`);

        if (data && data.embeds && data.embeds.length > 0) {
            let html = '<div class="embeds-grid">';

            data.embeds.forEach(embed => {
                html += `<div class="embed-card">
                    <div class="embed-preview" style="border-left: 4px solid ${embed.color || '#5865F2'}">
                        <h4>${embed.title || 'Untitled Embed'}</h4>
                        <p>${embed.description || ''}</p>
                    </div>
                    <div class="embed-actions">
                        <button class="btn-small btn-primary" onclick="editEmbed('${embed.embed_id}')">Edit</button>
                        <button class="btn-small btn-danger" onclick="deleteEmbed('${embed.embed_id}')">Delete</button>
                    </div>
                </div>`;
            });

            html += '</div>';
            embedsList.innerHTML = html;
        } else {
            embedsList.innerHTML = '<div class="empty-state">No embeds found. Click "Create Embed" to make one.</div>';
        }
    } catch (error) {
        console.error('Failed to load embeds:', error);
        embedsList.innerHTML = '<div class="error-state">Failed to load embeds</div>';
    }
}

async function loadServerSettingsTab() {
    const settingsContent = document.getElementById('server-settings-content');
    if (!settingsContent) return;

    try {
        const config = await apiCall(`/api/${currentServerId}/config`);
        console.log('Server config loaded:', config);

        // Settings are already in HTML, just populate the values
        document.getElementById('currency-name').value = config.currency_name || 'coins';
        document.getElementById('currency-symbol').value = config.currency_symbol || '$';
        document.getElementById('starting-balance').value = config.starting_balance || 0;

        // Feature toggles
        document.getElementById('feature-currency').checked = config.feature_currency !== false;
        document.getElementById('feature-tasks').checked = config.feature_tasks !== false;
        document.getElementById('feature-shop').checked = config.feature_shop !== false;
        document.getElementById('feature-announcements').checked = config.feature_announcements !== false;
        document.getElementById('feature-moderation').checked = config.feature_moderation !== false;

        showNotification('Server settings loaded', 'success');
    } catch (error) {
        console.error('Failed to load server settings:', error);
        showNotification('Failed to load server settings', 'error');
    }
}

async function loadPermissionsTab() {
    const permissionsContent = document.getElementById('permissions-content');
    if (!permissionsContent) return;

    try {
        const roles = await apiCall(`/api/${currentServerId}/roles`);
        console.log('Roles loaded:', roles);

        showNotification('Permissions loaded', 'success');
    } catch (error) {
        console.error('Failed to load permissions:', error);
        showNotification('Failed to load permissions', 'error');
    }
}

async function loadLogs() {
    const logsContent = document.getElementById('logs-content');
    if (!logsContent) return;

    logsContent.innerHTML = '<div class="loading">Logs feature coming soon...</div>';
}

// ========== USER MANAGEMENT ==========
function editUserBalance(userId, currentBalance) {
    const amount = prompt(`Edit balance for user ${userId}\nCurrent balance: $${currentBalance}\n\nEnter amount to ADD (use negative to subtract):`);

    if (amount === null) return;

    const parsedAmount = parseInt(amount);
    if (isNaN(parsedAmount)) {
        showNotification('Invalid amount', 'error');
        return;
    }

    updateUserBalance(userId, parsedAmount);
}

async function updateUserBalance(userId, amount) {
    try {
        await apiCall(`/api/${currentServerId}/users/${userId}/balance`, {
            method: 'PUT',
            body: JSON.stringify({ amount })
        });

        showNotification(`Balance updated for user ${userId}`, 'success');
        loadUsersTab(); // Reload users
    } catch (error) {
        console.error('Failed to update balance:', error);
        showNotification('Failed to update balance', 'error');
    }
}

// ========== SHOP MANAGEMENT ==========
function editShopItem(itemId) {
    showNotification(`Edit shop item ${itemId} - Feature coming soon`, 'info');
}

async function deleteShopItem(itemId) {
    if (!confirm(`Are you sure you want to delete this shop item?`)) return;

    try {
        await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
            method: 'DELETE'
        });

        showNotification('Shop item deleted', 'success');
        loadShop(); // Reload shop
    } catch (error) {
        console.error('Failed to delete shop item:', error);
        showNotification('Failed to delete shop item', 'error');
    }
}

// ========== TASK MANAGEMENT ==========
function editTask(taskId) {
    showNotification(`Edit task ${taskId} - Feature coming soon`, 'info');
}

async function deleteTask(taskId) {
    if (!confirm(`Are you sure you want to delete this task?`)) return;

    try {
        await apiCall(`/api/${currentServerId}/tasks/${taskId}`, {
            method: 'DELETE'
        });

        showNotification('Task deleted', 'success');
        loadTasks(); // Reload tasks
    } catch (error) {
        console.error('Failed to delete task:', error);
        showNotification('Failed to delete task', 'error');
    }
}

// ========== ANNOUNCEMENT MANAGEMENT ==========
function editAnnouncement(announcementId) {
    showNotification(`Edit announcement ${announcementId} - Feature coming soon`, 'info');
}

async function deleteAnnouncement(announcementId) {
    if (!confirm(`Are you sure you want to delete this announcement?`)) return;

    showNotification('Delete announcement - Feature coming soon', 'info');
}

// ========== EMBED MANAGEMENT ==========
function editEmbed(embedId) {
    showNotification(`Edit embed ${embedId} - Feature coming soon`, 'info');
}

async function deleteEmbed(embedId) {
    if (!confirm(`Are you sure you want to delete this embed?`)) return;

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}`, {
            method: 'DELETE'
        });

        showNotification('Embed deleted', 'success');
        loadEmbeds(); // Reload embeds
    } catch (error) {
        console.error('Failed to delete embed:', error);
        showNotification('Failed to delete embed', 'error');
    }
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
    loadEmbeds();
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
