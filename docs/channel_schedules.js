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
        const response = await fetch(`${API_BASE}/api/${currentServerId}/channel-schedules/${scheduleId}`, {
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
        const response = await fetch(`${API_BASE}/api/${currentServerId}/config`, {
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
