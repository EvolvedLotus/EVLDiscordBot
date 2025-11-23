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
        if (endpoint.includes('/undefined/')) {
            console.error('Prevented API call with undefined parameter:', endpoint);
            throw new Error('Invalid API call parameters');
        }

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

// ========== TAB NAVIGATION ==========

function showTab(tabName) {
    // Hide all tab contents
    const allTabs = document.querySelectorAll('.tab-content');
    allTabs.forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });

    // Remove active class from all tab buttons
    const allButtons = document.querySelectorAll('.tab-button');
    allButtons.forEach(btn => btn.classList.remove('active'));

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

    // Load tab data if server is selected
    if (currentServerId) {
        switch (tabName) {
            case 'dashboard':
                loadDashboard();
                break;
            case 'users':
                loadUsersTab();
                break;
            case 'shop':
                loadShopTab();
                break;
            case 'tasks':
                loadTasksTab();
                break;
            case 'announcements':
                loadAnnouncementsTab();
                break;
            case 'embeds':
                loadEmbedsTab();
                break;
            case 'transactions':
                loadTransactionsTab();
                break;
            case 'server-settings':
                loadServerSettingsTab();
                break;
            case 'permissions':
                loadPermissionsTab();
                break;
            case 'roles':
                loadRolesTab();
                break;
            case 'moderation':
                loadModerationTab();
                break;
            case 'config':
                loadConfigTab();
                break;
            case 'settings':
                loadSettingsTab();
                break;
            case 'logs':
                loadLogsTab();
                break;
        }
    }
}

// Tab loader functions (some may already exist, these are fallbacks)
function loadUsersTab() { loadUsers(); }
function loadShopTab() { loadShop(); }
function loadTasksTab() { loadTasks(); }
function loadAnnouncementsTab() { loadAnnouncements(); }
function loadEmbedsTab() { loadEmbeds(); }
function loadTransactionsTab() { loadTransactions(); }
function loadPermissionsTab() { console.log('Permissions tab - coming soon'); }
function loadRolesTab() { console.log('Roles tab - coming soon'); }
function loadModerationTab() { console.log('Moderation tab - coming soon'); }
function loadConfigTab() { loadServerSettings(); }
function loadSettingsTab() { console.log('Settings tab - coming soon'); }
function loadLogsTab() { console.log('Logs tab - coming soon'); }

// ========== USER MANAGEMENT ==========

let currentManagingUserId = null;

async function manageUser(userId) {
    currentManagingUserId = userId;
    const modal = document.getElementById('user-management-modal');
    const userNameSpan = document.getElementById('manage-user-name');
    const rolesContainer = document.getElementById('user-roles-container');

    if (!modal) return;

    // Set user name
    const user = discordDataCache.users[userId];
    userNameSpan.textContent = user ? (user.username || user.display_name) : userId;

    // Load roles
    rolesContainer.innerHTML = '<div class="loading">Loading roles...</div>';
    modal.style.display = 'block';

    try {
        const [userRoles, allRoles] = await Promise.all([
            apiCall(`/api/${currentServerId}/users/${userId}/roles`),
            apiCall(`/api/${currentServerId}/roles`)
        ]);

        if (allRoles && allRoles.roles) {
            let html = '<div class="roles-list-check">';
            allRoles.roles.forEach(role => {
                const hasRole = userRoles.roles.includes(role.id);
                html += `
                    <label class="role-item">
                        <input type="checkbox" value="${role.id}" ${hasRole ? 'checked' : ''}>
                        <span style="color: #${role.color.toString(16).padStart(6, '0')}">${role.name}</span>
                    </label>
                `;
            });
            html += '</div>';
            rolesContainer.innerHTML = html;
        }
    } catch (error) {
        rolesContainer.innerHTML = `<div class="error">Failed to load roles: ${error.message}</div>`;
    }
}

function closeUserManagementModal() {
    document.getElementById('user-management-modal').style.display = 'none';
    currentManagingUserId = null;
}

async function addBalance() {
    if (!currentManagingUserId) return;
    const amount = document.getElementById('balance-amount').value;
    const reason = document.getElementById('balance-reason').value;

    try {
        await apiCall(`/api/${currentServerId}/users/${currentManagingUserId}/balance/add`, {
            method: 'POST',
            body: JSON.stringify({ amount: parseInt(amount), reason })
        });
        showNotification('Balance added successfully', 'success');
        loadUsers();
    } catch (error) {
        showNotification('Failed to add balance: ' + error.message, 'error');
    }
}

async function removeBalance() {
    if (!currentManagingUserId) return;
    const amount = document.getElementById('balance-amount').value;
    const reason = document.getElementById('balance-reason').value;

    try {
        await apiCall(`/api/${currentServerId}/users/${currentManagingUserId}/balance/remove`, {
            method: 'POST',
            body: JSON.stringify({ amount: parseInt(amount), reason })
        });
        showNotification('Balance removed successfully', 'success');
        loadUsers();
    } catch (error) {
        showNotification('Failed to remove balance: ' + error.message, 'error');
    }
}

async function saveUserRoles() {
    if (!currentManagingUserId) return;
    const checkboxes = document.querySelectorAll('#user-roles-container input[type="checkbox"]');
    const roleIds = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);

    try {
        await apiCall(`/api/${currentServerId}/users/${currentManagingUserId}/roles`, {
            method: 'PUT',
            body: JSON.stringify({ roles: roleIds })
        });
        showNotification('Roles updated successfully', 'success');
    } catch (error) {
        showNotification('Failed to update roles: ' + error.message, 'error');
    }
}

async function kickUserFromModal() {
    if (!currentManagingUserId || !confirm('Kick this user?')) return;
    try {
        await apiCall(`/api/${currentServerId}/moderation/kick`, {
            method: 'POST',
            body: JSON.stringify({ user_id: currentManagingUserId })
        });
        showNotification('User kicked', 'success');
        closeUserManagementModal();
        loadUsers();
    } catch (error) {
        showNotification('Failed to kick user: ' + error.message, 'error');
    }
}

async function banUserFromModal() {
    if (!currentManagingUserId || !confirm('Ban this user?')) return;
    try {
        await apiCall(`/api/${currentServerId}/moderation/ban`, {
            method: 'POST',
            body: JSON.stringify({ user_id: currentManagingUserId })
        });
        showNotification('User banned', 'success');
        closeUserManagementModal();
        loadUsers();
    } catch (error) {
        showNotification('Failed to ban user: ' + error.message, 'error');
    }
}

async function timeoutUserFromModal() {
    if (!currentManagingUserId) return;
    const duration = prompt('Enter timeout duration in minutes:', '60');
    if (!duration) return;

    try {
        await apiCall(`/api/${currentServerId}/moderation/timeout`, {
            method: 'POST',
            body: JSON.stringify({ user_id: currentManagingUserId, duration: parseInt(duration) })
        });
        showNotification('User timed out', 'success');
    } catch (error) {
        showNotification('Failed to timeout user: ' + error.message, 'error');
    }
}

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

let currentUsersPage = 1;
const USERS_PER_PAGE = 50;

async function loadUsers(page = 1) {
    if (!currentServerId) return;
    currentUsersPage = parseInt(page);
    const list = document.getElementById('users-list');
    list.innerHTML = '<div class="loading">Loading users...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/users`);
        if (data.users && data.users.length > 0) {
            // Calculate pagination
            const totalUsers = data.users.length;
            const totalPages = Math.ceil(totalUsers / USERS_PER_PAGE);
            const startIndex = (page - 1) * USERS_PER_PAGE;
            const endIndex = Math.min(startIndex + USERS_PER_PAGE, totalUsers);
            const paginatedUsers = data.users.slice(startIndex, endIndex);

            let html = '<table class="data-table"><thead><tr><th>User</th><th>Balance</th><th>Level</th><th>XP</th><th>Actions</th></tr></thead><tbody>';
            paginatedUsers.forEach(user => {
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

            // Add pagination controls
            html += '<div class="pagination-controls">';
            html += `<button onclick="loadUsers(${page - 1})" ${page === 1 ? 'disabled' : ''} class="btn-small">Previous</button>`;
            html += `<span class="page-info">Page ${page} of ${totalPages} (${totalUsers} users)</span>`;
            html += `<button onclick="loadUsers(${page + 1})" ${page === totalPages ? 'disabled' : ''} class="btn-small">Next</button>`;
            html += '</div>';

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
                        <div class="card-actions">
                            <button onclick="editShopItem('${item.item_id}')" class="btn-small btn-primary">✏️ Edit</button>
                            <button onclick="deleteShopItem('${item.item_id}')" class="btn-small btn-danger">🗑️ Delete</button>
                        </div>
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

async function deleteShopItem(itemId) {
    if (!confirm('Are you sure you want to delete this item?')) return;

    try {
        await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
            method: 'DELETE'
        });
        showNotification('Item deleted successfully', 'success');
        loadShop();
    } catch (error) {
        showNotification(`Failed to delete item: ${error.message}`, 'error');
    }
}

async function editShopItem(itemId) {
    alert('Edit functionality coming soon!');
}

async function viewShopStatistics() {
    if (!currentServerId) return;
    try {
        const data = await apiCall(`/api/${currentServerId}/shop`);
        if (!data.items || data.items.length === 0) {
            showNotification('No shop items to analyze', 'info');
            return;
        }
        let totalItems = data.items.length;
        let activeItems = data.items.filter(item => item.is_active !== false).length;
        let totalValue = data.items.reduce((sum, item) => sum + (item.price || 0), 0);
        let outOfStock = data.items.filter(item => item.stock === 0).length;
        let unlimitedStock = data.items.filter(item => item.stock === -1).length;

        const statsHtml = `
            <div class="stats-grid">
                <div class="stat-card"><h3>Total Items</h3><p class="stat-value">${totalItems}</p></div>
                <div class="stat-card"><h3>Active Items</h3><p class="stat-value">${activeItems}</p></div>
                <div class="stat-card"><h3>Total Value</h3><p class="stat-value">$${totalValue.toLocaleString()}</p></div>
                <div class="stat-card"><h3>Out of Stock</h3><p class="stat-value">${outOfStock}</p></div>
                <div class="stat-card"><h3>Unlimited Stock</h3><p class="stat-value">${unlimitedStock}</p></div>
            </div>
        `;
        createModal('Shop Statistics', statsHtml);
    } catch (error) {
        showNotification(`Failed to load statistics: ${error.message}`, 'error');
    }
}

async function validateShopIntegrity() {
    if (!currentServerId) return;
    try {
        const data = await apiCall(`/api/${currentServerId}/shop`);
        if (!data.items || data.items.length === 0) {
            showNotification('No shop items to validate', 'info');
            return;
        }
        let issues = [];
        data.items.forEach((item, index) => {
            if (!item.item_id) issues.push(`Item #${index + 1}: Missing item_id`);
            if (!item.name || item.name.trim() === '') issues.push(`Item ${item.item_id || index + 1}: Missing name`);
            if (item.price === undefined || item.price === null) issues.push(`Item ${item.name || item.item_id}: Missing price`);
            if (item.price < 0) issues.push(`Item ${item.name || item.item_id}: Negative price`);
            if (item.stock !== undefined && item.stock < -1) issues.push(`Item ${item.name || item.item_id}: Invalid stock value`);
        });

        let reportHtml = '';
        if (issues.length === 0) {
            reportHtml = '<div class="success-message">✅ All shop items passed validation!</div>';
        } else {
            reportHtml = '<div class="error-message">Found issues:<ul>';
            issues.forEach(issue => reportHtml += `<li>${issue}</li>`);
            reportHtml += '</ul></div>';
        }
        createModal('Shop Integrity Check', reportHtml);
    } catch (error) {
        showNotification(`Failed to validate shop: ${error.message}`, 'error');
    }
}

async function loadTasks() {
    if (!currentServerId) return;
    const list = document.getElementById('tasks-list');
    if (!list) return;

    list.innerHTML = '<div class="loading">Loading tasks...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/tasks`);
        if (data.tasks && Object.keys(data.tasks).length > 0) {
            let html = '<div class="grid-container">';
            Object.values(data.tasks).forEach(task => {
                html += `
                    <div class="task-card">
                        <h4>${task.name}</h4>
                        <p>${task.description}</p>
                        <div class="reward">Reward: ${task.reward}</div>
                        <div class="card-actions">
                            <button onclick="editTask('${task.task_id}')" class="btn-small btn-primary">✏️ Edit</button>
                            <button onclick="deleteTask('${task.task_id}')" class="btn-small btn-danger">🗑️ Delete</button>
                        </div>
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

async function deleteTask(taskId) {
    if (!confirm('Are you sure you want to delete this task?')) return;

    try {
        await apiCall(`/api/${currentServerId}/tasks/${taskId}`, {
            method: 'DELETE'
        });
        showNotification('Task deleted successfully', 'success');
        loadTasks();
    } catch (error) {
        showNotification(`Failed to delete task: ${error.message}`, 'error');
    }
}

async function editTask(taskId) {
    // TODO: Implement edit modal population
    alert('Edit functionality coming soon!');
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

// Discord Data Cache for displaying names instead of IDs
let discordDataCache = {
    users: {},
    channels: {},
    roles: {}
};

// Fetch and cache Discord data
async function fetchDiscordData(serverId) {
    try {
        const [users, channels, roles] = await Promise.all([
            apiCall(`/api/${serverId}/users`),
            apiCall(`/api/${serverId}/channels`),
            apiCall(`/api/${serverId}/roles`)
        ]);

        if (users && users.users) {
            users.users.forEach(user => {
                discordDataCache.users[user.user_id] = user;
            });
        }

        if (channels && channels.channels) {
            channels.channels.forEach(channel => {
                discordDataCache.channels[channel.id] = channel;
            });
        }

        if (roles && roles.roles) {
            roles.roles.forEach(role => {
                discordDataCache.roles[role.id] = role;
            });
        }

        return { users, channels, roles };
    } catch (error) {
        console.error('Failed to fetch Discord data:', error);
        return { users: [], channels: [], roles: [] };
    }
}

function getUserDisplay(userId) {
    const user = discordDataCache.users[userId];
    if (user) {
        return user.username || user.display_name || `User ${userId}`;
    }
    return `User ${userId}`;
}

function getChannelDisplay(channelId) {
    const channel = discordDataCache.channels[channelId];
    if (channel) {
        return `#${channel.name}`;
    }
    return `Channel ${channelId}`;
}

function getRoleDisplay(roleId) {
    const role = discordDataCache.roles[roleId];
    if (role) {
        return role.name;
    }
    return `Role ${roleId}`;
}

// Full implementations for all tabs
async function loadAnnouncements() {
    if (!currentServerId) return;
    const content = document.getElementById('announcements-list');
    if (!content) return;

    content.innerHTML = '<div class="loading">Loading announcements...</div>';

    try {
        await fetchDiscordData(currentServerId);
        const data = await apiCall(`/api/${currentServerId}/announcements`);

        if (data && data.announcements && data.announcements.length > 0) {
            let html = '<div class="announcements-grid">';

            data.announcements.forEach(announcement => {
                const channelName = getChannelDisplay(announcement.channel_id);
                const createdBy = getUserDisplay(announcement.created_by);
                const createdDate = new Date(announcement.created_at).toLocaleString();

                html += `
                    <div class="announcement-card">
                        <div class="announcement-header">
                            <div class="announcement-title">
                                <span class="announcement-type">📢</span>
                                <h3>${announcement.title || 'Untitled'}</h3>
                                ${announcement.is_pinned ? '<span class="pinned-badge">📌 Pinned</span>' : ''}
                            </div>
                            <div class="announcement-actions">
                                <button onclick="editAnnouncement('${announcement.announcement_id}')" class="btn-small">✏️ Edit</button>
                                <button onclick="deleteAnnouncement('${announcement.announcement_id}')" class="btn-small btn-danger">🗑️ Delete</button>
                            </div>
                        </div>
                        <div class="announcement-content">
                            <p>${announcement.content}</p>
                        </div>
                        <div class="announcement-meta">
                            <span>📍 ${channelName}</span>
                            <span>👤 ${createdBy}</span>
                            <span>🕒 ${createdDate}</span>
                            ${announcement.message_id ? `<a href="https://discord.com/channels/${currentServerId}/${announcement.channel_id}/${announcement.message_id}" target="_blank">🔗 View</a>` : ''}
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            content.innerHTML = html;
        } else {
            content.innerHTML = `
                <div class="empty-state">
                    <h3>No announcements yet</h3>
                    <button onclick="showCreateAnnouncementModal()" class="btn-success">➕ Create First Announcement</button>
                </div>
            `;
        }
    } catch (error) {
        content.innerHTML = `<div class="error-state">Failed to load: ${error.message}</div>`;
    }
}

async function loadEmbeds() {
    if (!currentServerId) return;
    const list = document.getElementById('embeds-list');
    list.innerHTML = '<div class="loading">Loading embeds...</div>';

    try {
        await fetchDiscordData(currentServerId);
        const data = await apiCall(`/api/${currentServerId}/embeds`);

        if (data && data.embeds && data.embeds.length > 0) {
            let html = '<div class="embeds-grid">';

            data.embeds.forEach(embed => {
                const channelName = getChannelDisplay(embed.channel_id);
                const createdBy = getUserDisplay(embed.created_by);

                html += `
                    <div class="embed-card">
                        <div class="embed-preview" style="border-left: 4px solid ${embed.color || '#5865F2'}">
                            <h4>${embed.title || 'Untitled'}</h4>
                            <p>${embed.description || 'No description'}</p>
                        </div>
                        <div class="embed-meta">
                            <span>📍 ${channelName}</span>
                            <span>👤 ${createdBy}</span>
                        </div>
                        <div class="embed-actions">
                            <button onclick="editEmbed('${embed.embed_id}')" class="btn-small btn-primary">✏️ Edit</button>
                            <button onclick="sendEmbed('${embed.embed_id}')" class="btn-small btn-success">📤 Send</button>
                            <button onclick="deleteEmbed('${embed.embed_id}')" class="btn-small btn-danger">🗑️ Delete</button>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            list.innerHTML = html;
        } else {
            list.innerHTML = `<div class="empty-state"><h3>No embeds yet</h3></div>`;
        }
    } catch (error) {
        list.innerHTML = `<div class="error-state">Failed to load: ${error.message}</div>`;
    }
}

let currentTransactionsPage = 1;
const TRANSACTIONS_PER_PAGE = 50;

async function loadTransactions(page = 1) {
    if (!currentServerId) return;
    currentTransactionsPage = page;
    const list = document.getElementById('transactions-list');
    const statsSection = document.getElementById('transaction-stats');
    list.innerHTML = '<div class="loading">Loading transactions...</div>';

    try {
        await fetchDiscordData(currentServerId);
        const data = await apiCall(`/api/${currentServerId}/transactions`);

        if (data && data.transactions && data.transactions.length > 0) {
            // Calculate statistics
            let totalVolume = 0;
            let userActivity = {};

            data.transactions.forEach(txn => {
                totalVolume += Math.abs(txn.amount);
                userActivity[txn.user_id] = (userActivity[txn.user_id] || 0) + 1;
            });

            // Find most active user
            let mostActiveUserId = null;
            let maxActivity = 0;
            for (const [userId, count] of Object.entries(userActivity)) {
                if (count > maxActivity) {
                    maxActivity = count;
                    mostActiveUserId = userId;
                }
            }

            const avgTransaction = totalVolume / data.transactions.length;

            // Enhanced most active user display with Discord info
            let mostActiveUserDisplay = '-';
            if (mostActiveUserId) {
                const userInfo = discordDataCache.users[mostActiveUserId];
                if (userInfo) {
                    const avatarUrl = userInfo.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';
                    mostActiveUserDisplay = `<img src="${avatarUrl}" class="user-avatar-small" alt="avatar"> ${userInfo.username}`;
                } else {
                    mostActiveUserDisplay = getUserDisplay(mostActiveUserId);
                }
            }

            // Update statistics
            if (statsSection) {
                statsSection.style.display = 'grid';
                document.getElementById('total-transactions').textContent = data.transactions.length;
                document.getElementById('total-volume').textContent = `$${totalVolume.toLocaleString()}`;
                document.getElementById('most-active-user').innerHTML = mostActiveUserDisplay;
                document.getElementById('avg-transaction').textContent = `$${Math.round(avgTransaction).toLocaleString()}`;
            }

            // Calculate pagination
            const totalTransactions = data.transactions.length;
            const totalPages = Math.ceil(totalTransactions / TRANSACTIONS_PER_PAGE);
            const startIndex = (page - 1) * TRANSACTIONS_PER_PAGE;
            const endIndex = Math.min(startIndex + TRANSACTIONS_PER_PAGE, totalTransactions);
            const paginatedTransactions = data.transactions.slice(startIndex, endIndex);

            // Build transaction table
            let html = `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>User</th>
                            <th>Type</th>
                            <th>Amount</th>
                            <th>Balance Before</th>
                            <th>Balance After</th>
                            <th>Description</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            paginatedTransactions.forEach(txn => {
                const userName = getUserDisplay(txn.user_id);
                const date = new Date(txn.timestamp).toLocaleString();
                const amountClass = txn.amount >= 0 ? 'positive' : 'negative';
                const amountSign = txn.amount >= 0 ? '+' : '';

                html += `
                    <tr>
                        <td>${userName}</td>
                        <td><span class="transaction-type">${txn.transaction_type}</span></td>
                        <td class="${amountClass}">${amountSign}${txn.amount}</td>
                        <td>${txn.balance_before}</td>
                        <td>${txn.balance_after}</td>
                        <td>${txn.description || '-'}</td>
                        <td>${date}</td>
                    </tr>
                `;
            });

            html += '</tbody></table>';

            // Add pagination controls
            html += '<div class="pagination-controls">';
            html += `<button onclick="loadTransactions(${page - 1})" ${page === 1 ? 'disabled' : ''} class="btn-small">Previous</button>`;
            html += `<span class="page-info">Page ${page} of ${totalPages} (${totalTransactions} transactions)</span>`;
            html += `<button onclick="loadTransactions(${page + 1})" ${page === totalPages ? 'disabled' : ''} class="btn-small">Next</button>`;
            html += '</div>';

            list.innerHTML = html;
        } else {
            // No transactions
            if (statsSection) {
                statsSection.style.display = 'grid';
                document.getElementById('total-transactions').textContent = '0';
                document.getElementById('total-volume').textContent = '$0';
                document.getElementById('most-active-user').textContent = '-';
                document.getElementById('avg-transaction').textContent = '$0';
            }
            list.innerHTML = '<div class="empty-state">No transactions found</div>';
        }
    } catch (error) {
        console.error('Transaction loading error:', error);
        list.innerHTML = `<div class="error-state">Failed to load: ${error.message}</div>`;
    }
}

async function loadServerSettingsTab() {
    if (!currentServerId) return;
    const content = document.getElementById('server-settings-content');
    if (!content) return;

    try {
        await fetchDiscordData(currentServerId);

        // Populate channel dropdowns
        const channels = Object.values(discordDataCache.channels);
        const channelOptions = channels.map(ch =>
            `<option value="${ch.id}">${ch.name}</option>`
        ).join('');

        ['welcome-channel', 'log-channel', 'task-channel', 'shop-channel'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                select.innerHTML = '<option value="">None</option>' + channelOptions;
            }
        });

        // Load current settings
        const config = await apiCall(`/api/${currentServerId}/config`);

        if (config) {
            if (config.welcome_channel) document.getElementById('welcome-channel').value = config.welcome_channel;
            if (config.log_channel) document.getElementById('log-channel').value = config.log_channel;
            if (config.task_channel_id) document.getElementById('task-channel').value = config.task_channel_id;
            if (config.shop_channel_id) document.getElementById('shop-channel').value = config.shop_channel_id;

            if (config.currency_name) document.getElementById('currency-name').value = config.currency_name;
            if (config.currency_symbol) document.getElementById('currency-symbol').value = config.currency_symbol;

            document.getElementById('feature-currency').checked = config.feature_currency !== false;
            document.getElementById('feature-tasks').checked = config.feature_tasks !== false;
            document.getElementById('feature-shop').checked = config.feature_shop !== false;
            document.getElementById('feature-announcements').checked = config.feature_announcements !== false;
            document.getElementById('feature-moderation').checked = config.feature_moderation !== false;
        }

        showNotification('Settings loaded', 'success');
    } catch (error) {
        showNotification('Failed to load settings', 'error');
    }
}

async function loadLogs() {
    if (!currentServerId) return;
    const content = document.querySelector('#logs .content-area');
    if (!content) return;

    content.innerHTML = '<div class="loading">Loading logs...</div>';

    try {
        await fetchDiscordData(currentServerId);
        const data = await apiCall(`/api/${currentServerId}/logs`);

        if (data && data.logs && data.logs.length > 0) {
            let html = '<div class="logs-list">';

            data.logs.forEach(log => {
                const userName = getUserDisplay(log.user_id);
                const moderator = getUserDisplay(log.moderator_id);
                const date = new Date(log.created_at).toLocaleString();

                html += `
                    <div class="log-entry">
                        <div class="log-header">
                            <span class="log-action">${log.action}</span>
                            <span class="log-date">${date}</span>
                        </div>
                        <div class="log-details">
                            <span>👤 User: ${userName}</span>
                            <span>🛡️ By: ${moderator}</span>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            content.innerHTML = html;
        } else {
            content.innerHTML = '<div class="empty-state">No logs found</div>';
        }
    } catch (error) {
        content.innerHTML = `<div class="error-state">Failed to load: ${error.message}</div>`;
    }
}

// --- Restored Functions ---

async function loadRolesTab() {
    console.log('Loading roles...');
    try {
        const data = await apiCall(`/api/${currentServerId}/roles`);
        const rolesList = document.getElementById('server-roles-list');

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
    const permissionsContent = document.getElementById('permissions-dynamic-section');

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

// ========== MODAL SYSTEM ==========

function createModal(title, content) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'dynamic-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>${title}</h3>
                <button class="btn-close" onclick="closeModal()">×</button>
            </div>
            <div class="modal-body">
                ${content}
            </div>
        </div>
    `;

    // Close on background click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    return modal;
}

function closeModal() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        modal.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => modal.remove(), 300);
    });
}

function getChannelOptions() {
    const channels = Object.values(discordDataCache.channels);
    return channels.map(ch => `<option value="${ch.id}">${ch.name}</option>`).join('');
}

function getRoleOptions() {
    const roles = Object.values(discordDataCache.roles);
    return roles.map(role => `<option value="${role.id}">${role.name}</option>`).join('');
}

// ========== ANNOUNCEMENT ACTIONS ==========

function showCreateAnnouncementModal() {
    const modal = createModal('Create Announcement', `
        <form id="announcement-form" onsubmit="return false;">
            <div class="form-group">
                <label>Title</label>
                <input type="text" id="announcement-title" class="form-control" required>
            </div>
            <div class="form-group">
                <label>Content</label>
                <textarea id="announcement-content" class="form-control" rows="5" required></textarea>
            </div>
            <div class="form-group">
                <label>Channel</label>
                <select id="announcement-channel" class="form-control" required>
                    ${getChannelOptions()}
                </select>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="announcement-pin">
                    Pin this announcement
                </label>
            </div>
            <div class="button-group">
                <button type="button" onclick="createAnnouncement()" class="btn-success">Create</button>
                <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
            </div>
        </form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

async function createAnnouncement() {
    const title = document.getElementById('announcement-title').value;
    const content = document.getElementById('announcement-content').value;
    const channelId = document.getElementById('announcement-channel').value;
    const isPinned = document.getElementById('announcement-pin').checked;

    if (!title || !content || !channelId) {
        showNotification('Please fill all required fields', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/announcements`, {
            method: 'POST',
            body: JSON.stringify({
                title,
                content,
                channel_id: channelId,
                is_pinned: isPinned
            })
        });

        showNotification('Announcement created successfully!', 'success');
        closeModal();
        loadAnnouncements();
    } catch (error) {
        showNotification('Failed to create announcement: ' + error.message, 'error');
    }
}

async function editAnnouncement(announcementId) {
    // TODO: Implement edit functionality
    showNotification('Edit functionality coming soon', 'info');
}

async function deleteAnnouncement(announcementId) {
    if (!confirm('Are you sure you want to delete this announcement?')) return;

    try {
        await apiCall(`/api/${currentServerId}/announcements/${announcementId}`, {
            method: 'DELETE'
        });

        showNotification('Announcement deleted', 'success');
        loadAnnouncements();
    } catch (error) {
        showNotification('Failed to delete announcement: ' + error.message, 'error');
    }
}

// ========== EMBED ACTIONS ==========

function showCreateEmbedModal() {
    const modal = createModal('Create Embed', `
        <form id="embed-form" onsubmit="return false;">
            <div class="form-group">
                <label>Title</label>
                <input type="text" id="embed-title" class="form-control">
            </div>
            <div class="form-group">
                <label>Description</label>
                <textarea id="embed-description" class="form-control" rows="4"></textarea>
            </div>
            <div class="form-group">
                <label>Color (hex)</label>
                <input type="color" id="embed-color" class="form-control" value="#5865F2">
            </div>
            <div class="form-group">
                <label>Channel</label>
                <select id="embed-channel" class="form-control">
                    ${getChannelOptions()}
                </select>
            </div>
            <div class="button-group">
                <button type="button" onclick="createEmbed()" class="btn-success">Create</button>
                <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
            </div>
        </form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

async function createEmbed() {
    const title = document.getElementById('embed-title').value;
    const description = document.getElementById('embed-description').value;
    const color = document.getElementById('embed-color').value;
    const channelId = document.getElementById('embed-channel').value;

    try {
        await apiCall(`/api/${currentServerId}/embeds`, {
            method: 'POST',
            body: JSON.stringify({
                title,
                description,
                color,
                channel_id: channelId
            })
        });

        showNotification('Embed created successfully!', 'success');
        closeModal();
        loadEmbeds();
    } catch (error) {
        showNotification('Failed to create embed: ' + error.message, 'error');
    }
}

async function editEmbed(embedId) {
    showNotification('Edit functionality coming soon', 'info');
}

async function sendEmbed(embedId) {
    if (!confirm('Send this embed to Discord?')) return;

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}/send`, {
            method: 'POST'
        });

        showNotification('Embed sent!', 'success');
    } catch (error) {
        showNotification('Failed to send embed: ' + error.message, 'error');
    }
}

async function deleteEmbed(embedId) {
    if (!confirm('Are you sure you want to delete this embed?')) return;

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}`, {
            method: 'DELETE'
        });

        showNotification('Embed deleted', 'success');
        loadEmbeds();
    } catch (error) {
        showNotification('Failed to delete embed: ' + error.message, 'error');
    }
}

// ========== CHANNEL SETTINGS ACTIONS ==========

async function saveChannelSetting(type) {
    const channelMap = {
        'welcome': 'welcome-channel',
        'log': 'log-channel',
        'task': 'task-channel',
        'shop': 'shop-channel'
    };

    const selectId = channelMap[type];
    const channelId = document.getElementById(selectId).value;
    const statusId = `${selectId}-status`;

    try {
        const updateData = {};
        if (type === 'welcome') updateData.welcome_channel = channelId;
        if (type === 'log') updateData.log_channel = channelId;
        if (type === 'task') updateData.task_channel_id = channelId;
        if (type === 'shop') updateData.shop_channel_id = channelId;

        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify(updateData)
        });

        document.getElementById(statusId).textContent = '✓ Saved';
        document.getElementById(statusId).style.color = 'var(--success-color)';

        setTimeout(() => {
            document.getElementById(statusId).textContent = '';
        }, 2000);

        showNotification('Channel setting saved', 'success');
    } catch (error) {
        document.getElementById(statusId).textContent = '✗ Failed';
        document.getElementById(statusId).style.color = 'var(--danger-color)';
        showNotification('Failed to save: ' + error.message, 'error');
    }
}

async function saveCurrencySettings() {
    const currencyName = document.getElementById('currency-name').value;
    const currencySymbol = document.getElementById('currency-symbol').value;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                currency_name: currencyName,
                currency_symbol: currencySymbol
            })
        });

        document.getElementById('currency-settings-status').textContent = '✓ Saved';
        document.getElementById('currency-settings-status').style.color = 'var(--success-color)';

        setTimeout(() => {
            document.getElementById('currency-settings-status').textContent = '';
        }, 2000);

        showNotification('Currency settings saved', 'success');
    } catch (error) {
        showNotification('Failed to save: ' + error.message, 'error');
    }
}

async function saveFeatureToggle(feature) {
    const checkbox = document.getElementById(`feature-${feature}`);
    const statusId = `feature-${feature}-status`;

    try {
        const updateData = {};
        updateData[`feature_${feature}`] = checkbox.checked;

        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify(updateData)
        });

        document.getElementById(statusId).textContent = '✓ Saved';
        document.getElementById(statusId).style.color = 'var(--success-color)';

        setTimeout(() => {
            document.getElementById(statusId).textContent = '';
        }, 2000);

        showNotification(`${feature} feature ${checkbox.checked ? 'enabled' : 'disabled'}`, 'success');
    } catch (error) {
        showNotification('Failed to save: ' + error.message, 'error');
    }
}

async function saveBotBehavior() {
    const inactivityDays = document.getElementById('inactivity-days').value;
    const autoExpireTasks = document.getElementById('auto-expire-tasks').checked;
    const requireTaskProof = document.getElementById('require-task-proof').checked;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                inactivity_days: parseInt(inactivityDays),
                auto_expire_enabled: autoExpireTasks,
                require_proof: requireTaskProof
            })
        });

        document.getElementById('bot-behavior-status').textContent = '✓ Saved';
        document.getElementById('bot-behavior-status').style.color = 'var(--success-color)';

        setTimeout(() => {
            document.getElementById('bot-behavior-status').textContent = '';
        }, 2000);

        showNotification('Bot behavior settings saved', 'success');
    } catch (error) {
        showNotification('Failed to save: ' + error.message, 'error');
    }
}

// ========== TRANSACTION FILTERS ==========

function showTransactionFilters() {
    const filters = document.getElementById('transaction-filters');
    if (filters) {
        filters.style.display = filters.style.display === 'none' ? 'block' : 'none';
    }
}

function hideTransactionFilters() {
    const filters = document.getElementById('transaction-filters');
    if (filters) {
        filters.style.display = 'none';
    }
}

function applyFilters() {
    // TODO: Implement filter logic
    showNotification('Filters applied', 'info');
}

function clearFilters() {
    // TODO: Implement clear filters
    showNotification('Filters cleared', 'info');
}

async function exportTransactions() {
    showNotification('Export functionality coming soon', 'info');
}

async function archiveOldTransactions() {
    if (!confirm('Archive transactions older than 30 days?')) return;
    showNotification('Archive functionality coming soon', 'info');
}

// ========== SHOP ITEM MANAGEMENT ==========

function showCreateShopItemModal() {
    document.getElementById('shop-item-modal-title').textContent = 'Add Shop Item';
    document.getElementById('shop-item-form').reset();
    document.getElementById('shop-item-id').value = '';
    document.getElementById('shop-item-modal').style.display = 'block';
}

async function editShopItem(itemId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/shop`);
        const item = data.items.find(i => i.item_id === itemId);

        if (!item) {
            showNotification('Item not found', 'error');
            return;
        }

        document.getElementById('shop-item-modal-title').textContent = 'Edit Shop Item';
        document.getElementById('shop-item-id').value = itemId;
        document.getElementById('shop-item-name').value = item.name || '';
        document.getElementById('shop-item-description').value = item.description || '';
        document.getElementById('shop-item-price').value = item.price || 0;
        document.getElementById('shop-item-category').value = item.category || 'general';
        document.getElementById('shop-item-stock').value = item.stock !== undefined ? item.stock : -1;
        document.getElementById('shop-item-emoji').value = item.emoji || '';
        document.getElementById('shop-item-modal').style.display = 'block';
    } catch (error) {
        showNotification(`Failed to load item: ${error.message}`, 'error');
    }
}

async function saveShopItem(event) {
    event.preventDefault();

    const itemId = document.getElementById('shop-item-id').value;
    const itemData = {
        item_id: itemId || document.getElementById('shop-item-name').value.toLowerCase().replace(/\s+/g, '_'),
        name: document.getElementById('shop-item-name').value,
        description: document.getElementById('shop-item-description').value,
        price: parseInt(document.getElementById('shop-item-price').value),
        category: document.getElementById('shop-item-category').value,
        stock: parseInt(document.getElementById('shop-item-stock').value),
        emoji: document.getElementById('shop-item-emoji').value || '🛍️'
    };

    try {
        if (itemId) {
            // Update existing item
            await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
                method: 'PUT',
                body: JSON.stringify(itemData)
            });
            showNotification('Shop item updated successfully', 'success');
        } else {
            // Create new item
            await apiCall(`/api/${currentServerId}/shop`, {
                method: 'POST',
                body: JSON.stringify(itemData)
            });
            showNotification('Shop item created successfully', 'success');
        }

        closeShopItemModal();
        loadShop();
    } catch (error) {
        showNotification(`Failed to save shop item: ${error.message}`, 'error');
    }
}

function closeShopItemModal() {
    document.getElementById('shop-item-modal').style.display = 'none';
}

// ========== TASK MANAGEMENT ==========

function showCreateTaskModal() {
    document.getElementById('task-modal-title').textContent = 'Create Task';
    document.getElementById('task-form').reset();
    document.getElementById('task-id').value = '';
    document.getElementById('task-modal').style.display = 'block';
}

async function editTask(taskId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/tasks`);
        const task = Object.values(data.tasks).find(t => t.task_id === taskId);

        if (!task) {
            showNotification('Task not found', 'error');
            return;
        }

        document.getElementById('task-modal-title').textContent = 'Edit Task';
        document.getElementById('task-id').value = taskId;
        document.getElementById('task-name').value = task.name || '';
        document.getElementById('task-description').value = task.description || '';
        document.getElementById('task-reward').value = task.reward || 0;
        document.getElementById('task-duration').value = task.duration_hours || 24;
        document.getElementById('task-max-claims').value = task.max_claims !== undefined ? task.max_claims : -1;
        document.getElementById('task-modal').style.display = 'block';
    } catch (error) {
        showNotification(`Failed to load task: ${error.message}`, 'error');
    }
}

async function saveTask(event) {
    event.preventDefault();

    const taskId = document.getElementById('task-id').value;
    const taskData = {
        name: document.getElementById('task-name').value,
        description: document.getElementById('task-description').value,
        reward: parseInt(document.getElementById('task-reward').value),
        duration_hours: parseInt(document.getElementById('task-duration').value),
        max_claims: parseInt(document.getElementById('task-max-claims').value)
    };

    try {
        if (taskId) {
            // Update existing task
            await apiCall(`/api/${currentServerId}/tasks/${taskId}`, {
                method: 'PUT',
                body: JSON.stringify(taskData)
            });
            showNotification('Task updated successfully', 'success');
        } else {
            // Create new task
            await apiCall(`/api/${currentServerId}/tasks`, {
                method: 'POST',
                body: JSON.stringify(taskData)
            });
            showNotification('Task created successfully', 'success');
        }

        closeTaskModal();
        loadTasks();
    } catch (error) {
        showNotification(`Failed to save task: ${error.message}`, 'error');
    }
}

function closeTaskModal() {
    document.getElementById('task-modal').style.display = 'none';
}

// ========== ANNOUNCEMENT MANAGEMENT ==========

async function showCreateAnnouncementModal() {
    document.getElementById('announcement-modal-title').textContent = 'Create Announcement';
    document.getElementById('announcement-form').reset();
    document.getElementById('announcement-id').value = '';

    // Load channels
    await loadChannelsForSelect('announcement-channel');

    document.getElementById('announcement-modal').style.display = 'block';
}

async function editAnnouncement(announcementId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/announcements`);
        const announcement = data.announcements.find(a => a.id === announcementId);

        if (!announcement) {
            showNotification('Announcement not found', 'error');
            return;
        }

        document.getElementById('announcement-modal-title').textContent = 'Edit Announcement';
        document.getElementById('announcement-id').value = announcementId;
        document.getElementById('announcement-title').value = announcement.title || '';
        document.getElementById('announcement-content').value = announcement.content || '';
        document.getElementById('announcement-pinned').checked = announcement.pinned || false;

        // Load channels
        await loadChannelsForSelect('announcement-channel');
        document.getElementById('announcement-channel').value = announcement.channel_id || '';

        document.getElementById('announcement-modal').style.display = 'block';
    } catch (error) {
        showNotification(`Failed to load announcement: ${error.message}`, 'error');
    }
}

async function saveAnnouncement(event) {
    event.preventDefault();

    const announcementId = document.getElementById('announcement-id').value;
    const announcementData = {
        title: document.getElementById('announcement-title').value,
        content: document.getElementById('announcement-content').value,
        channel_id: document.getElementById('announcement-channel').value,
        pinned: document.getElementById('announcement-pinned').checked
    };

    try {
        if (announcementId) {
            // Update existing announcement
            await apiCall(`/api/${currentServerId}/announcements/${announcementId}`, {
                method: 'PUT',
                body: JSON.stringify(announcementData)
            });
            showNotification('Announcement updated successfully', 'success');
        } else {
            // Create and send new announcement
            await apiCall(`/api/${currentServerId}/announcements`, {
                method: 'POST',
                body: JSON.stringify(announcementData)
            });
            showNotification('Announcement sent successfully', 'success');
        }

        closeAnnouncementModal();
        loadAnnouncements();
    } catch (error) {
        showNotification(`Failed to save announcement: ${error.message}`, 'error');
    }
}

function closeAnnouncementModal() {
    document.getElementById('announcement-modal').style.display = 'none';
}

async function deleteAnnouncement(announcementId) {
    if (!confirm('Are you sure you want to delete this announcement?')) return;

    try {
        await apiCall(`/api/${currentServerId}/announcements/${announcementId}`, {
            method: 'DELETE'
        });
        showNotification('Announcement deleted successfully', 'success');
        loadAnnouncements();
    } catch (error) {
        showNotification(`Failed to delete announcement: ${error.message}`, 'error');
    }
}

// ========== EMBED MANAGEMENT ==========

async function showCreateEmbedModal() {
    document.getElementById('embed-modal-title').textContent = 'Create Embed';
    document.getElementById('embed-form').reset();
    document.getElementById('embed-id').value = '';
    document.getElementById('embed-modal').style.display = 'block';
}

async function editEmbed(embedId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/embeds`);
        const embed = data.embeds.find(e => e.id === embedId);

        if (!embed) {
            showNotification('Embed not found', 'error');
            return;
        }

        document.getElementById('embed-modal-title').textContent = 'Edit Embed';
        document.getElementById('embed-id').value = embedId;
        document.getElementById('embed-title').value = embed.title || '';
        document.getElementById('embed-description').value = embed.description || '';
        document.getElementById('embed-color').value = embed.color || '';
        document.getElementById('embed-footer').value = embed.footer || '';
        document.getElementById('embed-image-url').value = embed.image_url || '';
        document.getElementById('embed-thumbnail-url').value = embed.thumbnail_url || '';
        document.getElementById('embed-modal').style.display = 'block';
    } catch (error) {
        showNotification(`Failed to load embed: ${error.message}`, 'error');
    }
}

async function saveEmbed(event) {
    event.preventDefault();

    const embedId = document.getElementById('embed-id').value;
    const embedData = {
        title: document.getElementById('embed-title').value,
        description: document.getElementById('embed-description').value,
        color: document.getElementById('embed-color').value,
        footer: document.getElementById('embed-footer').value,
        image_url: document.getElementById('embed-image-url').value,
        thumbnail_url: document.getElementById('embed-thumbnail-url').value
    };

    try {
        if (embedId) {
            // Update existing embed
            await apiCall(`/api/${currentServerId}/embeds/${embedId}`, {
                method: 'PUT',
                body: JSON.stringify(embedData)
            });
            showNotification('Embed updated successfully', 'success');
        } else {
            // Create new embed
            await apiCall(`/api/${currentServerId}/embeds`, {
                method: 'POST',
                body: JSON.stringify(embedData)
            });
            showNotification('Embed created successfully', 'success');
        }

        closeEmbedModal();
        loadEmbeds();
    } catch (error) {
        showNotification(`Failed to save embed: ${error.message}`, 'error');
    }
}

function closeEmbedModal() {
    document.getElementById('embed-modal').style.display = 'none';
}

async function deleteEmbed(embedId) {
    if (!confirm('Are you sure you want to delete this embed?')) return;

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}`, {
            method: 'DELETE'
        });
        showNotification('Embed deleted successfully', 'success');
        loadEmbeds();
    } catch (error) {
        showNotification(`Failed to delete embed: ${error.message}`, 'error');
    }
}

async function sendEmbed(embedId) {
    document.getElementById('send-embed-id').value = embedId;

    // Load channels
    await loadChannelsForSelect('send-embed-channel');

    document.getElementById('send-embed-modal').style.display = 'block';
}

async function sendEmbedToChannel(event) {
    event.preventDefault();

    const embedId = document.getElementById('send-embed-id').value;
    const channelId = document.getElementById('send-embed-channel').value;

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}/send`, {
            method: 'POST',
            body: JSON.stringify({ channel_id: channelId })
        });
        showNotification('Embed sent successfully', 'success');
        closeSendEmbedModal();
    } catch (error) {
        showNotification(`Failed to send embed: ${error.message}`, 'error');
    }
}

function closeSendEmbedModal() {
    document.getElementById('send-embed-modal').style.display = 'none';
}

async function refreshEmbeds() {
    loadEmbeds();
}

// ========== HELPER FUNCTIONS ==========

async function loadChannelsForSelect(selectId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/channels`);
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="">Select a channel...</option>';

        if (data.channels && data.channels.length > 0) {
            data.channels.forEach(channel => {
                const option = document.createElement('option');
                option.value = channel.id;
                option.textContent = `#${channel.name}`;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load channels:', error);
    }
}

// Close modals when clicking outside
window.onclick = function (event) {
    const modals = ['shop-item-modal', 'task-modal', 'announcement-modal', 'embed-modal', 'send-embed-modal'];
    modals.forEach(modalId => {
        const modal = document.getElementById(modalId);
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
}

async function configureChannelPermissions() {
    if (!currentServerId) return;
    alert('Channel permissions configuration coming soon!');
}

// ========== LOGIN HANDLING ==========

async function handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const loginError = document.getElementById('login-error');

    loginError.style.display = 'none';

    try {
        const response = await fetch(apiUrl('/api/auth/login'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok && data.user) {
            // Store user data
            currentUser = data.user;

            // Hide login screen and show dashboard
            document.getElementById('login-screen').style.display = 'none';
            document.getElementById('main-dashboard').style.display = 'flex';

            // Load initial data
            await loadServers();
            showNotification('Login successful!', 'success');
        } else {
            loginError.textContent = data.error || 'Login failed. Please check your credentials.';
            loginError.style.display = 'block';
        }
    } catch (error) {
        console.error('Login error:', error);
        loginError.textContent = 'Connection error. Please try again.';
        loginError.style.display = 'block';
    }
}

function showLoginScreen() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('main-dashboard').style.display = 'none';
    currentUser = null;
    currentServerId = '';
}

async function loadServers() {
    try {
        const data = await apiCall('/api/servers');
        const select = document.getElementById('server-select');
        select.innerHTML = '<option value="">-- Select a server --</option>';

        if (data && data.servers && data.servers.length > 0) {
            data.servers.forEach(server => {
                const option = document.createElement('option');
                const serverId = server.id || server.guild_id;
                option.value = serverId;
                option.textContent = server.name || `Server ${serverId}`;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load servers:', error);
        showNotification('Failed to load servers', 'error');
    }
}

function onServerChange() {
    const select = document.getElementById('server-select');
    const selectedValue = select.value;

    if (!selectedValue || selectedValue === 'undefined' || selectedValue === 'null') {
        currentServerId = '';
        return;
    }

    currentServerId = selectedValue;

    if (currentServerId) {
        // Load the current tab's data
        const activeTab = document.querySelector('.tab-content.active');
        if (activeTab) {
            const tabId = activeTab.id;
            showTab(tabId);
        }
    }
}


// ========== PAGE INITIALIZATION ==========

function initializePage() {
    console.log('Initializing page...');

    // Attach login form handler
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        console.log('Login form found, attaching submit handler');
        loginForm.addEventListener('submit', handleLogin);
    } else {
        console.error('Login form not found!');
    }

    // Check if already logged in (for development)
    const loginScreen = document.getElementById('login-screen');
    if (loginScreen) {
        loginScreen.style.display = 'flex';
    }
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    // DOM is still loading, wait for it
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    // DOM is already loaded, run immediately
    initializePage();
}
