const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('saladbox', {
  chat: (message, conversationId, images) => ipcRenderer.invoke('api:chat', message, conversationId, images),
  getModels: () => ipcRenderer.invoke('api:models'),
  getTools: () => ipcRenderer.invoke('api:tools'),
  getConfig: () => ipcRenderer.invoke('api:config'),
  getOllamaModels: () => ipcRenderer.invoke('api:ollama-models'),
  getOpenRouterModels: () => ipcRenderer.invoke('api:openrouter-models'),
  
  getMCPServers: () => ipcRenderer.invoke('api:mcp-servers'),
  addMCPServer: (server) => ipcRenderer.invoke('api:mcp-add', server),
  removeMCPServer: (name) => ipcRenderer.invoke('api:mcp-remove', name),
  toggleMCPServer: (name, enabled) => ipcRenderer.invoke('api:mcp-toggle', name, enabled),
  
  getSetupStatus: () => ipcRenderer.invoke('api:setup-status'),
  runSetup: (config) => ipcRenderer.invoke('api:setup-run', config),

  // Image generation & HuggingFace
  getImageGenConfig: () => ipcRenderer.invoke('api:image-gen-config'),
  updateImageGenConfig: (config) => ipcRenderer.invoke('api:image-gen-update', config),
  saveHFToken: (token) => ipcRenderer.invoke('api:hf-token', token),
  getHFStatus: () => ipcRenderer.invoke('api:hf-status'),
  
  openFile: () => ipcRenderer.invoke('dialog:open-file'),
  openFolder: () => ipcRenderer.invoke('dialog:open-folder'),
  
  getVersion: () => ipcRenderer.invoke('app:get-version'),
  quit: () => ipcRenderer.invoke('app:quit'),
  getToken: () => ipcRenderer.invoke('app:get-token'),
  getHomeDir: () => ipcRenderer.invoke('app:get-home-dir'),
  
  // Conversation management
  getConversations: (limit, offset) => ipcRenderer.invoke('api:conversations', limit, offset),
  getConversation: (conversationId) => ipcRenderer.invoke('api:conversation', conversationId),
  deleteConversation: (conversationId) => ipcRenderer.invoke('api:conversation-delete', conversationId),
  
  onNewChat: (callback) => {
    ipcRenderer.on('new-chat', callback);
    return () => ipcRenderer.removeListener('new-chat', callback);
  },
  onOpenSettings: (callback) => {
    ipcRenderer.on('open-settings', callback);
    return () => ipcRenderer.removeListener('open-settings', callback);
  },
  // Notifications
  pollNotifications: () => ipcRenderer.invoke('api:notifications-poll'),

  openExternal: (url) => ipcRenderer.invoke('app:open-external', url),
  openChat: () => {
    window.location.href = 'index.html';
  },
  openDashboard: () => {
    window.location.href = 'dashboard.html';
  }
});
