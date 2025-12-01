// ========== MISSING FUNCTIONS FIX ==========
// This file contains all the missing functions that need to be added to app.js

// ========== SHOP ITEM FUNCTIONS ==========

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
        closeModal();
        loadShop();
    } catch (error) {
        console.error('Save shop item error:', error);
        showNotification('Failed to save shop item: ' + error.message, 'error');
    }
}

// ========== TASK MODAL FUNCTIONS ==========

function showCreateTaskModal() {
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
        <label>Duration (hours)</label>
        <input type="number" id="task-duration" class="form-control" min="1" value="24">
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
}

function toggleTaskRoleSelect() {
    const category = document.getElementById('task-category').value;
    const roleGroup = document.getElementById('task-role-select-group');
    if (category === 'role_required') {
        roleGroup.style.display = 'block';
    } else {
        roleGroup.style.display = 'none';
    }
}

async function saveTask(event) {
    if (event) event.preventDefault();

    const taskId = document.getElementById('task-id')?.value;
    const name = document.getElementById('task-name').value;
    const description = document.getElementById('task-description').value;
    const reward = document.getElementById('task-reward').value;
    const duration = document.getElementById('task-duration')?.value || 24;
    const maxClaims = document.getElementById('task-max-claims')?.value || -1;
    const category = document.getElementById('task-category').value;
    const roleId = document.getElementById('task-role')?.value;
    const isGlobal = document.getElementById('task-is-global')?.checked || false;

    if (!name || !description || !reward) {
        showNotification('Please fill all required fields', 'warning');
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
