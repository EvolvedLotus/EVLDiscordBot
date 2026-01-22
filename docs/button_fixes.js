/**
 * BUTTON FIXES - Ensures all buttons work properly
 * This file runs LAST to guarantee all functions are attached to window
 */

console.log('[ButtonFixes] Loading...');

// ========== MODAL SHOW FUNCTIONS ==========

// Shop Item Modal
window.showCreateShopItemModal = function () {
    console.log('[ButtonFixes] showCreateShopItemModal called');
    const modal = document.getElementById('shop-item-modal');
    if (modal) {
        const form = document.getElementById('shop-item-form');
        if (form) form.reset();
        const idField = document.getElementById('shop-item-id');
        if (idField) idField.value = '';
        modal.style.display = 'block';
    } else {
        console.error('[ButtonFixes] shop-item-modal not found!');
        alert('Shop Item modal not found. Please refresh the page.');
    }
};

// Task Modal
window.showCreateTaskModal = function () {
    console.log('[ButtonFixes] showCreateTaskModal called');
    const modal = document.getElementById('task-modal');
    if (modal) {
        const form = document.getElementById('task-form');
        if (form) form.reset();
        const idField = document.getElementById('task-id');
        if (idField) idField.value = '';
        modal.style.display = 'block';
    } else {
        console.error('[ButtonFixes] task-modal not found!');
        alert('Task modal not found. Please refresh the page.');
    }
};

// Announcement Modal
window.showCreateAnnouncementModal = function () {
    console.log('[ButtonFixes] showCreateAnnouncementModal called');
    const modal = document.getElementById('announcement-modal');
    if (modal) {
        const form = document.getElementById('announcement-form');
        if (form) form.reset();
        modal.style.display = 'block';

        // Populate channel dropdown
        const channelSelect = document.getElementById('announcement-channel');
        if (channelSelect && window.discordDataCache && window.discordDataCache.channels) {
            let html = '<option value="">Select a channel...</option>';
            Object.values(window.discordDataCache.channels).forEach(ch => {
                html += `<option value="${ch.id}">#${ch.name}</option>`;
            });
            channelSelect.innerHTML = html;
        }
    } else {
        console.error('[ButtonFixes] announcement-modal not found!');
        alert('Announcement modal not found. Please refresh the page.');
    }
};

// Embed Modal
window.showCreateEmbedModal = function () {
    console.log('[ButtonFixes] showCreateEmbedModal called');
    const modal = document.getElementById('embed-modal');
    if (modal) {
        const form = document.getElementById('embed-form');
        if (form) form.reset();
        const idField = document.getElementById('embed-id');
        if (idField) idField.value = '';
        modal.style.display = 'block';

        // Initialize preview if function exists
        if (typeof updateEmbedPreview === 'function') {
            updateEmbedPreview();
        }
    } else {
        console.error('[ButtonFixes] embed-modal not found!');
        alert('Embed modal not found. Please refresh the page.');
    }
};

// ========== SHOP STATISTICS & VALIDATION ==========

window.viewShopStatistics = async function () {
    console.log('[ButtonFixes] viewShopStatistics called');
    if (!window.currentServerId) {
        alert('Please select a server first.');
        return;
    }

    try {
        // Try to fetch actual stats
        const data = await window.apiCall(`/api/${window.currentServerId}/shop/stats`);
        if (data) {
            alert(`Shop Statistics:\n\n- Total Items: ${data.total_items || 0}\n- Total Sales: ${data.total_sales || 0}\n- Total Revenue: ${data.total_revenue || 0} coins`);
        }
    } catch (e) {
        // Fallback
        alert('Shop Statistics:\n\n- Statistics are being calculated...\n- Try refreshing the shop to see updated data.');
    }
};

window.validateShopIntegrity = async function () {
    console.log('[ButtonFixes] validateShopIntegrity called');
    if (!window.currentServerId) {
        alert('Please select a server first.');
        return;
    }

    if (window.showNotification) {
        window.showNotification('Validating shop integrity...', 'info');
    }

    try {
        const data = await window.apiCall(`/api/${window.currentServerId}/shop`);
        if (data && data.items) {
            const issues = [];
            data.items.forEach(item => {
                if (!item.name) issues.push(`Item ${item.item_id} has no name`);
                if (item.price < 0) issues.push(`${item.name} has negative price`);
            });

            if (issues.length === 0) {
                if (window.showNotification) {
                    window.showNotification('✅ Shop integrity check passed! All items valid.', 'success');
                } else {
                    alert('✅ Shop integrity check passed! All items valid.');
                }
            } else {
                alert('⚠️ Issues found:\n\n' + issues.join('\n'));
            }
        }
    } catch (e) {
        if (window.showNotification) {
            window.showNotification('Failed to validate shop', 'error');
        }
    }
};

// ========== SAVE HANDLERS ==========

window.saveShopItem = async function (event) {
    if (event) event.preventDefault();
    console.log('[ButtonFixes] saveShopItem called');

    const itemId = document.getElementById('shop-item-id')?.value;
    const name = document.getElementById('item-name')?.value;
    const price = document.getElementById('item-price')?.value;
    const description = document.getElementById('item-description')?.value || '';
    const roleId = document.getElementById('item-role-id')?.value || null;
    const stock = document.getElementById('item-stock')?.value || -1;

    if (!name || !price) {
        alert('Please fill in Item Name and Price.');
        return;
    }

    const payload = {
        name,
        price: parseInt(price),
        description,
        role_id: roleId,
        stock: parseInt(stock)
    };

    try {
        let url = `/api/${window.currentServerId}/shop`;
        let method = 'POST';

        if (itemId) {
            url += `/${itemId}`;
            method = 'PUT';
        }

        const response = await window.apiCall(url, {
            method: method,
            body: JSON.stringify(payload)
        });

        if (response) {
            if (window.showNotification) {
                window.showNotification(itemId ? 'Item updated!' : 'Item created!', 'success');
            }
            document.getElementById('shop-item-modal').style.display = 'none';
            if (window.loadShop) window.loadShop();
        }
    } catch (e) {
        console.error('[ButtonFixes] saveShopItem error:', e);
        if (window.showNotification) {
            window.showNotification('Error saving item: ' + e.message, 'error');
        } else {
            alert('Error saving item: ' + e.message);
        }
    }
};

window.saveTask = async function (event) {
    if (event) event.preventDefault();
    console.log('[ButtonFixes] saveTask called');

    const taskId = document.getElementById('task-id')?.value;
    const content = document.getElementById('task-content')?.value;
    const reward = document.getElementById('task-reward')?.value;
    const type = document.getElementById('task-type')?.value || 'manual';
    const target = document.getElementById('task-target')?.value || null;

    if (!content || !reward) {
        alert('Please fill in Task Description and Reward.');
        return;
    }

    const payload = {
        content,
        reward: parseInt(reward),
        type,
        target
    };

    try {
        let url = `/api/${window.currentServerId}/tasks`;
        let method = 'POST';

        if (taskId) {
            url += `/${taskId}`;
            method = 'PUT';
        }

        const response = await window.apiCall(url, {
            method: method,
            body: JSON.stringify(payload)
        });

        if (response) {
            if (window.showNotification) {
                window.showNotification(taskId ? 'Task updated!' : 'Task created!', 'success');
            }
            document.getElementById('task-modal').style.display = 'none';
            if (window.loadTasks) window.loadTasks();
        }
    } catch (e) {
        console.error('[ButtonFixes] saveTask error:', e);
        if (window.showNotification) {
            window.showNotification('Error saving task: ' + e.message, 'error');
        } else {
            alert('Error saving task: ' + e.message);
        }
    }
};

// ========== CLOSE MODAL HANDLER ==========

window.closeModal = function () {
    // Close any visible dynamic modal
    const dynamicModal = document.getElementById('dynamic-modal');
    if (dynamicModal) dynamicModal.remove();

    // Also hide common modals
    ['shop-item-modal', 'task-modal', 'announcement-modal', 'embed-modal', 'channel-schedule-modal'].forEach(id => {
        const modal = document.getElementById(id);
        if (modal) modal.style.display = 'none';
    });
};

// ========== CLICK OUTSIDE TO CLOSE ==========

document.addEventListener('click', function (e) {
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});

// ========== ENSURE updateServerTier IS GLOBAL ==========

// This will be defined in cms_additions.js but we ensure it's callable
if (typeof window.updateServerTier !== 'function') {
    window.updateServerTier = async function (serverId, serverName, currentTier) {
        console.log('[ButtonFixes] updateServerTier fallback called');
        const newTier = prompt(`Update Tier for "${serverName}"\nEnter 'free' or 'premium':`, currentTier);

        if (!newTier || (newTier !== 'free' && newTier !== 'premium')) {
            if (newTier) alert("Invalid tier. Please enter 'free' or 'premium'.");
            return;
        }

        if (newTier === currentTier) return;

        try {
            const response = await window.apiCall(`/api/${serverId}/config`, {
                method: 'PUT',
                body: JSON.stringify({ subscription_tier: newTier })
            });

            if (response) {
                if (window.showNotification) {
                    window.showNotification(`Updated ${serverName} to ${newTier.toUpperCase()}`, 'success');
                }
                if (window.loadServerManagement) window.loadServerManagement();
            }
        } catch (e) {
            console.error('[ButtonFixes] updateServerTier error:', e);
            if (window.showNotification) {
                window.showNotification('Error updating tier', 'error');
            }
        }
    };
}

console.log('[ButtonFixes] All button handlers attached to window ✅');
