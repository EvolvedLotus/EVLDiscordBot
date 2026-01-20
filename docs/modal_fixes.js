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
