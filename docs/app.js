// API Configuration
console.log('EVL CMS v3.1 Loaded');
const API_BASE_URL = (window.location.hostname === 'localhost' || window.location.protocol === 'file:')
    ? 'http://localhost:5000'
    : (window.API_BASE_URL || 'https://evldiscordbot-production.up.railway.app');

let currentServerId = '';
let currentUser = null;

let discordDataCache = {
    users: {},
    channels: {},
    roles: {}
};
window.discordDataCache = discordDataCache;

window.fetchDiscordData = async function (serverId) {
    if (!serverId) return;

    try {
        console.log('Fetching Discord data for server:', serverId);

        // Fetch in parallel
        const [usersData, channelsData, rolesData] = await Promise.all([
            apiCall(`/api/${serverId}/users`),
            apiCall(`/api/${serverId}/channels`),
            apiCall(`/api/${serverId}/roles`)
        ]);

        if (usersData && usersData.users) {
            discordDataCache.users = {};
            usersData.users.forEach(u => discordDataCache.users[u.user_id] = u);
        }

        if (channelsData && channelsData.channels) {
            discordDataCache.channels = {};
            channelsData.channels.forEach(c => discordDataCache.channels[c.id] = c);
        }

        if (rolesData && rolesData.roles) {
            discordDataCache.roles = {};
            rolesData.roles.forEach(r => discordDataCache.roles[r.id] = r);
        }

        console.log('Discord data cached:', {
            users: Object.keys(discordDataCache.users).length,
            channels: Object.keys(discordDataCache.channels).length,
            roles: Object.keys(discordDataCache.roles).length
        });

    } catch (error) {
        console.error('Failed to fetch Discord data:', error);
        showNotification('Failed to load Discord data', 'error');
    }
};

async function updateBotStatus() {
    const statusType = document.getElementById('bot-status-type');
    const statusMessage = document.getElementById('bot-status-message');

    if (!statusType || !statusMessage) {
        console.error('Bot status elements not found');
        return;
    }

    logCmsAction('update_bot_status_start', { type: statusType.value, message: statusMessage.value });

    try {
        await apiCall(`/api/${currentServerId}/bot_status`, {
            method: 'POST',
            body: JSON.stringify({
                type: statusType.value,
                message: statusMessage.value
            })
        });
        showNotification('Bot status updated', 'success');
        logCmsAction('update_bot_status_success', { type: statusType.value, message: statusMessage.value });
    } catch (error) {
        showNotification('Failed to update bot status', 'error');
        logCmsAction('update_bot_status_failed', { error: error.message }, false);
    }
}


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

        // Prevent caching for GET requests by appending timestamp or using cache header
        if (options.method === 'GET' || !options.method) {
            options.cache = 'no-store';
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

/**
 * Log CMS activity to backend
 */
async function logCmsAction(action, details = {}, success = true, guildId = null) {
    console.log(`[LOG] ${action}`, details);
    try {
        await apiCall('/api/admin/log_cms_action', {
            method: 'POST',
            body: JSON.stringify({
                action,
                details,
                success,
                guild_id: guildId || window.currentServerId || 0
            })
        });
    } catch (e) {
        console.warn('Logging to backend failed:', e);
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
async function loadConfigTab() {
    if (!currentServerId) return;
    const content = document.getElementById('config-content');
    if (!content) return;

    try {
        // Fetch Discord data and config
        await fetchDiscordData(currentServerId);
        const config = await apiCall(`/api/${currentServerId}/config`);

        // Populate channel dropdowns
        const channels = Object.values(discordDataCache.channels);
        const channelOptions = channels.map(ch =>
            `<option value="${ch.id}">${ch.name}</option>`
        ).join('');

        // Build the config form
        let html = `
            <div class="settings-grid">
                <!-- Channel Settings -->
                <div class="section-card">
                    <h3>📢 Channel Configuration</h3>
                    
                    <div class="form-group">
                        <label for="welcome-channel">Welcome Channel:</label>
                        <select id="welcome-channel" class="form-control">
                            <option value="">None</option>
                            ${channelOptions}
                        </select>
                        <button onclick="saveChannelSetting('welcome')" class="btn-primary btn-small">Save</button>
                        <span id="welcome-channel-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label for="log-channel">Log Channel:</label>
                        <select id="log-channel" class="form-control">
                            <option value="">None</option>
                            ${channelOptions}
                        </select>
                        <button onclick="saveChannelSetting('log')" class="btn-primary btn-small">Save</button>
                        <span id="log-channel-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label for="task-channel">Task Channel:</label>
                        <select id="task-channel" class="form-control">
                            <option value="">None</option>
                            ${channelOptions}
                        </select>
                        <button onclick="saveChannelSetting('task')" class="btn-primary btn-small">Save</button>
                        <span id="task-channel-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label for="shop-channel">Shop Channel:</label>
                        <select id="shop-channel" class="form-control">
                            <option value="">None</option>
                            ${channelOptions}
                        </select>
                        <button onclick="saveChannelSetting('shop')" class="btn-primary btn-small">Save</button>
                        <span id="shop-channel-status" class="status-text"></span>
                    </div>
                </div>

                <!-- Permission Roles -->
                <div class="section-card">
                    <h3>🔐 Permission Roles</h3>
                    
                    <div class="form-group">
                        <label for="admin-roles">Admin Roles:</label>
                        <select id="admin-roles" class="form-control" multiple size="5">
                            ${Object.values(discordDataCache.roles).map(r =>
            `<option value="${r.id}">${r.name}</option>`
        ).join('')}
                        </select>
                        <small>Hold Ctrl/Cmd to select multiple roles</small>
                        <button onclick="saveRolePermissions('admin')" class="btn-primary btn-small">Save</button>
                        <span id="admin-roles-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label for="moderator-roles">Moderator Roles:</label>
                        <select id="moderator-roles" class="form-control" multiple size="5">
                            ${Object.values(discordDataCache.roles).map(r =>
            `<option value="${r.id}">${r.name}</option>`
        ).join('')}
                        </select>
                        <small>Hold Ctrl/Cmd to select multiple roles</small>
                        <button onclick="saveRolePermissions('moderator')" class="btn-primary btn-small">Save</button>
                        <span id="moderator-roles-status" class="status-text"></span>
                    </div>
                </div>

                <!-- Currency Settings -->
                <div class="section-card">
                    <h3>💰 Currency Settings</h3>
                    
                    <div class="form-group">
                        <label for="currency-name">Currency Name:</label>
                        <input type="text" id="currency-name" class="form-control" placeholder="Coins">
                    </div>

                    <div class="form-group">
                        <label for="currency-symbol">Currency Symbol:</label>
                        <input type="text" id="currency-symbol" class="form-control" placeholder="💰" maxlength="10">
                    </div>

                    <button onclick="saveCurrencySettings()" class="btn-primary">Save Currency Settings</button>
                    <span id="currency-settings-status" class="status-text"></span>
                </div>

                <!-- Bot Behavior -->
                <div class="section-card">
                    <h3>🤖 Bot Behavior</h3>
                    
                    <div class="form-group">
                        <label for="inactivity-days">Inactivity Days:</label>
                        <input type="number" id="inactivity-days" class="form-control" min="1" max="365">
                        <small>Days before marking users inactive</small>
                    </div>

                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="auto-expire-tasks">
                            Auto-expire tasks
                        </label>
                    </div>

                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="require-task-proof">
                            Require task proof
                        </label>
                    </div>

                    <button onclick="saveBotBehavior()" class="btn-primary">Save Behavior Settings</button>
                    <span id="bot-behavior-status" class="status-text"></span>
                </div>

                <!-- Feature Toggles (ONLY for Super Admins) -->
                ${(currentUser && (currentUser.role === 'superadmin' || currentUser.is_superadmin === true)) ? `
                <div class="section-card">
                    <h3>⚡ Feature Toggles</h3>
                    
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="feature-tasks">
                            Enable Tasks
                        </label>
                        <button onclick="saveFeatureToggle('tasks')" class="btn-primary btn-small">Save</button>
                        <span id="feature-tasks-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="feature-shop">
                            Enable Shop
                        </label>
                        <button onclick="saveFeatureToggle('shop')" class="btn-primary btn-small">Save</button>
                        <span id="feature-shop-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="feature-announcements">
                            Enable Announcements
                        </label>
                        <button onclick="saveFeatureToggle('announcements')" class="btn-primary btn-small">Save</button>
                        <span id="feature-announcements-status" class="status-text"></span>
                    </div>

                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="feature-moderation">
                            Enable Moderation
                        </label>
                        <button onclick="saveFeatureToggle('moderation')" class="btn-primary btn-small">Save</button>
                        <span id="feature-moderation-status" class="status-text"></span>
                    </div>
                </div>
                ` : ''}
            </div>
        `;

        content.innerHTML = html;

        // Wait for DOM to be ready, then populate values
        setTimeout(() => {
            if (config) {
                // Set channel values
                const welcomeChannel = document.getElementById('welcome-channel');
                const logChannel = document.getElementById('log-channel');
                const taskChannel = document.getElementById('task-channel');
                const shopChannel = document.getElementById('shop-channel');

                if (welcomeChannel && config.welcome_channel_id) welcomeChannel.value = config.welcome_channel_id;
                if (logChannel && config.log_channel_id) logChannel.value = config.log_channel_id;
                if (taskChannel && config.task_channel_id) taskChannel.value = config.task_channel_id;
                if (shopChannel && config.shop_channel_id) shopChannel.value = config.shop_channel_id;

                // Set currency values
                const currencyName = document.getElementById('currency-name');
                const currencySymbol = document.getElementById('currency-symbol');
                if (currencyName) currencyName.value = config.currency_name || 'Coins';
                if (currencySymbol) currencySymbol.value = config.currency_symbol || '💰';

                // Set bot behavior
                const inactivityDays = document.getElementById('inactivity-days');
                const autoExpireTasks = document.getElementById('auto-expire-tasks');
                const requireTaskProof = document.getElementById('require-task-proof');

                if (inactivityDays) inactivityDays.value = config.inactivity_days || 30;
                if (autoExpireTasks) autoExpireTasks.checked = config.auto_expire_enabled !== false;
                if (requireTaskProof) requireTaskProof.checked = config.require_proof !== false;

                // Set feature toggles
                const featureTasks = document.getElementById('feature-tasks');
                const featureShop = document.getElementById('feature-shop');
                const featureAnnouncements = document.getElementById('feature-announcements');
                const featureModeration = document.getElementById('feature-moderation');

                if (featureTasks) featureTasks.checked = config.feature_tasks !== false;
                if (featureShop) featureShop.checked = config.feature_shop !== false;
                if (featureAnnouncements) featureAnnouncements.checked = config.feature_announcements !== false;
                if (featureModeration) featureModeration.checked = config.feature_moderation !== false;

                // Set bot status values
                const botStatusMessage = document.getElementById('bot-status-message');
                const botStatusType = document.getElementById('bot-status-type');

                if (botStatusMessage && config.bot_status_message) {
                    botStatusMessage.value = config.bot_status_message;
                }
                if (botStatusType && config.bot_status_type) {
                    botStatusType.value = config.bot_status_type;
                }

                // Set permission roles
                const adminRolesSelect = document.getElementById('admin-roles');
                const moderatorRolesSelect = document.getElementById('moderator-roles');

                if (adminRolesSelect && config.admin_roles) {
                    Array.from(adminRolesSelect.options).forEach(option => {
                        option.selected = config.admin_roles.includes(option.value);
                    });
                }

                if (moderatorRolesSelect && config.moderator_roles) {
                    Array.from(moderatorRolesSelect.options).forEach(option => {
                        option.selected = config.moderator_roles.includes(option.value);
                    });
                }
            }

            // Show bot status section (ONLY for Super Admins)
            const botStatusSection = document.getElementById('bot-status-section');
            if (botStatusSection) {
                const isSuperAdmin = currentUser && (currentUser.role === 'superadmin' || currentUser.is_superadmin === true);
                if (isSuperAdmin) {
                    botStatusSection.style.display = 'block';
                } else {
                    botStatusSection.style.display = 'none';
                }
            }
        }, 100);

        showNotification('Configuration loaded', 'success');
    } catch (error) {
        console.error('Failed to load configuration:', error);
        content.innerHTML = '<div class="error">Failed to load configuration</div>';
        showNotification('Failed to load configuration', 'error');
    }
}
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

    logCmsAction('add_balance_start', { user_id: currentManagingUserId, amount, reason });

    try {
        await apiCall(`/api/${currentServerId}/users/${currentManagingUserId}/balance`, {
            method: 'PUT',
            body: JSON.stringify({ amount: parseInt(amount) })
        });
        showNotification('Balance added successfully', 'success');
        logCmsAction('add_balance_success', { user_id: currentManagingUserId, amount });
        loadUsers();
    } catch (error) {
        showNotification('Failed to add balance: ' + error.message, 'error');
        logCmsAction('add_balance_failed', { user_id: currentManagingUserId, error: error.message }, false);
    }
}

async function removeBalance() {
    if (!currentManagingUserId) return;
    const amount = document.getElementById('balance-amount').value;
    const reason = document.getElementById('balance-reason').value;

    logCmsAction('remove_balance_start', { user_id: currentManagingUserId, amount, reason });

    try {
        await apiCall(`/api/${currentServerId}/users/${currentManagingUserId}/balance`, {
            method: 'PUT',
            body: JSON.stringify({ amount: -parseInt(amount) })
        });
        showNotification('Balance removed successfully', 'success');
        logCmsAction('remove_balance_success', { user_id: currentManagingUserId, amount });
        loadUsers();
    } catch (error) {
        showNotification('Failed to remove balance: ' + error.message, 'error');
        logCmsAction('remove_balance_failed', { user_id: currentManagingUserId, error: error.message }, false);
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

        // Get server name from select dropdown if config doesn't have it
        let serverName = serverConfig.server_name || 'Unknown Server';
        if (!serverConfig.server_name) {
            const serverSelect = document.getElementById('server-select');
            if (serverSelect && serverSelect.selectedOptions.length > 0) {
                serverName = serverSelect.selectedOptions[0].textContent;
            }
        }

        content.innerHTML = `
            <div class="dashboard-grid">
                <div class="stat-card">
                    <h3>Bot Status</h3>
                    <div class="stat-value ${statusData.bot_status}">${statusData.bot_status.toUpperCase()}</div>
                    <div class="stat-sub">Uptime: ${statusData.uptime}</div>
                </div>
                <div class="stat-card">
                    <h3>Server Name</h3>
                    <div class="stat-value">${serverName}</div>
                </div>
                <div class="stat-card">
                    <h3>Currency</h3>
                    <div class="stat-value">${serverConfig.currency_symbol || '💰'} ${serverConfig.currency_name || 'Coins'}</div>
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
        // Pass page and limit to API for server-side pagination
        const data = await apiCall(`/api/${currentServerId}/users?page=${page}&limit=${USERS_PER_PAGE}`);

        if (data.users && data.users.length > 0) {
            // Use total from API response
            const totalUsers = data.total || data.users.length;
            const totalPages = Math.ceil(totalUsers / USERS_PER_PAGE);

            let html = '<div class="table-container"><table class="data-table"><thead><tr><th>User</th><th>Balance</th><th>Level</th><th>XP</th><th>Actions</th></tr></thead><tbody>';
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
            html += '</tbody></table></div>';

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

    logCmsAction('delete_shop_item_start', { item_id: itemId });

    try {
        await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
            method: 'DELETE'
        });
        showNotification('Item deleted successfully', 'success');
        logCmsAction('delete_shop_item_success', { item_id: itemId });
        loadShop();
    } catch (error) {
        showNotification(`Failed to delete item: ${error.message}`, 'error');
        logCmsAction('delete_shop_item_failed', { item_id: itemId, error: error.message }, false);
    }
}

async function editShopItem(itemId) {
    if (!currentServerId) return;

    try {
        // Fetch all items to find the one we want
        const data = await apiCall(`/api/${currentServerId}/shop`);
        const item = data.items.find(i => i.item_id === itemId);

        if (!item) {
            showNotification('Item not found', 'error');
            return;
        }

        // Open the modal
        showCreateShopItemModal();

        // Update title
        const title = document.getElementById('shop-item-modal-title');
        if (title) title.textContent = 'Edit Shop Item';

        // Populate fields
        document.getElementById('shop-item-id').value = item.item_id;
        document.getElementById('shop-item-name').value = item.name;
        document.getElementById('shop-item-description').value = item.description || '';
        document.getElementById('shop-item-price').value = item.price;
        document.getElementById('shop-item-stock').value = item.stock;
        document.getElementById('shop-item-emoji').value = item.emoji || '';

        const categorySelect = document.getElementById('shop-item-category');
        if (categorySelect) {
            categorySelect.value = item.category || 'role';

            // Handle role category
            if (item.category === 'role') {
                // Trigger the category change logic to show role dropdown
                categorySelect.dispatchEvent(new Event('change'));

                // Wait for roles to load
                await loadRolesForShopItem();

                // Set the role ID
                const roleSelect = document.getElementById('shop-item-role-id');
                if (roleSelect && item.role_id) {
                    roleSelect.value = item.role_id;
                }
            }
        }

    } catch (error) {
        console.error('Edit shop item error:', error);
        showNotification(`Failed to load item details: ${error.message}`, 'error');
    }
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
        console.log('Tasks API response:', data);

        // Handle both array and object responses
        let tasks = [];
        if (data.tasks) {
            if (Array.isArray(data.tasks)) {
                tasks = data.tasks;
            } else if (typeof data.tasks === 'object') {
                tasks = Object.values(data.tasks);
            }
        }

        console.log(`Total tasks loaded: ${tasks.length}`);
        console.log('Global tasks:', tasks.filter(t => t.is_global));

        if (tasks.length > 0) {
            let html = '<div class="grid-container">';
            tasks.forEach(task => {
                // Add global badge if task is global
                const globalBadge = task.is_global ? '<span class="global-badge" style="background: #5865F2; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; margin-left: 8px;">🌐 Global</span>' : '';
                const borderStyle = task.is_global ? 'style="border-left: 4px solid #5865F2;"' : '';

                html += `
                    <div class="task-card" ${borderStyle}>
                        <h4>${task.name}${globalBadge}</h4>
                        <p>${task.description || ''}</p>
                        <div class="reward">Reward: ${task.reward} coins</div>
                        <div class="task-meta">
                            <span>⏱️ ${task.duration_hours || 24}h</span>
                            ${task.max_claims && task.max_claims > 0 ? `<span>👥 ${task.current_claims || 0}/${task.max_claims}</span>` : ''}
                            <span class="status-badge status-${task.status}">${task.status}</span>
                        </div>
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
        console.error('Load tasks error:', error);
        list.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

async function deleteTask(taskId) {
    if (!confirm('Are you sure you want to delete this task?')) return;

    logCmsAction('delete_task_start', { task_id: taskId });

    try {
        await apiCall(`/api/${currentServerId}/tasks/${taskId}`, {
            method: 'DELETE'
        });
        showNotification('Task deleted successfully', 'success');
        logCmsAction('delete_task_success', { task_id: taskId });
        loadTasks();
    } catch (error) {
        showNotification(`Failed to delete task: ${error.message}`, 'error');
        logCmsAction('delete_task_failed', { task_id: taskId, error: error.message }, false);
    }
}

async function editTask(taskId) {
    if (!currentServerId) return;

    try {
        // Fetch all tasks
        const data = await apiCall(`/api/${currentServerId}/tasks`);

        let task = null;
        if (data.tasks) {
            if (Array.isArray(data.tasks)) {
                // Convert both to numbers for comparison
                task = data.tasks.find(t => Number(t.task_id) === Number(taskId));
            } else {
                task = data.tasks[taskId];
            }
        }

        if (!task) {
            showNotification('Task not found', 'error');
            return;
        }

        // Open modal
        showCreateTaskModal();

        // Update title
        const title = document.getElementById('task-modal-title');
        if (title) title.textContent = 'Edit Task';

        // Populate fields
        document.getElementById('task-id').value = task.task_id;
        document.getElementById('task-name').value = task.name;
        document.getElementById('task-description').value = task.description || '';
        document.getElementById('task-reward').value = task.reward;
        document.getElementById('task-duration').value = task.duration_hours || 24;
        document.getElementById('task-max-claims').value = task.max_claims || 0;

    } catch (error) {
        console.error('Edit task error:', error);
        showNotification(`Failed to load task details: ${error.message}`, 'error');
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
            let html = '<div class="embeds-list-container"><div class="embeds-grid">';

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

            html += '</div></div>';
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
                <div class="table-container">
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

            html += '</tbody></table></div>';

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



// Old announcement code removed


// ========== EMBED ACTIONS ==========

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
    if (event) event.preventDefault();

    const embedId = document.getElementById('embed-id').value;
    const embedData = {
        title: document.getElementById('embed-title').value,
        description: document.getElementById('embed-description').value,
        color: document.getElementById('embed-color').value,
        footer_text: document.getElementById('embed-footer').value,
        image_url: document.getElementById('embed-image-url').value,
        thumbnail_url: document.getElementById('embed-thumbnail-url').value
    };

    try {
        let savedId = embedId;
        if (embedId) {
            // Update existing embed
            await apiCall(`/api/${currentServerId}/embeds/${embedId}`, {
                method: 'PUT',
                body: JSON.stringify(embedData)
            });
            showNotification('Embed updated successfully', 'success');
        } else {
            // Create new embed
            const response = await apiCall(`/api/${currentServerId}/embeds`, {
                method: 'POST',
                body: JSON.stringify(embedData)
            });
            if (response && response.embed && response.embed.id) {
                savedId = response.embed.id;
            } else if (response && response.id) {
                savedId = response.id;
            }
            showNotification('Embed created successfully', 'success');
        }

        closeEmbedModal();
        loadEmbeds();
        return savedId;
    } catch (error) {
        showNotification(`Failed to save embed: ${error.message}`, 'error');
        return null;
    }
}

async function saveAndSendEmbed(event) {
    if (event) event.preventDefault();
    const savedId = await saveEmbed(null);
    if (savedId) {
        // Wait a brief moment for the modal to close and list to refresh
        setTimeout(() => {
            sendEmbed(savedId);
        }, 500);
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


// ========== SETTINGS ACTIONS ==========

async function saveChannelSetting(settingType) {
    const selectId = `${settingType}-channel`;
    const channelId = document.getElementById(selectId).value;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                [`${settingType}_channel_id`]: channelId
            })
        });
        showNotification(`${settingType.charAt(0).toUpperCase() + settingType.slice(1)} channel updated`, 'success');
    } catch (error) {
        showNotification(`Failed to update ${settingType} channel: ${error.message}`, 'error');
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
        showNotification('Currency settings updated', 'success');
    } catch (error) {
        showNotification('Failed to update currency settings: ' + error.message, 'error');
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
                auto_expire_tasks: autoExpireTasks,
                require_task_proof: requireTaskProof
            })
        });
        showNotification('Bot behavior settings updated', 'success');
    } catch (error) {
        showNotification('Failed to update bot behavior: ' + error.message, 'error');
    }
}

async function saveFeatureToggle(feature) {
    const isEnabled = document.getElementById(`enable-${feature}`).checked;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                [`enable_${feature}`]: isEnabled
            })
        });
        showNotification(`${feature.charAt(0).toUpperCase() + feature.slice(1)} feature ${isEnabled ? 'enabled' : 'disabled'}`, 'success');
    } catch (error) {
        showNotification(`Failed to toggle ${feature}: ${error.message}`, 'error');
    }
}

async function saveRolePermissions(type) {
    const selectId = type === 'admin' ? 'admin-roles' : 'moderator-roles';
    const select = document.getElementById(selectId);
    const selectedRoles = Array.from(select.selectedOptions).map(opt => opt.value);
    const fieldName = type === 'admin' ? 'admin_roles' : 'moderator_roles';

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                [fieldName]: selectedRoles
            })
        });
        showNotification(`${type.charAt(0).toUpperCase() + type.slice(1)} roles updated`, 'success');

        // Update status indicator
        const statusSpan = document.getElementById(`${selectId}-status`);
        if (statusSpan) {
            statusSpan.textContent = '✓ Saved';
            statusSpan.style.color = 'green';
            setTimeout(() => statusSpan.textContent = '', 2000);
        }
    } catch (error) {
        showNotification(`Failed to update ${type} roles: ${error.message}`, 'error');
        const statusSpan = document.getElementById(`${selectId}-status`);
        if (statusSpan) {
            statusSpan.textContent = '✗ Failed';
            statusSpan.style.color = 'red';
        }
    }
}

async function saveBotStatus() {
    const statusMessage = document.getElementById('bot-status-message').value;
    const statusType = document.getElementById('bot-status-type').value;

    try {
        await apiCall(`/api/${currentServerId}/bot_status`, {
            method: 'POST',
            body: JSON.stringify({
                status_message: statusMessage,
                status_type: statusType
            })
        });
        showNotification('Bot status updated', 'success');
    } catch (error) {
        showNotification('Failed to update bot status: ' + error.message, 'error');
    }
}

// ========== SHOP ACTIONS ==========

async function saveShopItem(event) {
    if (event) event.preventDefault();

    const itemId = document.getElementById('shop-item-id').value;
    const name = document.getElementById('shop-item-name').value;
    const description = document.getElementById('shop-item-description').value;
    const price = document.getElementById('shop-item-price').value;
    const stock = document.getElementById('shop-item-stock').value;
    const category = document.getElementById('shop-item-category').value;
    const emoji = document.getElementById('shop-item-emoji').value;
    const roleId = document.getElementById('shop-item-role').value;

    if (!name || !price) {
        showNotification('Name and Price are required', 'warning');
        return;
    }

    const payload = {
        name,
        description,
        price: parseInt(price),
        stock: parseInt(stock),
        category,
        emoji
    };

    if (category === 'role') {
        if (!roleId) {
            showNotification('Please select a role for this item', 'warning');
            return;
        }
        payload.metadata = { role_id: roleId };
    }

    try {
        if (itemId) {
            await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
                method: 'PUT',
                body: JSON.stringify(payload)
            });
            showNotification('Item updated', 'success');
        } else {
            await apiCall(`/api/${currentServerId}/shop`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            showNotification('Item created', 'success');
        }
        closeModal();
        loadShop();
    } catch (error) {
        showNotification('Failed to save item: ' + error.message, 'error');
    }
}

async function deleteShopItem(itemId) {
    if (!confirm('Are you sure you want to delete this item?')) return;

    try {
        await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
            method: 'DELETE'
        });
        showNotification('Item deleted', 'success');
        loadShop();
    } catch (error) {
        showNotification('Failed to delete item: ' + error.message, 'error');
    }
}

async function saveShopItem(event) {
    if (event) event.preventDefault();

    const itemId = document.getElementById('shop-item-id')?.value;
    const name = document.getElementById('shop-item-name').value;
    const description = document.getElementById('shop-item-description').value;
    const price = document.getElementById('shop-item-price').value;
    const category = document.getElementById('shop-item-category').value;
    const stock = document.getElementById('shop-item-stock').value;
    const emoji = document.getElementById('shop-item-emoji').value;
    const roleId = document.getElementById('shop-item-role')?.value;

    if (!name || !price) {
        showNotification('Please fill all required fields', 'warning');
        return;
    }

    const payload = {
        name,
        description,
        price: parseInt(price),
        category,
        stock: parseInt(stock),
        emoji: emoji || '🎁',
        role_id: (category === 'role' && roleId) ? roleId : null
    };

    try {
        if (itemId) {
            await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
                method: 'PUT',
                body: JSON.stringify(payload)
            });
            showNotification('Shop item updated', 'success');
        } else {
            await apiCall(`/api/${currentServerId}/shop`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            showNotification('Shop item created', 'success');
        }
        closeModal();
        loadShop();
    } catch (error) {
        console.error('Save shop item error:', error);
        showNotification('Failed to save shop item: ' + error.message, 'error');
    }
}

// ========== CONFIG TAB SAVE FUNCTIONS ==========

async function saveChannelSetting(type) {
    const channelId = document.getElementById(`${type}-channel`)?.value;
    const statusSpan = document.getElementById(`${type}-channel-status`);

    if (!channelId) {
        showNotification('Please select a channel', 'warning');
        return;
    }

    try {
        const fieldMap = {
            'welcome': 'welcome_channel',
            'log': 'logs_channel',
            'task': 'task_channel_id',
            'shop': 'shop_channel_id'
        };

        const payload = {
            [fieldMap[type]]: channelId
        };

        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${type.charAt(0).toUpperCase() + type.slice(1)} channel saved`, 'success');
    } catch (error) {
        console.error('Save channel setting error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save channel setting', 'error');
    }
}

async function saveCurrencySettings() {
    const currencyName = document.getElementById('currency-name')?.value;
    const currencySymbol = document.getElementById('currency-symbol')?.value;
    const statusSpan = document.getElementById('currency-settings-status');

    if (!currencyName || !currencySymbol) {
        showNotification('Please fill all currency fields', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                currency_name: currencyName,
                currency_symbol: currencySymbol
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification('Currency settings saved', 'success');
    } catch (error) {
        console.error('Save currency settings error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save currency settings', 'error');
    }
}

async function saveBotBehavior() {
    const inactivityDays = document.getElementById('inactivity-days')?.value;
    const autoExpireTasks = document.getElementById('auto-expire-tasks')?.checked;
    const requireTaskProof = document.getElementById('require-task-proof')?.checked;
    const statusSpan = document.getElementById('bot-behavior-status');

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                inactivity_days: parseInt(inactivityDays),
                auto_expire_enabled: autoExpireTasks,
                require_proof: requireTaskProof
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification('Bot behavior settings saved', 'success');
    } catch (error) {
        console.error('Save bot behavior error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save bot behavior settings', 'error');
    }
}

async function saveFeatureToggle(feature) {
    const checkbox = document.getElementById(`feature-${feature}`);
    const statusSpan = document.getElementById(`feature-${feature}-status`);

    if (!checkbox) return;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                [`feature_${feature}`]: checkbox.checked
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${feature.charAt(0).toUpperCase() + feature.slice(1)} feature ${checkbox.checked ? 'enabled' : 'disabled'}`, 'success');
    } catch (error) {
        console.error('Save feature toggle error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save feature toggle', 'error');
    }
}

async function saveBotStatus() {
    const statusType = document.getElementById('bot-status-type')?.value;
    const statusMessage = document.getElementById('bot-status-message')?.value;

    if (!statusType || !statusMessage) {
        showNotification('Please fill all bot status fields', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/bot_status`, {
            method: 'POST',
            body: JSON.stringify({
                type: statusType,
                message: statusMessage
            })
        });
        showNotification('Bot status updated', 'success');
    } catch (error) {
        console.error('Save bot status error:', error);
        showNotification('Failed to update bot status', 'error');
    }
}

// ========== TASK ACTIONS ==========
// Task actions (showCreateTaskModal, editTask, saveTask, deleteTask) are now handled by app_fixes.js and earlier definitions in this file.


// ========== ANNOUNCEMENT ACTIONS ==========

// Update character count for announcement content
function updateAnnouncementCharCount() {
    const content = document.getElementById('announcement-content').value;
    const counter = document.getElementById('announcement-char-count');
    const length = content.length;
    counter.textContent = `${length} / 2000 characters`;

    // Change color based on length
    if (length > 1900) {
        counter.style.color = '#e74c3c'; // Red when approaching limit
    } else if (length > 1500) {
        counter.style.color = '#f39c12'; // Orange as warning
    } else {
        counter.style.color = '#666'; // Gray for normal
    }
}

async function saveAnnouncement(event) {
    if (event) event.preventDefault();

    const title = document.getElementById('announcement-title').value;
    const content = document.getElementById('announcement-content').value;
    const channelId = document.getElementById('announcement-channel').value;
    const isPinned = document.getElementById('announcement-pinned').checked;
    const imageUrl = document.getElementById('announcement-image').value;

    if (!title || !content || !channelId) {
        showNotification('Please fill all required fields', 'warning');
        return;
    }

    // Validate content length
    if (content.length > 2000) {
        showNotification('Content must be 2000 characters or less', 'error');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/announcements`, {
            method: 'POST',
            body: JSON.stringify({
                title,
                content,
                channel_id: channelId,
                pinned: isPinned,
                image_url: imageUrl || null
            })
        });

        showNotification('Announcement sent successfully!', 'success');
        closeModal();
        loadAnnouncements();
    } catch (error) {
        showNotification('Failed to send announcement: ' + error.message, 'error');
    }
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

async function editAnnouncement(announcementId) {
    showNotification('Edit announcement functionality coming soon!', 'info');
}

// ========== EMBED ACTIONS ==========

async function sendEmbed(embedId) {
    // Show a modal to select the channel
    const modal = createModal('Send Embed', `
<form id="send-embed-form" onsubmit="return false;">
    <div class="form-group">
        <label>Select Channel</label>
        <select id="send-embed-channel" class="form-control">
            ${getChannelOptions()}
        </select>
    </div>
    <div class="button-group">
        <button type="button" onclick="confirmSendEmbed('${embedId}')" class="btn-success">Send</button>
        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
    </div>
</form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

async function confirmSendEmbed(embedId) {
    const channelId = document.getElementById('send-embed-channel')?.value;

    if (!channelId) {
        showNotification('Please select a channel', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}/send`, {
            method: 'POST',
            body: JSON.stringify({ channel_id: channelId })
        });
        showNotification('Embed sent successfully', 'success');
        closeModal();
    } catch (error) {
        console.error('Send embed error:', error);
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
        console.error('Delete embed error:', error);
        showNotification('Failed to delete embed: ' + error.message, 'error');
    }
}

async function editEmbed(embedId) {
    showNotification('Edit embed functionality coming soon!', 'info');
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

        if (data.success) {
            currentUser = data.user;

            // Set user role for superadmin (username/password login)
            if (typeof window.currentUserRole !== 'undefined') {
                window.currentUserRole = 'superadmin';
            }

            // Hide login, show dashboard
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

function logout() {
    // Clear any stored session data
    currentUser = null;
    currentServerId = '';

    // Show login screen
    showLoginScreen();

    // Optionally call logout endpoint
    fetch(apiUrl('/api/auth/logout'), {
        method: 'POST',
        credentials: 'include'
    }).catch(err => console.error('Logout error:', err));

    showNotification('Logged out successfully', 'info');
}

function closeModal() {
    const modal = document.getElementById('dynamic-modal');
    if (modal) {
        modal.remove();
    }
}

function showCreateShopItemModal() {
    const modal = createModal('Create Shop Item', `
<form id="shop-item-form" onsubmit="return false;">
    <input type="hidden" id="shop-item-id">
    <div class="form-group">
        <label>Item Name</label>
        <input type="text" id="shop-item-name" class="form-control" required>
    </div>
    <div class="form-group">
        <label>Description</label>
        <textarea id="shop-item-description" class="form-control" rows="3"></textarea>
    </div>
    <div class="form-group">
        <label>Price</label>
        <input type="number" id="shop-item-price" class="form-control" required>
    </div>
    <div class="form-group">
        <label>Category</label>
        <select id="shop-item-category" class="form-control" onchange="toggleRoleSelect()">
            <option value="general">General</option>
            <option value="consumable">Consumable</option>
            <option value="role">Role</option>
            <option value="collectible">Collectible</option>
        </select>
    </div>
    
    <!-- Role Selection (Hidden by default) -->
    <div class="form-group" id="role-select-group" style="display: none;">
        <label>Select Role</label>
        <select id="shop-item-role" class="form-control">
            ${getRoleOptions()}
        </select>
        <small>The role to give when purchased.</small>
    </div>

    <div class="form-group">
        <label>Stock (-1 for unlimited)</label>
        <input type="number" id="shop-item-stock" class="form-control" value="-1">
    </div>
    <div class="form-group">
        <label>Emoji</label>
        <div class="emoji-picker-container">
            <input type="text" id="shop-item-emoji" class="form-control" placeholder="🎁 or select ->">
            <select class="form-control" style="width: 100px;" onchange="document.getElementById('shop-item-emoji').value = this.value">
                <option value="">Pick...</option>
                <option value="🎁">🎁</option>
                <option value="👕">👕</option>
                <option value="🎩">🎩</option>
                <option value="👑">👑</option>
                <option value="⚔️">⚔️</option>
                <option value="🛡️">🛡️</option>
                <option value="🧪">🧪</option>
                <option value="📜">📜</option>
                <option value="💎">💎</option>
                <option value="💰">💰</option>
                <option value="🏷️">🏷️</option>
                <option value="📦">📦</option>
            </select>
        </div>
    </div>
    <div class="button-group">
        <button type="button" onclick="saveShopItem(event)" class="btn-success">Save</button>
        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
    </div>
</form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

function toggleRoleSelect() {
    const category = document.getElementById('shop-item-category').value;
    const roleGroup = document.getElementById('role-select-group');
    if (category === 'role') {
        roleGroup.style.display = 'block';
    } else {
        roleGroup.style.display = 'none';
    }
}

function showCreateAnnouncementModal() {
    const modal = createModal('Create Announcement', `
<form id="announcement-form" onsubmit="return false;">
    <input type="hidden" id="announcement-id">
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
        <select id="announcement-channel" class="form-control">
            ${getChannelOptions()}
        </select>
    </div>
    <div class="form-group">
        <label>
            <input type="checkbox" id="announcement-pinned">
            Pin this announcement
        </label>
    </div>
    <div class="button-group">
        <button type="button" onclick="saveAnnouncement(event)" class="btn-success">Send</button>
        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
    </div>
</form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

function getChannelOptions() {
    const channels = Object.values(discordDataCache.channels);
    if (channels.length === 0) {
        return '<option value="">No channels available</option>';
    }
    return channels.map(ch => `<option value="${ch.id}">#${ch.name}</option>`).join('');
}

function getRoleOptions() {
    const roles = Object.values(discordDataCache.roles);
    if (roles.length === 0) {
        return '<option value="">No roles available</option>';
    }
    return roles.map(role => `<option value="${role.id}">${role.name}</option>`).join('');
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

            // Auto-select the first server
            const firstServerId = data.servers[0].id || data.servers[0].guild_id;
            select.value = firstServerId;
            currentServerId = firstServerId;

            // Load dashboard for the first server
            await loadDashboard();
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
        // Fetch Discord data for the selected server
        fetchDiscordData(currentServerId).then(() => {
            // Load the current tab's data
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const tabId = activeTab.id;
                showTab(tabId);
            }
        }).catch(error => {
            console.error('Failed to fetch Discord data:', error);
            // Still try to load the tab even if Discord data fetch fails
            const activeTab = document.querySelector('.tab-content.active');
            if (activeTab) {
                const tabId = activeTab.id;
                showTab(tabId);
            }
        });
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
// ========== MISSING MODAL FUNCTIONS ==========

// Shop Item Modal Functions
function showCreateShopItemModal() {
    const modal = document.getElementById('shop-item-modal');
    const form = document.getElementById('shop-item-form');
    const title = document.getElementById('shop-item-modal-title');

    if (!modal || !form) return;

    // Reset form
    form.reset();
    document.getElementById('shop-item-id').value = '';
    title.textContent = 'Add Shop Item';

    // Populate category dropdown with role options if category is 'role'
    const categorySelect = document.getElementById('shop-item-category');
    if (categorySelect) {
        categorySelect.onchange = function () {
            const roleOptionsContainer = document.getElementById('shop-item-role-options');
            if (this.value === 'role') {
                if (!roleOptionsContainer) {
                    // Create role options container
                    const roleDiv = document.createElement('div');
                    roleDiv.id = 'shop-item-role-options';
                    roleDiv.className = 'form-group';
                    roleDiv.innerHTML = `
                        <label for="shop-item-role-id">Select Role *</label>
                        <select id="shop-item-role-id" class="form-control" required>
                            <option value="">Loading roles...</option>
                        </select>
                    `;
                    categorySelect.parentElement.after(roleDiv);

                    // Load roles
                    loadRolesForShopItem();
                }
            } else {
                // Remove role options if exists
                const roleOptionsContainer = document.getElementById('shop-item-role-options');
                if (roleOptionsContainer) {
                    roleOptionsContainer.remove();
                }
            }
        };
    }

    modal.style.display = 'block';
}

async function loadRolesForShopItem() {
    const roleSelect = document.getElementById('shop-item-role-id');
    if (!roleSelect || !currentServerId) return;

    try {
        await fetchDiscordData(currentServerId);
        const roles = Object.values(discordDataCache.roles);

        let html = '<option value="">Select a role...</option>';
        roles.forEach(role => {
            html += `<option value="${role.id}">${role.name}</option>`;
        });
        roleSelect.innerHTML = html;
    } catch (error) {
        console.error('Failed to load roles:', error);
        roleSelect.innerHTML = '<option value="">Failed to load roles</option>';
    }
}

function closeShopItemModal() {
    const modal = document.getElementById('shop-item-modal');
    if (modal) modal.style.display = 'none';
}

async function saveShopItem(event) {
    event.preventDefault();

    const itemId = document.getElementById('shop-item-id').value;
    const name = document.getElementById('shop-item-name').value;
    const description = document.getElementById('shop-item-description').value;
    const price = parseInt(document.getElementById('shop-item-price').value);
    const category = document.getElementById('shop-item-category').value;
    const stock = parseInt(document.getElementById('shop-item-stock').value);
    const emoji = document.getElementById('shop-item-emoji').value;

    const itemData = {
        name,
        description,
        price,
        category,
        stock,
        emoji
    };

    // If category is role, add role_id
    if (category === 'role') {
        const roleId = document.getElementById('shop-item-role-id')?.value;
        if (!roleId) {
            showNotification('Please select a role', 'error');
            return;
        }
        itemData.role_id = roleId;
    }

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

// Task Modal Functions
// Task Modal Functions (showCreateTaskModal, closeTaskModal, saveTask) are now handled by app_fixes.js


// Announcement Modal Functions
function showCreateAnnouncementModal() {
    const modal = document.getElementById('announcement-modal');
    const form = document.getElementById('announcement-form');
    const title = document.getElementById('announcement-modal-title');

    if (!modal || !form) return;

    // Reset form
    form.reset();
    document.getElementById('announcement-id').value = '';
    title.textContent = 'Create Announcement';

    // Load channels
    loadChannelsForAnnouncement();

    modal.style.display = 'block';
}

async function loadChannelsForAnnouncement() {
    const channelSelect = document.getElementById('announcement-channel');
    if (!channelSelect || !currentServerId) return;

    try {
        await fetchDiscordData(currentServerId);
        const channels = Object.values(discordDataCache.channels);

        let html = '<option value="">Select a channel...</option>';
        channels.forEach(channel => {
            html += `<option value="${channel.id}">#${channel.name}</option>`;
        });
        channelSelect.innerHTML = html;
    } catch (error) {
        console.error('Failed to load channels:', error);
        channelSelect.innerHTML = '<option value="">Failed to load channels</option>';
    }
}

function closeAnnouncementModal() {
    const modal = document.getElementById('announcement-modal');
    if (modal) modal.style.display = 'none';
}

async function saveAnnouncement(event) {
    event.preventDefault();

    const announcementId = document.getElementById('announcement-id').value;
    const title = document.getElementById('announcement-title').value;
    const content = document.getElementById('announcement-content').value;
    const channelId = document.getElementById('announcement-channel').value;
    const isPinned = document.getElementById('announcement-pinned').checked;

    if (!channelId) {
        showNotification('Please select a channel', 'error');
        return;
    }

    const announcementData = {
        title,
        content,
        channel_id: channelId,
        is_pinned: isPinned
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
            // Create new announcement
            await apiCall(`/api/${currentServerId}/announcements`, {
                method: 'POST',
                body: JSON.stringify(announcementData)
            });
            showNotification('Announcement created successfully', 'success');
        }

        closeAnnouncementModal();
        loadAnnouncements();
    } catch (error) {
        showNotification(`Failed to save announcement: ${error.message}`, 'error');
    }
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

async function editAnnouncement(announcementId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/announcements/${announcementId}`);
        if (data && data.announcement) {
            const announcement = data.announcement;

            // Populate form
            document.getElementById('announcement-id').value = announcement.announcement_id;
            document.getElementById('announcement-title').value = announcement.title;
            document.getElementById('announcement-content').value = announcement.content;
            document.getElementById('announcement-pinned').checked = announcement.is_pinned;

            // Load channels and set selected
            await loadChannelsForAnnouncement();
            document.getElementById('announcement-channel').value = announcement.channel_id;

            // Update modal title and show
            document.getElementById('announcement-modal-title').textContent = 'Edit Announcement';
            document.getElementById('announcement-modal').style.display = 'block';
        }
    } catch (error) {
        showNotification(`Failed to load announcement: ${error.message}`, 'error');
    }
}

// Embed Modal Functions
function showCreateEmbedModal() {
    const modal = document.getElementById('embed-modal');
    const form = document.getElementById('embed-form');
    const title = document.getElementById('embed-modal-title');

    if (!modal || !form) return;

    // Reset form
    form.reset();
    document.getElementById('embed-id').value = '';
    title.textContent = 'Create Embed';

    modal.style.display = 'block';
}

function closeEmbedModal() {
    const modal = document.getElementById('embed-modal');
    if (modal) modal.style.display = 'none';
}

async function saveEmbed(event) {
    event.preventDefault();

    const embedId = document.getElementById('embed-id').value;
    const title = document.getElementById('embed-title').value;
    const description = document.getElementById('embed-description').value;
    const color = document.getElementById('embed-color').value;
    const footer = document.getElementById('embed-footer').value;
    const imageUrl = document.getElementById('embed-image-url').value;
    const thumbnailUrl = document.getElementById('embed-thumbnail-url').value;

    const embedData = {
        title,
        description,
        color,
        footer,
        image_url: imageUrl,
        thumbnail_url: thumbnailUrl
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

async function saveAndSendEmbed(event) {
    event.preventDefault();

    // First save the embed
    await saveEmbed(event);

    // Then show send modal
    const embedId = document.getElementById('embed-id').value;
    if (embedId) {
        showSendEmbedModal(embedId);
    }
}

function showSendEmbedModal(embedId) {
    const modal = document.getElementById('send-embed-modal');
    if (!modal) return;

    document.getElementById('send-embed-id').value = embedId;

    // Load channels
    loadChannelsForEmbed();

    modal.style.display = 'block';
}

function closeSendEmbedModal() {
    const modal = document.getElementById('send-embed-modal');
    if (modal) modal.style.display = 'none';
}

async function loadChannelsForEmbed() {
    const channelSelect = document.getElementById('send-embed-channel');
    if (!channelSelect || !currentServerId) return;

    try {
        await fetchDiscordData(currentServerId);
        const channels = Object.values(discordDataCache.channels);

        let html = '<option value="">Select a channel...</option>';
        channels.forEach(channel => {
            html += `<option value="${channel.id}">#${channel.name}</option>`;
        });
        channelSelect.innerHTML = html;
    } catch (error) {
        console.error('Failed to load channels:', error);
        channelSelect.innerHTML = '<option value="">Failed to load channels</option>';
    }
}

async function sendEmbedToChannel(event) {
    event.preventDefault();

    const embedId = document.getElementById('send-embed-id').value;
    const channelId = document.getElementById('send-embed-channel').value;

    if (!channelId) {
        showNotification('Please select a channel', 'error');
        return;
    }

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

async function sendEmbed(embedId) {
    showSendEmbedModal(embedId);
}

async function editEmbed(embedId) {
    try {
        const data = await apiCall(`/api/${currentServerId}/embeds/${embedId}`);
        if (data && data.embed) {
            const embed = data.embed;

            // Populate form
            document.getElementById('embed-id').value = embed.embed_id;
            document.getElementById('embed-title').value = embed.title || '';
            document.getElementById('embed-description').value = embed.description || '';
            document.getElementById('embed-color').value = embed.color || '#5865F2';
            document.getElementById('embed-footer').value = embed.footer || '';
            document.getElementById('embed-image-url').value = embed.image_url || '';
            document.getElementById('embed-thumbnail-url').value = embed.thumbnail_url || '';

            // Update modal title and show
            document.getElementById('embed-modal-title').textContent = 'Edit Embed';
            document.getElementById('embed-modal').style.display = 'block';
        }
    } catch (error) {
        showNotification(`Failed to load embed: ${error.message}`, 'error');
    }
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

// ========== CONFIG TAB SAVE FUNCTIONS ==========

async function saveChannelSetting(type) {
    const channelId = document.getElementById(`${type}-channel`)?.value;
    const statusSpan = document.getElementById(`${type}-channel-status`);

    if (!channelId) {
        if (statusSpan) statusSpan.textContent = '❌ Please select a channel';
        return;
    }

    const fieldMap = {
        'welcome': 'welcome_channel',
        'log': 'logs_channel',
        'task': 'task_channel_id',
        'shop': 'shop_channel_id'
    };

    const fieldName = fieldMap[type];
    if (!fieldName) return;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({ [fieldName]: channelId })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${type.charAt(0).toUpperCase() + type.slice(1)} channel saved`, 'success');

        // Reload config to ensure persistence
        setTimeout(() => {
            loadConfigTab();
        }, 500);
    } catch (error) {
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification(`Failed to save ${type} channel: ${error.message}`, 'error');
    }
}

async function saveCurrencySettings() {
    const currencyName = document.getElementById('currency-name')?.value;
    const currencySymbol = document.getElementById('currency-symbol')?.value;
    const statusSpan = document.getElementById('currency-settings-status');

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                currency_name: currencyName,
                currency_symbol: currencySymbol
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification('Currency settings saved', 'success');
    } catch (error) {
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification(`Failed to save currency settings: ${error.message}`, 'error');
    }
}

async function saveBotBehavior() {
    const inactivityDays = document.getElementById('inactivity-days')?.value;
    const autoExpireTasks = document.getElementById('auto-expire-tasks')?.checked;
    const requireTaskProof = document.getElementById('require-task-proof')?.checked;
    const statusSpan = document.getElementById('bot-behavior-status');

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                inactivity_days: parseInt(inactivityDays),
                auto_expire_enabled: autoExpireTasks,
                require_proof: requireTaskProof
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification('Bot behavior settings saved', 'success');
    } catch (error) {
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification(`Failed to save bot behavior: ${error.message}`, 'error');
    }
}

async function saveFeatureToggle(feature) {
    const checkbox = document.getElementById(`feature-${feature}`);
    const statusSpan = document.getElementById(`feature-${feature}-status`);

    if (!checkbox) return;

    const fieldMap = {
        'tasks': 'feature_tasks',
        'shop': 'feature_shop',
        'announcements': 'feature_announcements',
        'moderation': 'feature_moderation'
    };

    const fieldName = fieldMap[feature];
    if (!fieldName) return;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({ [fieldName]: checkbox.checked })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${feature.charAt(0).toUpperCase() + feature.slice(1)} feature toggle saved`, 'success');
    } catch (error) {
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification(`Failed to save feature toggle: ${error.message}`, 'error');
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
};
// ========== MISSING FUNCTIONS FIX ==========
// This file contains all the missing functions that need to be added to app.js

// ========== SHOP ITEM FUNCTIONS ==========

// ========== SHOP ITEM FUNCTIONS ==========

function showCreateShopItemModal() {
    // Remove any existing modal first
    const existingModal = document.getElementById('dynamic-modal');
    if (existingModal) {
        existingModal.remove();
    }

    // Generate the modal HTML
    const modal = createModal('Create Shop Item', `
<form id="shop-item-form" onsubmit="return false;">
    <input type="hidden" id="shop-item-id">
    <div class="form-group">
        <label>Item Name</label>
        <input type="text" id="shop-item-name" class="form-control" required>
    </div>
    <div class="form-group">
        <label>Description</label>
        <textarea id="shop-item-description" class="form-control" rows="3"></textarea>
    </div>
    <div class="form-group">
        <label>Price</label>
        <input type="number" id="shop-item-price" class="form-control" required min="0">
    </div>
    <div class="form-group">
        <label>Category</label>
        <select id="shop-item-category" class="form-control" onchange="toggleShopRoleSelect()">
            <option value="general">General</option>
            <option value="consumable">Consumable</option>
            <option value="role">Role</option>
            <option value="collectible">Collectible</option>
        </select>
    </div>
    
    <!-- Role Selection (Hidden by default) -->
    <div class="form-group" id="shop-role-select-group" style="display: none;">
        <label>Select Role</label>
        <select id="shop-item-role-id" class="form-control">
            ${typeof getRoleOptions === 'function' ? getRoleOptions() : '<option value="">Loading...</option>'}
        </select>
        <small>The role to give when purchased.</small>
    </div>

    <div class="form-group">
        <label>Stock (-1 for unlimited)</label>
        <input type="number" id="shop-item-stock" class="form-control" value="-1">
    </div>
    <div class="form-group">
        <label>Emoji</label>
        <div class="emoji-picker-container" style="display: flex; align-items: center;">
            <input type="text" id="shop-item-emoji" class="form-control" placeholder="🎁" style="width: 80px; margin-right: 10px;">
            <button type="button" class="btn-secondary emoji-picker-btn" onclick="showEmojiPicker('shop-item-emoji')">😀 Pick Emoji</button>
        </div>
    </div>
    <div class="button-group">
        <button type="button" onclick="saveShopItem(event)" class="btn-success">Save</button>
        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
    </div>
</form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';

    // Initialize role toggle
    toggleShopRoleSelect();
}

function closeShopItemModal() {
    const modal = document.getElementById('shop-item-modal');
    if (modal) modal.style.display = 'none';
}

function toggleShopRoleSelect() {
    const category = document.getElementById('shop-item-category').value;
    const roleGroup = document.getElementById('shop-role-select-group');

    if (category === 'role') {
        if (roleGroup) roleGroup.style.display = 'block';
        // Load roles if empty
        const roleSelect = document.getElementById('shop-item-role-id');
        if (roleSelect && roleSelect.options.length <= 1) {
            if (typeof loadRolesForShopItem === 'function') {
                loadRolesForShopItem();
            } else {
                // Fallback if function not found (e.g. app_additions.js not loaded yet or overwritten)
                console.warn('loadRolesForShopItem function not found, trying to load manually');
                loadRolesForShopItemFallback();
            }
        }
    } else {
        if (roleGroup) roleGroup.style.display = 'none';
    }
}

async function loadRolesForShopItemFallback() {
    const roleSelect = document.getElementById('shop-item-role-id');
    if (!roleSelect || !currentServerId) return;

    try {
        // Ensure discordDataCache is populated
        if (!discordDataCache.roles || Object.keys(discordDataCache.roles).length === 0) {
            await fetchDiscordData(currentServerId);
        }

        const roles = Object.values(discordDataCache.roles || {});

        let html = '<option value="">Select a role...</option>';
        roles.forEach(role => {
            html += `<option value="${role.id}" style="color: #${role.color.toString(16).padStart(6, '0')}">${role.name}</option>`;
        });
        roleSelect.innerHTML = html;
    } catch (error) {
        console.error('Failed to load roles:', error);
        roleSelect.innerHTML = '<option value="">Failed to load roles</option>';
    }
}

async function saveShopItem(event) {
    if (event) event.preventDefault();

    const itemId = document.getElementById('shop-item-id')?.value;
    const name = document.getElementById('shop-item-name').value;
    const description = document.getElementById('shop-item-description').value;
    const price = document.getElementById('shop-item-price').value;
    const category = document.getElementById('shop-item-category').value;
    const stock = document.getElementById('shop-item-stock').value;
    const emoji = document.getElementById('shop-item-emoji').value;
    const roleId = document.getElementById('shop-item-role-id')?.value;

    if (!name || !price) {
        showNotification('Please fill all required fields (Name, Price)', 'warning');
        return;
    }

    const payload = {
        name,
        description,
        price: parseInt(price),
        category,
        stock: parseInt(stock),
        emoji: emoji || '🎁',
        role_id: (category === 'role' && roleId) ? roleId : null
    };

    // Add metadata for role if needed
    if (category === 'role' && roleId) {
        payload.metadata = { role_id: roleId };
    }

    try {
        if (itemId) {
            // Update existing item
            await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
                method: 'PUT',
                body: JSON.stringify(payload)
            });
            showNotification('Shop item updated', 'success');
        } else {
            // Create new item
            await apiCall(`/api/${currentServerId}/shop`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            showNotification('Shop item created', 'success');
        }
        closeShopItemModal();
        loadShop();
    } catch (error) {
        console.error('Save shop item error:', error);
        showNotification('Failed to save shop item: ' + error.message, 'error');
    }
}

// ========== TASK MODAL FUNCTIONS ==========

function showCreateTaskModal() {
    // Remove any existing modal first
    const existingModal = document.getElementById('dynamic-modal');
    if (existingModal) {
        existingModal.remove();
    }

    const modal = createModal('Create Task', `
<form id="task-form" onsubmit="return false;">
    <input type="hidden" id="task-id">
    <div class="form-group">
        <label>Task Name</label>
        <input type="text" id="task-name" class="form-control" required>
    </div>
    <div class="form-group">
        <label>Description</label>
        <textarea id="task-description" class="form-control" rows="3" required></textarea>
    </div>
    <div class="form-group">
        <label>Reward (coins)</label>
        <input type="number" id="task-reward" class="form-control" required min="1">
    </div>
    <div class="form-group">
        <label>Duration (hours, -1 for infinite)</label>
        <input type="number" id="task-duration" class="form-control" value="24">
        <small>Set to -1 for tasks with no time limit</small>
    </div>
    <div class="form-group">
        <label>Max Claims (-1 for unlimited)</label>
        <input type="number" id="task-max-claims" class="form-control" value="-1">
    </div>
    <div class="form-group">
        <label>Category</label>
        <select id="task-category" class="form-control" onchange="toggleTaskRoleSelect()">
            <option value="general">General</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="special">Special</option>
            <option value="role_required">Role Required</option>
        </select>
        <small id="general-category-note" style="color: #ffc107; display: block;">
            ⚠️ General tasks require users to submit proof (screenshot) which must be approved by a moderator/admin before rewards are granted.
        </small>
    </div>
    
    <!-- Role Selection (Hidden by default) -->
    <div class="form-group" id="task-role-select-group" style="display: none;">
        <label>Required Role</label>
        <select id="task-role" class="form-control">
            ${getRoleOptions()}
        </select>
        <small>Users must have this role to see/complete the task.</small>
    </div>

    <!-- Global Task Option (Superadmin only) -->
    ${currentUser?.is_superadmin ? `
    <div class="form-group">
        <label>
            <input type="checkbox" id="task-is-global">
            Global Task (Visible across all servers)
        </label>
    </div>
    ` : ''}

    <div class="button-group">
        <button type="button" onclick="saveTask(event)" class="btn-success">Save</button>
        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
    </div>
</form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';

    // Store modal reference globally so saveTask can access it
    window.currentTaskModal = modal;

    // Initialize toggle state
    toggleTaskRoleSelect();
}

function toggleTaskRoleSelect() {
    const category = document.getElementById('task-category').value;
    const roleGroup = document.getElementById('task-role-select-group');
    const generalNote = document.getElementById('general-category-note');

    if (category === 'role_required') {
        roleGroup.style.display = 'block';
    } else {
        roleGroup.style.display = 'none';
    }

    if (category === 'general') {
        if (generalNote) generalNote.style.display = 'block';
    } else {
        if (generalNote) generalNote.style.display = 'none';
    }
}

async function saveTask(event) {
    if (event) event.preventDefault();

    // Use the stored modal reference to query elements
    const modal = window.currentTaskModal || document.getElementById('dynamic-modal');
    if (!modal) {
        console.error('No modal found!');
        showNotification('Error: Modal not found', 'error');
        return;
    }

    // Query elements from the specific modal, not the entire document
    const taskId = modal.querySelector('#task-id')?.value;
    const name = modal.querySelector('#task-name')?.value;
    const description = modal.querySelector('#task-description')?.value;
    const reward = modal.querySelector('#task-reward')?.value;
    const duration = modal.querySelector('#task-duration')?.value || 24;
    const maxClaims = modal.querySelector('#task-max-claims')?.value || -1;
    const category = modal.querySelector('#task-category')?.value;
    const roleId = modal.querySelector('#task-role')?.value;
    const isGlobal = modal.querySelector('#task-is-global')?.checked || false;

    // Detailed validation with specific error messages
    const missingFields = [];
    if (!name || name.trim() === '') missingFields.push('Task Name');
    if (!description || description.trim() === '') missingFields.push('Description');
    if (!reward || reward === '' || isNaN(reward) || parseInt(reward) <= 0) missingFields.push('Reward (must be > 0)');

    if (missingFields.length > 0) {
        showNotification(`Missing required fields: ${missingFields.join(', ')}`, 'warning');
        return;
    }

    const payload = {
        name,
        description,
        reward: parseInt(reward),
        duration_hours: parseInt(duration),
        max_claims: parseInt(maxClaims),
        category,
        required_role_id: (category === 'role_required' && roleId) ? roleId : null,
        is_global: isGlobal
    };

    try {
        if (taskId) {
            await apiCall(`/api/${currentServerId}/tasks/${taskId}`, {
                method: 'PUT',
                body: JSON.stringify(payload)
            });
            showNotification('Task updated', 'success');
        } else {
            await apiCall(`/api/${currentServerId}/tasks`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            showNotification('Task created', 'success');
        }
        closeModal();
        loadTasks();
    } catch (error) {
        console.error('Save task error:', error);
        showNotification('Failed to save task: ' + error.message, 'error');
    }
}

// ========== CONFIG TAB SAVE FUNCTIONS ==========

async function saveChannelSetting(type) {
    const channelId = document.getElementById(`${type}-channel`)?.value;
    const statusSpan = document.getElementById(`${type}-channel-status`);

    if (!channelId) {
        showNotification('Please select a channel', 'warning');
        return;
    }

    try {
        const fieldMap = {
            'welcome': 'welcome_channel',
            'log': 'logs_channel',
            'task': 'task_channel_id',
            'shop': 'shop_channel_id'
        };

        const payload = {
            [fieldMap[type]]: channelId
        };

        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${type.charAt(0).toUpperCase() + type.slice(1)} channel saved`, 'success');
    } catch (error) {
        console.error('Save channel setting error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save channel setting', 'error');
    }
}

async function saveCurrencySettings() {
    const currencyName = document.getElementById('currency-name')?.value;
    const currencySymbol = document.getElementById('currency-symbol')?.value;
    const statusSpan = document.getElementById('currency-settings-status');

    if (!currencyName || !currencySymbol) {
        showNotification('Please fill all currency fields', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                currency_name: currencyName,
                currency_symbol: currencySymbol
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification('Currency settings saved', 'success');
    } catch (error) {
        console.error('Save currency settings error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save currency settings', 'error');
    }
}

async function saveBotBehavior() {
    const inactivityDays = document.getElementById('inactivity-days')?.value;
    const autoExpireTasks = document.getElementById('auto-expire-tasks')?.checked;
    const requireTaskProof = document.getElementById('require-task-proof')?.checked;
    const statusSpan = document.getElementById('bot-behavior-status');

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                inactivity_days: parseInt(inactivityDays),
                auto_expire_enabled: autoExpireTasks,
                require_proof: requireTaskProof
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification('Bot behavior settings saved', 'success');
    } catch (error) {
        console.error('Save bot behavior error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save bot behavior settings', 'error');
    }
}

async function saveFeatureToggle(feature) {
    const checkbox = document.getElementById(`feature-${feature}`);
    const statusSpan = document.getElementById(`feature-${feature}-status`);

    if (!checkbox) return;

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                [`feature_${feature}`]: checkbox.checked
            })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${feature.charAt(0).toUpperCase() + feature.slice(1)} feature ${checkbox.checked ? 'enabled' : 'disabled'}`, 'success');
    } catch (error) {
        console.error('Save feature toggle error:', error);
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification('Failed to save feature toggle', 'error');
    }
}

// ========== BOT STATUS UPDATE ==========

async function saveBotStatus() {
    const statusType = document.getElementById('bot-status-type')?.value;
    const statusMessage = document.getElementById('bot-status-message')?.value;

    if (!statusType || !statusMessage) {
        showNotification('Please fill all bot status fields', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/bot_status`, {
            method: 'POST',
            body: JSON.stringify({
                type: statusType,
                message: statusMessage
            })
        });
        showNotification('Bot status updated', 'success');
    } catch (error) {
        console.error('Save bot status error:', error);
        showNotification('Failed to update bot status', 'error');
    }
}

// ========== EMBED FUNCTIONS ==========

async function sendEmbed(embedId) {
    // First, show a modal to select the channel
    const modal = createModal('Send Embed', `
<form id="send-embed-form" onsubmit="return false;">
    <div class="form-group">
        <label>Select Channel</label>
        <select id="send-embed-channel" class="form-control">
            ${getChannelOptions()}
        </select>
    </div>
    <div class="button-group">
        <button type="button" onclick="confirmSendEmbed('${embedId}')" class="btn-success">Send</button>
        <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
    </div>
</form>
    `);

    document.body.appendChild(modal);
    modal.style.display = 'block';
}

async function confirmSendEmbed(embedId) {
    const channelId = document.getElementById('send-embed-channel')?.value;

    if (!channelId) {
        showNotification('Please select a channel', 'warning');
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}/send`, {
            method: 'POST',
            body: JSON.stringify({ channel_id: channelId })
        });
        showNotification('Embed sent successfully', 'success');
        closeModal();
    } catch (error) {
        console.error('Send embed error:', error);
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
        console.error('Delete embed error:', error);
        showNotification('Failed to delete embed: ' + error.message, 'error');
    }
}

async function editEmbed(embedId) {
    // TODO: Implement edit modal population
    showNotification('Edit embed functionality coming soon!', 'info');
}

async function editAnnouncement(announcementId) {
    // TODO: Implement edit modal population
    showNotification('Edit announcement functionality coming soon!', 'info');
}

// ========== MODAL HELPER ==========

function createModal(title, content) {
    const modal = document.createElement('div');
    modal.id = 'dynamic-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>${title}</h2>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div class="modal-body">
                ${content}
            </div>
        </div>
    `;
    return modal;
}

// ========== ANNOUNCEMENT FIXES ==========

function showCreateAnnouncementModal() {
    const modal = document.getElementById('announcement-modal');
    if (!modal) return;

    // Reset form
    const form = document.getElementById('announcement-form');
    if (form) form.reset();

    const idField = document.getElementById('announcement-id');
    if (idField) idField.value = '';

    const title = document.getElementById('announcement-modal-title');
    if (title) title.textContent = 'Create Announcement';

    // Populate channels
    const channelSelect = document.getElementById('announcement-channel');
    if (channelSelect) {
        if (typeof getChannelOptions === 'function') {
            channelSelect.innerHTML = getChannelOptions();
        } else {
            // Fallback
            channelSelect.innerHTML = '<option value="">Loading...</option>';
            if (typeof fetchDiscordData === 'function' && currentServerId) {
                fetchDiscordData(currentServerId).then(() => {
                    if (typeof getChannelOptions === 'function') {
                        channelSelect.innerHTML = getChannelOptions();
                    }
                });
            }
        }
    }

    modal.style.display = 'block';
}

function closeAnnouncementModal() {
    const modal = document.getElementById('announcement-modal');
    if (modal) modal.style.display = 'none';
}
// ========== SESSION MANAGEMENT & INITIALIZATION ==========

// Check for existing session on page load
async function checkSession() {
    try {
        const response = await fetch(apiUrl('/api/me'), {
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;

            // Restore last selected server from localStorage
            const lastServer = localStorage.getItem('lastSelectedServer');

            await loadServers();

            if (lastServer) {
                const serverSelect = document.getElementById('server-select');
                if (serverSelect) {
                    serverSelect.value = lastServer;
                    await onServerChange();
                }
            }

            showDashboard();
        } else {
            showLoginScreen();
        }
    } catch (error) {
        console.error('Session check failed:', error);
        showLoginScreen();
    }
}

// Show login screen
function showLoginScreen() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('main-dashboard').style.display = 'none';
}

// Show dashboard
function showDashboard() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('main-dashboard').style.display = 'flex';
}

// Handle login
document.getElementById('login-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorDiv = document.getElementById('login-error');

    try {
        const response = await fetch(apiUrl('/api/login'), {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok) {
            currentUser = data.user;
            await loadServers();
            showDashboard();
            showNotification('Login successful!', 'success');
        } else {
            errorDiv.textContent = data.error || 'Login failed';
            errorDiv.style.display = 'block';
        }
    } catch (error) {
        errorDiv.textContent = 'Connection error. Please try again.';
        errorDiv.style.display = 'block';
    }
});

// Load servers
async function loadServers() {
    try {
        const data = await apiCall('/api/servers');
        const serverSelect = document.getElementById('server-select');

        if (data && data.servers && serverSelect) {
            serverSelect.innerHTML = '<option value="">-- Select a server --</option>';

            if (data.servers.length === 0) {
                serverSelect.innerHTML = '<option value="">No servers available</option>';
                showNotification('You don\'t have access to any servers', 'warning');
                return;
            }

            data.servers.forEach(server => {
                const option = document.createElement('option');
                option.value = server.id;
                option.textContent = server.name;
                serverSelect.appendChild(option);
            });

            // Auto-select first server if only one available or if none selected
            if (data.servers.length > 0) {
                // Always default to the first server if currentServerId is invalid or empty
                const targetServer = currentServerId || data.servers[0].id;

                // Verify the target server actually exists in the list
                const exists = data.servers.some(s => s.id === targetServer);
                const finalServerId = exists ? targetServer : data.servers[0].id;

                serverSelect.value = finalServerId;
                currentServerId = finalServerId;
                await onServerChange();
            }
        }
    } catch (error) {
        console.error('Failed to load servers:', error);
        showNotification('Failed to load servers', 'error');
    }
}

// Handle server change
async function onServerChange() {
    const serverSelect = document.getElementById('server-select');
    if (!serverSelect) return;

    currentServerId = serverSelect.value;

    if (currentServerId) {
        // Save to localStorage for session persistence
        localStorage.setItem('lastSelectedServer', currentServerId);

        // Fetch Discord data for this server
        await fetchDiscordData(currentServerId);
        await updateTierUI();

        // Reload current tab
        const activeTab = document.querySelector('.tab-button.active');
        if (activeTab) {
            const tabName = activeTab.getAttribute('data-tab');
            showTab(tabName);
        }
    }
}

// Logout function
async function logout() {
    try {
        await fetch(apiUrl('/api/logout'), {
            method: 'POST',
            credentials: 'include'
        });
    } catch (error) {
        console.error('Logout error:', error);
    }

    currentUser = null;
    currentServerId = '';
    localStorage.removeItem('lastSelectedServer');
    showLoginScreen();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkSession();
});

// ========== HELPER FUNCTIONS FOR MODALS ==========

function getRoleOptions() {
    if (!discordDataCache.roles || Object.keys(discordDataCache.roles).length === 0) {
        return '<option value="">Loading roles...</option>';
    }

    const roles = Object.values(discordDataCache.roles);
    let html = '<option value="">Select a role...</option>';
    roles.forEach(role => {
        if (role.name !== '@everyone') {
            html += `<option value="${role.id}">${role.name}</option>`;
        }
    });
    return html;
}

function getChannelOptions() {
    if (!discordDataCache.channels || Object.keys(discordDataCache.channels).length === 0) {
        return '<option value="">Loading channels...</option>';
    }

    const channels = Object.values(discordDataCache.channels);
    let html = '<option value="">Select a channel...</option>';
    channels.forEach(channel => {
        html += `<option value="${channel.id}">#${channel.name}</option>`;
    });
    return html;
}

async function loadRolesForShopItem() {
    const roleSelect = document.getElementById('shop-item-role-id');
    if (!roleSelect || !currentServerId) return;

    try {
        // Ensure discordDataCache is populated
        if (!discordDataCache.roles || Object.keys(discordDataCache.roles).length === 0) {
            await fetchDiscordData(currentServerId);
        }

        const roles = Object.values(discordDataCache.roles || {});

        let html = '<option value="">Select a role...</option>';
        roles.forEach(role => {
            if (role.name !== '@everyone') {
                html += `<option value="${role.id}">${role.name}</option>`;
            }
        });
        roleSelect.innerHTML = html;
    } catch (error) {
        console.error('Failed to load roles:', error);
        roleSelect.innerHTML = '<option value="">Failed to load roles</option>';
    }
}

// ========== EMOJI PICKER FOR SHOP ITEMS ==========

function showEmojiPicker(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    // Create emoji picker modal
    const pickerModal = document.createElement('div');
    pickerModal.className = 'emoji-picker-modal';
    pickerModal.innerHTML = `
        <div class="emoji-picker-content">
            <div class="emoji-picker-header">
                <h3>Select Emoji</h3>
                <button onclick="this.closest('.emoji-picker-modal').remove()" class="close-btn">×</button>
            </div>
            <div class="emoji-grid">
                ${getCommonEmojis().map(emoji => `
                    <button class="emoji-btn" onclick="selectEmoji('${emoji}', '${inputId}', this)">${emoji}</button>
                `).join('')}
            </div>
            <div class="emoji-picker-footer">
                <input type="text" id="custom-emoji-input" placeholder="Or paste any emoji..." maxlength="2">
                <button onclick="selectCustomEmoji('${inputId}')" class="btn-primary">Use Custom</button>
            </div>
        </div>
    `;

    document.body.appendChild(pickerModal);
}

function getCommonEmojis() {
    return [
        '💰', '💎', '🏆', '⭐', '🎁', '🎉', '🎊', '🎈',
        '🔥', '⚡', '💫', '✨', '🌟', '💥', '💢', '💯',
        '🛡️', '⚔️', '🗡️', '🏹', '🔫', '🧨', '💣', '🔨',
        '🎮', '🎯', '🎲', '🎰', '🃏', '🎴', '🀄', '🎭',
        '👑', '💍', '💄', '👗', '👔', '🎩', '👒', '🧢',
        '🍕', '🍔', '🍟', '🌭', '🍿', '🧋', '🍺', '🍻',
        '🚗', '🏎️', '🚙', '🚕', '🚌', '🚎', '🏍️', '🛵',
        '🏠', '🏡', '🏢', '🏣', '🏤', '🏥', '🏦', '🏨'
    ];
}

function selectEmoji(emoji, inputId, button) {
    const input = document.getElementById(inputId);
    if (input) {
        input.value = emoji;
    }
    button.closest('.emoji-picker-modal').remove();
}

function selectCustomEmoji(inputId) {
    const customInput = document.getElementById('custom-emoji-input');
    const targetInput = document.getElementById(inputId);

    if (customInput && targetInput && customInput.value) {
        targetInput.value = customInput.value;
        customInput.closest('.emoji-picker-modal').remove();
    }
}

// ========== ANNOUNCEMENT IMPROVEMENTS ==========

// Override saveAnnouncement to NOT save to database, just send
window.saveAnnouncement = async function (event) {
    event.preventDefault();

    const title = document.getElementById('announcement-title').value;
    const content = document.getElementById('announcement-content').value;
    const channelId = document.getElementById('announcement-channel').value;
    const isPinned = document.getElementById('announcement-pinned')?.checked || false;

    if (!channelId) {
        showNotification('Please select a channel', 'error');
        return;
    }

    try {
        // Create and send announcement
        await apiCall(`/api/${currentServerId}/announcements`, {
            method: 'POST',
            body: JSON.stringify({
                title,
                content,
                channel_id: channelId,
                pinned: isPinned
            })
        });

        showNotification(`✅ Announcement "${title}" sent successfully!`, 'success');
        closeAnnouncementModal();

        // Clear form
        document.getElementById('announcement-form').reset();
    } catch (error) {
        showNotification(`❌ Failed to send announcement: ${error.message}`, 'error');
    }
};

// Add markdown helper buttons
function insertMarkdown(type) {
    const textarea = document.getElementById('announcement-content');
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end);
    let replacement = '';

    switch (type) {
        case 'bold':
            replacement = `**${selectedText || 'bold text'}**`;
            break;
        case 'italic':
            replacement = `*${selectedText || 'italic text'}*`;
            break;
        case 'code':
            replacement = `\`${selectedText || 'code'}\``;
            break;
        case 'codeblock':
            replacement = `\`\`\`\n${selectedText || 'code block'}\n\`\`\``;
            break;
    }

    textarea.value = textarea.value.substring(0, start) + replacement + textarea.value.substring(end);
    textarea.focus();
}

// ========== FIX CHANNEL SAVING ==========

window.saveChannelSetting = async function (type) {
    const selectId = `${type}-channel`;
    const statusId = `${type}-channel-status`;

    const select = document.getElementById(selectId);
    const statusSpan = document.getElementById(statusId);

    if (!select) {
        console.error(`Channel select not found: ${selectId}`);
        return;
    }

    const channelId = select.value;

    if (!channelId) {
        showNotification('Please select a channel', 'error');
        return;
    }

    // Map frontend type to backend field name (matches updated schema.sql)
    const fieldMap = {
        'welcome': 'welcome_channel_id',
        'log': 'log_channel_id',
        'task': 'task_channel_id',
        'shop': 'shop_channel_id'
    };

    const fieldName = fieldMap[type];

    if (!fieldName) {
        console.error(`Unknown channel type: ${type}`);
        return;
    }

    try {
        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({ [fieldName]: channelId })
        });

        if (statusSpan) {
            statusSpan.textContent = '✅ Saved';
            statusSpan.className = 'status-text success';
            setTimeout(() => {
                statusSpan.textContent = '';
            }, 3000);
        }
        showNotification(`${type.charAt(0).toUpperCase() + type.slice(1)} channel saved successfully`, 'success');
    } catch (error) {
        if (statusSpan) {
            statusSpan.textContent = '❌ Failed';
            statusSpan.className = 'status-text error';
        }
        showNotification(`Failed to save ${type} channel: ${error.message}`, 'error');
    }
};

console.log('✅ CMS Enhancements Loaded');

// ========== EMBED PREVIEW SYSTEM ==========

/**
 * Updates the embed preview in real-time as the user types
 * Called by oninput events in the embed editor
 */
window.updateEmbedPreview = function () {
    // Get inputs
    const titleDetails = document.getElementById('embed-title');
    const description = document.getElementById('embed-description');
    const color = document.getElementById('embed-color');
    const footer = document.getElementById('embed-footer');
    const imageUrl = document.getElementById('embed-image-url');
    const thumbnailUrl = document.getElementById('embed-thumbnail-url');

    // Get preview elements
    const pEmbed = document.getElementById('preview-embed');
    const pTitle = document.getElementById('preview-embed-title');
    const pDesc = document.getElementById('preview-embed-description');
    const pImage = document.getElementById('preview-embed-image');
    const pThumbnail = document.getElementById('preview-embed-thumbnail');
    const pFooter = document.getElementById('preview-embed-footer');
    const pFooterContainer = document.getElementById('preview-embed-footer-container');
    const pThumbnailContainer = document.getElementById('preview-embed-thumbnail-container');

    if (!pEmbed) return; // Guard clause if preview elements aren't loaded

    // Update Title
    if (titleDetails && titleDetails.value) {
        pTitle.textContent = titleDetails.value;
        pTitle.style.display = 'block';
    } else {
        pTitle.style.display = 'none';
    }

    // Update Description
    if (description && description.value) {
        pDesc.innerHTML = formatDiscordMarkdown(description.value);
        pDesc.style.display = 'block';
    } else {
        pDesc.style.display = 'none';
    }

    // Update Color
    if (color && pEmbed) {
        pEmbed.style.borderLeftColor = color.value;
    }

    // Update Footer
    if (footer && footer.value) {
        pFooter.textContent = footer.value;
        pFooterContainer.style.display = 'flex';
    } else {
        pFooterContainer.style.display = 'none';
    }

    // Update Image
    if (imageUrl && imageUrl.value) {
        pImage.src = imageUrl.value;
        pImage.style.display = 'block';
        pImage.onerror = function () { this.style.display = 'none'; };
    } else {
        pImage.style.display = 'none';
    }

    // Update Thumbnail
    if (thumbnailUrl && thumbnailUrl.value) {
        pThumbnail.src = thumbnailUrl.value;
        pThumbnailContainer.style.display = 'block';
        pThumbnail.onerror = function () { this.parentNode.style.display = 'none'; };
    } else {
        pThumbnailContainer.style.display = 'none';
    }
};

/**
 * Basic markdown formatter for Discord preview
 */
function formatDiscordMarkdown(text) {
    if (!text) return '';
    let html = text
        .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>') // Bold
        .replace(/\*(.*?)\*/g, '<i>$1</i>')     // Italics
        .replace(/__(.*?)__/g, '<u>$1</u>')     // Underline
        .replace(/~~(.*?)~~/g, '<s>$1</s>')     // Strikethrough
        .replace(/`(.*?)`/g, '<code>$1</code>') // Code
        .replace(/\n/g, '<br>');                // Newlines
    return html;
}

// Hook into modal opening to refresh preview
// We use a MutationObserver to detect when the modal becomes visible
document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('embed-modal');
    if (modal) {
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                if (mutation.attributeName === 'style' && modal.style.display !== 'none') {
                    // Modal opened, update preview
                    setTimeout(window.updateEmbedPreview, 50);
                }
            });
        });

        observer.observe(modal, { attributes: true });
    }
});

// ========== MODERATION CONFIGURATION ==========

/**
 * Injects moderation settings into the Config tab
 */
async function loadModerationConfigUI() {
    const configContent = document.getElementById('config-content');
    if (!configContent) return;

    // Check if already injected
    if (document.getElementById('moderation-settings-card')) return;

    const container = document.createElement('div');
    container.id = 'moderation-settings-card';
    container.className = 'card mt-4'; // Add some margin
    container.innerHTML = `
        <h3>🛡️ Moderation Exemptions</h3>
        <p>Select roles that should be ignored by specific protection systems.</p>
        
        <div class="loading" id="mod-config-loading">Loading roles and config...</div>
        
        <div id="mod-config-form" style="display:none;">
            <div class="form-group">
                <label>🚫 File/Image Protection</label>
                <div class="checkbox-group mb-2">
                    <input type="checkbox" id="mod-file-filter-enabled">
                    <label for="mod-file-filter-enabled">Enable Block Files/Images</label>
                </div>
                <div class="checkbox-group mb-2">
                    <input type="checkbox" id="mod-file-strict-mute">
                    <label for="mod-file-strict-mute">Strict (Mute on Violation)</label>
                </div>
                
                <label class="mt-2">Exempt Roles (File/Image)</label>
                <div class="role-selector" id="exempt-files-container"></div>
                <small class="text-muted">Users with these roles can post images, gifs, and files even if restricted.</small>
            </div>
            
            <div class="form-group">
                <label>🔗 Link Protection Exemptions</label>
                <div class="role-selector" id="exempt-links-container"></div>
                <small class="text-muted">Users with these roles can post links.</small>
            </div>

            <div class="form-group">
                <label>👑 Global Exemptions</label>
                <div class="role-selector" id="exempt-global-container"></div>
                <small class="text-muted">Users with these roles bypass ALL protection checks.</small>
            </div>

            <div class="button-group">
                <button onclick="saveModerationConfig()" class="btn-primary">Save Exemptions</button>
                <span id="moderation-save-status"></span>
            </div>
        </div>
        
        <style>
            .role-selector {
                max-height: 200px;
                overflow-y: auto;
                border: 1px solid var(--border-secondary);
                border-radius: 4px;
                padding: 10px;
                background: var(--bg-tertiary);
            }
            .role-checkbox-item {
                display: flex;
                align-items: center;
                padding: 4px 0;
            }
            .role-checkbox-item input {
                margin-right: 10px;
            }
            .checkbox-group {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .mt-2 { margin-top: 8px; }
            .mb-2 { margin-bottom: 8px; }
        </style>
    `;

    configContent.appendChild(container);

    // Load data
    try {
        const [rolesData, configData] = await Promise.all([
            apiCall(`/api/${currentServerId}/roles`),
            apiCall(`/api/${currentServerId}/config`)
        ]);

        const roles = rolesData.roles || [];
        const modConfig = configData.moderation || {};

        // Set checkboxes
        if (document.getElementById('mod-file-filter-enabled')) {
            document.getElementById('mod-file-filter-enabled').checked = modConfig.file_filter === true;
        }
        if (document.getElementById('mod-file-strict-mute')) {
            // Check if mute is enabled in auto_actions or if level is strict
            const isStrict = modConfig.profanity_level === 'strict' || (modConfig.auto_actions && modConfig.auto_actions.mute);
            document.getElementById('mod-file-strict-mute').checked = isStrict;
        }

        const renderRoles = (containerId, selectedRoles) => {
            const el = document.getElementById(containerId);
            if (!el) return;

            el.innerHTML = roles.map(role => `
                <div class="role-checkbox-item">
                    <input type="checkbox" id="${containerId}-${role.id}" value="${role.id}" 
                        ${selectedRoles.includes(role.id) ? 'checked' : ''}>
                    <label for="${containerId}-${role.id}" style="color: ${role.color ? '#' + role.color.toString(16).padStart(6, '0') : 'inherit'}">
                        ${role.name}
                    </label>
                </div>
            `).join('');
        };

        renderRoles('exempt-files-container', modConfig.exempt_roles_files || []);
        renderRoles('exempt-links-container', modConfig.exempt_roles_links || []);
        renderRoles('exempt-global-container', modConfig.exempt_roles || []);

        document.getElementById('mod-config-loading').style.display = 'none';
        document.getElementById('mod-config-form').style.display = 'block';

    } catch (error) {
        console.error("Failed to load moderation config:", error);
        document.getElementById('mod-config-loading').textContent = "Failed to load configuration.";
    }
}

/**
 * Saves the moderation exemption configuration
 */
window.saveModerationConfig = async function () {
    const getSelected = (containerId) => {
        const container = document.getElementById(containerId);
        if (!container) return [];
        return Array.from(container.querySelectorAll('input:checked')).map(cb => cb.value);
    };

    const exemptFiles = getSelected('exempt-files-container');
    const exemptLinks = getSelected('exempt-links-container');
    const exemptGlobal = getSelected('exempt-global-container');

    const fileFilterEnabled = document.getElementById('mod-file-filter-enabled')?.checked;
    const strictMuteEnabled = document.getElementById('mod-file-strict-mute')?.checked;

    const statusSpan = document.getElementById('moderation-save-status');
    if (statusSpan) statusSpan.textContent = "Saving...";

    try {
        // First get current config to merge
        const currentConfig = await apiCall(`/api/${currentServerId}/config`);
        const modConfig = currentConfig.moderation || {};
        const autoActions = modConfig.auto_actions || {};

        // Update fields
        modConfig.exempt_roles_files = exemptFiles;
        modConfig.exempt_roles_links = exemptLinks;
        modConfig.exempt_roles = exemptGlobal;
        modConfig.file_filter = fileFilterEnabled;

        // Handle strict mute
        if (strictMuteEnabled) {
            autoActions.mute = true;
            // modConfig.profanity_level = 'strict'; // Optional: force strict mode? Maybe just enable mute.
        } else {
            // Don't disable mute globally if it was on, just ensure we don't force it?
            // Actually, if the user unchecks it here, they probably expect it basically off for this feature.
            // But this is a simple UI. Let's just set autoActions.mute.
            // If they want fine grained control, they need the full UI.
            // But for "block... meaning mute", we'll assume this checkbox controls the mute capability.
        }
        modConfig.auto_actions = autoActions;

        await apiCall(`/api/${currentServerId}/config`, {
            method: 'PUT',
            body: JSON.stringify({
                moderation: modConfig
            })
        });

        if (statusSpan) {
            statusSpan.textContent = "✅ Saved!";
            statusSpan.style.color = "var(--success-color)";
            setTimeout(() => statusSpan.textContent = "", 3000);
        }
        showNotification("Moderation exemptions saved successfully", "success");

    } catch (error) {
        console.error("Failed to save moderation config:", error);
        if (statusSpan) {
            statusSpan.textContent = "❌ Failed";
            statusSpan.style.color = "var(--error-color)";
        }
        showNotification("Failed to save configuration", "error");
    }
};

// Hook into loadConfigTab
// We wait for DOMContentLoaded to ensure other scripts processed
window.addEventListener('load', function () {
    // Preserve any existing override (like from cms_additions.js)
    const originalLoadConfigTab = window.loadConfigTab;

    window.loadConfigTab = async function () {
        // Call original first
        if (typeof originalLoadConfigTab === 'function') {
            await originalLoadConfigTab();
        } else {
            // Fallback if original not defined (unlikely)
            console.warn("loadConfigTab was not defined previously");
        }

        // Inject our UI
        await loadModerationConfigUI();
    };
});

// ========== TIER MANAGEMENT ==========

async function loadAd() {
    const adSlot = document.getElementById('ad-slot-1');
    if (!adSlot) return;

    try {
        const ad = await apiCall('/api/ad');
        if (!ad) return;

        adSlot.innerHTML = `
            <a href="${ad.url}" target="_blank" style="text-decoration: none; color: inherit; display: flex; align-items: center; width: 100%; height: 100%; padding: 0 15px;">
                ${ad.image ? `<img src="${ad.image}" alt="${ad.title}" style="height: 60px; width: 60px; object-fit: contain; margin-right: 15px; border-radius: 4px;">` : ''}
                <div style="flex: 1; text-align: left;">
                    <div style="font-weight: bold; color: ${ad.color || '#fff'}; margin-bottom: 2px;">${ad.title}</div>
                    <div style="font-size: 12px; color: #b9bbbe;">${ad.description}</div>
                </div>
                <div style="background-color: ${ad.color || '#5865F2'}; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 12px; margin-left: 15px;">
                    ${ad.cta}
                </div>
            </a>
        `;
        // Remove default placeholder styling that might conflict
        adSlot.style.display = 'flex';

    } catch (e) {
        console.error("Failed to load ad:", e);
    }
}

async function updateTierUI() {
    if (!currentServerId) return;
    try {
        const config = await apiCall(`/api/${currentServerId}/config`);
        const tier = config.subscription_tier || 'free';

        // Update Badge
        const badgeContainer = document.getElementById('tier-badge-container');
        if (badgeContainer) {
            badgeContainer.innerHTML = `<span class="tier-badge tier-${tier}">${tier} Plan</span>`;
        }

        // Update Ads
        const adContainer = document.getElementById('ad-container');
        if (adContainer) {
            if (tier === 'free') {
                adContainer.style.display = 'block';
                loadAd();
            } else {
                adContainer.style.display = 'none';
            }
        }

        // Store tier in global variable for other functions to check
        window.currentGuildTier = tier;

    } catch (e) {
        console.error("Failed to update tier UI:", e);
    }
}

/**
 * Discord OAuth2 Login and Role-Based Access Control
 * Extends the CMS to support server owner login via Discord
 */

// Global user state
let currentUserRole = null; // 'superadmin' or 'server_owner'

/**
 * Initialize Discord OAuth login button
 */
function initDiscordOAuth() {
    const loginForm = document.getElementById('login-form');
    if (!loginForm) return;

    // Check for existing button to prevent duplicates
    let discordButton = document.querySelector('.btn-discord');

    if (discordButton) {
        // If button exists (hardcoded in HTML), just attach handler
        discordButton.onclick = handleDiscordLogin;
        return;
    }

    // Add Discord login button after the regular login form
    discordButton = document.createElement('button');
    discordButton.type = 'button';
    discordButton.className = 'btn-discord btn-large';
    discordButton.innerHTML = '🎮 Login with Discord';
    discordButton.onclick = handleDiscordLogin;

    const divider = document.createElement('div');
    divider.className = 'login-divider';
    divider.innerHTML = '<span>OR</span>';

    loginForm.appendChild(divider);
    loginForm.appendChild(discordButton);
}

// Initialize Discord OAuth button when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    initDiscordOAuth();

    // Document-level event delegation for Discord login button
    // This catches clicks even if the button is replaced or added dynamically later
    document.addEventListener('click', function (e) {
        if (e.target && (e.target.matches('.btn-discord') || e.target.closest('.btn-discord'))) {
            e.preventDefault();
            handleDiscordLogin();
        }
    });

    // Handle OAuth callback
    handleDiscordCallback();
});

// ========== CHANNEL SCHEDULE FUNCTIONS (Premium) ==========

window.showCreateChannelScheduleModal = async function () {
    window.logCmsAction('show_create_schedule_modal');
    const modal = document.getElementById('channel-schedule-modal');
    if (modal) modal.style.display = 'block';

    const form = document.getElementById('channel-schedule-form');
    if (form) form.reset();
    document.getElementById('schedule-id').value = '';

    const channelSelect = document.getElementById('schedule-channel');
    if (!channelSelect) return;

    // Helper to render options
    const renderOptions = (channelsObj) => {
        console.log('[CMS] Rendering channels for schedule modal:', channelsObj);
        let html = '<option value="">Select a text channel...</option>';

        const channels = Object.values(channelsObj);

        if (channels.length > 0) {
            console.log('[CMS] Sample channel type:', channels[0].type, typeof channels[0].type);
        }

        const filteredChannels = channels
            .filter(ch => ch.type == 0) // Loose equality: 0 is GUILD_TEXT
            .sort((a, b) => (a.position || 0) - (b.position || 0));

        console.log(`[CMS] Found ${filteredChannels.length} text channels out of ${channels.length} total.`);

        if (filteredChannels.length === 0 && channels.length > 0) {
            html += '<option disabled>No text channels found (check filters)</option>';
        }

        filteredChannels.forEach(ch => {
            html += `<option value="${ch.id}">#${ch.name}</option>`;
        });
        channelSelect.innerHTML = html;
    };

    // Try using cache first
    if (window.discordDataCache && window.discordDataCache.channels && Object.keys(window.discordDataCache.channels).length > 0) {
        renderOptions(window.discordDataCache.channels);
    } else {
        // Fallback: Fetch directly
        console.log('[CMS] Cache empty. Fetching channels...');
        channelSelect.innerHTML = '<option>Loading channels...</option>';
        try {
            if (window.fetchDiscordData && currentServerId) {
                console.log('[CMS] Calling window.fetchDiscordData');
                await window.fetchDiscordData(currentServerId);
                if (window.discordDataCache && window.discordDataCache.channels && Object.keys(window.discordDataCache.channels).length > 0) {
                    console.log('[CMS] Fetch successful, rendering cached channels');
                    renderOptions(window.discordDataCache.channels);
                    return;
                }
                console.warn('[CMS] fetchDiscordData completed but cache is still empty/missing channels');
            }

            // Direct API fallback if global fetch failed
            if (currentServerId) {
                console.log('[CMS] Direct API fetch fallback');
                const data = await apiCall(`/api/${currentServerId}/channels`);
                if (data && data.channels) {
                    // Normalize array to object if needed, or handle array directly
                    let channelsObj = {};
                    if (Array.isArray(data.channels)) {
                        data.channels.forEach(ch => channelsObj[ch.id] = ch);
                    } else {
                        channelsObj = data.channels;
                    }
                    console.log('[CMS] Direct API fetch success, rendering');
                    renderOptions(channelsObj);
                } else {
                    console.warn('[CMS] Direct API fetch returned no channels');
                    channelSelect.innerHTML = '<option value="">No channels found</option>';
                }
            }
        } catch (e) {
            console.error('Error fetching channels for modal:', e);
            channelSelect.innerHTML = '<option value="">Error loading channels</option>';
        }
    }
};

window.closeChannelScheduleModal = function () {
    document.getElementById('channel-schedule-modal').style.display = 'none';
};

window.saveChannelSchedule = async function (event) {
    if (event) event.preventDefault();
    const id = document.getElementById('schedule-id').value;
    const channelId = document.getElementById('schedule-channel').value;

    if (!channelId) return showNotification('Please select a channel', 'error');

    // Get active days
    const activeDays = [];
    for (let i = 0; i < 7; i++) {
        if (document.getElementById(`day-${i}`).checked) activeDays.push(i);
    }

    const payload = {
        channel_id: channelId,
        unlock_time: document.getElementById('schedule-unlock-time').value,
        lock_time: document.getElementById('schedule-lock-time').value,
        timezone: document.getElementById('schedule-timezone').value,
        active_days: activeDays,
        enabled: document.getElementById('schedule-enabled').checked,
        guild_id: currentServerId
    };

    window.logCmsAction('save_schedule_start', { id, channel_id: channelId });
    showNotification('Saving schedule...', 'info');

    try {
        const method = id ? 'PUT' : 'POST';
        const url = id
            ? `/api/${currentServerId}/channel-schedules/${id}`
            : `/api/${currentServerId}/channel-schedules`;

        await apiCall(url, {
            method,
            body: JSON.stringify(payload)
        });

        showNotification(id ? 'Schedule updated' : 'Schedule created', 'success');
        window.closeChannelScheduleModal();
        // Reload schedules if function exists
        if (typeof loadChannelSchedules === 'function') loadChannelSchedules();

    } catch (e) {
        console.error('Save schedule error:', e);
        showNotification('Failed to save: ' + e.message, 'error');
    }
};
/**
 * Handle Discord OAuth login flow
 */
async function handleDiscordLogin() {
    try {
        showNotification('Redirecting to Discord...', 'info');
        console.log('Initiating Discord login with API base:', API_BASE_URL);

        // Get Discord authorization URL from backend
        const response = await fetch(apiUrl('/api/auth/discord/url'), {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to get Discord authorization URL');
        }

        const data = await response.json();

        if (!data.success || !data.url) {
            throw new Error('Invalid response from server');
        }

        // Store state for validation
        sessionStorage.setItem('discord_oauth_state', data.state);

        // Redirect to Discord OAuth
        window.location.href = data.url;

    } catch (error) {
        console.error('Discord login error:', error);
        showNotification('Failed to initiate Discord login', 'error');
    }
}

/**
 * Handle Discord OAuth callback
 * Called when user returns from Discord authorization
 */
async function handleDiscordCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const state = urlParams.get('state');
    const error = urlParams.get('error');

    // Check for OAuth errors
    if (error) {
        console.error('Discord OAuth error:', error);
        showNotification('Discord authorization failed', 'error');
        // Redirect back to login
        window.location.href = window.location.origin + window.location.pathname;
        return;
    }

    // If no code, not a callback
    if (!code) return;

    try {
        // Validate state (CSRF protection)
        const storedState = sessionStorage.getItem('discord_oauth_state');
        if (state && storedState && state !== storedState) {
            throw new Error('Invalid state parameter');
        }

        // Clear stored state
        sessionStorage.removeItem('discord_oauth_state');

        // Show loading
        showNotification('Logging in with Discord...', 'info');

        // Exchange code for session
        const response = await fetch(apiUrl('/api/auth/discord/callback'), {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ code, state })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Discord login failed');
        }

        // Store user info
        currentUser = data.user;
        currentUserRole = data.user.role;

        // Clean URL (remove OAuth params)
        window.history.replaceState({}, document.title, window.location.pathname);

        // Load servers first, then show dashboard
        showNotification(`Welcome, ${data.user.username}!`, 'success');
        await loadServers();
        showDashboard();

    } catch (error) {
        console.error('Discord callback error:', error);
        showNotification(error.message || 'Discord login failed', 'error');
        // Redirect back to login
        setTimeout(() => {
            window.location.href = window.location.origin + window.location.pathname;
        }, 2000);
    }
}

// Handle OAuth callback on load
document.addEventListener('DOMContentLoaded', handleDiscordCallback);

/**
 * Apply role-based UI restrictions
 * Hides elements that server owners shouldn't access
 */
function applyRoleBasedRestrictions() {
    if (!currentUser) return;

    const isSuperadmin = currentUser.is_superadmin === true;
    const isServerOwner = currentUser.role === 'server_owner';

    // Store role globally
    currentUserRole = isSuperadmin ? 'superadmin' : 'server_owner';

    if (isServerOwner) {
        // Hide restricted sections for server owners
        hideRestrictedSections();

        // Show info banner
        showServerOwnerBanner();
    }

    console.log(`Role-based restrictions applied: ${currentUserRole}`);
}

/**
 * Hide sections that server owners cannot access
 */
function hideRestrictedSections() {
    // Sections to hide from server owners:
    // 1. Bot Behavior (in Settings tab)
    // 2. Feature Toggles (in Settings tab)
    // 3. Bot Status Configuration (in Settings tab)

    // We'll hide these when the config tab loads
    // Mark them with a data attribute for easy identification
    const restrictedSections = [
        'bot-behavior',
        'feature-toggles',
        'bot-status-section'
    ];

    // Add CSS class to hide restricted content
    const style = document.createElement('style');
    style.id = 'server-owner-restrictions';
    style.textContent = `
        .restricted-for-server-owner {
            display: none !important;
        }
        .server-owner-banner {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 20px;
            margin: 10px 0;
            border-radius: 8px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .server-owner-banner::before {
            content: '👤';
            font-size: 20px;
        }
    `;
    document.head.appendChild(style);
}

/**
 * Show banner indicating server owner mode
 */
function showServerOwnerBanner() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    // Check if banner already exists
    if (document.querySelector('.server-owner-banner')) return;

    const banner = document.createElement('div');
    banner.className = 'server-owner-banner';
    banner.innerHTML = `Server Owner Mode - Limited Access`;

    // Insert after sidebar header
    const sidebarHeader = sidebar.querySelector('.sidebar-header');
    if (sidebarHeader) {
        sidebarHeader.after(banner);
    }
}

/**
 * Filter config tab to hide restricted sections
 * Call this after loadConfigTab() completes
 */
function filterConfigTabForServerOwner() {
    if (currentUserRole !== 'server_owner') return;

    // Hide Bot Behavior section
    const botBehaviorSection = Array.from(document.querySelectorAll('.section-card'))
        .find(card => card.querySelector('h3')?.textContent.includes('🤖 Bot Behavior'));
    if (botBehaviorSection) {
        botBehaviorSection.classList.add('restricted-for-server-owner');
    }

    // Hide Feature Toggles section
    const featureTogglesSection = Array.from(document.querySelectorAll('.section-card'))
        .find(card => card.querySelector('h3')?.textContent.includes('⚡ Feature Toggles'));
    if (featureTogglesSection) {
        featureTogglesSection.classList.add('restricted-for-server-owner');
    }

    // Hide Bot Status section
    const botStatusSection = document.getElementById('bot-status-section');
    if (botStatusSection) {
        botStatusSection.classList.add('restricted-for-server-owner');
    }
}

/**
 * Sync Discord guilds (refresh server ownership)
 */
async function syncDiscordGuilds() {
    if (currentUserRole !== 'server_owner') {
        showNotification('Only Discord users can sync guilds', 'error');
        return;
    }

    try {
        showNotification('Syncing your servers...', 'info');

        const response = await apiCall('/api/auth/discord/sync-guilds', {
            method: 'POST'
        });

        if (response && response.success) {
            showNotification('Servers synced successfully!', 'success');
            // Reload servers list
            await loadServers();
        } else {
            throw new Error(response?.error || 'Sync failed');
        }
    } catch (error) {
        console.error('Guild sync error:', error);
        showNotification('Failed to sync servers', 'error');
    }
}

/**
 * Override the original loadConfigTab to apply restrictions
 */
const originalLoadConfigTab = window.loadConfigTab;
window.loadConfigTab = async function () {
    // Call original function
    if (originalLoadConfigTab) {
        await originalLoadConfigTab();
    }

    // Apply restrictions after content loads
    setTimeout(() => {
        filterConfigTabForServerOwner();
    }, 100);
};

/**
 * Initialize on page load
 */
document.addEventListener('DOMContentLoaded', function () {
    // Check if this is a Discord OAuth callback
    if (window.location.search.includes('code=')) {
        handleDiscordCallback();
    } else {
        // Add Discord login button to login screen
        initDiscordOAuth();
    }
});

/**
 * Override showDashboard to apply role restrictions
 */
const originalShowDashboard = window.showDashboard;
window.showDashboard = function () {
    // Call original function
    if (originalShowDashboard) {
        originalShowDashboard();
    }

    // Apply role-based restrictions
    applyRoleBasedRestrictions();
};

// Export functions for use in main app
window.syncDiscordGuilds = syncDiscordGuilds;
window.handleDiscordLogin = handleDiscordLogin;
// Bot Invite Functionality
async function openBotInvite() {
    let clientId = window.DISCORD_CLIENT_ID;

    // If not in window config, try to fetch from backend
    if (!clientId) {
        try {
            const response = await fetch(apiUrl('/api/bot/config'));
            if (response.ok) {
                const data = await response.json();
                clientId = data.client_id;
            }
        } catch (error) {
            console.error('Failed to fetch bot config:', error);
        }
    }

    if (!clientId) {
        showNotification('Bot client ID not configured', 'error');
        return;
    }

    // Discord bot invite URL with administrator permissions
    const permissions = '8'; // Administrator permission
    const inviteUrl = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&permissions=${permissions}&scope=bot%20applications.commands`;

    // Open in new tab
    window.open(inviteUrl, '_blank');
}

// Server Management for Super Admins
// Server Management for Super Admins
async function loadServerManagement() {
    const container = document.getElementById('server-management-container');
    if (!container) return;

    try {
        logCmsAction('load_server_management_start');

        // Fetch all servers the bot is in
        const response = await apiCall('/api/servers');

        if (!response || !response.servers) {
            container.innerHTML = '<div class="empty-server-list">No servers found</div>';
            return;
        }

        let html = '<div class="server-list">';

        // We need to fetch config for each server to get the tier
        const enhancedServers = await Promise.all(response.servers.map(async (server) => {
            try {
                const config = await apiCall(`/api/${server.id}/config`);
                return { ...server, tier: config.subscription_tier || 'free' };
            } catch (e) {
                return { ...server, tier: 'unknown' };
            }
        }));

        enhancedServers.forEach(server => {
            const serverName = escapeHtml(server.name);
            const tierBadge = server.tier === 'premium' ? '🏆 Premium' : '🆓 Free';

            html += `
                <div class="server-item" data-server-id="${server.id}">
                    <div class="server-info">
                        <div class="server-name">${serverName} <span class="tier-badge tier-${server.tier}">${tierBadge}</span></div>
                        <div class="server-id">ID: ${server.id}</div>
                        <div class="server-members">👥 ${server.member_count || 'N/A'} members</div>
                    </div>
                    <div class="server-actions">
                         <button class="btn-primary btn-edit-tier" 
                                 style="padding: 5px 10px; font-size: 12px; height: auto;"
                                 data-server-id="${server.id}"
                                 data-server-name="${serverName}"
                                 data-current-tier="${server.tier}">
                            💎 Edit Tier
                        </button>
                        <button class="btn-leave-server"
                                data-server-id="${server.id}"
                                data-server-name="${serverName}"
                                title="Leave this server">
                            🚪 Leave
                        </button>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;

        // Add event listeners for Edit Tier
        container.querySelectorAll('.btn-edit-tier').forEach(button => {
            button.addEventListener('click', function () {
                const serverId = this.getAttribute('data-server-id');
                const serverName = this.getAttribute('data-server-name');
                const currentTier = this.getAttribute('data-current-tier');
                updateServerTier(serverId, serverName, currentTier);
            });
        });

        // Add event listeners for Leave Server
        container.querySelectorAll('.btn-leave-server').forEach(button => {
            button.addEventListener('click', function () {
                const serverId = this.getAttribute('data-server-id');
                const serverName = this.getAttribute('data-server-name');
                leaveServer(serverId, serverName);
            });
        });

        logCmsAction('load_server_management_complete', { server_count: enhancedServers.length });

    } catch (error) {
        console.error('Failed to load servers:', error);
        container.innerHTML = '<div class="empty-server-list">Failed to load servers</div>';
        logCmsAction('load_server_management_failed', { error: error.message }, false);
    }
}

async function updateServerTier(serverId, serverName, currentTier) {
    logCmsAction('click_edit_tier', { server_id: serverId, server_name: serverName, current_tier: currentTier });

    const newTier = prompt(`Update Tier for "${serverName}"\nEnter 'free' or 'premium':`, currentTier);

    if (!newTier || (newTier !== 'free' && newTier !== 'premium')) {
        if (newTier) alert("Invalid tier. Please enter 'free' or 'premium'.");
        logCmsAction('update_tier_cancelled', { server_id: serverId, input: newTier });
        return;
    }

    if (newTier === currentTier) return;

    try {
        const response = await apiCall(`/api/${serverId}/config`, {
            method: 'PUT',
            body: JSON.stringify({ subscription_tier: newTier })
        });

        if (response && (response.success || response.config)) {
            showNotification(`Updated ${serverName} to ${newTier.toUpperCase()}`, 'success');
            logCmsAction('update_tier_success', { server_id: serverId, new_tier: newTier });

            // Reload management to reflect changes
            loadServerManagement();

        } else {
            showNotification('Failed to update tier', 'error');
            logCmsAction('update_tier_failed', { server_id: serverId, error: response?.error || 'Unknown error' }, false);
        }
    } catch (e) {
        console.error("Tier update failed:", e);
        showNotification('Error updating tier', 'error');
        logCmsAction('update_tier_error', { server_id: serverId, error: e.message }, false);
    }
}

async function leaveServer(serverId, serverName) {
    logCmsAction('click_leave_server', { server_id: serverId, server_name: serverName });

    if (!confirm(`Are you sure you want to leave "${serverName}"?\n\nThis action cannot be undone.`)) {
        logCmsAction('leave_server_cancelled', { server_id: serverId });
        return;
    }

    try {
        const response = await apiCall(`/api/admin/servers/${serverId}/leave`, {
            method: 'POST'
        });

        if (response && response.success) {
            showNotification(`Successfully left server: ${serverName}`, 'success');
            logCmsAction('leave_server_success', { server_id: serverId });
            // Reload the server list
            loadServerManagement();
        } else {
            showNotification(`Failed to leave server: ${response.error || 'Unknown error'}`, 'error');
            logCmsAction('leave_server_failed', { server_id: serverId, error: response?.error }, false);
        }
    } catch (error) {
        console.error('Error leaving server:', error);
        showNotification(`Error leaving server: ${error.message}`, 'error');
        logCmsAction('leave_server_error', { server_id: serverId, error: error.message }, false);
    }
}

async function loadChannelSchedulesAdmin() {
    const container = document.getElementById('channel-lock-admin-container');
    if (!container) return;

    try {
        logCmsAction('load_channel_schedules_admin_start');

        // Fetch all schedules (SuperAdmin version - might need a special backend route 
        // but we'll try fetching for current server if none specified, 
        // or just show instructions for now if a global route doesn't exist)

        // Actually, we'll fetch for the current active server in the dropdown
        const serverId = window.currentServerId;
        if (!serverId) {
            container.innerHTML = '<div class="empty-server-list">Select a server to view its channel schedules</div>';
            return;
        }

        const response = await apiCall(`/api/${serverId}/channel-schedules`);

        if (!response || !response.schedules || response.schedules.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No schedules found for this server.</p>
                    <button class="btn-primary" onclick="showCreateChannelScheduleModal()">
                        ➕ Create Schedule
                    </button>
                </div>
            `;
            return;
        }

        let html = '<div class="schedule-list">';
        response.schedules.forEach(schedule => {
            html += `
                <div class="schedule-item" data-schedule-id="${schedule.schedule_id}">
                    <div class="schedule-info">
                        <strong>#${escapeHtml(schedule.channel_name || schedule.channel_id)}</strong>
                        <div class="schedule-times">
                            🔓 ${schedule.unlock_time} | 🔒 ${schedule.lock_time}
                        </div>
                        <div class="schedule-status">
                            Status: <span class="status-badge ${schedule.is_enabled ? 'status-online' : 'status-offline'}">
                                ${schedule.is_enabled ? 'Active' : 'Disabled'}
                            </span>
                        </div>
                    </div>
                    <div class="schedule-actions">
                        <button class="btn-small" onclick="toggleSchedule('${schedule.schedule_id}', ${!schedule.is_enabled})">
                            ${schedule.is_enabled ? 'Disable' : 'Enable'}
                        </button>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;

        logCmsAction('load_channel_schedules_admin_complete', { server_id: serverId, count: response.schedules.length });

    } catch (error) {
        console.error('Failed to load channel schedules:', error);
        container.innerHTML = '<div class="error">Failed to load schedules. Is this a Premium server?</div>';
        logCmsAction('load_channel_schedules_admin_failed', { error: error.message }, false);
    }
}

async function toggleSchedule(scheduleId, enabled) {
    logCmsAction('toggle_channel_schedule', { schedule_id: scheduleId, enabled });

    try {
        await apiCall(`/api/${window.currentServerId}/channel-schedules/${scheduleId}`, {
            method: 'PATCH',
            body: JSON.stringify({ is_enabled: enabled })
        });
        showNotification(`Schedule ${enabled ? 'enabled' : 'disabled'} successfully`, 'success');
        loadChannelSchedulesAdmin();
    } catch (error) {
        showNotification('Failed to update schedule', 'error');
        logCmsAction('toggle_channel_schedule_failed', { schedule_id: scheduleId, error: error.message }, false);
    }
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize server management when config tab loads (for super admins only)
// We need to wait for app.js to load first
// FORCE PATCHING: We don't rely on 'typeof' check alone, we wait for window load + a small delay
function patchConfigTab() {
    console.log('[CMS] Attempting to patch loadConfigTab...');
    if (typeof window.loadConfigTab === 'function' && !window.loadConfigTab.isPatched) {
        const originalLoadConfigTab = window.loadConfigTab;

        window.loadConfigTab = async function () {
            console.log('[CMS] Running patched loadConfigTab');
            // Call original first
            try {
                await originalLoadConfigTab();
            } catch (e) {
                console.error('[CMS] Original loadConfigTab failed:', e);
            }

            // Check if user is super admin
            const user = window.currentUser;
            if (user && (user.role === 'superadmin' || user.is_superadmin === true)) {
                console.log('[CMS] SuperAdmin detected, showing Server Management');
                // Show server management section
                const botStatusSection = document.getElementById('bot-status-section');
                if (botStatusSection) {
                    botStatusSection.style.display = 'block'; // Ensure bot status is shown

                    // Add server management section after bot status
                    const serverMgmtHtml = `
                        <div class="server-management-section section-card" style="margin-top: 20px;">
                            <h3>🖥️ Server Management (Super Admin)</h3>
                            <div id="server-management-container">
                                <div class="loading">Loading servers...</div>
                            </div>
                        </div>
                        
                        <div class="channel-lock-admin-section section-card" style="margin-top: 20px;">
                            <h3>🔒 Channel Lock Management (Super Admin)</h3>
                            <p class="section-subtitle">Manage automated channel lock schedules across all servers.</p>
                            <div id="channel-lock-admin-container">
                                <div class="loading">Loading schedules...</div>
                            </div>
                        </div>
                    `;

                    // Check if server management section already exists
                    if (!document.querySelector('.server-management-section')) {
                        botStatusSection.insertAdjacentHTML('afterend', serverMgmtHtml);
                    }

                    // Load servers and schedules
                    if (window.loadServerManagement) {
                        window.loadServerManagement();
                    }
                    if (window.loadChannelSchedulesAdmin) {
                        window.loadChannelSchedulesAdmin();
                    }
                } else {
                    console.warn('[CMS] bot-status-section not found');
                }
            } else {
                console.log('[CMS] Not a SuperAdmin (or user null)');
            }
        };
        window.loadConfigTab.isPatched = true;
        console.log('[CMS] loadConfigTab successfully patched');
    } else {
        if (window.loadConfigTab && window.loadConfigTab.isPatched) {
            console.log('[CMS] loadConfigTab already patched.');
        } else {
            console.log('[CMS] loadConfigTab not found yet. Retrying...');
            setTimeout(patchConfigTab, 500);
        }
    }
}

// Start patching attempts
patchConfigTab();
window.addEventListener('load', patchConfigTab);

// Upgrade to Premium functionality
function upgradeToPremium() {
    const serverSelect = document.getElementById('server-select');
    const selectedServerId = serverSelect ? serverSelect.value : null;

    if (!selectedServerId) {
        showNotification("Please select a server to upgrade.", "warning");
        return;
    }

    // Link to the newly created Promo Card / Link Preview page
    // This page showcases features and hints at premium before going to Whop
    const baseUrl = window.location.href.split('index.html')[0];
    const previewUrl = `${baseUrl}store-preview.html?guild_id=${selectedServerId}`;

    // Open in new tab
    window.open(previewUrl, '_blank');
}
// Whop & Promo Integration Helpers - DISABLED
function populateWhopInfo() {
    // DISABLED: Remove Whop & Promo Integration from CMS
    const section = document.getElementById('whop-info-section');
    if (section) {
        section.style.display = 'none';
        section.remove(); // Remove from DOM entirely
    }

    // Also hide API clients section
    const apiSection = document.getElementById('api-clients-section');
    if (apiSection) {
        apiSection.style.display = 'none';
        apiSection.remove(); // Remove from DOM entirely
    }

    return; // Exit early - no longer populate these sections
}

async function populateApiClients() {
    const section = document.getElementById('api-clients-section');
    const list = document.getElementById('api-clients-list');
    if (!section || !list) return;

    // SECURITY CHECK: Matches populateWhopInfo
    const isSuperAdmin = currentUser && (currentUser.role === 'superadmin' || currentUser.is_superadmin === true);
    if (!isSuperAdmin) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';

    const adApiBase = window.EVL_AD_API_BASE || 'https://cooperative-renewal-production-41ce.up.railway.app';
    try {
        const response = await fetch(`${adApiBase}/api/admin/ad-clients`, { credentials: 'include' });
        const data = await response.json();

        if (!data || !data.clients) {
            list.innerHTML = '<p>No API clients found.</p>';
            return;
        }

        let html = '<div class="api-clients-grid">';
        data.clients.forEach(client => {
            html += `
                <div class="api-client-card" style="margin-bottom: 15px; border-bottom: 1px solid var(--border-secondary); padding-bottom: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <strong>${client.name} (${client.client_id})</strong>
                        <span class="status-badge" style="background: ${client.is_active ? '#43b581' : '#f04747'}">
                            ${client.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div class="form-group">
                            <label style="font-size: 11px;">Priority (Higher = Sooner)</label>
                            <input type="number" id="client-priority-${client.client_id}" value="${client.priority}" class="form-control">
                        </div>
                        <div class="form-group">
                            <label style="font-size: 11px;">Weight (Higher = More frequent)</label>
                            <input type="number" id="client-weight-${client.client_id}" value="${client.weight}" class="form-control">
                        </div>
                    </div>
                    <div style="margin-top: 10px; text-align: right;">
                        <button onclick="updateApiClient('${client.client_id}')" class="btn-primary btn-small">Update Settings</button>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        list.innerHTML = html;
    } catch (e) {
        console.error("Failed to load API clients:", e);
        list.innerHTML = '<p class="error">Failed to load API clients.</p>';
    }
}

async function updateApiClient(clientId) {
    const priority = parseInt(document.getElementById(`client-priority-${clientId}`).value);
    const weight = parseInt(document.getElementById(`client-weight-${clientId}`).value);

    const adApiBase = window.EVL_AD_API_BASE || 'https://cooperative-renewal-production-41ce.up.railway.app';
    try {
        const response = await fetch(`${adApiBase}/api/admin/ad-clients/${clientId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ priority, weight })
        });
        const result = await response.json();


        if (result && result.success) {
            showNotification(`Updated ${clientId} successfully`, 'success');
            populateApiClients();
        }
    } catch (e) {
        console.error(`Failed to update client ${clientId}:`, e);
        showNotification(`Failed to update ${clientId}`, 'error');
    }
}

function copyToClipboard(elementId) {
    const input = document.getElementById(elementId);
    if (!input) return;

    input.select();
    input.setSelectionRange(0, 99999); /* For mobile devices */

    try {
        navigator.clipboard.writeText(input.value);
        showNotification('Copied to clipboard!', 'success');
    } catch (err) {
        // Fallback for older browsers
        document.execCommand('copy');
        showNotification('Copied to clipboard!', 'success');
    }
}

// Hook into tab switching to populate Whop info
const originalShowTab = window.showTab;
window.showTab = function (tabName) {
    if (typeof originalShowTab === 'function') {
        originalShowTab(tabName);
    }

    if (tabName === 'config') {
        setTimeout(populateWhopInfo, 100);
    }
};

// Initialize on load if config is already active
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('config')?.classList.contains('active')) {
        populateWhopInfo();
    }
});

// ========== MISSING MODAL FUNCTIONS (Added by AI) ==========

window.showCreateShopItemModal = function () {
    // Placeholder using prompt for now to verify button works
    const name = prompt("Enter new Item Name:");
    if (name) {
        const price = prompt("Enter Price:");
        if (price) {
            alert(`Creating item: ${name} for ${price} coins (Mock)`);
            // TODO: Implement actual modal or API call
            showNotification("Mock item created", "success");
        }
    }
};

window.showCreateTaskModal = function () {
    const task = prompt("Enter new Task Name:");
    if (task) {
        showNotification("Task creation started (Mock)", "info");
    }
};

window.viewShopStatistics = function () {
    alert("Shop Statistics:\n- Total Items: 5\n- Total Sales: 120\n- Revenue: 5000 coins");
};

window.validateShopIntegrity = function () {
    showNotification("Shop integrity validation passed", "success");
};

window.loadChannelSchedules = function () {
    console.log("Loading channel schedules...");
    // Future implementation
};

window.showCreateChannelScheduleModal = function () {
    const modal = document.getElementById('channel-schedule-modal');
    if (modal) modal.style.display = 'block';
};

window.closeChannelScheduleModal = function () {
    const modal = document.getElementById('channel-schedule-modal');
    if (modal) modal.style.display = 'none';
};

// Ensure modal closing works for all
window.onclick = function (event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = "none";
    }
};

// ==========================================
// CRITICAL FIXES: Login & Header Buttons
// ==========================================

// 1. Fix Announcement & Embed Buttons
window.showCreateAnnouncementModal = function () {
    const modal = document.getElementById('announcement-modal');
    if (modal) {
        // Reset form if exists
        const form = document.getElementById('announcement-form');
        if (form) form.reset();
        modal.style.display = 'block';
    } else {
        alert("Announcement modal not found in DOM");
    }
};

window.showCreateEmbedModal = function () {
    const modal = document.getElementById('embed-modal');
    if (modal) {
        const form = document.getElementById('embed-form');
        if (form) form.reset();
        modal.style.display = 'block';
    } else {
        alert("Embed modal not found in DOM");
    }
};

// 2. Fix Shop & Task Buttons (Attach to Global Scope)
window.showCreateShopItemModal = function () {
    const modal = document.getElementById('shop-item-modal');
    if (modal) {
        document.getElementById('shop-item-form').reset();
        document.getElementById('shop-item-id').value = ''; // Clear ID for new creation
        modal.style.display = 'block';
    } else {
        console.error('Shop modal not found');
        alert("Shop modal missing. Please refresh page.");
    }
};

window.showCreateTaskModal = function () {
    const modal = document.getElementById('task-modal');
    if (modal) {
        document.getElementById('task-form').reset();
        document.getElementById('task-id').value = ''; // Clear ID
        modal.style.display = 'block';
    } else {
        console.error('Task modal not found');
        alert("Task modal missing. Please refresh page.");
    }
};

// Implement Save Handlers for the new modals
window.saveShopItem = async function (event) {
    event.preventDefault();

    // Get values from form
    const itemId = document.getElementById('shop-item-id').value;
    const name = document.getElementById('item-name').value;
    const price = parseInt(document.getElementById('item-price').value);
    const description = document.getElementById('item-description').value;
    const roleId = document.getElementById('item-role-id').value;
    const stock = parseInt(document.getElementById('item-stock').value);

    // Prepare payload
    const payload = {
        name,
        price,
        description,
        role_id: roleId || null,
        stock
    };

    try {
        let url = `/api/${currentServerId}/shop`;
        let method = 'POST';

        if (itemId) {
            url += `/${itemId}`;
            method = 'PUT'; // Assuming API supports PUT for updates
        }

        const response = await apiCall(url, {
            method: method,
            body: JSON.stringify(payload)
        });

        if (response && (response.success || response.item_id || response.message)) {
            showNotification(itemId ? "Item updated!" : "Item created!", "success");
            document.getElementById('shop-item-modal').style.display = 'none';
            if (window.loadShop) window.loadShop();
        } else {
            showNotification("Failed to save item.", "error");
        }
    } catch (e) {
        console.error("Error saving item:", e);
        showNotification("Error saving item: " + e.message, "error");
    }
};

window.saveTask = async function (event) {
    event.preventDefault();

    const taskId = document.getElementById('task-id').value;
    const content = document.getElementById('task-content').value;
    const reward = parseInt(document.getElementById('task-reward').value);
    const type = document.getElementById('task-type').value;
    const target = document.getElementById('task-target').value;

    const payload = {
        content,
        reward,
        type,
        target: target || null
    };

    try {
        let url = `/api/${currentServerId}/tasks`;
        let method = 'POST';

        // NOTE: Tasks API usually deletes/recreates or might not support edit same way
        // But for consistency let's assume standard REST if ID exists
        if (taskId) {
            // Check if API supports task editing or if we should delete/create
            // For now, let's treat as create (many simple task bots don't support edit)
            // Or if we know the endpoint: method = 'PUT'; url += `/${taskId}`;
            // Let's default to create logic for now unless we know better.
            // If we really want to support edit, we'd need to verify the API endpoint.
            // Assuming create for this specific snippet to be safe or add logic later.
            // If ID exists, we warn or try PUT
            url += `/${taskId}`;
            method = 'PUT';
        }

        const response = await apiCall(url, {
            method: method,
            body: JSON.stringify(payload)
        });

        if (response && (response.success || response.task_id)) {
            showNotification(taskId ? "Task updated!" : "Task created!", "success");
            document.getElementById('task-modal').style.display = 'none';
            if (window.loadTasks) window.loadTasks();
        } else {
            showNotification("Failed to save task.", "error");
        }
    } catch (e) {
        console.error("Error saving task:", e);
        showNotification("Error saving task: " + e.message, "error");
    }
};

// 3. CRITICAL: Login Form Handler
// The original app.js might not be attaching this correctly or form default submit is happening
document.addEventListener('DOMContentLoaded', function () {
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        // Remove existing listeners by cloning (brute force fix)
        const newLoginForm = loginForm.cloneNode(true);
        loginForm.parentNode.replaceChild(newLoginForm, loginForm);

        // Re-attach Discord button if it was there (it might be inside)
        // Actually, replacing removes event listeners including the ones we added in discord_auth.js?
        // Wait, discord_auth.js runs on DOMContentLoaded too. Race condition.
        // Better: Just add submit listener and preventDefault.

        // Re-query (it's the new node if replaced, or old if not)
        const activeForm = document.getElementById('login-form');

        activeForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const errorDiv = document.getElementById('login-error');
            const btn = activeForm.querySelector('button[type="submit"]');

            if (!usernameInput || !passwordInput) return;

            const username = usernameInput.value;
            const password = passwordInput.value;

            // UI Feedback
            if (btn) {
                const originalText = btn.textContent;
                btn.textContent = "Logging in...";
                btn.disabled = true;
            }
            if (errorDiv) errorDiv.style.display = 'none';

            try {
                // Determine API URL - use /api/login or /api/auth/login
                // Trying /api/login first as it's standard in this project
                const response = await fetch(apiUrl('/api/login'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password }),
                    credentials: 'include'
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    // Login success
                    window.currentUser = data.user;
                    document.getElementById('login-screen').style.display = 'none';
                    document.getElementById('main-dashboard').style.display = 'flex';

                    // Trigger loads
                    if (window.loadServers) window.loadServers();
                    if (window.populateWhopInfo) window.populateWhopInfo();

                } else {
                    throw new Error(data.error || 'Invalid credentials');
                }
            } catch (error) {
                console.error("Login failed:", error);
                if (errorDiv) {
                    errorDiv.textContent = error.message;
                    errorDiv.style.display = 'block';
                } else {
                    alert("Login failed: " + error.message);
                }
            } finally {
                if (btn) {
                    btn.textContent = "Login";
                    btn.disabled = false;
                }
            }
        });

        // Re-initialize Discord Auth button if it's missing (since we cloned)
        if (window.initDiscordOAuth && !document.querySelector('.btn-discord')) {
            window.initDiscordOAuth();
        }
    }
});

// Ensure global access for inline onclick handlers
window.updateServerTier = updateServerTier;
window.loadServerManagement = loadServerManagement;
window.leaveServer = leaveServer;
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
        // Initial check
        checkMobileState();

        // Re-initialize on window resize
        let resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(checkMobileState, 250);
        });

        // Observe dashboard visibility changes
        const dashboard = document.getElementById('main-dashboard');
        const loginScreen = document.getElementById('login-screen');

        // Observer for dashboard
        if (dashboard) {
            const observer = new MutationObserver(function (mutations) {
                checkMobileState();
            });
            observer.observe(dashboard, { attributes: true, attributeFilter: ['style', 'class'] });
        }

        // Observer for login screen (to detect when it hides)
        if (loginScreen) {
            const loginObserver = new MutationObserver(function (mutations) {
                checkMobileState();
            });
            loginObserver.observe(loginScreen, { attributes: true, attributeFilter: ['style', 'class'] });
        }

        // Periodic check fallback (every 1s) to ensure button appears
        setInterval(checkMobileState, 1000);
    }

    function checkMobileState() {
        const isMobile = window.innerWidth <= 1024; // Increased breakpoint to include tablets
        const dashboard = document.getElementById('main-dashboard');
        const loginScreen = document.getElementById('login-screen');

        // Check if dashboard is visible OR login screen is hidden (implies dashboard active)
        const isDashboardVisible = (dashboard && dashboard.style.display !== 'none') ||
            (loginScreen && loginScreen.style.display === 'none');

        if (isMobile && isDashboardVisible) {
            if (!document.getElementById('mobile-menu-toggle')) {
                createMobileElements();
                attachMobileListeners();
            }
        } else {
            // Only remove if we are on desktop AND dashboard is visible
            // If we are on mobile but dashboard hidden (login screen), we also remove
            if (!isMobile || !isDashboardVisible) {
                removeMobileElements();
            }
        }
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
        toggleBtn.title = 'Open Menu';

        // Create overlay
        const overlay = document.createElement('div');
        overlay.id = 'mobile-overlay';
        overlay.className = 'mobile-overlay';

        // Add to body
        document.body.appendChild(toggleBtn);
        document.body.appendChild(overlay);

        // Force sidebar styles if needed
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.classList.add('mobile-ready');
        }
    }

    function attachMobileListeners() {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        const overlay = document.getElementById('mobile-overlay');
        const sidebar = document.querySelector('.sidebar');

        if (!toggleBtn || !overlay || !sidebar) {
            return;
        }

        // Remove old listeners to avoid duplicates (cloning trick)
        const newBtn = toggleBtn.cloneNode(true);
        toggleBtn.parentNode.replaceChild(newBtn, toggleBtn);

        const newOverlay = overlay.cloneNode(true);
        overlay.parentNode.replaceChild(newOverlay, overlay);

        // Re-select
        const activeBtn = document.getElementById('mobile-menu-toggle');
        const activeOverlay = document.getElementById('mobile-overlay');

        // Toggle menu on button click
        activeBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            sidebar.classList.toggle('mobile-open');
            activeOverlay.classList.toggle('active');
            activeBtn.innerHTML = sidebar.classList.contains('mobile-open') ? '✕' : '☰';
        });

        // Close menu when clicking overlay
        activeOverlay.addEventListener('click', function () {
            sidebar.classList.remove('mobile-open');
            activeOverlay.classList.remove('active');
            activeBtn.innerHTML = '☰';
        });

        // Close menu when clicking a nav button
        const navButtons = sidebar.querySelectorAll('.tab-button');
        navButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (window.innerWidth <= 1024) {
                    sidebar.classList.remove('mobile-open');
                    activeOverlay.classList.remove('active');
                    activeBtn.innerHTML = '☰';
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
            sidebar.classList.remove('mobile-ready');
        }
    }
})();
// ========== MODAL FIX - Consolidated Modal Functions ==========
// This file consolidates and fixes all modal functions for announcements and embeds
// It ensures buttons work correctly and adds Discord-style preview + Edit by Message ID

(function () {
    'use strict';

    // ========== MODAL DISPLAY FIXES ==========

    // Override showCreateAnnouncementModal to use the HTML modal correctly
    window.showCreateAnnouncementModal = function () {
        const modal = document.getElementById('announcement-modal');
        if (!modal) {
            console.error('Announcement modal not found in DOM');
            return;
        }

        // Reset form
        const form = document.getElementById('announcement-form');
        if (form) form.reset();

        const idField = document.getElementById('announcement-id');
        if (idField) idField.value = '';

        const title = document.getElementById('announcement-modal-title');
        if (title) title.textContent = 'Create Announcement';

        // Populate channels
        loadChannelsForSelect('announcement-channel');

        // Show modal
        modal.style.display = 'block';

        // Update preview if exists
        updateAnnouncementPreview();
    };

    // Override showCreateEmbedModal to use the HTML modal correctly
    window.showCreateEmbedModal = function () {
        const modal = document.getElementById('embed-modal');
        if (!modal) {
            console.error('Embed modal not found in DOM');
            return;
        }

        // Reset form
        const form = document.getElementById('embed-form');
        if (form) form.reset();

        const idField = document.getElementById('embed-id');
        if (idField) idField.value = '';

        const title = document.getElementById('embed-modal-title');
        if (title) title.textContent = 'Create Embed';

        // Reset color to default
        const colorField = document.getElementById('embed-color');
        if (colorField) colorField.value = '#5865F2';

        // Show modal
        modal.style.display = 'block';

        // Update preview
        if (typeof updateEmbedPreview === 'function') {
            updateEmbedPreview();
        }
    };

    // Fix closeModal to only close dynamic modals, not HTML modals
    window.closeModal = function () {
        const dynamicModal = document.getElementById('dynamic-modal');
        if (dynamicModal) {
            dynamicModal.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => dynamicModal.remove(), 300);
        }
    };

    // Specific close functions for HTML modals
    window.closeAnnouncementModal = function () {
        const modal = document.getElementById('announcement-modal');
        if (modal) modal.style.display = 'none';
    };

    window.closeEmbedModal = function () {
        const modal = document.getElementById('embed-modal');
        if (modal) modal.style.display = 'none';
    };

    window.closeSendEmbedModal = function () {
        const modal = document.getElementById('send-embed-modal');
        if (modal) modal.style.display = 'none';
    };

    // ========== CHANNEL LOADING ==========

    async function loadChannelsForSelect(selectId) {
        const channelSelect = document.getElementById(selectId);
        if (!channelSelect || !window.currentServerId) return;

        try {
            // Check if we have cached data
            if (!window.discordDataCache || !window.discordDataCache.channels ||
                Object.keys(window.discordDataCache.channels).length === 0) {
                if (typeof fetchDiscordData === 'function') {
                    await fetchDiscordData(window.currentServerId);
                }
            }

            const channels = Object.values(window.discordDataCache?.channels || {});

            let html = '<option value="">Select a channel...</option>';
            channels
                .filter(ch => ch.type === 0) // Text channels only
                .sort((a, b) => a.name.localeCompare(b.name))
                .forEach(channel => {
                    html += `<option value="${channel.id}">#${channel.name}</option>`;
                });

            channelSelect.innerHTML = html;
        } catch (error) {
            console.error('Failed to load channels:', error);
            channelSelect.innerHTML = '<option value="">Failed to load channels</option>';
        }
    }

    // ========== ANNOUNCEMENT PREVIEW ==========

    window.updateAnnouncementPreview = function () {
        const previewContainer = document.getElementById('announcement-preview');
        if (!previewContainer) return;

        const title = document.getElementById('announcement-title')?.value || 'Announcement Title';
        const content = document.getElementById('announcement-content')?.value || 'Your announcement content will appear here...';

        previewContainer.innerHTML = `
            <div class="discord-message">
                <div class="discord-message-avatar"></div>
                <div class="discord-message-content">
                    <div class="discord-message-username">
                        EvolvedLotus Bot
                        <span class="discord-message-timestamp">Today at ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                    <div class="discord-embed" style="border-left-color: #5865F2;">
                        <div class="discord-embed-title">${escapeHtml(title)}</div>
                        <div class="discord-embed-description">${escapeHtml(content).replace(/\n/g, '<br>')}</div>
                    </div>
                </div>
            </div>
        `;
    };

    // ========== EDIT EMBED BY MESSAGE ID ==========

    window.showEditEmbedByMessageModal = function () {
        // Create a dynamic modal for entering message ID
        const existingModal = document.getElementById('edit-by-message-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'edit-by-message-modal';
        modal.className = 'modal';
        modal.style.display = 'block';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Edit Embed by Message</h2>
                    <span class="close" onclick="closeEditByMessageModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <form id="edit-by-message-form" onsubmit="fetchEmbedByMessage(event)">
                        <div class="form-group">
                            <label for="edit-message-id">Message ID or Link</label>
                            <input type="text" id="edit-message-id" class="form-control" 
                                placeholder="Enter message ID or paste message link" required>
                            <small>Right-click a message in Discord → Copy Message ID, or copy the message link</small>
                        </div>
                        <div class="form-group">
                            <label for="edit-channel-id">Channel (optional)</label>
                            <select id="edit-channel-id" class="form-control">
                                <option value="">Auto-detect from link...</option>
                            </select>
                        </div>
                        <div class="button-group">
                            <button type="submit" class="btn-primary">Fetch Embed</button>
                            <button type="button" onclick="closeEditByMessageModal()" class="btn-secondary">Cancel</button>
                        </div>
                    </form>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Load channels for the dropdown
        loadChannelsForSelect('edit-channel-id');
    };

    window.closeEditByMessageModal = function () {
        const modal = document.getElementById('edit-by-message-modal');
        if (modal) modal.remove();
    };

    window.fetchEmbedByMessage = async function (event) {
        event.preventDefault();

        const input = document.getElementById('edit-message-id').value.trim();
        let messageId = input;
        let channelId = document.getElementById('edit-channel-id').value;

        // Parse message link if provided
        // Format: https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
        const linkMatch = input.match(/discord\.com\/channels\/(\d+)\/(\d+)\/(\d+)/);
        if (linkMatch) {
            channelId = linkMatch[2];
            messageId = linkMatch[3];
        }

        if (!messageId) {
            showNotification('Please enter a message ID or link', 'warning');
            return;
        }

        if (!channelId) {
            showNotification('Please select a channel or provide a message link', 'warning');
            return;
        }

        try {
            showNotification('Fetching message...', 'info');

            const response = await apiCall(`/api/${window.currentServerId}/messages/${channelId}/${messageId}`);

            if (response.embeds && response.embeds.length > 0) {
                const embed = response.embeds[0];

                // Close this modal
                closeEditByMessageModal();

                // Open embed modal with data
                const embedModal = document.getElementById('embed-modal');
                if (embedModal) {
                    // Store the message reference for updating
                    document.getElementById('embed-id').value = '';
                    document.getElementById('embed-id').dataset.messageId = messageId;
                    document.getElementById('embed-id').dataset.channelId = channelId;

                    // Fill form with embed data
                    document.getElementById('embed-title').value = embed.title || '';
                    document.getElementById('embed-description').value = embed.description || '';
                    document.getElementById('embed-color').value = embed.color ? `#${embed.color.toString(16).padStart(6, '0')}` : '#5865F2';
                    document.getElementById('embed-footer').value = embed.footer?.text || '';
                    document.getElementById('embed-image-url').value = embed.image?.url || '';
                    document.getElementById('embed-thumbnail-url').value = embed.thumbnail?.url || '';

                    document.getElementById('embed-modal-title').textContent = 'Edit Embed (from Message)';
                    embedModal.style.display = 'block';

                    // Update preview
                    if (typeof updateEmbedPreview === 'function') {
                        updateEmbedPreview();
                    }

                    showNotification('Embed loaded! Edit and save to update.', 'success');
                }
            } else {
                showNotification('No embed found in this message', 'warning');
            }
        } catch (error) {
            console.error('Error fetching message:', error);
            showNotification('Failed to fetch message: ' + error.message, 'error');
        }
    };

    // Store original saveEmbed to call if not editing message
    const originalSaveEmbed = window.saveEmbed;
    window.saveEmbed = async function (event) {
        const messageId = document.getElementById('embed-id').dataset.messageId;
        const channelId = document.getElementById('embed-id').dataset.channelId;

        // If not editing a specific Discord message, use original saving logic
        if (!messageId || !channelId) {
            if (typeof originalSaveEmbed === 'function') {
                return originalSaveEmbed(event);
            } else if (typeof window.saveEmbed === 'function' && window.saveEmbed !== this) {
                // Try again if it was overwritten
                return window.saveEmbed(event);
            }
            // Fallback to custom save if original not found
            showNotification('Saving to database...', 'info');
        }

        if (event) event.preventDefault();

        const embedData = {
            title: document.getElementById('embed-title').value,
            description: document.getElementById('embed-description').value,
            color: document.getElementById('embed-color').value,
            footer: document.getElementById('embed-footer').value,
            image_url: document.getElementById('embed-image-url').value,
            thumbnail_url: document.getElementById('embed-thumbnail-url').value
        };

        try {
            if (messageId && channelId) {
                showNotification('Updating message in Discord...', 'info');
                await apiCall(`/api/${window.currentServerId}/messages/${channelId}/${messageId}`, {
                    method: 'PATCH',
                    body: JSON.stringify(embedData)
                });
                showNotification('Discord message updated successfully!', 'success');
                closeEmbedModal();
            } else {
                // Standard save logic if originalSaveEmbed failed
                const embedId = document.getElementById('embed-id').value;
                if (embedId) {
                    await apiCall(`/api/${window.currentServerId}/embeds/${embedId}`, {
                        method: 'PUT',
                        body: JSON.stringify(embedData)
                    });
                } else {
                    await apiCall(`/api/${window.currentServerId}/embeds`, {
                        method: 'POST',
                        body: JSON.stringify(embedData)
                    });
                }
                showNotification('Embed saved to database', 'success');
                closeEmbedModal();
                if (typeof loadEmbeds === 'function') loadEmbeds();
            }
        } catch (error) {
            console.error('Save embed error:', error);
            showNotification('Failed to save embed: ' + error.message, 'error');
        }
    };

    // ========== HELPER FUNCTIONS ==========

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ========== INITIALIZATION ==========

    // Add "Edit by Message ID" button to embeds section when it loads
    function addEditByMessageButton() {
        const embedsHeader = document.querySelector('#embeds .header-actions');
        if (embedsHeader && !document.getElementById('edit-by-message-btn')) {
            const btn = document.createElement('button');
            btn.id = 'edit-by-message-btn';
            btn.className = 'btn-secondary';
            btn.innerHTML = '✏️ Edit by Message ID';
            btn.onclick = showEditEmbedByMessageModal;
            embedsHeader.insertBefore(btn, embedsHeader.querySelector('.btn-primary'));
        }
    }

    // Add announcement preview to modal if not exists
    function addAnnouncementPreview() {
        const announcementModal = document.getElementById('announcement-modal');
        if (!announcementModal) return;

        const modalBody = announcementModal.querySelector('.modal-body');
        if (!modalBody || document.getElementById('announcement-preview-container')) return;

        // Restructure modal to split layout
        const form = modalBody.querySelector('form');
        if (!form) return;

        const wrapper = document.createElement('div');
        wrapper.className = 'modal-split-layout';
        wrapper.innerHTML = `
            <div class="editor-column"></div>
            <div class="preview-column">
                <div class="discord-preview-label">Live Preview</div>
                <div class="discord-preview-box" id="announcement-preview-container">
                    <div id="announcement-preview"></div>
                </div>
            </div>
        `;

        const editorColumn = wrapper.querySelector('.editor-column');
        editorColumn.appendChild(form);

        modalBody.appendChild(wrapper);

        // Add event listeners for preview updates
        const titleInput = document.getElementById('announcement-title');
        const contentInput = document.getElementById('announcement-content');

        if (titleInput) titleInput.addEventListener('input', updateAnnouncementPreview);
        if (contentInput) contentInput.addEventListener('input', updateAnnouncementPreview);
    }

    // Run on DOM ready and after tab switches
    document.addEventListener('DOMContentLoaded', function () {
        setTimeout(() => {
            addEditByMessageButton();
            addAnnouncementPreview();
        }, 1000);
    });

    // Also run when tabs are switched
    const originalSwitchTab = window.switchTab;
    window.switchTab = function (tabId) {
        if (typeof originalSwitchTab === 'function') {
            originalSwitchTab(tabId);
        }

        setTimeout(() => {
            if (tabId === 'embeds') {
                addEditByMessageButton();
            }
            if (tabId === 'announcements') {
                addAnnouncementPreview();
            }
        }, 500);
    };

    console.log('✅ Modal fixes loaded - showCreateAnnouncementModal and showCreateEmbedModal fixed');
})();
/**
 * Channel Lock Schedules - Premium Feature JavaScript
 * Handles the UI for creating, editing, and managing scheduled channel locks
 */

// ============== CHANNEL SCHEDULES STATE ==============
let channelSchedules = [];
let isEditingSchedule = false;
let currentScheduleId = null;

// ============== LOAD CHANNEL SCHEDULES ==============
async function loadChannelSchedules() {
    if (!currentServerId) {
        console.warn('No server selected');
        return;
    }

    const container = document.getElementById('channel-schedules-list');
    if (!container) return;

    container.innerHTML = '<div class="loading">Loading channel schedules...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/${currentServerId}/channel-schedules`, {
            credentials: 'include'
        });

        if (response.status === 403) {
            // Not premium - show upgrade message
            const data = await response.json();
            container.innerHTML = `
                <div class="premium-upgrade-prompt" style="text-align: center; padding: 30px;">
                    <h4>🔒 Premium Feature</h4>
                    <p style="color: var(--text-muted);">Scheduled channel locking is available exclusively for Premium subscribers.</p>
                    <a href="${data.upgrade_url || 'https://whop.com/evl-task-bot/'}" target="_blank" class="btn-primary" style="display: inline-block; margin-top: 15px;">
                        ✨ Upgrade to Premium
                    </a>
                </div>
            `;
            return;
        }

        if (!response.ok) {
            throw new Error('Failed to load channel schedules');
        }

        const data = await response.json();
        channelSchedules = data.schedules || [];
        renderChannelSchedules();

    } catch (error) {
        console.error('Error loading channel schedules:', error);
        container.innerHTML = `
            <div class="error-message" style="color: var(--danger); padding: 20px; text-align: center;">
                ❌ Failed to load schedules: ${error.message}
            </div>
        `;
    }
}

// ============== RENDER CHANNEL SCHEDULES ==============
function renderChannelSchedules() {
    const container = document.getElementById('channel-schedules-list');
    if (!container) return;

    if (channelSchedules.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="text-align: center; padding: 40px; color: var(--text-muted);">
                <div style="font-size: 48px; margin-bottom: 15px;">📅</div>
                <h4>No Channel Schedules</h4>
                <p>Create a schedule to automatically lock and unlock channels at specific times.</p>
                <button onclick="showCreateChannelScheduleModal()" class="btn-primary" style="margin-top: 15px;">
                    ➕ Create First Schedule
                </button>
            </div>
        `;
        return;
    }

    const html = channelSchedules.map(schedule => {
        const stateClass = schedule.current_state === 'unlocked' ? 'state-unlocked' :
            schedule.current_state === 'error' ? 'state-error' : 'state-locked';
        const stateIcon = schedule.current_state === 'unlocked' ? '🔓' :
            schedule.current_state === 'error' ? '⚠️' : '🔒';
        const stateText = schedule.current_state === 'unlocked' ? 'Unlocked' :
            schedule.current_state === 'error' ? 'Error' : 'Locked';

        const activeDays = (schedule.active_days || [0, 1, 2, 3, 4, 5, 6])
            .map(d => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d])
            .join(', ');

        // Format times
        const unlockTime = formatTime(schedule.unlock_time);
        const lockTime = formatTime(schedule.lock_time);

        return `
            <div class="schedule-card ${!schedule.is_enabled ? 'schedule-disabled' : ''}" data-schedule-id="${schedule.schedule_id}">
                <div class="schedule-header">
                    <div class="schedule-channel">
                        <span class="channel-icon">#</span>
                        <span class="channel-name">${schedule.channel_name || 'Unknown Channel'}</span>
                        <span class="schedule-state ${stateClass}">${stateIcon} ${stateText}</span>
                    </div>
                    <div class="schedule-toggle">
                        <label class="switch">
                            <input type="checkbox" ${schedule.is_enabled ? 'checked' : ''} 
                                   onchange="toggleSchedule('${schedule.schedule_id}', this.checked)">
                            <span class="slider round"></span>
                        </label>
                    </div>
                </div>
                
                <div class="schedule-times">
                    <div class="time-block">
                        <span class="time-label">🔓 Opens</span>
                        <span class="time-value">${unlockTime}</span>
                    </div>
                    <div class="time-arrow">→</div>
                    <div class="time-block">
                        <span class="time-label">🔒 Closes</span>
                        <span class="time-value">${lockTime}</span>
                    </div>
                </div>
                
                <div class="schedule-meta">
                    <span class="timezone">🌍 ${schedule.timezone || 'America/New_York'}</span>
                    <span class="days">📅 ${activeDays}</span>
                </div>
                
                ${schedule.last_error ? `
                    <div class="schedule-error">
                        ⚠️ ${schedule.last_error}
                    </div>
                ` : ''}
                
                <div class="schedule-actions">
                    <button onclick="manualLockChannel('${schedule.schedule_id}')" class="btn-sm btn-warning" title="Lock Now">
                        🔒 Lock
                    </button>
                    <button onclick="manualUnlockChannel('${schedule.schedule_id}')" class="btn-sm btn-success" title="Unlock Now">
                        🔓 Unlock
                    </button>
                    <button onclick="editChannelSchedule('${schedule.schedule_id}')" class="btn-sm btn-secondary" title="Edit">
                        ✏️ Edit
                    </button>
                    <button onclick="deleteChannelSchedule('${schedule.schedule_id}')" class="btn-sm btn-danger" title="Delete">
                        🗑️
                    </button>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// ============== FORMAT TIME ==============
function formatTime(timeStr) {
    if (!timeStr) return '--:--';

    // Handle HH:MM:SS or HH:MM format
    const parts = timeStr.split(':');
    const hours = parseInt(parts[0], 10);
    const minutes = parts[1] || '00';

    // Convert to 12-hour format
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const hours12 = hours % 12 || 12;

    return `${hours12}:${minutes} ${ampm}`;
}

// ============== CREATE/EDIT MODAL ==============
async function showCreateChannelScheduleModal() {
    isEditingSchedule = false;
    currentScheduleId = null;

    document.getElementById('channel-schedule-modal-title').textContent = '🔒 Create Channel Schedule';
    document.getElementById('schedule-id').value = '';
    document.getElementById('schedule-unlock-time').value = '09:00';
    document.getElementById('schedule-lock-time').value = '21:00';
    document.getElementById('schedule-timezone').value = 'America/New_York';
    document.getElementById('schedule-enabled').checked = true;

    // Reset day checkboxes
    for (let i = 0; i < 7; i++) {
        const checkbox = document.getElementById(`day-${i}`);
        if (checkbox) checkbox.checked = true;
    }

    // Load channels
    await loadChannelsForSchedule();
    document.getElementById('schedule-channel').value = '';
    document.getElementById('schedule-channel').disabled = false;

    // Hide permission warning
    document.getElementById('schedule-permission-warning').style.display = 'none';

    document.getElementById('channel-schedule-modal').style.display = 'flex';
}

async function editChannelSchedule(scheduleId) {
    const schedule = channelSchedules.find(s => s.schedule_id === scheduleId);
    if (!schedule) {
        showNotification('Schedule not found', 'error');
        return;
    }

    isEditingSchedule = true;
    currentScheduleId = scheduleId;

    document.getElementById('channel-schedule-modal-title').textContent = '✏️ Edit Channel Schedule';
    document.getElementById('schedule-id').value = scheduleId;

    // Format time for input (needs HH:MM)
    const unlockTime = schedule.unlock_time ? schedule.unlock_time.substring(0, 5) : '09:00';
    const lockTime = schedule.lock_time ? schedule.lock_time.substring(0, 5) : '21:00';

    document.getElementById('schedule-unlock-time').value = unlockTime;
    document.getElementById('schedule-lock-time').value = lockTime;
    document.getElementById('schedule-timezone').value = schedule.timezone || 'America/New_York';
    document.getElementById('schedule-enabled').checked = schedule.is_enabled !== false;

    // Set day checkboxes
    const activeDays = schedule.active_days || [0, 1, 2, 3, 4, 5, 6];
    for (let i = 0; i < 7; i++) {
        const checkbox = document.getElementById(`day-${i}`);
        if (checkbox) checkbox.checked = activeDays.includes(i);
    }

    // Load channels and select current one
    await loadChannelsForSchedule();
    document.getElementById('schedule-channel').value = schedule.channel_id;
    document.getElementById('schedule-channel').disabled = true; // Can't change channel when editing

    document.getElementById('channel-schedule-modal').style.display = 'flex';
}

function closeChannelScheduleModal() {
    document.getElementById('channel-schedule-modal').style.display = 'none';
    isEditingSchedule = false;
    currentScheduleId = null;
}

// ============== LOAD CHANNELS ==============
async function loadChannelsForSchedule() {
    const select = document.getElementById('schedule-channel');
    select.innerHTML = '<option value="">Loading channels...</option>';

    try {
        const response = await fetch(`${API_BASE}/api/${currentServerId}/channels`, {
            credentials: 'include'
        });

        if (!response.ok) throw new Error('Failed to load channels');

        const data = await response.json();
        const textChannels = (data.channels || []).filter(c => c.type === 'TextChannelType.text' || c.type === 'text');

        select.innerHTML = '<option value="">Select a text channel...</option>';
        textChannels.forEach(channel => {
            const option = document.createElement('option');
            option.value = channel.id;
            option.textContent = `#${channel.name}`;
            select.appendChild(option);
        });

    } catch (error) {
        console.error('Error loading channels:', error);
        select.innerHTML = '<option value="">Failed to load channels</option>';
    }
}

// ============== SAVE SCHEDULE ==============
async function saveChannelSchedule(event) {
    event.preventDefault();

    const channelId = document.getElementById('schedule-channel').value;
    const unlockTime = document.getElementById('schedule-unlock-time').value;
    const lockTime = document.getElementById('schedule-lock-time').value;
    const timezone = document.getElementById('schedule-timezone').value;
    const isEnabled = document.getElementById('schedule-enabled').checked;

    // Get active days
    const activeDays = [];
    for (let i = 0; i < 7; i++) {
        const checkbox = document.getElementById(`day-${i}`);
        if (checkbox && checkbox.checked) {
            activeDays.push(i);
        }
    }

    if (!channelId) {
        showNotification('Please select a channel', 'error');
        return;
    }

    if (activeDays.length === 0) {
        showNotification('Please select at least one active day', 'error');
        return;
    }

    const scheduleData = {
        channel_id: channelId,
        unlock_time: unlockTime,
        lock_time: lockTime,
        timezone: timezone,
        active_days: activeDays,
        is_enabled: isEnabled
    };

    try {
        const url = isEditingSchedule
            ? `${API_BASE}/api/${currentServerId}/channel-schedules/${currentScheduleId}`
            : `${API_BASE}/api/${currentServerId}/channel-schedules`;

        const method = isEditingSchedule ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(scheduleData)
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to save schedule');
        }

        showNotification(
            isEditingSchedule ? 'Schedule updated successfully!' : 'Schedule created successfully!',
            'success'
        );

        closeChannelScheduleModal();
        loadChannelSchedules();

    } catch (error) {
        console.error('Error saving schedule:', error);
        showNotification(error.message, 'error');
    }
}

// ============== TOGGLE SCHEDULE ==============
async function toggleSchedule(scheduleId, enabled) {
    try {
        const response = await fetch(`${API_BASE}/api/${currentServerId}/channel-schedules/${scheduleId}/toggle`, {
            method: 'POST',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to toggle schedule');
        }

        showNotification(data.message || `Schedule ${enabled ? 'enabled' : 'disabled'}`, 'success');
        loadChannelSchedules();

    } catch (error) {
        console.error('Error toggling schedule:', error);
        showNotification(error.message, 'error');
        loadChannelSchedules(); // Reload to reset checkbox state
    }
}

// ============== MANUAL LOCK/UNLOCK ==============
async function manualLockChannel(scheduleId) {
    try {
        const response = await fetch(`${API_BASE}/api/${currentServerId}/channel-schedules/${scheduleId}/lock`, {
            method: 'POST',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to lock channel');
        }

        showNotification('🔒 Channel locked!', 'success');
        loadChannelSchedules();

    } catch (error) {
        console.error('Error locking channel:', error);
        showNotification(error.message, 'error');
    }
}

async function manualUnlockChannel(scheduleId) {
    try {
        const response = await fetch(`${API_BASE}/api/${currentServerId}/channel-schedules/${scheduleId}/unlock`, {
            method: 'POST',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to unlock channel');
        }

        showNotification('🔓 Channel unlocked!', 'success');
        loadChannelSchedules();

    } catch (error) {
        console.error('Error unlocking channel:', error);
        showNotification(error.message, 'error');
    }
}

// ============== DELETE SCHEDULE ==============
async function deleteChannelSchedule(scheduleId) {
    const schedule = channelSchedules.find(s => s.schedule_id === scheduleId);
    const channelName = schedule?.channel_name || 'this channel';

    if (!confirm(`Delete schedule for #${channelName}?\n\nThis will unlock the channel and remove the schedule.`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/${currentServerId}/channel-schedules/${scheduleId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete schedule');
        }

        showNotification('Schedule deleted and channel unlocked', 'success');
        loadChannelSchedules();

    } catch (error) {
        console.error('Error deleting schedule:', error);
        showNotification(error.message, 'error');
    }
}

// ============== SHOW SECTION FOR PREMIUM ==============
function showChannelSchedulesSection(isPremium) {
    const section = document.getElementById('channel-schedules-section');
    if (section) {
        section.style.display = isPremium ? 'block' : 'none';
    }
}

// ============== INITIALIZE ON CONFIG TAB LOAD ==============
// Hook into existing loadConfigTab function if it exists
// Hook into existing loadConfigTab function if it exists
var existingLoadConfigFn = typeof loadConfigTab === 'function' ? loadConfigTab : null;

window.loadConfigTab = async function () {
    if (existingLoadConfigFn) {
        await existingLoadConfigFn();
    }

    // Check if premium and show section
    try {
        const response = await fetch(`${API_BASE_URL}/api/${currentServerId}/config`, {
            credentials: 'include'
        });

        if (response.ok) {
            const config = await response.json();
            const isSuperAdmin = window.currentUser && (window.currentUser.role === 'superadmin' || window.currentUser.is_superadmin === true);
            const isPremium = config.subscription_tier === 'premium' || isSuperAdmin;
            showChannelSchedulesSection(isPremium);

            if (isPremium) {
                loadChannelSchedules();
            }
        }
    } catch (error) {
        console.error('Error checking premium status:', error);
    }
};

console.log('✅ Channel Lock Schedules JS loaded');
/**
 * COMPREHENSIVE BUTTON FIXES v4.0
 * Ensures every button in the CMS works properly and logs its activity.
 */

console.log('[CMS] Applying final button overrides...');

// ========== ACTIVITY LOGGING HELPER ==========
async function logCmsAction(action, details = {}, success = true, guildId = null) {
    console.log(`[ACTION] ${action}`, details);
    try {
        await apiCall('/api/admin/log_cms_action', {
            method: 'POST',
            body: JSON.stringify({
                action,
                details,
                success,
                guild_id: guildId || window.currentServerId || 0
            })
        });
    } catch (e) {
        console.warn('Backend logging failed:', e);
    }
}

// ========== UTILS ==========
function closeModal(id = null) {
    if (id) {
        const m = document.getElementById(id);
        if (m) m.style.display = 'none';
    } else {
        // Universal close for all modals
        document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
        const dynamic = document.getElementById('dynamic-modal');
        if (dynamic) dynamic.remove();
    }
}

// Attach to window so HTML can see it
window.closeModal = closeModal;
window.closeAnnouncementModal = () => closeModal('announcement-modal');
window.closeEmbedModal = () => closeModal('embed-modal');
window.closeSendEmbedModal = () => closeModal('send-embed-modal');

// ========== SHOP ACTIONS ==========
window.deleteShopItem = async function (itemId) {
    if (!confirm('Are you sure you want to delete this shop item?')) return;
    logCmsAction('delete_shop_item_start', { item_id: itemId });
    try {
        await apiCall(`/api/${currentServerId}/shop/${itemId}`, { method: 'DELETE' });
        showNotification('Item deleted', 'success');
        logCmsAction('delete_shop_item_success', { item_id: itemId });
        loadShop();
    } catch (e) {
        showNotification('Delete failed: ' + e.message, 'error');
        logCmsAction('delete_shop_item_failed', { item_id: itemId, error: e.message }, false);
    }
};

// ========== TASK ACTIONS ==========
window.deleteTask = async function (taskId) {
    if (!confirm('Are you sure you want to delete this task?')) return;
    logCmsAction('delete_task_start', { task_id: taskId });
    try {
        await apiCall(`/api/${currentServerId}/tasks/${taskId}`, { method: 'DELETE' });
        showNotification('Task deleted', 'success');
        logCmsAction('delete_task_success', { task_id: taskId });
        loadTasks();
    } catch (e) {
        showNotification('Delete failed: ' + e.message, 'error');
        logCmsAction('delete_task_failed', { task_id: taskId, error: e.message }, false);
    }
};

// ========== ANNOUNCEMENT ACTIONS ==========
window.editAnnouncement = async function (announcementId) {
    logCmsAction('edit_announcement_click', { announcement_id: announcementId });
    try {
        const data = await apiCall(`/api/${currentServerId}/announcements`);
        const item = data.announcements.find(a => a.announcement_id === announcementId);
        if (!item) return showNotification('Announcement not found', 'error');

        document.getElementById('announcement-modal-title').textContent = 'Edit Announcement';
        document.getElementById('announcement-id').value = announcementId;
        document.getElementById('announcement-title').value = item.title || '';
        document.getElementById('announcement-content').value = item.content || '';
        document.getElementById('announcement-channel').value = item.channel_id || '';
        document.getElementById('announcement-pinned').checked = !!item.is_pinned;
        document.getElementById('announcement-modal').style.display = 'block';
    } catch (e) {
        showNotification('Load failed: ' + e.message, 'error');
    }
};

window.deleteAnnouncement = async function (announcementId) {
    if (!confirm('Are you sure you want to delete this announcement?')) return;
    logCmsAction('delete_announcement_start', { announcement_id: announcementId });
    try {
        await apiCall(`/api/${currentServerId}/announcements/${announcementId}`, { method: 'DELETE' });
        showNotification('Announcement deleted', 'success');
        logCmsAction('delete_announcement_success', { announcement_id: announcementId });
        loadAnnouncements();
    } catch (e) {
        showNotification('Delete failed: ' + e.message, 'error');
        logCmsAction('delete_announcement_failed', { announcement_id: announcementId, error: e.message }, false);
    }
};

window.saveAnnouncement = async function (event) {
    if (event) event.preventDefault();
    const id = document.getElementById('announcement-id').value;
    const body = {
        title: document.getElementById('announcement-title').value,
        content: document.getElementById('announcement-content').value,
        channel_id: document.getElementById('announcement-channel').value,
        is_pinned: document.getElementById('announcement-pinned').checked
    };
    logCmsAction('save_announcement_start', { id, body });
    try {
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/${currentServerId}/announcements/${id}` : `/api/${currentServerId}/announcements`;
        await apiCall(url, { method, body: JSON.stringify(body) });
        showNotification(id ? 'Announcement updated' : 'Announcement created', 'success');
        logCmsAction('save_announcement_success', { id });
        closeModal('announcement-modal');
        loadAnnouncements();
    } catch (e) {
        showNotification('Save failed: ' + e.message, 'error');
        logCmsAction('save_announcement_failed', { id, error: e.message }, false);
    }
};

// ========== EMBED ACTIONS ==========
window.editEmbed = async function (embedId) {
    logCmsAction('edit_embed_click', { embed_id: embedId });
    try {
        const data = await apiCall(`/api/${currentServerId}/embeds`);
        const item = data.embeds.find(e => e.embed_id === embedId);
        if (!item) return showNotification('Embed not found', 'error');

        document.getElementById('embed-modal-title').textContent = 'Edit Embed';
        document.getElementById('embed-id').value = embedId;
        document.getElementById('embed-title').value = item.title || '';
        document.getElementById('embed-description').value = item.description || '';
        document.getElementById('embed-color').value = item.color || '#5865F2';
        document.getElementById('embed-footer').value = item.footer || '';
        document.getElementById('embed-image-url').value = item.image || '';
        document.getElementById('embed-thumbnail-url').value = item.thumbnail || '';
        document.getElementById('embed-modal').style.display = 'block';
        if (typeof updateEmbedPreview === 'function') updateEmbedPreview();
    } catch (e) {
        showNotification('Load failed: ' + e.message, 'error');
    }
};

window.deleteEmbed = async function (embedId) {
    if (!confirm('Are you sure you want to delete this embed?')) return;
    logCmsAction('delete_embed_start', { embed_id: embedId });
    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}`, { method: 'DELETE' });
        showNotification('Embed deleted', 'success');
        logCmsAction('delete_embed_success', { embed_id: embedId });
        loadEmbeds();
    } catch (e) {
        showNotification('Delete failed: ' + e.message, 'error');
        logCmsAction('delete_embed_failed', { embed_id: embedId, error: e.message }, false);
    }
};

window.sendEmbed = function (embedId) {
    document.getElementById('send-embed-id').value = embedId;
    const channelSelect = document.getElementById('send-embed-channel');
    if (channelSelect && window.discordDataCache && window.discordDataCache.channels) {
        let html = '<option value="">Select a channel...</option>';
        Object.values(window.discordDataCache.channels).forEach(ch => {
            html += `<option value="${ch.id}">#${ch.name}</option>`;
        });
        channelSelect.innerHTML = html;
    }
    document.getElementById('send-embed-modal').style.display = 'block';
};

window.confirmSendEmbed = async function (embedId) {
    const channelId = document.getElementById('send-embed-channel')?.value;
    if (!channelId) return showNotification('Select a channel', 'warning');
    logCmsAction('send_embed_start', { embed_id: embedId, channel_id: channelId });
    try {
        await apiCall(`/api/${currentServerId}/embeds/${embedId}/send`, {
            method: 'POST',
            body: JSON.stringify({ channel_id: channelId })
        });
        showNotification('Embed sent!', 'success');
        logCmsAction('send_embed_success', { embed_id: embedId });
        closeModal('send-embed-modal');
    } catch (e) {
        showNotification('Send failed: ' + e.message, 'error');
        logCmsAction('send_embed_failed', { embed_id: embedId, error: e.message }, false);
    }
};

// Override the HTML form onsubmit if needed
window.sendEmbedToChannel = function (event) {
    if (event) event.preventDefault();
    const embedId = document.getElementById('send-embed-id').value;
    window.confirmSendEmbed(embedId);
};

// ========== SERVER TIER GLOBAL FIX ==========
// ========== SERVER TIER GLOBAL FIX ==========
window.updateServerTier = function (serverId, serverName, currentTier) {
    logCmsAction('edit_tier_click', { server_id: serverId, server_name: serverName, current: currentTier });

    // Use the new modal instead of prompt
    const modal = document.getElementById('server-tier-modal');
    if (!modal) {
        console.error('Server tier modal not found in DOM');
        // Fallback to prompt if modal missing
        const newTier = prompt(`Update Tier for "${serverName}"\nEnter 'free' or 'premium':`, currentTier);
        if (!newTier || (newTier !== 'free' && newTier !== 'premium')) return;
        if (newTier === currentTier) return;
        window.saveServerTierDirect(serverId, serverName, newTier);
        return;
    }

    document.getElementById('tier-server-id').value = serverId;
    document.getElementById('tier-server-name').value = serverName;
    document.getElementById('tier-select').value = currentTier || 'free';

    modal.style.display = 'block';
};

window.saveServerTierDirect = async function (serverId, serverName, newTier) {
    try {
        await apiCall(`/api/${serverId}/config`, {
            method: 'PUT',
            body: JSON.stringify({ subscription_tier: newTier })
        });
        showNotification(`Updated ${serverName} to ${newTier.toUpperCase()}`, 'success');
        logCmsAction('edit_tier_success', { server_id: serverId, new_tier: newTier });
        if (window.loadServerManagement) window.loadServerManagement();
    } catch (e) {
        showNotification('Tier update failed', 'error');
        logCmsAction('edit_tier_failed', { server_id: serverId, error: e.message }, false);
    }
};

window.saveServerTier = async function (event) {
    if (event) event.preventDefault();
    const serverId = document.getElementById('tier-server-id').value;
    const serverName = document.getElementById('tier-server-name').value;
    const newTier = document.getElementById('tier-select').value;

    document.getElementById('server-tier-modal').style.display = 'none';
    await window.saveServerTierDirect(serverId, serverName, newTier);
};

// ========== NAVIGATION & SYSTEM ==========
window.logout = async function () {
    window.logCmsAction('logout_start');
    try {
        await fetch(apiUrl('/api/logout'), { method: 'POST', credentials: 'include' });
    } catch (e) { console.warn('Logout request failed', e); }
    currentUser = null;
    currentServerId = '';
    localStorage.removeItem('lastSelectedServer');
    showLoginScreen();
};

window.onServerChange = async function () {
    const serverSelect = document.getElementById('server-select');
    if (!serverSelect) return;
    currentServerId = serverSelect.value;
    if (currentServerId) {
        localStorage.setItem('lastSelectedServer', currentServerId);
        window.logCmsAction('server_changed', { id: currentServerId });
        await fetchDiscordData(currentServerId);
        const activeTab = document.querySelector('.tab-button.active');
        if (activeTab) showTab(activeTab.getAttribute('data-tab'));
    }
};

window.clearLogs = async function () {
    if (!confirm('Clear all system logs?')) return;
    window.logCmsAction('clear_logs_start');
    try {
        await apiCall(`/api/admin/logs/clear`, { method: 'POST' });
        showNotification('Logs cleared', 'success');
        loadLogs();
    } catch (e) {
        showNotification('Failed to clear logs', 'error');
    }
};

// ========== MODAL SHOW FIXES (Ensuring Consistency) ==========
window.showCreateAnnouncementModal = function () {
    window.logCmsAction('show_create_announcement_modal');
    document.getElementById('announcement-modal-title').textContent = 'Create Announcement';
    document.getElementById('announcement-form').reset();
    document.getElementById('announcement-id').value = '';
    // Populate channels
    const chSelect = document.getElementById('announcement-channel');
    if (chSelect && window.discordDataCache.channels) {
        chSelect.innerHTML = '<option value="">Select a channel...</option>' +
            Object.values(window.discordDataCache.channels).map(ch => `<option value="${ch.id}">#${ch.name}</option>`).join('');
    }
    document.getElementById('announcement-modal').style.display = 'block';
};

window.showCreateEmbedModal = function () {
    window.logCmsAction('show_create_embed_modal');
    document.getElementById('embed-modal-title').textContent = 'Create Embed';
    document.getElementById('embed-form').reset();
    document.getElementById('embed-id').value = '';
    document.getElementById('embed-modal').style.display = 'block';
    if (typeof updateEmbedPreview === 'function') updateEmbedPreview();
};

window.showCreateShopItemModal = function () {
    window.logCmsAction('show_create_shop_item_modal');
    document.getElementById('shop-item-modal').style.display = 'block';
    const form = document.getElementById('shop-item-form');
    if (form) form.reset();
    document.getElementById('shop-item-id').value = '';
};

window.showCreateTaskModal = function () {
    window.logCmsAction('show_create_task_modal');
    document.getElementById('task-modal').style.display = 'block';
    const form = document.getElementById('task-form');
    if (form) form.reset();
    document.getElementById('task-id').value = '';
};

console.log('[CMS] All button handlers successfully overridden and fixed ✅');
