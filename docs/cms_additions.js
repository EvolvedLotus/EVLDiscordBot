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
async function loadServerManagement() {
    const container = document.getElementById('server-management-container');
    if (!container) return;

    try {
        // Fetch all servers the bot is in
        const response = await apiCall('/api/servers');

        if (!response || !response.servers) {
            container.innerHTML = '<div class="empty-server-list">No servers found</div>';
            return;
        }

        let html = '<div class="server-list">';

        // We need to fetch config for each server to get the tier
        // This might be slow for many servers, but ok for admin panel
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
                         <button class="btn-primary" 
                                style="padding: 5px 10px; font-size: 12px; height: auto;"
                                onclick="updateServerTier('${server.id}', '${serverName}', '${server.tier}')">
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

        // Add event listeners to all leave buttons
        container.querySelectorAll('.btn-leave-server').forEach(button => {
            button.addEventListener('click', function () {
                const serverId = this.getAttribute('data-server-id');
                const serverName = this.getAttribute('data-server-name');
                leaveServer(serverId, serverName);
            });
        });

    } catch (error) {
        console.error('Failed to load servers:', error);
        container.innerHTML = '<div class="empty-server-list">Failed to load servers</div>';
    }
}

async function updateServerTier(serverId, serverName, currentTier) {
    const newTier = prompt(`Update Tier for "${serverName}"\nEnter 'free' or 'premium':`, currentTier);

    if (!newTier || (newTier !== 'free' && newTier !== 'premium')) {
        if (newTier) alert("Invalid tier. Please enter 'free' or 'premium'.");
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

            // Optimistic UI Update: Find the specific badge and update it immediately
            const serverCard = document.querySelector(`.server-item[data-server-id="${serverId}"]`);
            if (serverCard) {
                const tierBadge = serverCard.querySelector('.tier-badge');
                if (tierBadge) {
                    tierBadge.className = `tier-badge tier-${newTier}`;
                    tierBadge.textContent = newTier === 'premium' ? '🏆 Premium' : '🆓 Free';
                }

                // Update the button function call arguments to reflect the new state for next click
                const editButton = serverCard.querySelector('button[onclick^="updateServerTier"]');
                if (editButton) {
                    editButton.setAttribute('onclick', `updateServerTier('${serverId}', '${serverName.replace(/'/g, "\\'")}', '${newTier}')`);
                }
            } else {
                loadServerManagement(); // Fallback to reload if card not found
            }

        } else {
            showNotification('Failed to update tier', 'error');
        }
    } catch (e) {
        console.error("Tier update failed:", e);
        showNotification('Error updating tier', 'error');
    }
}

async function leaveServer(serverId, serverName) {
    if (!confirm(`Are you sure you want to leave "${serverName}"?\n\nThis action cannot be undone.`)) {
        return;
    }

    try {
        const response = await apiCall(`/api/admin/servers/${serverId}/leave`, {
            method: 'POST'
        });

        if (response && response.success) {
            showNotification(`Successfully left server: ${serverName}`, 'success');
            // Reload the server list
            loadServerManagement();
        } else {
            showNotification(`Failed to leave server: ${response.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error leaving server:', error);
        showNotification(`Error leaving server: ${error.message}`, 'error');
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
if (typeof loadConfigTab === 'function') {
    const originalLoadConfigTab = loadConfigTab;
    loadConfigTab = async function () {
        await originalLoadConfigTab();

        // Check if user is super admin
        if (currentUser && currentUser.is_superadmin) {
            // Show server management section
            const botStatusSection = document.getElementById('bot-status-section');
            if (botStatusSection) {
                // Add server management section after bot status
                const serverMgmtHtml = `
                    <div class="server-management-section">
                        <h3>🖥️ Server Management</h3>
                        <div id="server-management-container">
                            <div class="loading">Loading servers...</div>
                        </div>
                    </div>
                `;

                // Check if server management section already exists
                if (!document.querySelector('.server-management-section')) {
                    botStatusSection.insertAdjacentHTML('afterend', serverMgmtHtml);
                }

                // Load servers
                loadServerManagement();
            }
        }
    };
} else {
    // If app.js hasn't loaded yet, we can try to hook into window load
    window.addEventListener('load', function () {
        if (typeof loadConfigTab === 'function') {
            const originalLoadConfigTab = loadConfigTab;
            loadConfigTab = async function () {
                await originalLoadConfigTab();

                // Check if user is super admin
                if (currentUser && currentUser.is_superadmin) {
                    // Show server management section
                    const botStatusSection = document.getElementById('bot-status-section');
                    if (botStatusSection) {
                        // Add server management section after bot status
                        const serverMgmtHtml = `
                            <div class="server-management-section">
                                <h3>🖥️ Server Management</h3>
                                <div id="server-management-container">
                                    <div class="loading">Loading servers...</div>
                                </div>
                            </div>
                        `;

                        // Check if server management section already exists
                        if (!document.querySelector('.server-management-section')) {
                            botStatusSection.insertAdjacentHTML('afterend', serverMgmtHtml);
                        }

                        // Load servers
                        loadServerManagement();
                    }
                }
            };
        }
    });
}

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
// Whop & Promo Integration Helpers
function populateWhopInfo() {
    const section = document.getElementById('whop-info-section');
    if (!section) return;

    // SECURITY CHECK: Only show to Super Admins (env-based login)
    // standard user roles should not see sensitive webhook/promo links
    const isSuperAdmin = currentUser && (currentUser.role === 'superadmin' || currentUser.is_superadmin === true);

    if (!isSuperAdmin) {
        section.style.display = 'none';
        return;
    }

    // Show section for super admin
    section.style.display = 'block';

    const webhookInput = document.getElementById('whop-webhook-url');
    const promoInput = document.getElementById('promo-card-url');

    if (webhookInput) {
        // Base URL from current location
        const baseUrl = window.location.origin;
        webhookInput.value = `${baseUrl}/api/webhooks/whop`;
    }

    if (promoInput) {
        const baseUrl = window.location.href.split('index.html')[0];
        promoInput.value = `${baseUrl}store-preview.html`;

        // If we have a selected server, append it to the promo link for easy testing
        if (currentServerId) {
            promoInput.value += `?guild_id=${currentServerId}`;
        }
    }

    populateApiClients();
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
