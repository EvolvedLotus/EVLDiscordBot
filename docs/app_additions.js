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
            data.servers.forEach(server => {
                const option = document.createElement('option');
                option.value = server.id;
                option.textContent = server.name;
                serverSelect.appendChild(option);
            });
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

// ========== ENHANCED SHOP ITEM MODAL ==========

// Override the existing showCreateShopItemModal
const originalShowCreateShopItemModal = window.showCreateShopItemModal;
window.showCreateShopItemModal = function () {
    if (originalShowCreateShopItemModal) {
        originalShowCreateShopItemModal();
    }

    // Add emoji picker button if not already added
    const emojiInput = document.getElementById('shop-item-emoji');
    if (emojiInput && !emojiInput.nextElementSibling?.classList.contains('emoji-picker-btn')) {
        const pickerBtn = document.createElement('button');
        pickerBtn.type = 'button';
        pickerBtn.className = 'emoji-picker-btn';
        pickerBtn.textContent = '😀 Pick Emoji';
        pickerBtn.onclick = () => showEmojiPicker('shop-item-emoji');
        emojiInput.parentNode.appendChild(pickerBtn);
    }
};

// Override saveShopItem to show success message
const originalSaveShopItem = window.saveShopItem;
window.saveShopItem = async function (event) {
    event.preventDefault();

    const itemId = document.getElementById('shop-item-id').value;
    const name = document.getElementById('shop-item-name').value;
    const description = document.getElementById('shop-item-description').value;
    const price = parseInt(document.getElementById('shop-item-price').value);
    const category = document.getElementById('shop-item-category').value;
    const stock = parseInt(document.getElementById('shop-item-stock').value);
    const emoji = document.getElementById('shop-item-emoji').value || '🎁';

    const itemData = {
        name,
        description,
        price,
        category,
        stock,
        emoji
    };

    // If category is role, add role_id in metadata
    if (category === 'role') {
        const roleId = document.getElementById('shop-item-role-id')?.value;
        if (!roleId) {
            showNotification('Please select a role', 'error');
            return;
        }
        itemData.metadata = {
            role_id: roleId
        };
    }

    try {
        if (itemId) {
            await apiCall(`/api/${currentServerId}/shop/${itemId}`, {
                method: 'PUT',
                body: JSON.stringify(itemData)
            });
            showNotification(`✅ Shop item "${name}" updated successfully!`, 'success');
        } else {
            await apiCall(`/api/${currentServerId}/shop`, {
                method: 'POST',
                body: JSON.stringify(itemData)
            });
            showNotification(`✅ Shop item "${name}" created successfully!`, 'success');
        }

        closeShopItemModal();
        loadShop();
    } catch (error) {
        showNotification(`❌ Failed to save shop item: ${error.message}`, 'error');
    }
};

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
