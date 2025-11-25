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

    // Add Discord login button after the regular login form
    const discordButton = document.createElement('button');
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

/**
 * Handle Discord OAuth login flow
 */
async function handleDiscordLogin() {
    try {
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

        // Show dashboard
        showNotification(`Welcome, ${data.user.username}!`, 'success');
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
