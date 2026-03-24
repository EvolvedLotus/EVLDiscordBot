import re

js_path = r'C:\Users\xmarc\OneDrive\Documents\GitHub\EvolvedLotusBusiness\task-bot-discord\docs\app.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js = f.read()

# Replace loadDashboard
old_dashboard = """        content.innerHTML = `
            <div class="dashboard-grid">
                <div class="stat-card">
                    <h3>Bot Status</h3>
                    <div class="stat-value ${statusData.bot_status}">${statusData.bot_status.toUpperCase()}</div>
                    <div class="stat-sub">Uptime: ${statusData.uptime}</div>
                </div>
                <div class="stat-card">
                    <h3>Server Name</h3>
                    <div class="stat-value">${serverName}</div>
                </div>
                <div class="stat-card">
                    <h3>Currency</h3>
                    <div class="stat-value">${serverConfig.currency_symbol || '💰'} ${serverConfig.currency_name || 'Coins'}</div>
                </div>
            </div>
        `;"""
new_dashboard = """        content.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <i style="font-size:24px; margin-bottom:8px; display:block;">🤖</i>
                    <div class="stat-value ${statusData.bot_status}">${statusData.bot_status.toUpperCase()}</div>
                    <div class="stat-label">Bot Status (Uptime: ${statusData.uptime})</div>
                </div>
                <div class="stat-card">
                    <i style="font-size:24px; margin-bottom:8px; display:block;">🌐</i>
                    <div class="stat-value" style="font-size:24px !important;">${serverName}</div>
                    <div class="stat-label">Server Name</div>
                </div>
                <div class="stat-card">
                    <i style="font-size:24px; margin-bottom:8px; display:block;">${serverConfig.currency_symbol || '💰'}</i>
                    <div class="stat-value" style="font-size:24px !important;">${serverConfig.currency_name || 'Coins'}</div>
                    <div class="stat-label">Currency</div>
                </div>
            </div>
        `;"""
js = js.replace(old_dashboard, new_dashboard)

# Replace loadUsers
old_users = """            let html = '<div class="table-container"><table class="data-table"><thead><tr><th>User</th><th>Balance</th><th>Level</th><th>XP</th><th>Actions</th></tr></thead><tbody>';
            data.users.forEach(user => {
                html += `
                    <tr>
                        <td>${user.username || user.user_id}</td>
                        <td>${user.balance}</td>
                        <td>${user.level}</td>
                        <td>${user.xp}</td>
                        <td>
                            <button onclick="manageUser('${user.user_id}')" class="btn-small btn-primary">Manage</button>
                        </td>
                    </tr>
                `;
            });
            html += '</tbody></table></div>';"""

new_users = """            let html = '<div class="users-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">';
            data.users.forEach(user => {
                html += `
                    <div class="card user-card" onclick="manageUser('${user.user_id}')" style="cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: 16px;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <div class="avatar-placeholder" style="width: 40px; height: 40px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center;">👤</div>
                            <div>
                                <h4 style="margin: 0; font-size: 15px;">${user.username || user.user_id}</h4>
                                <div style="font-size: 12px; color: var(--text-muted);">Lvl ${user.level} • ${user.xp} XP</div>
                            </div>
                        </div>
                        <div class="coin-value" style="font-size: 16px; font-weight: bold; color: var(--discord-yellow); text-align: right;">
                            ${user.balance} 💰
                        </div>
                    </div>
                `;
            });
            html += '</div>';"""
js = js.replace(old_users, new_users)

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js)
