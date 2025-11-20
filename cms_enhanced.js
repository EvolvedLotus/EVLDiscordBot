// Enhanced CMS Script with Full Functionality
// This file provides complete CMS functionality with Discord integration

const API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8080'
    : (window.API_BASE_URL || 'https://evldiscordbot-production.up.railway.app');

let currentServerId = '';
let currentUser = null;
let discordDataCache = {
    users: {},
    channels: {},
    roles: {}
};

// ========== UTILITY FUNCTIONS ==========

function apiUrl(endpoint) {
    return `${API_BASE_URL}${endpoint}`;
}

async function apiCall(endpoint, options = {}) {
    options.credentials = 'include';
    options.headers = options.headers || {};
    options.headers['Content-Type'] = 'application/json';

    try {
        const response = await fetch(apiUrl(endpoint), options);

        if (response.status === 401) {
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

function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container') || createNotificationContainer();

    const toast = document.createElement('div');
    toast.className = `notification ${type}`;
    toast.innerHTML = `
        <div class="notification-content">
            <span class="notification-icon">${getNotificationIcon(type)}</span>
            <span class="notification-message">${message}</span>
        </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function createNotificationContainer() {
    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);
    return container;
}

function getNotificationIcon(type) {
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    return icons[type] || icons.info;
}

// ========== DISCORD DATA HELPERS ==========

async function fetchDiscordData(serverId) {
    try {
        const [users, channels, roles] = await Promise.all([
            apiCall(`/api/${serverId}/users`),
            apiCall(`/api/${serverId}/channels`),
            apiCall(`/api/${serverId}/roles`)
        ]);

        // Cache the data
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

// ========== ENHANCED TAB LOADERS ==========

async function loadAnnouncements() {
    if (!currentServerId) return;
    const content = document.getElementById('tab-content');
    content.innerHTML = '<div class="loading">Loading announcements...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/announcements`);

        if (data && data.announcements && data.announcements.length > 0) {
            let html = `
                <div class="announcements-header">
                    <h2>📢 Announcements</h2>
                    <div class="announcements-actions">
                        <button onclick="showCreateAnnouncementModal()" class="btn-success">➕ Create Announcement</button>
                        <button onclick="loadAnnouncements()" class="btn-primary">🔄 Refresh</button>
                    </div>
                </div>
                <div class="announcements-list">
            `;

            data.announcements.forEach(announcement => {
                const channelName = getChannelDisplay(announcement.channel_id);
                const createdBy = getUserDisplay(announcement.created_by);
                const createdDate = new Date(announcement.created_at).toLocaleString();

                html += `
                    <div class="announcement-card">
                        <div class="announcement-header">
                            <div class="announcement-title">
                                <span class="announcement-type">📢</span>
                                <h3>${announcement.title || 'Untitled Announcement'}</h3>
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
                            <span>👤 By ${createdBy}</span>
                            <span>🕒 ${createdDate}</span>
                            ${announcement.message_id ? `<a href="https://discord.com/channels/${currentServerId}/${announcement.channel_id}/${announcement.message_id}" target="_blank">🔗 View in Discord</a>` : ''}
                        </div>
                    </div>
                `;
            });

            html += '</div></div>';
            content.innerHTML = html;
        } else {
            content.innerHTML = `
                <div class="empty-state">
                    <h3>No announcements yet</h3>
                    <p>Create your first announcement to get started!</p>
                    <button onclick="showCreateAnnouncementModal()" class="btn-success">➕ Create Announcement</button>
                </div>
            `;
        }
    } catch (error) {
        content.innerHTML = `<div class="error-state">Failed to load announcements: ${error.message}</div>`;
    }
}

async function loadEmbeds() {
    if (!currentServerId) return;
    const list = document.getElementById('embeds-list');
    list.innerHTML = '<div class="loading">Loading embeds...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/embeds`);

        if (data && data.embeds && data.embeds.length > 0) {
            let html = '<div class="embeds-grid">';

            data.embeds.forEach(embed => {
                const channelName = getChannelDisplay(embed.channel_id);
                const createdBy = getUserDisplay(embed.created_by);

                html += `
                    <div class="embed-card">
                        <div class="embed-preview" style="border-left: 4px solid ${embed.color || '#5865F2'}">
                            <h4>${embed.title || 'Untitled Embed'}</h4>
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
            list.innerHTML = `
                <div class="empty-state">
                    <h3>No embeds created yet</h3>
                    <p>Create your first embed to get started!</p>
                </div>
            `;
        }
    } catch (error) {
        list.innerHTML = `<div class="error-state">Failed to load embeds: ${error.message}</div>`;
    }
}

async function loadTransactions() {
    if (!currentServerId) return;
    const list = document.getElementById('transactions-list');
    list.innerHTML = '<div class="loading">Loading transactions...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/transactions`);

        if (data && data.transactions && data.transactions.length > 0) {
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

            data.transactions.forEach(txn => {
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
            list.innerHTML = html;
        } else {
            list.innerHTML = '<div class="empty-state">No transactions found</div>';
        }
    } catch (error) {
        list.innerHTML = `<div class="error-state">Failed to load transactions: ${error.message}</div>`;
    }
}

async function loadLogs() {
    if (!currentServerId) return;
    const content = document.getElementById('logs-content') || document.querySelector('#logs .content-area');
    if (!content) return;

    content.innerHTML = '<div class="loading">Loading logs...</div>';

    try {
        const data = await apiCall(`/api/${currentServerId}/logs`);

        if (data && data.logs && data.logs.length > 0) {
            let html = `
                <div class="logs-container">
                    <div class="logs-filters">
                        <select id="log-type-filter" onchange="filterLogs()">
                            <option value="">All Types</option>
                            <option value="moderation">Moderation</option>
                            <option value="transaction">Transaction</option>
                            <option value="task">Task</option>
                            <option value="shop">Shop</option>
                        </select>
                        <input type="date" id="log-date-filter" onchange="filterLogs()">
                    </div>
                    <div class="logs-list">
            `;

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
                        ${log.details ? `<div class="log-metadata">${JSON.stringify(log.details, null, 2)}</div>` : ''}
                    </div>
                `;
            });

            html += '</div></div>';
            content.innerHTML = html;
        } else {
            content.innerHTML = '<div class="empty-state">No logs found</div>';
        }
    } catch (error) {
        content.innerHTML = `<div class="error-state">Failed to load logs: ${error.message}</div>`;
    }
}

async function loadServerSettingsTab() {
    if (!currentServerId) return;
    const content = document.getElementById('server-settings-content');
    if (!content) return;

    try {
        // Fetch Discord data first
        await fetchDiscordData(currentServerId);

        // Populate channel dropdowns
        const channels = Object.values(discordDataCache.channels);
        const channelOptions = channels.map(ch =>
            `<option value="${ch.id}">${ch.name}</option>`
        ).join('');

        // Populate all channel selectors
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

        showNotification('Server settings loaded', 'success');
    } catch (error) {
        showNotification('Failed to load server settings', 'error');
        console.error(error);
    }
}

async function loadPermissionsTab() {
    if (!currentServerId) return;
    const content = document.getElementById('permissions-content');
    if (!content) return;

    try {
        // Fetch Discord data
        await fetchDiscordData(currentServerId);

        // Populate role dropdowns
        const roles = Object.values(discordDataCache.roles);
        const rolesList = document.getElementById('roles-list');

        if (rolesList) {
            let html = '<div class="roles-grid">';
            roles.forEach(role => {
                const colorStyle = role.color ? `style="border-left: 4px solid #${role.color.toString(16).padStart(6, '0')}"` : '';
                html += `
                    <div class="role-card" ${colorStyle}>
                        <h4>${role.name}</h4>
                        <div class="role-info">
                            <span>Position: ${role.position}</span>
                            <span>Members: ${role.member_count || 0}</span>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            rolesList.innerHTML = html;
        }

        // Populate user dropdowns
        const users = Object.values(discordDataCache.users);
        const userOptions = users.map(user =>
            `<option value="${user.user_id}">${user.username || user.display_name || user.user_id}</option>`
        ).join('');

        ['target-user-select', 'mod-target-user'].forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                select.innerHTML = '<option value="">Select a user...</option>' + userOptions;
            }
        });

        // Populate role assignment dropdowns
        const roleOptions = roles.map(role =>
            `<option value="${role.id}">${role.name}</option>`
        ).join('');

        const assignRoleSelect = document.getElementById('assign-role-select');
        if (assignRoleSelect) {
            assignRoleSelect.innerHTML = '<option value="">Select a role...</option>' + roleOptions;
        }

        showNotification('Permissions loaded', 'success');
    } catch (error) {
        showNotification('Failed to load permissions', 'error');
        console.error(error);
    }
}

// ========== MODAL FUNCTIONS ==========

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

function createModal(title, content) {
    const modal = document.createElement('div');
    modal.className = 'modal';
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
    return modal;
}

function closeModal() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => modal.remove());
}

function getChannelOptions() {
    const channels = Object.values(discordDataCache.channels);
    return channels.map(ch => `<option value="${ch.id}">${ch.name}</option>`).join('');
}

// ========== ACTION FUNCTIONS ==========

async function createAnnouncement() {
    const title = document.getElementById('announcement-title').value;
    const content = document.getElementById('announcement-content').value;
    const channelId = document.getElementById('announcement-channel').value;
    const isPinned = document.getElementById('announcement-pin').checked;

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
        showNotification('Failed to create announcement', 'error');
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
        showNotification('Failed to delete announcement', 'error');
    }
}

// Export functions to global scope
window.loadAnnouncements = loadAnnouncements;
window.loadEmbeds = loadEmbeds;
window.loadTransactions = loadTransactions;
window.loadLogs = loadLogs;
window.loadServerSettingsTab = loadServerSettingsTab;
window.loadPermissionsTab = loadPermissionsTab;
window.showCreateAnnouncementModal = showCreateAnnouncementModal;
window.createAnnouncement = createAnnouncement;
window.deleteAnnouncement = deleteAnnouncement;
window.closeModal = closeModal;
window.fetchDiscordData = fetchDiscordData;
window.getUserDisplay = getUserDisplay;
window.getChannelDisplay = getChannelDisplay;
window.getRoleDisplay = getRoleDisplay;
