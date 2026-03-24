import os
import re

html_path = r'C:\Users\xmarc\OneDrive\Documents\GitHub\EvolvedLotusBusiness\task-bot-discord\docs\index.html'
js_path = r'C:\Users\xmarc\OneDrive\Documents\GitHub\EvolvedLotusBusiness\task-bot-discord\docs\app.js'
css_path = r'C:\Users\xmarc\OneDrive\Documents\GitHub\EvolvedLotusBusiness\task-bot-discord\docs\styles.css'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Make sidebar nav buttons icon-only
html = re.sub(r'(<button class="tab-button[^>]*data-icon="(.*?)"[^>]*>)\s*(Dashboard|Users|Shop|Tasks|Announce|Embeds|Settings|Logs)\s*(</button>)', r'\1\n                    \2\n                \4', html, flags=re.MULTILINE|re.IGNORECASE)

# Shop actions
shop_actions_old = """<div class="header-actions">
                        <button onclick="showCreateShopItemModal()" class="btn-success">➕ Add Item</button>
                        <button onclick="viewShopStatistics()" class="btn-secondary">📊 Statistics</button>
                        <button onclick="validateShopIntegrity()" class="btn-secondary">🔍 Validate</button>
                        <button onclick="loadShop()" class="btn-primary">🔄 Refresh</button>
                    </div>"""
shop_actions_new = """<div class="header-actions">
                        <div class="action-group-left">
                            <button onclick="showCreateShopItemModal()" class="btn-success">➕ Add Item</button>
                            <button onclick="loadShop()" class="btn-primary">🔄 Refresh</button>
                        </div>
                        <div class="action-group-right">
                            <button onclick="viewShopStatistics()" class="btn-secondary">📊 Statistics</button>
                            <button onclick="validateShopIntegrity()" class="btn-secondary">🔍 Validate</button>
                        </div>
                    </div>"""
html = html.replace(shop_actions_old, shop_actions_new)

# Embeds actions
embeds_actions_old = """<div class="header-actions">
                        <button onclick="showCreateEmbedModal()" class="btn-success">➕ Create Embed</button>
                        <button id="edit-by-message-btn" class="btn-secondary"
                            onclick="showEditEmbedByMessageModal()">✏️ Edit by Link/ID</button>
                        <button onclick="loadEmbeds()" class="btn-primary">🔄 Refresh</button>
                    </div>"""
embeds_actions_new = """<div class="header-actions">
                        <div class="action-group-left">
                            <button onclick="showCreateEmbedModal()" class="btn-success">➕ Create Embed</button>
                            <button id="edit-by-message-btn" class="btn-secondary"
                                onclick="showEditEmbedByMessageModal()">✏️ Edit by Link/ID</button>
                        </div>
                        <button onclick="loadEmbeds()" class="btn-secondary btn-outline">🔄 Refresh</button>
                    </div>"""
html = html.replace(embeds_actions_old, embeds_actions_new)

# Logs actions
logs_actions_old = """<div class="header-actions">
                        <select id="log-level" onchange="loadLogs()" class="form-control" style="width: 150px;">
                            <option value="all">All Levels</option>
                            <option value="error">Errors Only</option>
                            <option value="warning">Warnings</option>
                            <option value="info">Info</option>
                        </select>
                        <button onclick="clearLogs()" class="btn-danger">🗑️ Clear Logs</button>
                        <button onclick="loadLogs()" class="btn-primary">🔄 Refresh</button>
                    </div>"""
logs_actions_new = """<div class="header-actions logs-header-actions">
                        <select id="log-level" onchange="loadLogs()" class="form-control" style="width: 150px;">
                            <option value="all">All Levels</option>
                            <option value="error">Errors Only</option>
                            <option value="warning">Warnings</option>
                            <option value="info">Info</option>
                        </select>
                        <div class="action-group-right">
                            <button onclick="clearLogs()" class="btn-danger">🗑️ Clear Logs</button>
                            <button onclick="loadLogs()" class="btn-primary">🔄 Refresh</button>
                        </div>
                    </div>"""
html = html.replace(logs_actions_old, logs_actions_new)

# Appending required classes/HTML tags for labels
html = html.replace('<input type="checkbox" id="schedule-enabled" checked>\n                            Enable this schedule', 'Enable this schedule\n                            <input type="checkbox" id="schedule-enabled" checked>')
# Write back HTML
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("Updated index.html")

# Update app.js Config Tab output logic
with open(js_path, 'r', encoding='utf-8') as f:
    js = f.read()

# Replace config loading to fix button locations per section
js = re.sub(r"""<div class="form-group">\s*<label for="welcome-channel">Welcome Channel:</label>\s*<select id="welcome-channel" class="form-control">\s*<option value="">None</option>\s*\$\{channelOptions\}\s*</select>\s*<button onclick="saveChannelSetting\('welcome'\)" class="btn-primary btn-small">Save</button>\s*<span id="welcome-channel-status" class="status-text"></span>\s*</div>""", r"""<div class="form-group config-inline-group">\n                        <div class="input-wrapper">\n                            <label for="welcome-channel">Welcome Channel:</label>\n                            <select id="welcome-channel" class="form-control">\n                                <option value="">None</option>\n                                ${channelOptions}\n                            </select>\n                        </div>\n                        <button onclick="saveChannelSetting('welcome')" class="btn-primary btn-small">Save</button>\n                        <span id="welcome-channel-status" class="status-text"></span>\n                    </div>""", js)

js = js.replace('''<h3>📢 Channel Configuration</h3>''', '''<h3>📢 Channel Configuration</h3><hr class="config-divider">''')
js = js.replace('''<h3>🔐 Permission Roles</h3>''', '''<h3>🔐 Permission Roles</h3><hr class="config-divider">''')
js = js.replace('''<h3>💰 Currency Settings</h3>''', '''<h3>💰 Currency Settings</h3><hr class="config-divider">''')
js = js.replace('''<h3>🤖 Bot Behavior</h3>''', '''<h3>🤖 Bot Behavior</h3><hr class="config-divider">''')
js = js.replace('''<h3>⚡ Feature Toggles</h3>''', '''<h3>⚡ Feature Toggles</h3><hr class="config-divider">''')


with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js)
print("Updated app.js")

css_append = """

/* ========================================
   AI SPECIFIC UI OVERRIDES AND FIXES
   ======================================== */

/* GLOBAL LAYOUT & SPACING */
html, body {
    height: 100vh;
    overflow: hidden;
}
.dashboard-container {
    height: 100vh;
    overflow: hidden;
}
.main-content {
    height: 100vh;
    overflow-y: auto;
}
.content-area {
    padding: 16px 20px !important;
    max-width: 1200px !important;
    margin: 0 auto;
}
.section-header {
    height: 90px !important;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.section-header h2 {
    display: inline-flex;
    align-items: center;
    margin: 0;
}
#tier-badge-container {
    display: inline-flex;
    align-items: center;
    margin-left: 12px;
}
.header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
}
.action-group-left, .action-group-right {
    display: flex;
    align-items: center;
    gap: 8px;
}
.logs-header-actions {
    justify-content: space-between;
    width: 100%;
}

/* SIDEBAR REFINEMENTS */
.sidebar .nav-menu {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px 0 !important;
}
.tab-button {
    width: 44px !important;
    height: 44px !important;
    padding: 0 !important;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px !important;
    margin-bottom: 12px !important;
    border-radius: 50% !important;
}
.tab-button.active {
    background: transparent !important;
}
.tab-button.active::before {
    height: 44px !important;
    width: 4px !important;
    border-radius: 0 4px 4px 0 !important;
    left: -14px !important;
    background: var(--accent-primary) !important;
    box-shadow: none !important;
}
.tab-button:hover {
    background: rgba(255,255,255,0.08) !important;
    transform: none !important;
}
.server-selector {
    padding: 16px 14px !important;
}
#server-select {
    width: 44px !important;
    height: 44px !important;
    padding: 0 !important;
    border-radius: 50% !important;
    color: transparent !important;
    background-position: center !important;
}
.sidebar-footer {
    margin-top: auto;
    flex-direction: column;
    gap: 16px;
    align-items: center;
    padding: 20px 0 !important;
}
#bot-status {
    flex-direction: column;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
}
#sidebar-status-dot {
    width: 8px !important;
    height: 8px !important;
}
#sidebar-status-text {
    font-size: 11px !important;
    line-height: 11px;
}
.sidebar-footer button[onclick="logout()"] {
    border-top: 1px solid rgba(255,255,255,0.1);
    border-radius: 0;
    width: 100%;
    margin-top: 8px;
    padding-top: 16px;
    background: transparent !important;
    border-left: none; border-right: none; border-bottom: none;
}

/* DASHBOARD STATS */
.stats-grid {
    display: grid !important;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)) !important;
}
.stat-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}
.stat-card i {
    align-self: flex-start;
    margin-bottom: 8px;
}
.stat-value {
    font-size: 32px !important;
    line-height: 1.2;
}
.stat-label {
    font-size: 13px !important;
    color: var(--text-secondary);
}

/* USERS & MODALS */
.user-card {
    cursor: pointer;
}
.coin-value {
    text-align: right;
    display: block;
}

/* SHOP LIST */
#shop-list .shop-card {
    display: flex;
    flex-direction: column;
    min-height: 140px;
}
.shop-card .price {
    font-size: 18px !important;
    font-weight: 700 !important;
    color: var(--accent-primary);
}

/* TASKS LIST */
#tasks-list .task-card {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas: "desc badge" "desc reward";
    gap: 8px;
}
.task-card .task-desc { grid-area: desc; }
.task-card .task-badge { grid-area: badge; justify-self: end; }
.task-card .task-reward { grid-area: reward; justify-self: end; font-weight: bold; }

/* ANNOUNCEMENTS LIST */
#announcements-list .announcement-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
}
.pinned-tag {
    background: var(--discord-yellow);
    color: #000;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: bold;
}

/* EMBEDS LIST */
#embeds-list .embed-card {
    border-left: 4px solid var(--embed-color, #5865F2) !important;
    padding-left: 16px !important;
}
.embed-card .embed-desc {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-secondary);
}

/* LOGS */
#logs-content .log-entry {
    font-family: monospace;
    padding: 8px;
    border-left: 3px solid transparent;
    height: 36px;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}
.log-entry.error { border-left-color: var(--discord-red); }
.log-entry.warning { border-left-color: var(--discord-yellow); }
.log-entry.info { border-left-color: var(--discord-blurple); }

/* CONFIG FORMS */
.config-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.05);
    margin: 16px 0;
}
.config-inline-group {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}
.config-inline-group select {
    width: 240px !important;
}
#bot-status-section {
    background: var(--glass-bg);
    padding: 24px;
    border-radius: 16px;
    border: var(--glass-border);
}
.premium-badge {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 8px;
    background: linear-gradient(135deg, #FFD700, #FDB931);
    color: #000;
    margin-left: 8px;
}

/* MODALS */
.modal {
    background-color: rgba(0, 0, 0, 0.7) !important;
}
.modal-content {
    max-width: 560px !important;
    border: 1px solid var(--border-secondary) !important;
}
.modal-content.wide-modal {
    max-width: 860px !important;
}
.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
}
label {
    display: block;
    margin-bottom: 4px;
}
.form-control {
    border-color: var(--border-secondary) !important;
}
.button-group {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 24px;
}
.button-group .btn-secondary { background: transparent; }

/* FIX EMBED PREVIEW */
#preview-embed {
    max-width: 480px !important;
    background-color: #2b2d31 !important;
}
.discord-preview-box {
    background-color: #313338 !important; 
}

/* TOASTS */
#notification-container {
    position: fixed;
    bottom: 16px !important;
    right: 16px !important;
    top: auto !important;
    left: auto !important;
    z-index: 9999 !important;
}
.toast {
    width: 320px !important;
    display: flex;
    align-items: center;
}
.toast.error::before { content: "✕ "; font-weight: bold; margin-right: 8px; }
.toast.success::before { content: "✓ "; font-weight: bold; margin-right: 8px; }

/* FOOTERS */
.site-footer {
    display: flex;
    padding: 16px;
    align-items: center;
    justify-content: center;
}
.site-footer--dashboard {
    margin-top: auto;
}
.site-footer a {
    font-size: 11px;
    color: var(--text-muted);
}
"""

with open(css_path, 'a', encoding='utf-8') as f:
    f.write(css_append)
print("Updated styles.css")

