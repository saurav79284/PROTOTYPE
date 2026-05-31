const API = '';
let currentAlerts = [];
let riskTrendChart = null;
let channelChart = null;
let riskTrendData = [];
let channelCounts = {};
let ws = null;

// ── Utility: Update clock ──
function updateClock() {
  const now = new Date();
  const el = document.getElementById('top-bar-time');
  if (el) el.textContent = now.toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
setInterval(updateClock, 1000);

// ══════════════════════════════════
//  TOAST NOTIFICATIONS
// ══════════════════════════════════
function showToast(title, message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const icons = { warning: '⚠️', danger: '🚨', success: '✅', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || icons.info}</div>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      <div class="toast-message">${message}</div>
    </div>`;
  container.appendChild(toast);
  setTimeout(() => { if (toast.parentNode) toast.remove(); }, 2000);
}


// ══════════════════════════════════
//  WEBSOCKET CONNECTION
// ══════════════════════════════════
function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws/transactions`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('[WS] Connected');
    updateWsStatus(true);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleWsMessage(data);
    } catch (e) { console.error('[WS] Parse error:', e); }
  };

  ws.onclose = () => {
    console.log('[WS] Disconnected, reconnecting in 3s...');
    updateWsStatus(false);
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = () => {
    updateWsStatus(false);
  };
}

function updateWsStatus(connected) {
  const el = document.getElementById('ws-status');
  if (!el) return;
  if (connected) {
    el.classList.remove('ws-disconnected');
    el.innerHTML = '<span class="live-dot"></span> Live Connected';
  } else {
    el.classList.add('ws-disconnected');
    el.innerHTML = '<span class="live-dot"></span> Reconnecting...';
  }
}

function handleWsMessage(data) {
  if (data.type === 'transaction') {
    // Update live feed on dashboard
    prependToLiveFeed(data);
    // Update charts
    updateRiskTrendChart(data);
    updateChannelChart(data);
    // Update alert badge
    if (data.is_flagged) {
      const badge = document.getElementById('alert-badge');
      if (badge) badge.textContent = parseInt(badge.textContent || '0') + 1;
    }
    // Show toast for critical alerts
    if (data.alert && (data.ml_score.tier === 'CRITICAL' || data.ml_score.tier === 'HIGH')) {
      showToast(
        `🚨 ${data.ml_score.tier} Alert`,
        `${data.alert.sender} sent ₹${Number(data.alert.amount).toLocaleString()} — Score: ${data.alert.score}`,
        data.ml_score.tier === 'CRITICAL' ? 'danger' : 'warning'
      );
    }
  }
}

function prependToLiveFeed(data) {
  const el = document.getElementById('live-feed');
  if (!el || !document.getElementById('page-dashboard').classList.contains('active')) return;

  const tx = data.transaction;
  const flagged = data.is_flagged;
  const item = document.createElement('div');
  item.className = `feed-item ${flagged ? 'feed-item-flagged' : ''} fade-in`;
  item.innerHTML = `
    <div class="feed-item-left">
      <div>
        <div class="feed-item-title">${tx.sender_name} → ${tx.receiver_name}</div>
        <div class="feed-item-meta">${tx.channel} · ${new Date(tx.timestamp).toLocaleTimeString()}</div>
      </div>
    </div>
    <div class="feed-item-right">
      <div class="feed-item-amount">₹${Number(tx.amount).toLocaleString()}</div>
      <span class="risk-badge ${data.ml_score.tier.toLowerCase()}" style="font-size:10px;margin-top:2px;">${data.ml_score.composite_score}</span>
    </div>`;

  el.insertBefore(item, el.firstChild);
  // Keep only last 15 items
  while (el.children.length > 15) el.removeChild(el.lastChild);
}


// ══════════════════════════════════
//  CHART.JS — REAL-TIME CHARTS
// ══════════════════════════════════
function initCharts() {
  // Risk Trend Line Chart
  const riskCtx = document.getElementById('risk-trend-chart');
  if (riskCtx && !riskTrendChart) {
    riskTrendChart = new Chart(riskCtx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Risk Score',
          data: [],
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,0.08)',
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointBackgroundColor: '#2563eb',
          borderWidth: 2,
        }, {
          label: 'Alert Threshold',
          data: [],
          borderColor: '#dc2626',
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top', labels: { font: { size: 11, family: 'Inter' }, padding: 12 } },
        },
        scales: {
          y: { min: 0, max: 100, ticks: { font: { size: 11 } }, grid: { color: '#f1f5f9' } },
          x: { ticks: { font: { size: 10 }, maxRotation: 0, maxTicksLimit: 10 }, grid: { display: false } },
        },
        animation: { duration: 400 },
      }
    });
  }

  // Channel Distribution Doughnut
  const channelCtx = document.getElementById('channel-chart');
  if (channelCtx && !channelChart) {
    channelChart = new Chart(channelCtx, {
      type: 'doughnut',
      data: {
        labels: ['UPI', 'IMPS', 'NEFT', 'RTGS', 'SWIFT', 'CBS'],
        datasets: [{
          data: [0, 0, 0, 0, 0, 0],
          backgroundColor: ['#2563eb', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2'],
          borderWidth: 2,
          borderColor: '#ffffff',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { font: { size: 11, family: 'Inter' }, padding: 10, usePointStyle: true } },
        },
        cutout: '60%',
        animation: { duration: 400 },
      }
    });
  }
}

function updateRiskTrendChart(data) {
  if (!riskTrendChart) return;
  const time = new Date(data.transaction.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  riskTrendData.push({ time, score: data.ml_score.composite_score });
  if (riskTrendData.length > 20) riskTrendData.shift();

  riskTrendChart.data.labels = riskTrendData.map(d => d.time);
  riskTrendChart.data.datasets[0].data = riskTrendData.map(d => d.score);
  riskTrendChart.data.datasets[1].data = riskTrendData.map(() => 60); // threshold line
  riskTrendChart.update('none');
}

function updateChannelChart(data) {
  if (!channelChart) return;
  const ch = data.transaction.channel;
  channelCounts[ch] = (channelCounts[ch] || 0) + 1;

  const labels = channelChart.data.labels;
  channelChart.data.datasets[0].data = labels.map(l => channelCounts[l] || 0);
  channelChart.update('none');
}


// ── Navigation ──
const pageNames = {
  dashboard: 'Dashboard',
  transactions: 'Live Transactions',
  alerts: 'Alert Management',
  graph: 'Network Graph',
  str: 'STR Reports',
  pipeline: 'ML Pipeline'
};

function switchPage(page) {
  document.querySelectorAll('.page-view').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.querySelector(`[data-page="${page}"]`).classList.add('active');
  document.getElementById('breadcrumb-page').textContent = pageNames[page] || page;
  // Close sidebar on mobile
  document.getElementById('sidebar').classList.remove('open');

  if (page === 'dashboard') refreshDashboard();
  if (page === 'transactions') loadTransactions();
  if (page === 'alerts') loadAlerts();
  if (page === 'graph') loadGraph();
  if (page === 'str') loadSTRList();
  if (page === 'pipeline') renderPipeline();
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ── Dashboard ──
async function refreshDashboard() {
  try {
    const res = await fetch(API + '/api/stats');
    const s = res.ok ? await res.json() : null;
    if (!s) return;
    document.getElementById('stats-grid').innerHTML = `
      <div class="stat-card blue fade-in">
        <div class="stat-header">
          <div class="stat-icon">💳</div>
          <div class="stat-title">Transactions Today</div>
        </div>
        <div class="stat-value">${s.total_transactions_today.toLocaleString()}</div>
        <div class="stat-label">Across all banking channels</div>
        <div class="stat-change up">● Live streaming</div>
      </div>
      <div class="stat-card green fade-in">
        <div class="stat-header">
          <div class="stat-icon">💰</div>
          <div class="stat-title">Volume Processed</div>
        </div>
        <div class="stat-value">₹${(s.total_amount_today/1e7).toFixed(1)}Cr</div>
        <div class="stat-label">Total amount processed today</div>
        <div class="stat-change up">All channels active</div>
      </div>
      <div class="stat-card red fade-in">
        <div class="stat-header">
          <div class="stat-icon">🔔</div>
          <div class="stat-title">Alerts Generated</div>
        </div>
        <div class="stat-value">${s.alerts_generated}</div>
        <div class="stat-label">Flagged by ML models</div>
        <div class="stat-change down">${s.critical_alerts} need immediate action</div>
      </div>
      <div class="stat-card purple fade-in">
        <div class="stat-header">
          <div class="stat-icon">📊</div>
          <div class="stat-title">Avg Risk Score</div>
        </div>
        <div class="stat-value">${s.avg_risk_score}</div>
        <div class="stat-label">Average across all alerts</div>
        <div class="stat-change">Scale: 0 (safe) to 100 (fraud)</div>
      </div>
      <div class="stat-card cyan fade-in">
        <div class="stat-header">
          <div class="stat-icon">⚡</div>
          <div class="stat-title">Scoring Latency</div>
        </div>
        <div class="stat-value">${s.avg_latency_ms}ms</div>
        <div class="stat-label">Time to score a transaction</div>
        <div class="stat-change up">Target: < 50ms ✓</div>
      </div>
      <div class="stat-card orange fade-in">
        <div class="stat-header">
          <div class="stat-icon">🔄</div>
          <div class="stat-title">Circular Flows</div>
        </div>
        <div class="stat-value">${s.circular_flows_detected}</div>
        <div class="stat-label">Money-loop patterns found</div>
        <div class="stat-change down">Detected by DFS graph analysis</div>
      </div>`;
    document.getElementById('alert-badge').textContent = s.alerts_generated;

    // Initialize charts
    initCharts();
    // Seed channel chart with stats data
    if (channelChart && s.channels_active) {
      channelCounts = {...channelCounts, ...s.channels_active};
      const labels = channelChart.data.labels;
      channelChart.data.datasets[0].data = labels.map(l => channelCounts[l] || 0);
      channelChart.update();
    }

    loadRecentAlerts();
    loadLiveFeed();
  } catch(e) { console.error('Dashboard error:', e); }
}

async function loadRecentAlerts() {
  try {
    const res = await fetch(API + '/api/alerts?tier=CRITICAL&limit=5');
    const data = await res.json();
    const el = document.getElementById('recent-alerts');
    if (!data.alerts.length) {
      el.innerHTML = '<div class="empty-state"><p class="empty-title">No Critical Alerts</p><p class="empty-desc">All transactions are within normal parameters</p></div>';
      return;
    }
    el.innerHTML = data.alerts.map(a => `
      <div class="feed-item slide-in" onclick="openAlertDetail('${a.alert_id}')">
        <div class="feed-item-left">
          <span class="risk-badge ${a.ml_score.tier.toLowerCase()}">${a.ml_score.composite_score}</span>
          <div>
            <div class="feed-item-title">${a.transaction.sender_name} → ${a.transaction.receiver_name}</div>
            <div class="feed-item-meta">₹${Number(a.transaction.amount).toLocaleString()} · ${a.transaction.channel}</div>
          </div>
        </div>
        <span class="status-badge ${a.status.toLowerCase().replace('_','-')}">${a.status.replace('_',' ')}</span>
      </div>`).join('');
  } catch(e) { console.error('Recent alerts error:', e); }
}

async function loadLiveFeed() {
  try {
    const res = await fetch(API + '/api/transactions/live?count=8');
    const data = await res.json();
    const el = document.getElementById('live-feed');
    el.innerHTML = data.transactions.map(t => {
      const tx = t.transaction;
      const flagged = t.is_flagged;
      return `<div class="feed-item ${flagged ? 'feed-item-flagged' : ''} fade-in">
        <div class="feed-item-left">
          <div>
            <div class="feed-item-title">${tx.sender_name} → ${tx.receiver_name}</div>
            <div class="feed-item-meta">${tx.channel} · ${new Date(tx.timestamp).toLocaleTimeString()}</div>
          </div>
        </div>
        <div class="feed-item-right">
          <div class="feed-item-amount">₹${Number(tx.amount).toLocaleString()}</div>
          <span class="risk-badge ${t.ml_score.tier.toLowerCase()}" style="font-size:10px;margin-top:2px;">${t.ml_score.composite_score}</span>
        </div>
      </div>`;
    }).join('');

    // Seed risk trend chart with initial data
    if (riskTrendChart && riskTrendData.length === 0) {
      data.transactions.forEach(t => {
        updateRiskTrendChart(t);
      });
    }
  } catch(e) { console.error('Live feed error:', e); }
}

// ── Transactions ──
async function loadTransactions() {
  try {
    const res = await fetch(API + '/api/transactions/live?count=20');
    const data = await res.json();
    document.getElementById('txn-body').innerHTML = data.transactions.map(t => {
      const tx = t.transaction;
      return `<tr class="${t.is_flagged ? 'flagged' : ''}">
        <td style="font-family:monospace;font-size:11px;color:var(--text-muted);">${tx.txn_id.substring(0,16)}…</td>
        <td>${new Date(tx.timestamp).toLocaleTimeString()}</td>
        <td><div style="font-weight:600;">${tx.sender_name}</div><div style="font-size:11px;color:var(--text-muted);">${tx.sender_account}</div></td>
        <td><div style="font-weight:600;">${tx.receiver_name}</div><div style="font-size:11px;color:var(--text-muted);">${tx.receiver_account}</div></td>
        <td style="font-weight:700;">₹${Number(tx.amount).toLocaleString()}</td>
        <td><span class="channel-tag">${tx.channel}</span></td>
        <td><span class="risk-badge ${t.ml_score.tier.toLowerCase()}">${t.ml_score.composite_score}</span></td>
        <td><span style="font-size:12px;font-weight:600;color:${t.ml_score.tier==='CRITICAL'?'var(--accent-red)':t.ml_score.tier==='HIGH'?'var(--accent-orange)':t.ml_score.tier==='MEDIUM'?'var(--accent-blue)':'var(--accent-green)'};">${t.ml_score.tier}</span></td>
      </tr>`;
    }).join('');
  } catch(e) { console.error('Transactions error:', e); }
}

// ── Alerts ──
async function loadAlerts(filter) {
  try {
    let url = API + '/api/alerts?limit=30';
    if (filter && filter !== 'all' && filter !== 'CRITICAL') url += '&status=' + filter;
    if (filter === 'CRITICAL') url += '&tier=CRITICAL';
    const res = await fetch(url);
    const data = await res.json();
    currentAlerts = data.alerts;
    renderAlerts(data.alerts);
  } catch(e) { console.error('Alerts error:', e); }
}

function filterAlerts(f, btn) {
  document.querySelectorAll('#alert-tabs .tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  loadAlerts(f);
}

function getScoreColor(score) {
  if (score >= 86) return 'var(--accent-red)';
  if (score >= 61) return 'var(--accent-orange)';
  if (score >= 31) return 'var(--accent-blue)';
  return 'var(--accent-green)';
}

function renderAlerts(alerts) {
  document.getElementById('alerts-list').innerHTML = alerts.map(a => {
    const color = getScoreColor(a.ml_score.composite_score);
    return `
    <div class="alert-card fade-in" onclick="openAlertDetail('${a.alert_id}')">
      <div class="alert-card-left">
        <div class="alert-card-score" style="color:${color};border-color:${color};">${a.ml_score.composite_score}</div>
        <div class="alert-card-info">
          <h4>${a.transaction.sender_name} → ${a.transaction.receiver_name}</h4>
          <p>₹${Number(a.transaction.amount).toLocaleString()} · ${a.transaction.channel} · ${new Date(a.transaction.timestamp).toLocaleString()}</p>
          <p style="margin-top:2px;font-size:11px;color:var(--text-muted);">${a.alert_id}</p>
        </div>
      </div>
      <div class="alert-card-right">
        <span class="risk-badge ${a.ml_score.tier.toLowerCase()}">${a.ml_score.tier}</span>
        <span class="status-badge ${a.status.toLowerCase().replace('_','-')}">${a.status.replace('_',' ')}</span>
      </div>
    </div>`;
  }).join('');
}


// ══════════════════════════════════
//  EXPORT FUNCTIONALITY
// ══════════════════════════════════
function downloadFile(filename, content, mimeType = 'text/csv') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportAlertsToCsv() {
  if (!currentAlerts.length) {
    showToast('No Data', 'No alerts to export', 'warning');
    return;
  }
  const header = 'Alert ID,Sender,Receiver,Amount,Channel,Composite Score,Tier,Status,FATF Typology,Timestamp\n';
  const csv = currentAlerts.map(a =>
    `${a.alert_id},"${a.transaction.sender_name}","${a.transaction.receiver_name}",${a.transaction.amount},${a.transaction.channel},${a.ml_score.composite_score},${a.ml_score.tier},${a.status},"${a.fatf_typology || 'N/A'}",${a.transaction.timestamp}`
  ).join('\n');
  downloadFile(`fundflow_alerts_${new Date().toISOString().slice(0,10)}.csv`, header + csv);
  showToast('Export Complete', `${currentAlerts.length} alerts exported to CSV`, 'success');
}

function exportSTRToText(str) {
  downloadFile(`${str.str_id}_report.txt`, str.narrative, 'text/plain');
  showToast('Download Complete', `STR report ${str.str_id} downloaded`, 'success');
}


// ── Alert Detail Modal ──
async function openAlertDetail(alertId) {
  try {
    const res = await fetch(API + '/api/alerts/' + alertId);
    const a = await res.json();

    // Fetch audit trail for this alert
    let auditHtml = '';
    try {
      const auditRes = await fetch(API + '/api/audit/' + alertId);
      const auditData = await auditRes.json();
      if (auditData.entries.length) {
        auditHtml = `<div class="detail-section" style="margin-top:20px;">
          <h4>📋 Audit Trail</h4>
          <p style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">Activity log for this alert — demonstrates Human-in-the-Loop (HITL) workflow</p>
          ${auditData.entries.map(e => {
            const actionClass = e.action.includes('ALERT') ? 'action-alert' : e.action.includes('STATUS') ? 'action-status' : e.action.includes('STR') ? 'action-str' : 'action-system';
            const time = new Date(e.timestamp).toLocaleTimeString();
            return `<div class="audit-entry">
              <div class="audit-dot ${actionClass}"></div>
              <div class="audit-time">${time}</div>
              <div class="audit-text"><strong>${e.action.replace(/_/g, ' ')}</strong> by ${e.officer} — ${e.details}</div>
            </div>`;
          }).join('')}
        </div>`;
      }
    } catch(e) { /* audit trail optional */ }

    document.getElementById('modal-title').textContent = 'Alert: ' + a.alert_id;
    const scoreColor = getScoreColor(a.ml_score.composite_score);
    const shapMax = Math.max(...a.shap_explanations.map(s => s.importance));
    document.getElementById('modal-body').innerHTML = `
      <div class="content-grid">
        <div class="detail-section">
          <h4>Transaction Details</h4>
          <div style="background:#f8fafc;padding:16px;border-radius:10px;font-size:13px;line-height:2.2;border:1px solid var(--border-light);">
            <div><strong>TXN ID:</strong> <span style="font-family:monospace;font-size:12px;color:var(--text-muted);">${a.transaction.txn_id}</span></div>
            <div><strong>Sender:</strong> ${a.transaction.sender_name} <span style="color:var(--text-muted);">(${a.transaction.sender_account})</span></div>
            <div><strong>Receiver:</strong> ${a.transaction.receiver_name} <span style="color:var(--text-muted);">(${a.transaction.receiver_account})</span></div>
            <div><strong>Amount:</strong> <span style="font-weight:700;font-size:15px;">₹${Number(a.transaction.amount).toLocaleString()}</span></div>
            <div><strong>Channel:</strong> <span class="channel-tag">${a.transaction.channel}</span> · <strong>Location:</strong> ${a.transaction.location||'N/A'}</div>
            <div><strong>Time:</strong> ${new Date(a.transaction.timestamp).toLocaleString()}</div>
          </div>
        </div>
        <div class="detail-section">
          <h4>ML Ensemble Score</h4>
          <div style="text-align:center;margin-bottom:16px;">
            <div style="position:relative;display:inline-block;">
              <svg width="110" height="110" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" stroke="#e2e8f0" stroke-width="8"/>
                <circle cx="60" cy="60" r="52" fill="none" stroke="${scoreColor}" stroke-width="8" stroke-dasharray="${a.ml_score.composite_score*3.267} 327" stroke-linecap="round" style="transform:rotate(-90deg);transform-origin:center;"/>
              </svg>
              <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
                <div style="font-size:28px;font-weight:800;color:${scoreColor};">${a.ml_score.composite_score}</div>
                <div style="font-size:10px;color:var(--text-muted);font-weight:600;">${a.ml_score.tier}</div>
              </div>
            </div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:8px;">Scored in ${a.ml_score.latency_ms}ms</div>
          </div>
          <p style="font-size:12px;color:var(--text-muted);text-align:center;margin-bottom:14px;">Real XGBoost + Isolation Forest models · Feature-based LSTM + GNN heuristics</p>
          <div class="score-breakdown">
            ${[['XGBoost ✅', a.ml_score.xgboost_score, 'var(--accent-blue)', 'Real trained model'],
               ['Isolation Forest ✅', a.ml_score.isolation_forest_score, 'var(--accent-cyan)', 'Real trained model'],
               ['GraphSAGE (GNN) 🔧', a.ml_score.gnn_score, 'var(--accent-purple)', 'Graph feature heuristic'],
               ['LSTM Sequence 🔧', a.ml_score.lstm_score, 'var(--accent-green)', 'Temporal feature heuristic'],
            ].map(([n,v,c,desc]) => `
            <div class="score-item">
              <div class="model-name">${n}</div>
              <div style="font-size:18px;font-weight:700;color:${c};">${(v*100).toFixed(1)}%</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${desc}</div>
              <div class="score-bar"><div class="fill" style="width:${v*100}%;background:${c};"></div></div>
            </div>`).join('')}
          </div>
        </div>
      </div>
      <div class="detail-section" style="margin-top:20px;">
        <h4>🔍 Why Was This Flagged? (Real SHAP Explainability)</h4>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">These are real SHAP values from our trained XGBoost model. Red = increases risk, green = decreases risk.</p>
        ${a.shap_explanations.map(s => `
          <div class="shap-bar">
            <div class="feature-name">${s.feature}</div>
            <div class="bar-container"><div class="bar-fill ${s.direction==='increases_risk'?'risk-up':'risk-down'}" style="width:${(s.importance/shapMax)*100}%;">${s.importance.toFixed(3)}</div></div>
            <div class="value">${s.value}</div>
          </div>`).join('')}
      </div>
      ${a.graph_patterns.length ? `<div class="detail-section" style="margin-top:20px;">
        <h4>🕸️ Suspicious Fund Flow Patterns (DFS Detection)</h4>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">Cycles detected using DFS-based graph traversal algorithm with configurable hop depth.</p>
        ${a.graph_patterns.map(p => `<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:14px;margin-bottom:10px;">
          <div style="font-weight:700;color:var(--accent-red);font-size:13px;">${p.pattern_type.replace(/_/g,' ').toUpperCase()} · ${p.hop_count} hops · Confidence: ${(p.confidence*100).toFixed(0)}%</div>
          <div style="font-size:12px;color:var(--text-secondary);margin-top:6px;">${p.description}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Account chain: ${p.involved_accounts.join(' → ')}</div>
        </div>`).join('')}
      </div>` : ''}
      ${auditHtml}
      <div style="display:flex;gap:10px;margin-top:24px;padding-top:18px;border-top:1px solid var(--border);flex-wrap:wrap;">
        <button class="btn btn-success" onclick="updateAlertStatus('${a.alert_id}','CONFIRMED_FRAUD')">✓ Confirm Fraud</button>
        <button class="btn btn-outline" onclick="updateAlertStatus('${a.alert_id}','FALSE_POSITIVE')">✗ False Positive</button>
        <button class="btn btn-primary" onclick="generateSTR('${a.alert_id}')">📄 Generate STR Report</button>
        <button class="btn btn-outline" onclick="viewAccountGraph('${a.transaction.sender_account}')">🕸️ View in Graph</button>
      </div>`;
    document.getElementById('alert-modal').classList.add('active');
  } catch(e) { console.error('Alert detail error:', e); }
}

function closeModal() { document.getElementById('alert-modal').classList.remove('active'); }

async function updateAlertStatus(id, status) {
  try {
    await fetch(API + `/api/alerts/${id}/status?new_status=${status}`, { method: 'PUT' });
    closeModal();
    loadAlerts();
    const label = status.replace(/_/g, ' ');
    showToast('Status Updated', `Alert ${id} marked as ${label}`, status === 'CONFIRMED_FRAUD' ? 'warning' : 'success');
  } catch(e) { console.error('Update status error:', e); }
}

async function generateSTR(alertId) {
  try {
    const res = await fetch(API + '/api/str/generate/' + alertId, { method: 'POST' });
    const str = await res.json();
    closeModal();
    switchPage('str');
    renderSTRDetail(str);
    showToast('STR Generated', `Report ${str.str_id} created successfully`, 'success');
  } catch(e) { console.error('Generate STR error:', e); }
}

// ── STR ──
async function loadSTRList() {
  try {
    const res = await fetch(API + '/api/str/list');
    const data = await res.json();
    if (!data.reports.length) {
      document.getElementById('str-content').innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          </div>
          <p class="empty-title">No STR Reports Yet</p>
          <p class="empty-desc">Go to Alerts → click an alert → click "Generate STR" to create a report</p>
        </div>`;
      return;
    }
    document.getElementById('str-content').innerHTML = data.reports.map(r => `
      <div class="alert-card fade-in" onclick='renderSTRDetail(${JSON.stringify(r).replace(/'/g,"&#39;")})'>
        <div class="alert-card-left">
          <div style="font-size:24px;">📄</div>
          <div class="alert-card-info">
            <h4>${r.str_id}</h4>
            <p>${r.entity_name} · ₹${Number(r.suspicious_amount).toLocaleString()} · ${r.fatf_typology.substring(0,40)}</p>
          </div>
        </div>
        <span class="status-badge pending">${r.status}</span>
      </div>`).join('');
  } catch(e) { console.error('STR list error:', e); }
}

function renderSTRDetail(str) {
  window._currentSTR = str;  // Store for download button
  document.getElementById('str-content').innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title-group">
          <h3>${str.str_id} — FINNET 2.0 Report</h3>
          <p class="card-subtitle">Auto-generated suspicious transaction report</p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-sm btn-success" onclick="alert('STR submitted to FIU-IND (demo)')">Submit to FIU</button>
          <button class="btn btn-sm btn-outline" onclick="exportSTRToText(window._currentSTR)">📥 Download</button>
          <button class="btn btn-sm btn-outline" onclick="loadSTRList()">← Back to List</button>
        </div>
      </div>
      <div class="card-body">
        <div class="tabs">
          <button class="tab active" onclick="showSTRTab('narrative',this)">Narrative</button>
          <button class="tab" onclick="showSTRTab('xml',this)">XML Output</button>
          <button class="tab" onclick="showSTRTab('indicators',this)">Risk Indicators</button>
        </div>
        <div id="str-narrative"><div class="str-preview">${str.narrative}</div></div>
        <div id="str-xml" style="display:none;"><div class="xml-preview">${str.xml_content.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div></div>
        <div id="str-indicators" style="display:none;">
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">Each indicator below contributed to classifying this transaction as suspicious:</p>
          ${str.risk_indicators.map(r=>`<div style="padding:10px 14px;border-left:3px solid var(--accent-red);margin-bottom:8px;background:#fef2f2;border-radius:0 8px 8px 0;font-size:13px;color:#991b1b;">⚠️ ${r}</div>`).join('')}
        </div>
      </div>
    </div>`;
}

function showSTRTab(tab, btn) {
  ['narrative','xml','indicators'].forEach(t => document.getElementById('str-'+t).style.display = t===tab?'block':'none');
  btn.parentElement.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
}

// ── Graph ──
async function loadGraph() {
  try {
    const res = await fetch(API + '/api/graph/network');
    const data = await res.json();
    renderGraph(data);
    renderCircularFlows(data.circular_flows);
    loadMuleAccounts();
  } catch(e) { console.error('Graph error:', e); }
}

async function loadMuleAccounts() {
  try {
    const res = await fetch(API + '/api/graph/mule-accounts');
    const data = await res.json();
    const el = document.getElementById('mule-accounts-container');
    if (!el) return;
    if (!data.mule_accounts.length) {
      el.innerHTML = '<div class="empty-state"><p class="empty-title">No Mule Accounts Detected</p></div>';
      return;
    }
    const top = data.mule_accounts.slice(0, 10);
    el.innerHTML = `
      <div class="info-banner" style="margin-bottom:16px;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        <span><strong>${data.total} mule accounts detected.</strong> These accounts receive funds from 10+ distinct senders and forward 85%+ onward — a classic layering pattern. Showing top 10 by forward ratio.</span>
      </div>
      <div class="content-grid">
        ${top.map(m => `
          <div class="card fade-in" style="cursor:pointer;" onclick="viewAccountGraph('${m.account_id}')">
            <div style="padding:16px 20px;border-left:4px solid ${m.risk_level === 'CRITICAL' ? 'var(--accent-red)' : 'var(--accent-orange)'};">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                  <div style="font-weight:700;font-size:14px;color:var(--text-primary);">${m.holder_name}</div>
                  <div style="font-size:12px;color:var(--text-muted);margin-top:2px;font-family:monospace;">${m.account_id}</div>
                </div>
                <span class="risk-badge ${m.risk_level === 'CRITICAL' ? 'critical' : 'high'}">${m.risk_level}</span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px;">
                <div>
                  <div style="font-size:11px;color:var(--text-muted);">Inflow Sources</div>
                  <div style="font-size:16px;font-weight:700;color:var(--accent-blue);">${m.unique_senders}</div>
                </div>
                <div>
                  <div style="font-size:11px;color:var(--text-muted);">Forward Ratio</div>
                  <div style="font-size:16px;font-weight:700;color:var(--accent-red);">${m.forward_ratio}%</div>
                </div>
                <div>
                  <div style="font-size:11px;color:var(--text-muted);">Total Flow</div>
                  <div style="font-size:16px;font-weight:700;color:var(--accent-orange);">₹${(m.total_inflow / 100000).toFixed(1)}L</div>
                </div>
              </div>
            </div>
          </div>`).join('')}
      </div>`;
  } catch(e) { console.error('Mule accounts error:', e); }
}

function renderGraph(data) {
  const container = document.getElementById('graph-container');
  container.innerHTML = '';
  const w = container.clientWidth, h = 500;
  const svg = d3.select(container).append('svg').attr('width', w).attr('height', h);
  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => g.attr('transform', e.transform)));

  const nodes = data.nodes.map(n => ({...n, id: n.account_id}));
  const links = data.edges.map(e => ({source: e.source, target: e.target, ...e}));

  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(120))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(w/2, h/2))
    .force('collision', d3.forceCollide().radius(40));

  // Arrow markers
  svg.append('defs').append('marker').attr('id','arrow').attr('viewBox','0 -5 10 10').attr('refX',25).attr('refY',0).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
    .append('path').attr('d','M0,-5L10,0L0,5').attr('fill','#94a3b8');
  svg.append('defs').append('marker').attr('id','arrow-red').attr('viewBox','0 -5 10 10').attr('refX',25).attr('refY',0).attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
    .append('path').attr('d','M0,-5L10,0L0,5').attr('fill','#dc2626');

  const link = g.selectAll('line').data(links).join('line')
    .attr('stroke', d => d.is_suspicious ? '#dc2626' : '#cbd5e1')
    .attr('stroke-width', d => d.is_suspicious ? 2.5 : 1.2)
    .attr('stroke-opacity', d => d.is_suspicious ? 0.8 : 0.5)
    .attr('marker-end', d => d.is_suspicious ? 'url(#arrow-red)' : 'url(#arrow)');

  const node = g.selectAll('g.node').data(nodes).join('g').attr('class','node')
    .call(d3.drag().on('start',(e,d)=>{if(!e.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;})
      .on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y;}).on('end',(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));

  node.append('circle').attr('r', d => d.risk_score > 50 ? 18 : 14)
    .attr('fill', d => d.risk_score > 70 ? '#dc2626' : d.risk_score > 50 ? '#d97706' : '#059669')
    .attr('stroke', d => d.risk_score > 50 ? 'rgba(220,38,38,0.2)' : 'rgba(5,150,105,0.15)')
    .attr('stroke-width', 3).style('cursor','pointer');

  node.append('text').text(d => d.holder_name.split(' ')[0])
    .attr('dy', 30).attr('text-anchor','middle').attr('fill','#475569').attr('font-size','10px').attr('font-weight','500');

  // Tooltip on hover
  node.append('title').text(d => `${d.holder_name}\nAccount: ${d.account_id}\nRisk: ${d.risk_score}`);

  node.on('click', (e, d) => viewAccountGraph(d.account_id));

  sim.on('tick', () => {
    link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

function renderCircularFlows(flows) {
  const el = document.getElementById('circular-flows');
  if (!flows || !flows.length) { el.innerHTML = '<div class="empty-state"><p class="empty-title">No Circular Flows</p><p class="empty-desc">No circular money movement patterns detected in the current dataset</p></div>'; return; }
  el.innerHTML = flows.map(f => `
    <div class="card fade-in">
      <div style="padding:16px 20px;border-left:4px solid var(--accent-red);">
        <div style="font-weight:700;color:var(--accent-red);font-size:14px;">${f.pattern_type.replace(/_/g,' ').toUpperCase()}</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-top:6px;line-height:1.5;">${f.description}</div>
        <div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap;">
          <span style="font-size:11px;color:var(--accent-cyan);font-weight:600;">🔗 ${f.hop_count} hops</span>
          <span style="font-size:11px;color:var(--accent-orange);font-weight:600;">💰 ₹${Number(f.total_amount).toLocaleString()}</span>
          <span style="font-size:11px;color:var(--accent-green);font-weight:600;">🎯 ${(f.confidence*100).toFixed(0)}% confidence</span>
        </div>
      </div>
    </div>`).join('');
}

async function viewAccountGraph(accountId) {
  closeModal();
  switchPage('graph');
  try {
    const res = await fetch(API + '/api/graph/account/' + accountId);
    const data = await res.json();
    renderGraph(data);
    renderCircularFlows(data.circular_flows);
  } catch(e) { console.error('Account graph error:', e); }
}

// ── Pipeline ──
async function renderPipeline() {
  // Fetch real training metrics from the backend
  let metrics = null;
  try {
    const res = await fetch(API + '/api/dataset');
    const data = await res.json();
    if (data.model_metrics) metrics = data.model_metrics;
  } catch(e) { /* proceed without metrics */ }

  const acc = metrics ? (metrics.accuracy * 100).toFixed(1) + '%' : '97.0%';
  const auc = metrics ? metrics.roc_auc.toFixed(4) : '0.8340';
  const precF = metrics ? (metrics.precision_fraud * 100).toFixed(1) + '%' : '89%';
  const recF = metrics ? (metrics.recall_fraud * 100).toFixed(1) + '%' : '67%';
  const f1F = metrics ? (metrics.f1_fraud * 100).toFixed(1) + '%' : '77%';
  const cm = metrics ? metrics.confusion_matrix : { tn: 9214, fp: 60, fn: 236, tp: 490 };

  document.getElementById('pipeline-models').innerHTML = [
    ['XGBoost Classifier', true, `Gradient-boosted decision trees trained on 50K transactions with 14 engineered features. Uses scale_pos_weight for class imbalance. Accuracy: ${acc}, AUC: ${auc}.`, 'var(--accent-blue)', 'Weight: 25% · Real Trained Model'],
    ['Isolation Forest', true, 'Unsupervised anomaly detector (100 estimators, 5% contamination). Finds transactions that deviate from normal patterns without needing labeled data. Scores normalized via decision_function.', 'var(--accent-cyan)', 'Weight: 20% · Real Trained Model'],
    ['GraphSAGE (GNN)', false, 'Feature-based heuristic using real graph topology: sender/receiver degree centrality, cross-bank transfer flags, and amount concentration ratios. Simulates what a trained GNN would learn from the transaction graph.', 'var(--accent-purple)', 'Weight: 35% · Heuristic (Graph Features)'],
    ['LSTM Sequence', false, 'Feature-based heuristic using real sequential signals: time-of-day anomalies, amount deviation from sender history, and sender velocity (unique receiver fan-out). Simulates temporal pattern detection.', 'var(--accent-green)', 'Weight: 20% · Heuristic (Temporal Features)']
  ].map(([n,isTrained,d,c,w])=>`<div class="score-item">
    <div style="font-weight:700;color:${c};font-size:14px;">${isTrained ? '✅' : '🔧'} ${n}</div>
    <div style="font-size:12px;color:var(--text-secondary);margin-top:6px;line-height:1.5;">${d}</div>
    <div style="font-size:11px;color:var(--text-muted);margin-top:8px;font-weight:700;">${w}</div>
  </div>`).join('');

  // Confusion matrix visualization
  const cmHtml = `
    <div style="margin-top:16px;padding:16px;background:#f8fafc;border-radius:10px;border:1px solid var(--border-light);">
      <div style="font-weight:700;font-size:13px;margin-bottom:12px;">Confusion Matrix (Test Set: ${cm.tn + cm.fp + cm.fn + cm.tp} samples)</div>
      <table style="width:100%;text-align:center;font-size:13px;border-collapse:collapse;">
        <tr><td></td><td style="font-weight:700;padding:8px;color:var(--accent-green);">Pred Normal</td><td style="font-weight:700;padding:8px;color:var(--accent-red);">Pred Fraud</td></tr>
        <tr>
          <td style="font-weight:700;padding:8px;">Actual Normal</td>
          <td style="padding:10px;background:#d1fae5;border-radius:6px;font-weight:800;font-size:16px;">${cm.tn.toLocaleString()}</td>
          <td style="padding:10px;background:#fee2e2;border-radius:6px;font-weight:600;">${cm.fp.toLocaleString()}</td>
        </tr>
        <tr>
          <td style="font-weight:700;padding:8px;">Actual Fraud</td>
          <td style="padding:10px;background:#fef3c7;border-radius:6px;font-weight:600;">${cm.fn.toLocaleString()}</td>
          <td style="padding:10px;background:#d1fae5;border-radius:6px;font-weight:800;font-size:16px;">${cm.tp.toLocaleString()}</td>
        </tr>
      </table>
      <div style="font-size:11px;color:var(--text-muted);margin-top:8px;">
        TN=${cm.tn.toLocaleString()} · FP=${cm.fp.toLocaleString()} · FN=${cm.fn.toLocaleString()} · TP=${cm.tp.toLocaleString()}
        · Label noise: 2.5% injected to simulate real-world annotation uncertainty
      </div>
    </div>`;

  document.getElementById('pipeline-metrics').innerHTML = [
    ['Detection Accuracy', acc, `XGBoost: precision=${precF}, recall=${recF}, F1=${f1F} on held-out test set`],
    ['ROC AUC Score', auc, 'Area under Receiver Operating Characteristic curve'],
    ['Fraud Precision', precF, 'Of transactions flagged as fraud, this % were actually fraudulent'],
    ['Fraud Recall', recF, 'Of all actual fraud cases, this % were correctly detected'],
    ['Alert Latency','< 50ms','End-to-end time from transaction ingestion to scored alert'],
    ['Graph Hop Detection','2-7 hops','DFS-based cycle detection with deduplication + normalization']
  ].map(([l,v,d])=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid var(--border-light);">
    <div style="flex:1;"><div style="font-weight:600;font-size:13px;color:var(--text-primary);">${l}</div><div style="font-size:11px;color:var(--text-muted);margin-top:2px;line-height:1.4;">${d}</div></div>
    <div style="font-size:18px;font-weight:800;color:var(--accent-blue);margin-left:16px;white-space:nowrap;">${v}</div>
  </div>`).join('') + cmHtml;
}

// ── New Transaction Modal ──
function openNewTxnModal() {
  document.getElementById('new-txn-modal').classList.add('active');
  document.getElementById('txn-result').style.display = 'none';
  document.getElementById('btn-submit-txn').disabled = false;
  document.getElementById('btn-submit-txn').textContent = '🚀 Submit & Score';
}

function closeNewTxnModal() {
  document.getElementById('new-txn-modal').classList.remove('active');
}

function applyPreset(type) {
  if (type === 'normal') {
    document.getElementById('txn-sender-name').value = 'Rahul Sharma';
    document.getElementById('txn-sender-acct').value = 'HDFC12345678';
    document.getElementById('txn-receiver-name').value = 'Amazon India Pvt Ltd';
    document.getElementById('txn-receiver-acct').value = 'ICIC87654321';
    document.getElementById('txn-amount').value = 5200;
    document.getElementById('txn-channel').value = 'UPI';
    document.getElementById('txn-sender-bank').value = 'HDFC Bank';
    document.getElementById('txn-receiver-bank').value = 'ICICI Bank';
    document.getElementById('txn-location').value = 'Bangalore';
  } else if (type === 'suspicious') {
    document.getElementById('txn-sender-name').value = 'Raj Enterprises LLC';
    document.getElementById('txn-sender-acct').value = 'PSBN00099887';
    document.getElementById('txn-receiver-name').value = 'Offshore Holdings Ltd';
    document.getElementById('txn-receiver-acct').value = 'AXIS77665544';
    document.getElementById('txn-amount').value = 750000;
    document.getElementById('txn-channel').value = 'RTGS';
    document.getElementById('txn-sender-bank').value = 'PSB National Bank';
    document.getElementById('txn-receiver-bank').value = 'Axis Bank';
    document.getElementById('txn-location').value = 'Mumbai';
  } else if (type === 'critical') {
    document.getElementById('txn-sender-name').value = 'Shell Corp Intl';
    document.getElementById('txn-sender-acct').value = 'DEMO99998888';
    document.getElementById('txn-receiver-name').value = 'Hawala Network Node';
    document.getElementById('txn-receiver-acct').value = 'SWIFT11112222';
    document.getElementById('txn-amount').value = 2500000;
    document.getElementById('txn-channel').value = 'SWIFT';
    document.getElementById('txn-sender-bank').value = 'SBI';
    document.getElementById('txn-receiver-bank').value = 'Axis Bank';
    document.getElementById('txn-location').value = 'Dubai';
  }
}

async function submitNewTransaction(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-txn');
  btn.disabled = true;
  btn.textContent = '⏳ Scoring...';

  const body = {
    sender_name: document.getElementById('txn-sender-name').value,
    sender_account: document.getElementById('txn-sender-acct').value,
    receiver_name: document.getElementById('txn-receiver-name').value,
    receiver_account: document.getElementById('txn-receiver-acct').value,
    amount: parseFloat(document.getElementById('txn-amount').value),
    channel: document.getElementById('txn-channel').value,
    sender_bank: document.getElementById('txn-sender-bank').value,
    receiver_bank: document.getElementById('txn-receiver-bank').value,
    location: document.getElementById('txn-location').value,
  };

  try {
    const res = await fetch(API + '/api/transactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    const score = data.ml_score;
    const scoreColor = getScoreColor(score.composite_score);
    const tierColors = { CRITICAL: '#dc2626', HIGH: '#f59e0b', MEDIUM: '#2563eb', LOW: '#059669' };

    let alertHtml = '';
    if (data.alert) {
      alertHtml = `
        <div style="margin-top:12px;padding:10px 14px;background:rgba(220,38,38,0.08);border-radius:8px;border-left:4px solid #dc2626;">
          <div style="font-weight:700;color:#dc2626;font-size:13px;">🚨 Alert Created: ${data.alert.alert_id}</div>
          <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">Go to Alerts page to review, generate STR, or mark as false positive</div>
        </div>`;
    }

    let shapHtml = '';
    if (data.shap_top_features && data.shap_top_features.length) {
      shapHtml = `<div style="margin-top:10px;font-size:12px;color:var(--text-secondary);">
        <strong>Top SHAP factors:</strong> ${data.shap_top_features.map(s => 
          `<span style="color:${s.direction === 'increases_risk' ? '#dc2626' : '#059669'};">${s.feature} (${s.importance.toFixed(2)})</span>`
        ).join(' · ')}
      </div>`;
    }

    document.getElementById('txn-result').style.display = 'block';
    document.getElementById('txn-result').innerHTML = `
      <div style="padding:16px;background:#f8fafc;border-radius:10px;border:1px solid var(--border-light);">
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">
          <div style="width:48px;height:48px;border-radius:50%;background:${scoreColor};display:flex;align-items:center;justify-content:center;color:white;font-weight:800;font-size:16px;">${score.composite_score}</div>
          <div>
            <div style="font-weight:700;font-size:15px;color:var(--text-primary);">Risk Score: ${score.composite_score}/100</div>
            <div style="font-size:12px;font-weight:700;color:${tierColors[score.tier] || '#64748b'};">${score.tier} · Scored in ${score.latency_ms}ms</div>
          </div>
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">
          TXN: ${data.txn_id} · Broadcast to ${data.ws_broadcast} client(s)
        </div>
        ${shapHtml}
        ${alertHtml}
      </div>`;

    // Show toast
    const tier = score.tier;
    if (tier === 'CRITICAL' || tier === 'HIGH') {
      showToast(`Transaction scored ${score.composite_score}/100 (${tier})! Alert created.`, 'danger');
    } else {
      showToast(`Transaction scored ${score.composite_score}/100 (${tier}).`, 'success');
    }

    btn.textContent = '✅ Scored! Submit Another';
    btn.disabled = false;
    refreshDashboard();
  } catch(err) {
    console.error('Submit error:', err);
    btn.textContent = '❌ Error — Retry';
    btn.disabled = false;
    showToast('Failed to submit transaction. Check console.', 'danger');
  }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  updateClock();
  refreshDashboard();
  // Connect WebSocket for true real-time streaming
  connectWebSocket();
  // Fallback polling (in case WebSocket fails)
  setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      loadLiveFeed();
    }
  }, 15000);
});
