// ── Dashboard State ──────────────────────────────────────────
const API_URL = 'http://127.0.0.1:8765';
let currentView = 'overview';
let activityChart = null;
let platformChart = null;
let searchDebounce = null;

// ── Platform Helpers ────────────────────────────────────────
const PLATFORM_LABELS = {
  telegram: 'Telegram',
  http: 'Desktop',
  websocket: 'WebSocket',
  cli: 'CLI',
  slack: 'Slack',
};

const PLATFORM_COLORS = {
  telegram: '#0088cc',
  http: '#8b5cf6',
  websocket: '#a855f7',
  cli: '#10b981',
  slack: '#e01e5a',
};

const PLATFORM_ICONS = {
  telegram: 'TG',
  http: 'DT',
  websocket: 'WS',
  cli: 'CLI',
  slack: 'SL',
};

function getPlatformClass(platform) {
  return PLATFORM_COLORS[platform] ? platform : 'default';
}

let apiToken = '';

async function fetchJSON(path, options = {}) {
  if (!apiToken && window.saladbox?.getToken) {
    try {
      apiToken = await window.saladbox.getToken();
    } catch (e) {
      console.error('Failed to get security token:', e);
    }
  }
  
  options.headers = options.headers || {};
  if (apiToken) {
    options.headers['Authorization'] = `Bearer ${apiToken}`;
  }
  
  const res = await fetch(`${API_URL}${path}`, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadStats() {
  try {
    return await fetchJSON('/api/dashboard/stats');
  } catch (e) {
    console.error('Failed to load stats:', e);
    return null;
  }
}

async function loadConversations(platform = null, limit = 50, offset = 0) {
  try {
    let path = `/api/dashboard/conversations?limit=${limit}&offset=${offset}`;
    if (platform) path += `&platform=${platform}`;
    return await fetchJSON(path);
  } catch (e) {
    console.error('Failed to load conversations:', e);
    return { conversations: [] };
  }
}

async function loadMessages(conversationId) {
  try {
    return await fetchJSON(`/api/dashboard/conversations/${encodeURIComponent(conversationId)}`);
  } catch (e) {
    console.error('Failed to load messages:', e);
    return { messages: [] };
  }
}

async function searchMessages(query, platform = null) {
  try {
    let path = `/api/dashboard/search?q=${encodeURIComponent(query)}`;
    if (platform) path += `&platform=${platform}`;
    return await fetchJSON(path);
  } catch (e) {
    console.error('Failed to search messages:', e);
    return { results: [] };
  }
}

// ── Time Formatting ─────────────────────────────────────────
function parseDate(dateStr) {
  if (!dateStr) return null;
  let clean = dateStr;
  // Truncate sub-millisecond precision to 3 digits (e.g., .123456 -> .123)
  if (clean.includes('.')) {
    clean = clean.replace(/\.(\d{3})\d+/, '.$1');
  }
  
  if (clean.endsWith('Z') || /[-+]\d{2}:?\d{2}$/.test(clean)) {
    const d = new Date(clean);
    if (!isNaN(d.getTime())) return d;
  }
  
  clean = clean.replace(' ', 'T');
  if (!clean.includes('Z') && !clean.includes('+') && !clean.includes('-')) {
    clean += 'Z';
  }
  const d = new Date(clean);
  return isNaN(d.getTime()) ? new Date(dateStr) : d;
}

function stripMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/!\[.*?\]\(.*?\)/g, '')
    .replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/^#+\s+/gm, '')
    .replace(/[\*_~`\-]/g, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function timeAgo(dateStr) {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return '';
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDate(dateStr) {
  const date = parseDate(dateStr);
  if (!date || isNaN(date.getTime())) return '';
  return date.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

// ── Navigation ──────────────────────────────────────────────
function switchView(view) {
  currentView = view;

  // Update nav
  document.querySelectorAll('.dash-nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });

  // Update views
  document.querySelectorAll('.dash-view').forEach(v => {
    v.classList.toggle('active', v.id === `view-${view}`);
  });

  // Hide detail panel
  document.getElementById('conversation-detail').classList.add('hidden');

  // Load data for view
  switch (view) {
    case 'overview':
      loadOverview();
      break;
    case 'conversations':
      loadAllConversations();
      break;
    case 'telegram':
      loadPlatformConversations('telegram', 'telegram-conversations');
      break;
    case 'desktop':
      loadPlatformConversations('http', 'desktop-conversations');
      break;
    case 'search':
      document.getElementById('search-input').focus();
      break;
  }
}

// ── Overview ────────────────────────────────────────────────
async function loadOverview() {
  const stats = await loadStats();
  if (!stats) return;

  // Update stat cards
  document.getElementById('stat-conversations').textContent =
    stats.total_conversations?.toLocaleString() || '0';
  document.getElementById('stat-messages').textContent =
    stats.total_messages?.toLocaleString() || '0';
  document.getElementById('stat-avg').textContent =
    stats.avg_messages_per_conversation || '0';
  document.getElementById('stat-platforms').textContent =
    stats.platforms?.length || '0';

  // Activity chart (messages over time)
  renderActivityChart(stats.messages_per_day || []);

  // Platform distribution
  renderPlatformChart(stats.platforms || []);

  // Recent conversations
  const { conversations } = await loadConversations(null, 5);
  renderConversationsList(conversations, 'recent-conversations');
}

function renderActivityChart(data) {
  const ctx = document.getElementById('chart-activity');
  if (!ctx) return;

  if (activityChart) activityChart.destroy();

  const labels = data.map(d => {
    const date = new Date(d.date);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });
  const values = data.map(d => d.count);

  activityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: '#8b5cf6',
        backgroundColor: 'rgba(139, 92, 246, 0.08)',
        borderWidth: 2.5,
        tension: 0.4,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#8b5cf6',
        pointHoverBorderColor: '#fff',
        pointHoverBorderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a1a1e',
          titleColor: '#f4f4f5',
          bodyColor: '#a1a1aa',
          borderColor: '#27272a',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          displayColors: false,
          callbacks: {
            title: (items) => items[0]?.label || '',
            label: (item) => `${item.raw} messages`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(39, 39, 42, 0.5)', drawBorder: false },
          ticks: { color: '#63637a', font: { size: 11 }, maxTicksLimit: 7 }
        },
        y: {
          grid: { color: 'rgba(39, 39, 42, 0.5)', drawBorder: false },
          ticks: { color: '#63637a', font: { size: 11 }, precision: 0 },
          beginAtZero: true,
        }
      },
      interaction: { intersect: false, mode: 'index' }
    }
  });
}

function renderPlatformChart(platforms) {
  const ctx = document.getElementById('chart-platforms');
  const legend = document.getElementById('platform-legend');
  if (!ctx || !legend) return;

  if (platformChart) platformChart.destroy();

  if (platforms.length === 0) {
    legend.innerHTML = '<span style="color: var(--text-muted); font-size: 13px;">No data yet</span>';
    return;
  }

  const labels = platforms.map(p => PLATFORM_LABELS[p.platform] || p.platform);
  const values = platforms.map(p => p.conversations);
  const colors = platforms.map(p => PLATFORM_COLORS[p.platform] || '#6b7280');

  platformChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderColor: '#16161a',
        borderWidth: 3,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '68%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a1a1e',
          titleColor: '#f4f4f5',
          bodyColor: '#a1a1aa',
          borderColor: '#27272a',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
        }
      }
    }
  });

  // Custom legend
  legend.innerHTML = platforms.map((p, i) => `
    <div class="legend-item">
      <span class="legend-dot" style="background: ${colors[i]}"></span>
      <span class="legend-label">${labels[i]}</span>
      <span class="legend-value">${p.conversations} chats / ${p.messages} msgs</span>
    </div>
  `).join('');
}

// ── Conversation Lists ──────────────────────────────────────
function renderConversationsList(conversations, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!conversations || conversations.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <h3>No conversations yet</h3>
        <p>Start chatting to see your conversations appear here.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = conversations.map(conv => {
    const platform = conv.platform || 'cli';
    const platformClass = getPlatformClass(platform);
    const icon = PLATFORM_ICONS[platform] || '?';
    const title = conv.title || conv.id || 'Untitled';
    const rawPreview = conv.last_assistant_message
      ? conv.last_assistant_message
      : conv.last_user_message
        ? conv.last_user_message
        : 'No messages';
    const preview = stripMarkdown(rawPreview).substring(0, 120);
    const time = timeAgo(conv.updated_at);
    const count = conv.message_count || 0;

    return `
      <div class="conv-item" data-id="${conv.id}" onclick="openConversation('${encodeURIComponent(conv.id)}', '${title.replace(/'/g, "\\'")}', '${platform}')">
        <div class="conv-platform-icon ${platformClass}">${icon}</div>
        <div class="conv-body">
          <div class="conv-title">${escapeHtml(title)}</div>
          <div class="conv-preview">${escapeHtml(preview)}</div>
        </div>
        <div class="conv-meta">
          <span class="conv-time">${time}</span>
          <span class="conv-badge messages">${count} msgs</span>
        </div>
      </div>
    `;
  }).join('');
}

async function loadAllConversations() {
  const platform = document.getElementById('filter-platform')?.value || null;
  const { conversations } = await loadConversations(platform || null, 100);
  renderConversationsList(conversations, 'all-conversations');
}

async function loadPlatformConversations(platform, containerId) {
  const { conversations } = await loadConversations(platform, 100);
  renderConversationsList(conversations, containerId);
}

// ── Conversation Detail ─────────────────────────────────────
async function openConversation(encodedId, title, platform) {
  const id = decodeURIComponent(encodedId);
  localStorage.setItem('open_chat_id', id);
  if (window.saladbox?.openChat) {
    window.saladbox.openChat();
  } else {
    window.location.href = 'index.html';
  }
}

// ── Search ──────────────────────────────────────────────────
async function performSearch(query) {
  const container = document.getElementById('search-results');
  if (!query || query.length < 2) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </div>
        <h3>Search your messages</h3>
        <p>Type at least 2 characters to search across all conversations and platforms.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';

  const { results } = await searchMessages(query);

  if (!results || results.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <h3>No results</h3>
        <p>No messages matched "${escapeHtml(query)}".</p>
      </div>
    `;
    return;
  }

  container.innerHTML = results.map(r => {
    const platform = r.conv_platform || r.platform || 'cli';
    const highlighted = highlightMatch(r.content, query);
    const time = formatDate(r.created_at);
    const convTitle = r.conv_title || r.conversation_id;

    return `
      <div class="search-result-item" onclick="openConversation('${encodeURIComponent(r.conversation_id)}', '${(convTitle || '').replace(/'/g, "\\'")}', '${platform}')">
        <div class="search-result-header">
          <span class="search-result-platform">${PLATFORM_LABELS[platform] || platform}</span>
          <span class="search-result-time">${time}</span>
        </div>
        <div class="search-result-content">${highlighted}</div>
        <div class="search-result-conv">${escapeHtml(convTitle)}</div>
      </div>
    `;
  }).join('');
}

function highlightMatch(text, query) {
  if (!text) return '';
  const truncated = text.length > 300 ? text.substring(0, 300) + '...' : text;
  const escaped = escapeHtml(truncated);
  const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
  return escaped.replace(regex, '<mark>$1</mark>');
}

// ── Utilities ───────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function renderMarkdown(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true, mangle: false, headerIds: false });
    return marked.parse(text);
  }
  return escapeHtml(text).replace(/\n/g, '<br>');
}

// ── Event Listeners ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Navigation
  document.querySelectorAll('.dash-nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  // View All buttons
  document.querySelectorAll('.view-all-btn').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.target));
  });

  // Back to chat
  document.getElementById('back-to-chat')?.addEventListener('click', () => {
    if (window.saladbox?.openChat) {
      window.saladbox.openChat();
    } else {
      window.location.href = 'index.html';
    }
  });

  // Detail back button
  document.getElementById('detail-back')?.addEventListener('click', () => {
    document.getElementById('conversation-detail').classList.add('hidden');
  });

  // Platform filter
  document.getElementById('filter-platform')?.addEventListener('change', loadAllConversations);

  // Search
  const searchInput = document.getElementById('search-input');
  searchInput?.addEventListener('input', (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => performSearch(e.target.value.trim()), 300);
  });

  searchInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      clearTimeout(searchDebounce);
      performSearch(e.target.value.trim());
    }
  });

  // Initial load
  loadOverview();
});
