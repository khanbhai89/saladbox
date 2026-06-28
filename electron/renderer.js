// State
const API_URL = 'http://127.0.0.1:8765';
let apiToken = '';

async function authenticatedFetch(url, options = {}) {
  options.headers = options.headers || {};
  if (apiToken) {
    options.headers['Authorization'] = `Bearer ${apiToken}`;
  }
  return fetch(url, options);
}
let conversationId = Date.now().toString();
let isProcessing = false;
let currentProvider = 'ollama';
let useCustomModel = false;
let customModelName = '';
let models = { ollama: {}, openrouter: {} };

// TTS State
let ttsEnabled = true;
let ttsAutoRead = false;
let ttsVoiceName = '';
let ttsRate = 1.0;
let currentUtterance = null;
let isSpeaking = false;

const MCP_PRESETS = {
  github: {
    name: "github",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-github"],
    env: { GITHUB_PERSONAL_ACCESS_TOKEN: "" },
  },
  "brave-search": {
    name: "brave-search",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-brave-search"],
    env: { BRAVE_API_KEY: "" },
  },
  opencode: {
    name: "opencode",
    command: "npx",
    args: ["-y", "opencode-mcp-tool"],
    env: { OPENCODE_MODEL: "anthropic/claude-sonnet-4-5", OPENCODE_API_KEY: "" },
  },
};

// DOM Elements
const messagesContainer = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-btn');
const newChatButton = document.getElementById('new-chat-btn');
const settingsButton = document.getElementById('settings-btn');
const closeSettingsButton = document.getElementById('close-settings');
const settingsPanel = document.getElementById('settings-panel');
const settingsOverlay = document.getElementById('settings-overlay');
const statusElement = document.getElementById('status');
const appVersionElement = document.getElementById('app-version');
const backendStatus = document.getElementById('backend-status');

// Settings Elements
const providerSelect = document.getElementById('provider-select');
const defaultModelSelect = document.getElementById('default-model-select');
const codeModelSelect = document.getElementById('code-model-select');
const fastModelSelect = document.getElementById('fast-model-select');
const customModelToggle = document.getElementById('custom-model-toggle');
const customModelInput = document.getElementById('custom-model-input');
const customModelNameInput = document.getElementById('custom-model-name');
const toolsList = document.getElementById('tools-list');

// Initialize
async function init() {
  try {
    apiToken = await window.saladbox.getToken();
  } catch (error) {
    console.error('Failed to get security token:', error);
  }
  await loadVersion();
  await loadModels();
  await loadTools();
  await loadConversations();
  
  const openChatId = localStorage.getItem('open_chat_id');
  if (openChatId) {
    localStorage.removeItem('open_chat_id');
    await loadConversation(openChatId);
  }
  
  await loadMCPServerStatus();
  setupEventListeners();
  loadSettings();
  initSidebarResize();
  startNotificationPolling();
}

function setupEventListeners() {
  // Send message
  sendButton.addEventListener('click', sendMessage);
  messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  
  // Auto-resize textarea
  messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    updateCharCount();
  });
  
  // New chat
  newChatButton.addEventListener('click', newChat);
  
  // Theme toggle
  document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
  
  // Search button
  document.getElementById('search-conv-btn')?.addEventListener('click', toggleSearch);
  
  // Voice input
  document.getElementById('voice-input-btn')?.addEventListener('click', toggleVoiceInput);
  
  // File attachment
  document.getElementById('attach-file-btn')?.addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = 'image/*,.txt,.md,.pdf,.doc,.docx';
    input.onchange = (e) => handleFileUpload(e.target.files);
    input.click();
  });
  
  // Handle paste for images
  messageInput.addEventListener('paste', handlePaste);
  
  // Handle drag and drop
  const chatContainer = document.querySelector('.chat-container');
  if (chatContainer) {
    chatContainer.addEventListener('dragover', (e) => {
      e.preventDefault();
      chatContainer.classList.add('drag-over');
    });
    chatContainer.addEventListener('dragleave', () => {
      chatContainer.classList.remove('drag-over');
    });
    chatContainer.addEventListener('drop', (e) => {
      e.preventDefault();
      chatContainer.classList.remove('drag-over');
      handleFileUpload(e.dataTransfer.files);
    });
  }
  
  // Keyboard shortcuts
  document.addEventListener('keydown', handleKeyboardShortcuts);
  
  // Dashboard
  const dashboardButton = document.getElementById('dashboard-btn');
  if (dashboardButton) {
    dashboardButton.addEventListener('click', () => {
      window.location.href = 'dashboard.html';
    });
  }

  // Settings
  settingsButton.addEventListener('click', openSettings);
  closeSettingsButton.addEventListener('click', closeSettings);
  settingsOverlay.addEventListener('click', closeSettings);

  // Notification button - clear badge and show recent notifications
  const notifBtn = document.getElementById('notification-btn');
  if (notifBtn) {
    notifBtn.addEventListener('click', () => {
      const badge = document.getElementById('notification-badge');
      if (badge) {
        badge.textContent = '0';
        badge.classList.add('hidden');
      }
    });
  }

  // Settings tab switching
  document.querySelectorAll('.settings-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.dataset.tab;
      document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.settings-tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      const content = document.querySelector(`.settings-tab-content[data-tab="${tabName}"]`);
      if (content) content.classList.add('active');
    });
  });
  
  // Provider change
  providerSelect.addEventListener('change', (e) => {
    currentProvider = e.target.value;
    updateModelSelects();
    if (window.availableModels) {
      updateModelSelectsWithData(window.availableModels);
    }
    saveSettings();
  });
  
  // Custom model toggle
  customModelToggle.addEventListener('change', (e) => {
    useCustomModel = e.target.checked;
    customModelInput.style.display = useCustomModel ? 'block' : 'none';
    saveSettings();
  });
  
  // Custom model name
  customModelNameInput.addEventListener('change', (e) => {
    customModelName = e.target.value;
    saveSettings();
  });
  
  // Model selects
  [defaultModelSelect, codeModelSelect, fastModelSelect].forEach((select, index) => {
    select.addEventListener('change', async (e) => {
      const modelType = ['default', 'code', 'fast'][index];
      const modelName = e.target.value;
      
      try {
        await setModel(modelType, modelName);
      } catch (error) {
        console.error('Failed to set model:', error);
      }
      
      saveSettings();
    });
  });
  
  // ── Image Generation Settings ──────────────────────────────
  const imageGenBackend = document.getElementById('image-gen-backend');
  const imageGenModel = document.getElementById('image-gen-model');
  const imageGenQuantize = document.getElementById('image-gen-quantize');
  const imageGenWidth = document.getElementById('image-gen-width');
  const imageGenHeight = document.getElementById('image-gen-height');
  const imageGenSteps = document.getElementById('image-gen-steps');
  const drawthingsUrl = document.getElementById('drawthings-url');

  const imageGenInputs = [imageGenBackend, imageGenModel, imageGenQuantize, imageGenWidth, imageGenHeight, imageGenSteps, drawthingsUrl];
  imageGenInputs.forEach(input => {
    if (input) {
      input.addEventListener('change', async () => {
        try {
          await window.saladbox.updateImageGenConfig({
            backend: imageGenBackend?.value,
            model: imageGenModel?.value,
            quantize: parseInt(imageGenQuantize?.value),
            default_width: parseInt(imageGenWidth?.value),
            default_height: parseInt(imageGenHeight?.value),
            default_steps: parseInt(imageGenSteps?.value),
            drawthings_url: drawthingsUrl?.value,
          });
        } catch (e) {
          console.error('Failed to update image gen config:', e);
        }
      });
    }
  });

  // ── HuggingFace Token ──────────────────────────────────────
  const hfTokenInput = document.getElementById('hf-token-input');
  const hfTokenToggle = document.getElementById('hf-token-toggle');
  const hfTokenSaveBtn = document.getElementById('hf-token-save-btn');
  const hfTokenStatus = document.getElementById('hf-token-status');
  const hfLink = document.getElementById('hf-link');

  if (hfTokenToggle) {
    hfTokenToggle.addEventListener('click', () => {
      if (hfTokenInput) {
        hfTokenInput.type = hfTokenInput.type === 'password' ? 'text' : 'password';
      }
    });
  }

  if (hfLink) {
    hfLink.addEventListener('click', (e) => {
      e.preventDefault();
      window.saladbox.openExternal('https://huggingface.co/settings/tokens');
    });
  }

  if (hfTokenSaveBtn) {
    hfTokenSaveBtn.addEventListener('click', async () => {
      const token = hfTokenInput?.value?.trim();
      if (!token) {
        if (hfTokenStatus) hfTokenStatus.textContent = 'Please enter a token';
        return;
      }
      try {
        hfTokenSaveBtn.disabled = true;
        hfTokenSaveBtn.textContent = 'Saving...';
        const result = await window.saladbox.saveHFToken(token);
        if (result.success) {
          if (hfTokenStatus) {
            hfTokenStatus.textContent = '✓ Token saved successfully';
            hfTokenStatus.style.color = 'var(--success)';
          }
        } else {
          if (hfTokenStatus) {
            hfTokenStatus.textContent = '✗ ' + (result.error || 'Failed to save');
            hfTokenStatus.style.color = 'var(--error)';
          }
        }
      } catch (e) {
        if (hfTokenStatus) {
          hfTokenStatus.textContent = '✗ Error saving token';
          hfTokenStatus.style.color = 'var(--error)';
        }
      } finally {
        hfTokenSaveBtn.disabled = false;
        hfTokenSaveBtn.textContent = 'Save Token';
      }
    });
  }

  // Suggestion cards
  document.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
      const message = card.dataset.message;
      messageInput.value = message;
      messageInput.focus();
    });
  });
  
  // IPC events
  window.saladbox.onNewChat(newChat);
  window.saladbox.onOpenSettings(openSettings);
  
  // MCP preset buttons
  document.querySelectorAll('.settings-section .mcp-preset-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const mcpType = btn.dataset.mcp;
      const preset = MCP_PRESETS[mcpType];
      if (preset) {
        try {
          await window.saladbox.addMCPServer(preset);
          btn.disabled = true;
          btn.classList.add('selected');
          alert('MCP server added. Restart Saladbox to apply changes.');
        } catch (error) {
          console.error('Failed to add MCP server:', error);
        }
      }
    });
  });
  
  // Preference toggles
  document.getElementById('spell-check-toggle')?.addEventListener('change', (e) => {
    messageInput.spellcheck = e.target.checked;
    saveSettings();
  });
  
  document.getElementById('sound-toggle')?.addEventListener('change', saveSettings);
  document.getElementById('startup-toggle')?.addEventListener('change', saveSettings);
  document.getElementById('minimize-tray-toggle')?.addEventListener('change', saveSettings);

  // TTS settings
  document.getElementById('tts-enabled-toggle')?.addEventListener('change', (e) => {
    ttsEnabled = e.target.checked;
    if (!ttsEnabled) stopSpeaking();
    saveSettings();
  });

  document.getElementById('tts-auto-read-toggle')?.addEventListener('change', (e) => {
    ttsAutoRead = e.target.checked;
    saveSettings();
  });

  document.getElementById('tts-rate-slider')?.addEventListener('input', (e) => {
    ttsRate = parseFloat(e.target.value);
    const display = document.getElementById('tts-rate-value');
    if (display) display.textContent = ttsRate.toFixed(1);
    saveSettings();
  });

  document.getElementById('tts-voice-select')?.addEventListener('change', (e) => {
    ttsVoiceName = e.target.value;
    saveSettings();
  });

  // Populate TTS voices (may load asynchronously in Chromium)
  populateTTSVoices();
  if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = populateTTSVoices;
  }

  // Debug mode
  document.getElementById('debug-toggle')?.addEventListener('change', (e) => {
    window.saladbox.setDebugMode(e.target.checked);
    saveSettings();
  });
  
  // View logs
  document.getElementById('view-logs-btn')?.addEventListener('click', showLogViewer);
  
  // Data management
  document.getElementById('export-data-btn')?.addEventListener('click', exportAllData);
  document.getElementById('import-data-btn')?.addEventListener('click', importAllData);
  document.getElementById('clear-data-btn')?.addEventListener('click', clearAllData);
  
  // Temperature slider
  document.getElementById('temperature-slider')?.addEventListener('input', (e) => {
    document.getElementById('temperature-value').textContent = e.target.value;
    saveSettings();
  });
  
  // Add template
  document.getElementById('add-template-btn')?.addEventListener('click', addNewTemplate);

  // Collapsible sections
  document.querySelectorAll('.section-title.collapsible').forEach(title => {
    title.addEventListener('click', (e) => {
      if (e.target.closest('.btn-icon-small') && !e.target.closest('.collapse-btn')) return;
      title.classList.toggle('collapsed');
      const section = title.dataset.section;
      if (section === 'conversations') {
        document.querySelector('.conversations-section')?.classList.toggle('collapsed');
      } else if (section === 'mcp') {
        document.querySelector('.mcp-section')?.classList.toggle('collapsed');
      }
    });
  });

  // Emoji button
  document.getElementById('emoji-btn')?.addEventListener('click', toggleEmojiPicker);

  // Markdown toolbar buttons
  document.querySelectorAll('.md-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const type = btn.dataset.md;
      if (type) insertMarkdown(type);
    });
  });
}

function openSettings() {
  settingsPanel.classList.remove('hidden');
  settingsOverlay.classList.remove('hidden');
  loadImageGenConfig();
  loadHFStatus();
}

function closeSettings() {
  settingsPanel.classList.add('hidden');
  settingsOverlay.classList.add('hidden');
}

async function sendMessage() {
  const message = messageInput.value.trim();
  if (!message || isProcessing) return;
  
  const uploadedImages = Array.from(document.querySelectorAll('.uploaded-image img'))
    .map(img => img.src)
    .filter(src => src.startsWith('data:'));
  
  isProcessing = true;
  sendButton.disabled = true;
  updateStatus('Thinking...', 'thinking');
  
  const startTime = Date.now();
  
  messageInput.value = '';
  messageInput.style.height = 'auto';
  
  const welcome = messagesContainer.querySelector('.welcome');
  if (welcome) welcome.remove();
  
  addMessage('user', message);
  
  uploadedImages.forEach(imgSrc => {
    addImageToChat('uploaded-image', imgSrc);
  });
  
  document.querySelectorAll('.uploaded-image').forEach(el => el.remove());
  
  const typingMessage = addMessage('assistant', 'typing');
  
  try {
    const response = await window.saladbox.chat(message, conversationId, uploadedImages);
    
    const responseTime = Date.now() - startTime;
    const responseTimeSec = (responseTime / 1000).toFixed(1);
    
    typingMessage.remove();
    
    if (response.error) {
      addMessage('assistant', response.error, true);
    } else {
      const assistantMsg = addMessage('assistant', response.message);
      
      const timeIndicator = document.createElement('div');
      timeIndicator.className = 'response-time';
      timeIndicator.textContent = `Response time: ${responseTimeSec}s`;
      assistantMsg.querySelector('.message-content').appendChild(timeIndicator);

      // Auto-read response aloud if enabled
      if (ttsAutoRead && ttsEnabled) {
        speakText(response.message);
      }
    }
  } catch (error) {
    typingMessage.remove();
    addMessage('assistant', `Error: ${error.message}`, true);
  }
  
  isProcessing = false;
  sendButton.disabled = false;
  updateStatus('Ready', 'ready');
  messageInput.focus();
  loadConversations();
}

function updateStatus(text, type = 'ready') {
  const statusText = document.getElementById('status-text');
  const statusIndicator = document.getElementById('connection-status');
  
  if (statusText) statusText.textContent = text;
  if (statusIndicator) {
    statusIndicator.className = 'status-indicator';
    if (type === 'thinking') statusIndicator.classList.add('thinking');
    if (type === 'disconnected') statusIndicator.classList.add('disconnected');
  }
}

function updateCharCount() {
  const count = messageInput.value.length;
  let counter = document.getElementById('char-count');
  if (!counter) {
    counter = document.createElement('span');
    counter.id = 'char-count';
    counter.className = 'char-count';
    document.querySelector('.input-hint')?.appendChild(counter);
  }
  counter.textContent = `${count} chars`;
}

function newChat() {
  conversationId = Date.now().toString();
  
  messagesContainer.innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">
        <img src="assets/icon.png" alt="Saladbox" width="56" height="56" style="border-radius:14px">
      </div>
      <h2>How can I help you today?</h2>
      <p>I'm your local AI assistant with 30+ tools for system control, web search, weather, crypto, and more.</p>
      <div class="suggestions">
        <button class="suggestion-card" data-message="Check my system resources">
          <div class="suggestion-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
              <line x1="8" y1="21" x2="16" y2="21"></line>
              <line x1="12" y1="17" x2="12" y2="21"></line>
            </svg>
          </div>
          <span>System resources</span>
        </button>
        <button class="suggestion-card" data-message="What is Bitcoin price?">
          <div class="suggestion-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="1" x2="12" y2="23"></line>
              <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
            </svg>
          </div>
          <span>Crypto prices</span>
        </button>
        <button class="suggestion-card" data-message="What time is it?">
          <div class="suggestion-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
          </div>
          <span>Current time</span>
        </button>
        <button class="suggestion-card" data-message="Generate a secure password">
          <div class="suggestion-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
          </div>
          <span>Password</span>
        </button>
      </div>
    </div>
  `;
  
  document.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
      const message = card.dataset.message;
      messageInput.value = message;
      messageInput.focus();
    });
  });
  
  document.querySelectorAll('.conversation-item').forEach(item => {
    item.classList.remove('active');
  });
  
  loadConversations();
}

// Functions that were missing - added back
function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  applyTheme(newTheme);
}

function handleKeyboardShortcuts(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
    e.preventDefault();
    newChat();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === ',') {
    e.preventDefault();
    openSettings();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault();
    toggleSearch();
  }
  if (e.key === 'Escape') {
    closeSettings();
    closeSearch();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
    e.preventDefault();
    messageInput.focus();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
    e.preventDefault();
    exportChatAsMarkdown();
  }
}

let searchVisible = false;
function toggleSearch() {
  const sidebarContent = document.querySelector('.sidebar-content');
  if (!sidebarContent) return;
  
  let searchContainer = document.getElementById('search-container');
  
  if (!searchVisible) {
    if (!searchContainer) {
      searchContainer = document.createElement('div');
      searchContainer.id = 'search-container';
      searchContainer.className = 'search-container';
      searchContainer.innerHTML = `<input type="text" id="conversation-search" placeholder="Search conversations...">`;
      sidebarContent.insertBefore(searchContainer, sidebarContent.firstChild);
      
      document.getElementById('conversation-search')?.addEventListener('input', (e) => {
        searchConversations(e.target.value);
      });
    }
    searchContainer.classList.remove('hidden');
    document.getElementById('conversation-search')?.focus();
  } else {
    closeSearch();
  }
  searchVisible = !searchVisible;
}

function closeSearch() {
  const searchContainer = document.getElementById('search-container');
  if (searchContainer) searchContainer.classList.add('hidden');
  searchVisible = false;
}

function searchConversations(query) {
  const items = document.querySelectorAll('.conversation-item');
  query = query.toLowerCase();
  items.forEach(item => {
    const text = item.textContent.toLowerCase();
    item.style.display = text.includes(query) ? '' : 'none';
  });
}

let mediaRecorder = null;
let audioChunks = [];

function toggleVoiceInput() {
  const btn = document.getElementById('voice-input-btn');
  if (btn?.classList.contains('recording')) {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      btn.classList.remove('recording');
      updateStatus('Processing...', 'thinking');
    }
  } else {
    startRecording();
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    
    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      stream.getTracks().forEach(track => track.stop());
      await processAudio(audioBlob);
    };
    
    mediaRecorder.start();
    document.getElementById('voice-input-btn')?.classList.add('recording');
    updateStatus('Recording...', 'thinking');
  } catch (error) {
    console.error('Failed to start recording:', error);
    alert('Could not access microphone.');
  }
}

async function processAudio(audioBlob) {
  updateStatus('Transcribing...', 'thinking');
  const reader = new FileReader();
  reader.onload = async () => {
    const base64 = reader.result.split(',')[1];
    try {
      const response = await authenticatedFetch(`${API_URL}/api/transcribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio: base64 })
      });
      const data = await response.json();
      if (data.text) {
        messageInput.value += (messageInput.value ? ' ' : '') + data.text;
        messageInput.focus();
      }
    } catch (error) {
      console.error('Transcription failed:', error);
    }
    updateStatus('Ready', 'ready');
  };
  reader.readAsDataURL(audioBlob);
}

function handleFileUpload(files) {
  if (!files || files.length === 0) return;
  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = (e) => {
      if (file.type.startsWith('image/')) {
        addImageToChat(file.name, e.target.result);
      } else {
        addFileToChat(file.name, e.target.result);
      }
    };
    reader.readAsDataURL(file);
  });
}

function handlePaste(e) {
  const items = e.clipboardData?.items;
  if (!items) return;
  for (let item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile();
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => addImageToChat('pasted-image', e.target.result);
        reader.readAsDataURL(file);
      }
    }
  }
}

function addImageToChat(name, dataUrl) {
  const imgDiv = document.createElement('div');
  imgDiv.className = 'uploaded-image';
  imgDiv.innerHTML = `<img src="${dataUrl}" alt="${name}"><span class="image-name">${name}</span>`;
  document.querySelector('.messages')?.appendChild(imgDiv);
}

function addFileToChat(name, content) {
  const fileDiv = document.createElement('div');
  fileDiv.className = 'uploaded-file';
  fileDiv.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg><span>${name}</span>`;
  document.querySelector('.messages')?.appendChild(fileDiv);
}

function exportChatAsMarkdown() {
  const messages = document.querySelectorAll('.message');
  let md = '# Saladbox Chat Export\n\n' + `Exported: ${new Date().toLocaleString()}\n\n---\n\n`;
  messages.forEach(msg => {
    const role = msg.classList.contains('user') ? '**User**' : '**Assistant**';
    const content = msg.querySelector('.message-content')?.textContent || '';
    md += `${role}:\n\n${content}\n\n---\n\n`;
  });
  const blob = new Blob([md], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `saladbox-chat-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function setModel(type, model) {
  return authenticatedFetch(`${API_URL}/models/set`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: currentProvider, type, model })
  }).then(r => r.json());
}

function saveSettings() {
  const settings = {
    useCustomModel,
    customModelName,
    provider: currentProvider,
    systemPrompt: document.getElementById('system-prompt')?.value || '',
    temperature: parseFloat(document.getElementById('temperature-slider')?.value) || 0.7,
    maxTokens: parseInt(document.getElementById('max-tokens')?.value) || 4096,
    spellCheck: document.getElementById('spell-check-toggle')?.checked ?? true,
    soundEnabled: document.getElementById('sound-toggle')?.checked ?? false,
    startWithSystem: document.getElementById('startup-toggle')?.checked ?? false,
    minimizeToTray: document.getElementById('minimize-tray-toggle')?.checked ?? true,
    ttsEnabled: document.getElementById('tts-enabled-toggle')?.checked ?? true,
    ttsAutoRead: document.getElementById('tts-auto-read-toggle')?.checked ?? false,
    ttsVoiceName: document.getElementById('tts-voice-select')?.value || '',
    ttsRate: parseFloat(document.getElementById('tts-rate-slider')?.value) || 1.0,
  };
  localStorage.setItem('saladbox_settings', JSON.stringify(settings));
}

function initSidebarResize() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  
  let isResizing = false;
  
  document.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('sidebar-resize-handle')) {
      isResizing = true;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }
  });
  
  document.addEventListener('mousemove', (e) => {
    if (isResizing) {
      const newWidth = Math.max(200, Math.min(400, e.clientX));
      sidebar.style.width = newWidth + 'px';
      localStorage.setItem('saladbox_sidebar_width', newWidth);
    }
  });
  
  document.addEventListener('mouseup', () => {
    isResizing = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
  
  // Restore saved width
  const savedWidth = localStorage.getItem('saladbox_sidebar_width');
  if (savedWidth) {
    sidebar.style.width = savedWidth + 'px';
  }
}

async function loadMCPServerStatus() {
  try {
    const data = await window.saladbox.getMCPServers();
    const container = document.getElementById('mcp-status-list');
    const title = document.querySelector('.mcp-status-title');
    const count = document.getElementById('mcp-count');
    
    if (!data.servers || data.servers.length === 0) {
      if (title) title.style.display = 'none';
      if (container) container.style.display = 'none';
      return;
    }
    
    if (title) title.style.display = 'flex';
    if (container) container.style.display = 'block';
    if (count) count.textContent = data.servers.length;
    
    container.innerHTML = data.servers.map(server => `
      <div class="mcp-status-item ${server.enabled ? 'enabled' : 'disabled'}">
        <span class="mcp-status-dot"></span>
        <span class="mcp-status-name">${server.name}</span>
      </div>
    `).join('');
  } catch (error) {
    console.error('Failed to load MCP server status:', error);
  }
}

async function loadVersion() {
  try {
    const version = await window.saladbox.getVersion();
    appVersionElement.textContent = `v${version}`;
  } catch (error) {
    console.error('Failed to load version:', error);
  }
}

async function loadModels() {
  try {
    models = await window.saladbox.getModels();
    
    if (models.openrouter?.enabled) {
      currentProvider = 'openrouter';
      providerSelect.value = 'openrouter';
    } else {
      currentProvider = 'ollama';
      providerSelect.value = 'ollama';
    }
    
    updateModelSelects();
    await populateModelDropdowns();
    backendStatus.textContent = 'Connected';
    backendStatus.style.color = 'var(--success)';
  } catch (error) {
    console.error('Failed to load models:', error);
    backendStatus.textContent = 'Disconnected';
    backendStatus.style.color = 'var(--error)';
  }
}

async function populateModelDropdowns() {
  // Get available models from both providers
  const [ollamaModels, openrouterModels] = await Promise.all([
    window.saladbox.getOllamaModels(),
    window.saladbox.getOpenRouterModels()
  ]);
  
  const modelData = {
    ollama: ollamaModels.map(m => ({ name: m.name, id: m.name })),
    openrouter: openrouterModels.slice(0, 50).map(m => ({ name: m.name || m.id, id: m.id }))
  };
  
  // Store for later use
  window.availableModels = modelData;
  
  updateModelSelectsWithData(modelData);
  populateQuickModelSwitcher(modelData);
}

function populateQuickModelSwitcher(modelData) {
  const quickSelect = document.getElementById('quick-model-select');
  if (!quickSelect) return;
  
  quickSelect.innerHTML = '<option value="">Default Model</option>';
  
  const popularModels = [
    'anthropic/claude-3.5-sonnet',
    'openai/gpt-4o',
    'openai/gpt-4o-mini',
    'llama3',
    'llama3.1',
    'mistral',
    'codellama'
  ];
  
  popularModels.forEach(modelId => {
    const option = document.createElement('option');
    option.value = modelId;
    option.textContent = modelId.split('/').pop();
    quickSelect.appendChild(option);
  });
  
  quickSelect.addEventListener('change', (e) => {
    const model = e.target.value;
    if (model) {
      setModel('default', model);
    }
  });
}

function updateModelSelects() {
  const providerModels = models[currentProvider] || {};
  
  [defaultModelSelect, codeModelSelect, fastModelSelect].forEach((select, index) => {
    const modelKey = ['default_model', 'code_model', 'fast_model'][index];
    const currentModel = providerModels[modelKey] || '';
    
    if (currentModel && !select.querySelector(`option[value="${currentModel}"]`)) {
      const option = document.createElement('option');
      option.value = currentModel;
      option.textContent = currentModel;
      select.appendChild(option);
    }
    
    if (currentModel) {
      select.value = currentModel;
    }
  });
}

function updateModelSelectsWithData(modelData) {
  [defaultModelSelect, codeModelSelect, fastModelSelect].forEach((select) => {
    const currentValue = select.value;
    select.innerHTML = '';
    
    // Add Ollama models
    const ollamaGroup = document.createElement('optgroup');
    ollamaGroup.label = 'Ollama (Local)';
    
    if (modelData.ollama.length === 0) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No models installed';
      ollamaGroup.appendChild(option);
    } else {
      modelData.ollama.forEach(model => {
        const option = document.createElement('option');
        option.value = model.id;
        option.textContent = model.name;
        if (currentProvider === 'ollama') {
          ollamaGroup.appendChild(option);
        }
      });
    }
    
    // Add OpenRouter models
    const openrouterGroup = document.createElement('optgroup');
    openrouterGroup.label = 'OpenRouter (Cloud)';
    
    const popularModels = [
      'anthropic/claude-3.5-sonnet',
      'anthropic/claude-3-opus',
      'openai/gpt-4o',
      'openai/gpt-4o-mini',
      'google/gemini-pro-1.5',
      'meta-llama/llama-3.1-70b-instruct'
    ];
    
    popularModels.forEach(modelId => {
      const option = document.createElement('option');
      option.value = modelId;
      option.textContent = modelId.split('/').pop();
      openrouterGroup.appendChild(option);
    });
    
    select.appendChild(ollamaGroup);
    select.appendChild(openrouterGroup);
    
    // Restore selection
    if (currentValue && select.querySelector(`option[value="${currentValue}"]`)) {
      select.value = currentValue;
    }
  });
}

async function loadImageGenConfig() {
  try {
    const config = await window.saladbox.getImageGenConfig();
    const fields = {
      'image-gen-backend': config.backend,
      'image-gen-model': config.model,
      'image-gen-quantize': String(config.quantize),
      'image-gen-width': config.default_width,
      'image-gen-height': config.default_height,
      'image-gen-steps': config.default_steps,
      'drawthings-url': config.drawthings_url,
    };
    for (const [id, value] of Object.entries(fields)) {
      const el = document.getElementById(id);
      if (el) el.value = value;
    }
  } catch (e) {
    console.error('Failed to load image gen config:', e);
  }
}

async function loadHFStatus() {
  try {
    const status = await window.saladbox.getHFStatus();
    const mfluxEl = document.getElementById('mflux-status');
    const dtEl = document.getElementById('drawthings-status');
    const hfEl = document.getElementById('hf-status');

    if (mfluxEl) {
      mfluxEl.textContent = status.mflux_available ? 'Installed' : 'Not installed';
      mfluxEl.style.color = status.mflux_available ? 'var(--success)' : 'var(--text-secondary)';
    }
    if (dtEl) {
      dtEl.textContent = status.drawthings_available ? 'Running' : 'Not running';
      dtEl.style.color = status.drawthings_available ? 'var(--success)' : 'var(--text-secondary)';
    }
    if (hfEl) {
      hfEl.textContent = status.hf_configured ? 'Configured' : 'No token';
      hfEl.style.color = status.hf_configured ? 'var(--success)' : 'var(--warning, orange)';
    }

    // Show masked token if configured
    const hfInput = document.getElementById('hf-token-input');
    if (hfInput && status.hf_configured && !hfInput.value) {
      hfInput.placeholder = 'hf_••••••••••••(saved)';
    }
  } catch (e) {
    console.error('Failed to load HF status:', e);
  }
}

// ── Notification Polling ──────────────────────────────────────
let notificationPollInterval = null;

function startNotificationPolling() {
  // Request browser notification permission on startup
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }

  // Poll every 5 seconds for pending notifications from the backend
  notificationPollInterval = setInterval(async () => {
    try {
      const data = await window.saladbox.pollNotifications();
      if (data.notifications && data.notifications.length > 0) {
        data.notifications.forEach(notif => {
          showNotification(notif.message);
        });
      }
    } catch (e) {
      // Silently ignore — backend may be temporarily unavailable
    }
  }, 5000);
}

function showNotification(message) {
  // Update notification badge
  const badge = document.getElementById('notification-badge');
  if (badge) {
    let count = parseInt(badge.textContent) || 0;
    count++;
    badge.textContent = count;
    badge.classList.remove('hidden');
  }
  
  // 1. Show system notification (works even when app is in background)
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('Saladbox Reminder', {
      body: message,
      icon: 'assets/icon.png',
    });
  }

  // 2. Add a notification bubble in the chat area so the user sees it in-app too
  const notifDiv = document.createElement('div');
  notifDiv.className = 'message assistant notification-message';
  notifDiv.innerHTML = `
    <div class="message-avatar" style="background: var(--warning, #f59e0b);">!</div>
    <div class="message-content">
      <div class="notification-badge">Reminder</div>
      <p>${escapeHtml(message)}</p>
    </div>
    <div class="message-timestamp">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
  `;
  messagesContainer.appendChild(notifDiv);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  // 3. Play a subtle sound if sound is enabled
  try {
    const settings = JSON.parse(localStorage.getItem('saladbox_settings') || '{}');
    if (settings.soundEnabled) {
      const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ==');
      audio.volume = 0.3;
      audio.play().catch(() => {});
    }
  } catch (e) {}
}

// ── Text-to-Speech ──────────────────────────────────────────

function speakText(text, button = null) {
  // If already speaking, stop
  if (isSpeaking) {
    window.speechSynthesis.cancel();
    isSpeaking = false;
    if (button) updateSpeakButton(button, false);
    return;
  }

  // Strip markdown for cleaner speech
  const cleanText = stripMarkdown(text);
  if (!cleanText) return;

  currentUtterance = new SpeechSynthesisUtterance(cleanText);
  currentUtterance.rate = ttsRate;

  // Set voice if configured
  if (ttsVoiceName) {
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find(v => v.name === ttsVoiceName);
    if (voice) currentUtterance.voice = voice;
  }

  currentUtterance.onstart = () => {
    isSpeaking = true;
    if (button) updateSpeakButton(button, true);
  };

  currentUtterance.onend = () => {
    isSpeaking = false;
    if (button) updateSpeakButton(button, false);
  };

  currentUtterance.onerror = () => {
    isSpeaking = false;
    if (button) updateSpeakButton(button, false);
  };

  window.speechSynthesis.speak(currentUtterance);
}

function stopSpeaking() {
  window.speechSynthesis.cancel();
  isSpeaking = false;
}

function updateSpeakButton(button, speaking) {
  if (speaking) {
    button.classList.add('speaking');
    button.title = 'Stop speaking';
    button.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"></rect></svg>';
  } else {
    button.classList.remove('speaking');
    button.title = 'Read aloud';
    button.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>';
  }
}

function stripMarkdown(text) {
  return text
    .replace(/```[\s\S]*?```/g, ' code block ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/^\s*[-*+]\s/gm, '')
    .replace(/^\s*\d+\.\s/gm, '')
    .replace(/\n{2,}/g, '. ')
    .replace(/\n/g, ' ')
    .trim();
}

function populateTTSVoices() {
  const select = document.getElementById('tts-voice-select');
  if (!select) return;

  const voices = window.speechSynthesis.getVoices();
  const currentValue = select.value;

  select.innerHTML = '<option value="">System Default</option>';

  voices.forEach(voice => {
    const option = document.createElement('option');
    option.value = voice.name;
    option.textContent = `${voice.name} (${voice.lang})`;
    if (voice.name === ttsVoiceName) option.selected = true;
    select.appendChild(option);
  });

  if (ttsVoiceName && !select.value) {
    select.value = '';
  }
}

async function loadTools() {
  try {
    const data = await window.saladbox.getTools();
    toolsList.innerHTML = '';
    
    data.tools.forEach(tool => {
      const item = document.createElement('div');
      item.className = 'tool-item';
      item.innerHTML = `
        <span class="tool-name">${formatToolName(tool.name)}</span>
        <span class="tool-status ${tool.enabled ? '' : 'disabled'}">
          ${tool.enabled ? 'On' : 'Off'}
        </span>
      `;
      toolsList.appendChild(item);
    });
  } catch (error) {
    console.error('Failed to load tools:', error);
  }
}

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

async function loadConversations() {
  try {
    const data = await window.saladbox.getConversations(20, 0);
    const container = document.getElementById('conversations');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!data.conversations || data.conversations.length === 0) {
      container.innerHTML = `
        <div class="conversation-item active">
          <div class="conv-title">New conversation</div>
        </div>
      `;
      return;
    }
    
    data.conversations.forEach(conv => {
      const item = document.createElement('div');
      item.className = 'conversation-item' + (conv.id === conversationId ? ' active' : '');
      item.dataset.id = conv.id;
      
      const title = conv.title || 'Untitled';
      
      // Extract preview from last assistant message or last user message
      let previewText = '';
      if (conv.last_assistant_message) {
        previewText = conv.last_assistant_message;
      } else if (conv.last_user_message) {
        previewText = conv.last_user_message;
      }
      
      // Clean up markdown/extra spaces and truncate preview
      previewText = previewText.replace(/[#*`_\-\[\]\(\)]/g, '').replace(/\s+/g, ' ').trim();
      const preview = previewText ? (previewText.substring(0, 45) + (previewText.length > 45 ? '...' : '')) : 'No messages';
      
      // Format date/time using updated_at
      const rawDate = conv.updated_at;
      let date = '';
      if (rawDate) {
        const parsed = parseDate(rawDate);
        if (parsed && !isNaN(parsed.getTime())) {
          date = parsed.toLocaleDateString();
        }
      }
      
      item.innerHTML = `
        <div class="conv-title">${escapeHtml(title)}</div>
        <div class="conv-preview">${escapeHtml(preview)}</div>
        ${date ? `<div class="conv-date">${date}</div>` : ''}
      `;
      
      item.addEventListener('click', () => loadConversation(conv.id));
      container.appendChild(item);
    });
    
  } catch (error) {
    console.error('Failed to load conversations:', error);
  }
}

async function loadConversation(convId, offset = 0) {
  try {
    conversationId = convId;

    const data = await window.saladbox.getConversation(convId);
    const container = document.getElementById('messages');
    
    if (offset === 0) {
      container.innerHTML = '';
    }
    
    if (data.messages && data.messages.length > 0) {
      data.messages.forEach(msg => {
        if (msg.role === 'user') {
          addMessage('user', msg.content);
        } else if (msg.role === 'assistant') {
          if (msg.content && msg.content.trim() !== '') {
            addMessage('assistant', msg.content);
          } else if (msg.tool_calls && msg.tool_calls.length > 0) {
            // Optional: render tool calls. But typically we only want to show text.
          }
        }
      });
    }
    
    // Update active state in sidebar
    document.querySelectorAll('.conversation-item').forEach(item => {
      item.classList.toggle('active', item.dataset.id === conversationId);
    });
    
    // Update header with conversation title
    updateConversationHeader(conversationId, data.title);
    
    // Add load more if there are more messages
    if (data.hasMore) {
      const loadMore = document.createElement('div');
      loadMore.className = 'load-more-container';
      loadMore.innerHTML = `<button class="btn-secondary" id="load-more-btn">Load More (${data.remaining} more)</button>`;
      container.insertBefore(loadMore, container.firstChild);
      
      document.getElementById('load-more-btn')?.addEventListener('click', () => {
        loadMore.remove();
        loadConversation(conversationId, offset + data.messages.length);
      });
    }
    
  } catch (error) {
    console.error('Failed to load conversation:', error);
  }
}

let conversationOffset = 0;
function loadMoreMessages(convId, currentCount) {
  conversationOffset = currentCount;
  loadConversation(convId, conversationOffset);
}

function updateConversationHeader(convId, title) {
  let header = document.getElementById('conv-header');
  if (!header) {
    header = document.createElement('div');
    header.id = 'conv-header';
    header.className = 'conversation-header';
    document.querySelector('.main').insertBefore(header, document.querySelector('.chat-container'));
  }
  
  const tags = getConversationTags(convId);
  
  header.innerHTML = `
    <span class="conv-title">${escapeHtml(title || 'New Chat')}</span>
    ${tags.map(t => `<span class="conv-tag" style="background: ${t.color}">${t.name}</span>`).join('')}
    <div class="conv-actions">
      <button class="btn-icon rename-conv-btn" title="Rename">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
        </svg>
      </button>
      <button class="btn-icon tag-conv-btn" title="Add tag">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path>
          <line x1="7" y1="7" x2="7.01" y2="7"></line>
        </svg>
      </button>
      <button class="btn-icon export-conv-btn" title="Export as Markdown">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
      </button>
    </div>
  `;
  
  header.querySelector('.rename-conv-btn').addEventListener('click', () => {
    const newTitle = prompt('Enter new conversation title:', title || 'New Chat');
    if (newTitle && newTitle.trim()) {
      renameConversation(convId, newTitle.trim());
    }
  });
  
  header.querySelector('.tag-conv-btn').addEventListener('click', () => {
    addTagToConversation(convId);
  });
  
  header.querySelector('.export-conv-btn').addEventListener('click', exportChatAsMarkdown);
}

const TAG_COLORS = ['#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899'];

function getConversationTags(convId) {
  const tags = JSON.parse(localStorage.getItem('saladbox_conv_tags') || '{}');
  return tags[convId] || [];
}

function addTagToConversation(convId) {
  const tagName = prompt('Enter tag name:');
  if (!tagName || !tagName.trim()) return;
  
  const tags = JSON.parse(localStorage.getItem('saladbox_conv_tags') || '{}');
  if (!tags[convId]) tags[convId] = [];
  
  tags[convId].push({
    name: tagName.trim(),
    color: TAG_COLORS[tags[convId].length % TAG_COLORS.length]
  });
  
  localStorage.setItem('saladbox_conv_tags', JSON.stringify(tags));
  
  // Refresh header
  loadConversation(convId);
}

async function renameConversation(convId, newTitle) {
  try {
    await authenticatedFetch(`${API_URL}/api/conversation/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: convId, title: newTitle })
    });
    
    // Update UI
    const convItem = document.querySelector(`.conversation-item[data-id="${convId}"]`);
    if (convItem) {
      convItem.querySelector('.conv-title').textContent = newTitle;
    }
    
    updateConversationHeader(convId, newTitle);
  } catch (error) {
    console.error('Failed to rename conversation:', error);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function addMessage(role, content, isError = false) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${role}${isError ? ' error' : ''}`;
  
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? 'U' : 'S';
  
  const contentDiv = document.createElement('div');
  contentDiv.className = 'message-content';
  
  if (content === 'typing') {
    contentDiv.innerHTML = `
      <div class="typing">
        <span></span>
        <span></span>
        <span></span>
      </div>
    `;
  } else if (role === 'assistant' && !isError) {
    contentDiv.innerHTML = renderMarkdown(content);
    addMessageActions(contentDiv, content);
  } else {
    contentDiv.textContent = content;
  }
  
  const timestamp = document.createElement('div');
  timestamp.className = 'message-timestamp';
  timestamp.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  
  messageDiv.appendChild(avatar);
  messageDiv.appendChild(contentDiv);
  messageDiv.appendChild(timestamp);
  messagesContainer.appendChild(messageDiv);
  
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  
  return messageDiv;
}

function addMessageActions(contentDiv, content) {
  const actions = document.createElement('div');
  actions.className = 'message-actions';

  // Copy button
  const copyBtn = document.createElement('button');
  copyBtn.className = 'message-action-btn';
  copyBtn.title = 'Copy';
  copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(content);
    copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
    setTimeout(() => {
      copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
    }, 2000);
  });
  actions.appendChild(copyBtn);

  // Speak button (TTS)
  if (ttsEnabled) {
    const speakBtn = document.createElement('button');
    speakBtn.className = 'message-action-btn';
    speakBtn.title = 'Read aloud';
    speakBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>';
    speakBtn.addEventListener('click', () => speakText(content, speakBtn));
    actions.appendChild(speakBtn);
  }

  contentDiv.style.position = 'relative';
  contentDiv.appendChild(actions);

  // Add copy buttons to code blocks
  contentDiv.querySelectorAll('pre').forEach(pre => {
    const codeCopyBtn = document.createElement('button');
    codeCopyBtn.className = 'code-copy-btn';
    codeCopyBtn.title = 'Copy code';
    codeCopyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
    codeCopyBtn.addEventListener('click', () => {
      const code = pre.querySelector('code')?.textContent || pre.textContent;
      navigator.clipboard.writeText(code);
      codeCopyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
      setTimeout(() => {
        codeCopyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
      }, 2000);
    });
    pre.style.position = 'relative';
    pre.appendChild(codeCopyBtn);
  });
}

function renderMarkdown(text) {
  // Enhanced markdown rendering with tables support
  if (typeof marked !== 'undefined') {
    const renderer = new marked.Renderer();
    // Handle both old marked API (href, title, text) and new v5+ API ({href, title, text})
    renderer.link = function(tokenOrHref, titleArg, textArg) {
      let href, title, linkText;
      if (typeof tokenOrHref === 'object' && tokenOrHref !== null && 'href' in tokenOrHref) {
        // New marked v5+ API: single token object
        href = tokenOrHref.href;
        title = tokenOrHref.title || '';
        linkText = tokenOrHref.text || href;
      } else {
        // Old marked v4 API: separate arguments
        href = tokenOrHref;
        title = titleArg || '';
        linkText = textArg || href;
      }
      const titleAttr = title ? ` title="${title}"` : '';
      return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${linkText}</a>`;
    };
    // Handle both old and new image API
    renderer.image = function(tokenOrHref, titleArg, textArg) {
      let href, title, alt;
      if (typeof tokenOrHref === 'object' && tokenOrHref !== null && 'href' in tokenOrHref) {
        href = tokenOrHref.href;
        title = tokenOrHref.title || '';
        alt = tokenOrHref.text || '';
      } else {
        href = tokenOrHref;
        title = titleArg || '';
        alt = textArg || '';
      }
      const titleAttr = title ? ` title="${title}"` : '';
      return `<img src="${href}" alt="${alt}"${titleAttr} style="max-width:100%;border-radius:8px;">`;
    };
    try {
      marked.setOptions({
        breaks: true,
        gfm: true,
        renderer: renderer
      });
    } catch (e) {
      // Fallback for newer marked versions where setOptions API changed
      marked.use({ renderer: renderer });
    }
    const html = marked.parse(text);
    return html.replace(/<p><\/p>/g, '').replace(/<br\s*\/?>/g, '<br>').trim();
  }
  
  // Fallback simple markdown with basic table support
  text = text.replace(/\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*\n\|[-:\s|]+\|\n((?:\|.+\|.+\|\n?)+)/g, renderSimpleTable);
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
  text = text.replace(/^- (.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  text = text.replace(/\n\n+/g, '</p><p>');
  text = text.replace(/\n/g, '<br>');
  
  return '<p>' + text + '</p>';
}

function renderSimpleTable(match, header1, header2, rows) {
  let html = '<table class="md-table"><thead><tr>';
  html += `<th>${header1}</th><th>${header2}</th>`;
  html += '</tr></thead><tbody>';
  
  const rowLines = rows.trim().split('\n');
  rowLines.forEach(row => {
    const cells = row.split('|').filter(c => c.trim());
    if (cells.length >= 2) {
      html += '<tr>';
      html += `<td>${cells[0].trim()}</td><td>${cells[1].trim()}</td>`;
      html += '</tr>';
    }
  });
  
  html += '</tbody></table>';
  return html;
}

function formatToolName(name) {
  return name.split('_').map(word => 
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ');
}

function loadSettings() {
  const saved = localStorage.getItem('saladbox_settings');
  if (saved) {
    const settings = JSON.parse(saved);
    useCustomModel = settings.useCustomModel || false;
    customModelName = settings.customModelName || '';
    currentProvider = settings.provider || 'ollama';
    
    customModelToggle.checked = useCustomModel;
    customModelInput.style.display = useCustomModel ? 'block' : 'none';
    customModelNameInput.value = customModelName;
    providerSelect.value = currentProvider;
    
    // Load system prompt settings
    if (settings.systemPrompt) {
      document.getElementById('system-prompt').value = settings.systemPrompt;
    }
    if (settings.temperature) {
      document.getElementById('temperature-slider').value = settings.temperature;
      document.getElementById('temperature-value').textContent = settings.temperature;
    }
    if (settings.maxTokens) {
      document.getElementById('max-tokens').value = settings.maxTokens;
    }
    
    // Load preferences
    if (settings.spellCheck !== undefined) {
      document.getElementById('spell-check-toggle').checked = settings.spellCheck;
      messageInput.spellcheck = settings.spellCheck;
    }
    if (settings.soundEnabled !== undefined) {
      document.getElementById('sound-toggle').checked = settings.soundEnabled;
    }
    if (settings.startWithSystem !== undefined) {
      document.getElementById('startup-toggle').checked = settings.startWithSystem;
    }
    if (settings.minimizeToTray !== undefined) {
      document.getElementById('minimize-tray-toggle').checked = settings.minimizeToTray;
    }

    // Load TTS settings
    if (settings.ttsEnabled !== undefined) {
      ttsEnabled = settings.ttsEnabled;
      const el = document.getElementById('tts-enabled-toggle');
      if (el) el.checked = settings.ttsEnabled;
    }
    if (settings.ttsAutoRead !== undefined) {
      ttsAutoRead = settings.ttsAutoRead;
      const el = document.getElementById('tts-auto-read-toggle');
      if (el) el.checked = settings.ttsAutoRead;
    }
    if (settings.ttsVoiceName !== undefined) {
      ttsVoiceName = settings.ttsVoiceName;
      // Voice select will be populated when voices load asynchronously
    }
    if (settings.ttsRate !== undefined) {
      ttsRate = settings.ttsRate;
      const slider = document.getElementById('tts-rate-slider');
      const display = document.getElementById('tts-rate-value');
      if (slider) slider.value = settings.ttsRate;
      if (display) display.textContent = settings.ttsRate.toFixed(1);
    }
  }

  // Load theme
  const savedTheme = localStorage.getItem('saladbox_theme') || 'dark';
  applyTheme(savedTheme);
}

function applyTheme(newTheme) {
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('saladbox_theme', newTheme);
  
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.innerHTML = newTheme === 'dark' 
      ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`
      : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
  }
}

function showLogViewer() {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.id = 'log-viewer-modal';
  modal.innerHTML = `
    <div class="modal-content log-viewer">
      <div class="modal-header">
        <h3>Application Logs</h3>
        <button class="icon-btn" onclick="this.closest('.modal-overlay').remove()">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="log-filters">
          <button class="btn-secondary active" data-level="all">All</button>
          <button class="btn-secondary" data-level="error">Errors</button>
          <button class="btn-secondary" data-level="warn">Warnings</button>
          <button class="btn-secondary" data-level="info">Info</button>
        </div>
        <div class="log-content" id="log-content">
          <p>Loading logs...</p>
        </div>
      </div>
    </div>
  `;
  
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.remove();
  });
  
  document.body.appendChild(modal);
  
  // Load logs
  loadLogs();
  
  // Filter buttons
  modal.querySelectorAll('.log-filters button').forEach(btn => {
    btn.addEventListener('click', () => {
      modal.querySelectorAll('.log-filters button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterLogs(btn.dataset.level);
    });
  });
}

function loadLogs() {
  const logContent = document.getElementById('log-content');
  if (!logContent) return;
  
  const logs = window.saladbox?.getLogs?.() || [];
  
  if (logs.length === 0) {
    logContent.innerHTML = '<p class="log-empty">No logs available</p>';
    return;
  }
  
  window.allLogs = logs;
  renderLogs(logs);
}

function renderLogs(logs) {
  const logContent = document.getElementById('log-content');
  if (!logContent) return;
  
  logContent.innerHTML = logs.map(log => `
    <div class="log-entry ${log.level}">
      <span class="log-time">${log.time || ''}</span>
      <span class="log-level">${log.level.toUpperCase()}</span>
      <span class="log-message">${log.message || log}</span>
    </div>
  `).join('');
  
  logContent.scrollTop = logContent.scrollHeight;
}

function filterLogs(level) {
  if (!window.allLogs) return;
  
  if (level === 'all') {
    renderLogs(window.allLogs);
  } else {
    const filtered = window.allLogs.filter(l => l.level === level);
    renderLogs(filtered);
  }
}

async function exportAllData() {
  try {
    const data = {
      settings: localStorage.getItem('saladbox_settings'),
      theme: localStorage.getItem('saladbox_theme'),
      conversations: await window.saladbox?.getConversations?.(1000, 0) || []
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `saladbox-backup-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    alert('Data exported successfully!');
  } catch (error) {
    console.error('Export failed:', error);
    alert('Export failed: ' + error.message);
  }
}

async function importAllData() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      
      if (data.settings) localStorage.setItem('saladbox_settings', data.settings);
      if (data.theme) localStorage.setItem('saladbox_theme', data.theme);
      
      alert('Data imported! Please restart the app.');
      window.location.reload();
    } catch (error) {
      console.error('Import failed:', error);
      alert('Import failed: ' + error.message);
    }
  };
  input.click();
}

function clearAllData() {
  if (!confirm('Are you sure you want to clear all data? This cannot be undone!')) return;
  
  localStorage.clear();
  alert('All data cleared. Please restart the app.');
  window.location.reload();
}

// Prompt Templates
const DEFAULT_TEMPLATES = [
  { name: 'Summarize', prompt: 'Please summarize the following text:' },
  { name: 'Explain Like I\'m 5', prompt: 'Explain this concept in simple terms that a 5-year-old could understand:' },
  { name: 'Code Review', prompt: 'Please review the following code and suggest improvements:' },
  { name: 'Debug', prompt: 'Help me debug the following code:' },
  { name: 'Translate', prompt: 'Translate the following to Spanish:' }
];

function loadPromptTemplates() {
  const saved = JSON.parse(localStorage.getItem('saladbox_templates') || 'null');
  const templates = saved || DEFAULT_TEMPLATES;
  
  const list = document.getElementById('prompt-templates-list');
  if (!list) return;
  
  list.innerHTML = templates.map((t, i) => `
    <div class="template-item">
      <span class="template-name">${t.name}</span>
      <div class="template-actions">
        <button class="btn-icon-small" onclick="useTemplate(${i})" title="Use">▶</button>
        <button class="btn-icon-small" onclick="editTemplate(${i})" title="Edit">✎</button>
        <button class="btn-icon-small" onclick="deleteTemplate(${i})" title="Delete">×</button>
      </div>
    </div>
  `).join('');
  
  localStorage.setItem('saladbox_templates', JSON.stringify(templates));
}

window.useTemplate = function(index) {
  const templates = JSON.parse(localStorage.getItem('saladbox_templates') || '[]');
  if (templates[index]) {
    messageInput.value = templates[index].prompt;
    messageInput.focus();
  }
};

window.editTemplate = function(index) {
  const templates = JSON.parse(localStorage.getItem('saladbox_templates') || '[]');
  if (!templates[index]) return;

  const newName = window.prompt('Template name:', templates[index].name);
  const newPrompt = window.prompt('Template prompt:', templates[index].prompt);

  if (newName && newPrompt) {
    templates[index] = { name: newName, prompt: newPrompt };
    localStorage.setItem('saladbox_templates', JSON.stringify(templates));
    loadPromptTemplates();
  }
};

window.deleteTemplate = function(index) {
  if (!confirm('Delete this template?')) return;
  
  const templates = JSON.parse(localStorage.getItem('saladbox_templates') || '[]');
  templates.splice(index, 1);
  localStorage.setItem('saladbox_templates', JSON.stringify(templates));
  loadPromptTemplates();
};

function addNewTemplate() {
  const newName = window.prompt('Template name:');
  const newPrompt = window.prompt('Template prompt:');

  if (newName && newPrompt) {
    const templates = JSON.parse(localStorage.getItem('saladbox_templates') || '[]');
    templates.push({ name: newName, prompt: newPrompt });
    localStorage.setItem('saladbox_templates', JSON.stringify(templates));
    loadPromptTemplates();
  }
}

// Open external links in default browser
document.addEventListener('click', (e) => {
  const link = e.target.closest('a[href]');
  if (!link) return;
  const href = link.getAttribute('href');
  if (href && (href.startsWith('http://') || href.startsWith('https://'))) {
    e.preventDefault();
    if (window.saladbox && window.saladbox.openExternal) {
      window.saladbox.openExternal(href);
    } else {
      window.open(href, '_blank');
    }
  }
});

// Initialize prompt templates on load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    loadPromptTemplates();
    init();
  });
} else {
  loadPromptTemplates();
  init();
}

// Desktop Notifications (mention-based)
function showDesktopNotification(title, body) {
  if (!('Notification' in window)) return;

  if (Notification.permission === 'granted') {
    new Notification(title, { body, icon: 'assets/icon-128.png' });
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        new Notification(title, { body, icon: 'assets/icon-128.png' });
      }
    });
  }
}

function notifyOnMention(message) {
  const mentionPatterns = ['@you', 'hey', 'help'];
  const lower = message.toLowerCase();

  if (mentionPatterns.some(p => lower.includes(p))) {
    showDesktopNotification('Saladbox', 'You were mentioned in a message');
  }
}

// Notification on response is handled inside sendMessage directly

// Auto-save with indicator
let autoSaveTimeout = null;
function debounceAutoSave() {
  showAutoSaveIndicator('saving');
  clearTimeout(autoSaveTimeout);
  autoSaveTimeout = setTimeout(() => {
    saveSettings();
    showAutoSaveIndicator('saved');
    setTimeout(() => hideAutoSaveIndicator(), 2000);
  }, 1000);
}

function showAutoSaveIndicator(status) {
  let indicator = document.getElementById('auto-save-indicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'auto-save-indicator';
    indicator.className = 'auto-save-indicator';
    indicator.innerHTML = `
      <span class="save-dot"></span>
      <span class="save-text">Saving...</span>
    `;
    document.body.appendChild(indicator);
  }
  
  indicator.classList.add('visible');
  indicator.className = `auto-save-indicator visible ${status}`;
  
  const text = indicator.querySelector('.save-text');
  if (status === 'saving') text.textContent = 'Saving...';
  if (status === 'saved') text.textContent = 'Saved';
}

function hideAutoSaveIndicator() {
  const indicator = document.getElementById('auto-save-indicator');
  if (indicator) {
    indicator.classList.remove('visible');
  }
}

// Add save on input
messageInput.addEventListener('input', () => {
  updateWordCount();
  updateTokenCount(messageInput);
  updateContextIndicator();
  debounceAutoSave();
});

function updateWordCount() {
  const text = messageInput.value.trim();
  const words = text ? text.split(/\s+/).length : 0;
  const wordDisplay = document.getElementById('word-count');
  if (wordDisplay) {
    wordDisplay.textContent = words > 0 ? `${words} words` : '';
  }
}

function updateContextIndicator() {
  const indicator = document.getElementById('context-indicator');
  if (!indicator) return;
  const tokens = estimateTokens(messageInput.value);
  const maxTokens = parseInt(document.getElementById('max-tokens')?.value) || 4096;
  const ratio = tokens / maxTokens;
  if (ratio > 0.8) {
    indicator.textContent = 'Near context limit';
    indicator.className = 'context-indicator full';
  } else if (ratio > 0.5) {
    indicator.textContent = 'Context filling';
    indicator.className = 'context-indicator warning';
  } else {
    indicator.textContent = '';
    indicator.className = 'context-indicator';
  }
}

// Performance stats
function trackPerformance(label, startTime) {
  const duration = Date.now() - startTime;
  console.log(`[Performance] ${label}: ${duration}ms`);
  
  // Store in session for stats view
  if (!window.performanceMetrics) window.performanceMetrics = [];
  window.performanceMetrics.push({ label, duration, timestamp: Date.now() });
}

// Markdown Toolbar Functions
function insertMarkdown(type) {
  const start = messageInput.selectionStart;
  const end = messageInput.selectionEnd;
  const text = messageInput.value;
  const selected = text.substring(start, end);
  
  let insertion = '';
  let cursorOffset = 0;
  
  switch(type) {
    case 'bold':
      insertion = `**${selected || 'bold text'}**`;
      cursorOffset = selected ? insertion.length : 2;
      break;
    case 'italic':
      insertion = `*${selected || 'italic text'}*`;
      cursorOffset = selected ? insertion.length : 1;
      break;
    case 'code':
      if (selected.includes('\n')) {
        insertion = `\`\`\`\n${selected || 'code'}\n\`\`\``;
      } else {
        insertion = `\`${selected || 'code'}\``;
      }
      cursorOffset = selected ? insertion.length : 1;
      break;
    case 'link':
      insertion = `[${selected || 'link text'}](url)`;
      cursorOffset = selected ? insertion.length - 1 : 1;
      break;
    case 'list':
      insertion = `\n- ${selected || 'item'}`;
      cursorOffset = insertion.length;
      break;
  }
  
  messageInput.value = text.substring(0, start) + insertion + text.substring(end);
  messageInput.focus();
  messageInput.selectionStart = messageInput.selectionEnd = start + cursorOffset;
}

// Emoji Picker
const EMOJI_LIST = ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍', '🤩', '😘', '😗', '😚', '😙', '🥲', '😋', '😛', '😜', '🤪', '😝', '🤑', '🤗', '🤭', '🤫', '🤔', '🤐', '🤨', '😐', '😑', '😶', '😏', '😒', '🙄', '😬', '🤥', '😌', '😔', '😪', '🤤', '😴', '😷', '🤒', '🤕', '🤢', '🤮', '🤧', '🥵', '🥶', '🥴', '😵', '🤯', '🤠', '🥳', '🥸', '😎', '🤓', '🧐', '😕', '😟', '🙁', '😮', '😯', '😲', '😳', '🥺', '😦', '😧', '😨', '😰', '😥', '😢', '😭', '😱', '😖', '😣', '😞', '😓', '😩', '😫', '🥱', '😤', '😡', '😠', '🤬', '😈', '👿', '💀', '☠️', '💩', '🤡', '👹', '👺', '👻', '👽', '👾', '🤖', '👍', '👎', '👏', '🙌', '🤝', '🙏', '💪', '🤘', '🤙', '👈', '👉', '👆', '👇', '✋', '🤚', '🖐', '🖖', '👋', '🤏', '✌️', '🤞', '🤟', '🤘', '🤙', '👇', '⭐', '🌟', '💫', '🔥', '💥', '✨', '💯', '✅', '❌', '⚠️', '💡', '💬', '💭', '🗯️', '♠️', '♣️', '♥️', '♦️'];

function toggleEmojiPicker() {
  let picker = document.querySelector('.emoji-picker');
  
  if (picker) {
    picker.classList.toggle('visible');
  } else {
    picker = document.createElement('div');
    picker.className = 'emoji-picker visible';
    
    EMOJI_LIST.slice(0, 64).forEach(emoji => {
      const btn = document.createElement('button');
      btn.className = 'emoji-btn';
      btn.textContent = emoji;
      btn.addEventListener('click', () => {
        messageInput.value += emoji;
        messageInput.focus();
        picker.classList.remove('visible');
      });
      picker.appendChild(btn);
    });
    
    document.querySelector('.input-toolbar').appendChild(picker);
  }
}

// Add token estimation
function estimateTokens(text) {
  return Math.ceil(text.length / 4);
}

function updateTokenCount(input) {
  const tokens = estimateTokens(input.value);
  let tokenDisplay = document.getElementById('token-count');
  if (!tokenDisplay) {
    tokenDisplay = document.createElement('span');
    tokenDisplay.id = 'token-count';
    tokenDisplay.className = 'token-count';
    document.querySelector('.input-hint').appendChild(tokenDisplay);
  }
  tokenDisplay.textContent = `~${tokens} tokens`;
}

// Merge conversations
document.getElementById('merge-conv-btn')?.addEventListener('click', showMergeDialog);

function showMergeDialog() {
  const conversations = Array.from(document.querySelectorAll('.conversation-item[data-id]'));
  
  if (conversations.length < 2) {
    alert('Need at least 2 conversations to merge');
    return;
  }
  
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal-content" style="max-width: 400px;">
      <div class="modal-header">
        <h3>Merge Conversations</h3>
        <button class="icon-btn" onclick="this.closest('.modal-overlay').remove()">✕</button>
      </div>
      <div class="modal-body">
        <p style="margin-bottom: 12px; color: var(--text-secondary);">Select conversations to merge:</p>
        <div class="merge-select-list">
          ${conversations.map(c => `
            <label class="merge-item">
              <input type="checkbox" value="${c.dataset.id}">
              <span>${c.querySelector('.conv-title')?.textContent || 'Untitled'}</span>
            </label>
          `).join('')}
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
        <button class="btn-primary" id="confirm-merge-btn">Merge</button>
      </div>
    </div>
  `;
  
  document.body.appendChild(modal);
  
  modal.querySelector('#confirm-merge-btn').addEventListener('click', () => {
    const selected = Array.from(modal.querySelectorAll('input:checked')).map(i => i.value);
    if (selected.length < 2) {
      alert('Select at least 2 conversations');
      return;
    }
    mergeConversations(selected);
    modal.remove();
  });
}

async function mergeConversations(conversationIds) {
  try {
    const response = await authenticatedFetch(`${API_URL}/api/conversations/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_ids: conversationIds })
    });
    
    if (response.ok) {
      alert('Conversations merged!');
      loadConversations();
    }
  } catch (error) {
    console.error('Merge failed:', error);
    alert('Merge failed: ' + error.message);
  }
}
