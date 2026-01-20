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
            adContainer.style.display = tier === 'free' ? 'block' : 'none';
        }

        // Store tier in global variable for other functions to check
        window.currentGuildTier = tier;

    } catch (e) {
        console.error("Failed to update tier UI:", e);
    }
}

