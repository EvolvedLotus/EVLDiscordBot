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

        response.servers.forEach(server => {
            html += `
                <div class="server-item" data-server-id="${server.id}">
                    <div class="server-info">
                        <div class="server-name">${escapeHtml(server.name)}</div>
                        <div class="server-id">ID: ${server.id}</div>
                        <div class="server-members">👥 ${server.member_count || 'N/A'} members</div>
                    </div>
                    <div class="server-actions">
                        <button onclick="leaveServer('${server.id}', '${escapeHtml(server.name)}')" 
                                class="btn-leave-server"
                                title="Leave this server">
                            🚪 Leave Server
                        </button>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;

    } catch (error) {
        console.error('Failed to load servers:', error);
        container.innerHTML = '<div class="empty-server-list">Failed to load servers</div>';
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
