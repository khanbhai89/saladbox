const { app, BrowserWindow, ipcMain, dialog, Menu, Tray, nativeImage, globalShortcut, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const https = require('https');
const { printBanner, printSection, printStatus } = require('./banner');

let mainWindow = null;
let pythonProcess = null;
let tray = null;
const PORT = 8765;
const API_URL = `http://127.0.0.1:${PORT}`;
const crypto = require('crypto');
const apiToken = crypto.randomBytes(32).toString('hex');

const originalRequest = http.request;
http.request = function (url, options, callback) {
  let actualUrl = url;
  let actualOptions = options;
  let actualCallback = callback;
  
  if (typeof url === 'string' || url instanceof URL) {
    if (typeof options === 'function') {
      actualCallback = options;
      actualOptions = {};
    }
  } else {
    actualCallback = options;
    actualOptions = url;
    actualUrl = null;
  }
  
  actualOptions = actualOptions || {};
  actualOptions.headers = actualOptions.headers || {};
  
  const targetUrl = actualUrl ? actualUrl.toString() : '';
  const isLocalBackend = 
    targetUrl.includes(`127.0.0.1:${PORT}`) || 
    targetUrl.includes(`localhost:${PORT}`) ||
    (actualOptions.host === '127.0.0.1' && actualOptions.port === PORT) ||
    (actualOptions.hostname === '127.0.0.1' && actualOptions.port === PORT) ||
    (actualOptions.host === 'localhost' && actualOptions.port === PORT) ||
    (actualOptions.hostname === 'localhost' && actualOptions.port === PORT);
    
  if (isLocalBackend && apiToken) {
    actualOptions.headers['Authorization'] = `Bearer ${apiToken}`;
  }
  
  if (actualUrl) {
    return originalRequest.call(http, actualUrl, actualOptions, actualCallback);
  } else {
    return originalRequest.call(http, actualOptions, actualCallback);
  }
};

function isDev() {
  return process.argv.includes('--dev');
}

function getPythonPath() {
  if (isDev()) {
    const venvPython = path.join(__dirname, '..', '.venv', 'bin', 'python');
    return venvPython;
  }
  const resourcePath = process.resourcesPath;
  if (process.platform === 'win32') {
    return path.join(resourcePath, 'python', 'Scripts', 'python.exe');
  }
  return path.join(resourcePath, 'python', 'bin', 'python');
}

function getSaladboxPath() {
  if (isDev()) {
    return path.join(__dirname, '..');
  }
  return process.resourcesPath;
}

async function checkServerReady(maxAttempts = 30) {
  return new Promise((resolve) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      const req = http.get(`${API_URL}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve(true);
        } else {
          if (attempts < maxAttempts) {
            setTimeout(check, 500);
          } else {
            resolve(false);
          }
        }
      });
      req.on('error', () => {
        if (attempts < maxAttempts) {
          setTimeout(check, 500);
        } else {
          resolve(false);
        }
      });
      req.setTimeout(1000, () => {
        req.destroy();
        if (attempts < maxAttempts) {
          setTimeout(check, 500);
        } else {
          resolve(false);
        }
      });
    };
    check();
  });
}

async function startPythonBackend() {
  const pythonPath = getPythonPath();
  const saladboxPath = getSaladboxPath();
  
  printSection('Starting Backend');
  printStatus('Python:', pythonPath);
  printStatus('App Path:', saladboxPath);
  printStatus('Port:', String(PORT));
  
  pythonProcess = spawn(pythonPath, ['-m', 'saladbox', '--http', '--port', String(PORT)], {
    cwd: saladboxPath,
    env: { ...process.env, SALADBOX_API_TOKEN: apiToken },
    stdio: ['ignore', 'pipe', 'pipe']
  });
  
  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data.toString().trim()}`);
  });
  
  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Error] ${data.toString().trim()}`);
  });
  
  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });
  
  const ready = await checkServerReady();
  if (!ready) {
    throw new Error('Failed to start Python backend');
  }
  
  printStatus('Backend ready at', `http://127.0.0.1:${PORT}`, 'success');
  return true;
}

function stopPythonBackend() {
  if (pythonProcess) {
    printSection('Shutting Down');
    printStatus('Stopping Python backend...', '', 'warning');
    pythonProcess.kill();
    pythonProcess = null;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    minWidth: 600,
    minHeight: 400,
    title: 'Saladbox',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    show: false
  });
  
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  
  // Open all external links in the default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, url) => {
    // Allow navigation to any file in the electron app directory (dashboard, etc.)
    const appDir = `file://${__dirname}`;
    if (!url.startsWith(appDir)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (isDev()) {
      mainWindow.webContents.openDevTools();
    }
  });
  
  mainWindow.on('close', (event) => {
    if (process.platform === 'darwin') {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'trayTemplate.png');
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon);
  
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show', click: () => mainWindow && mainWindow.show() },
    { label: 'New Chat', click: () => mainWindow && mainWindow.webContents.send('new-chat') },
    { type: 'separator' },
    { label: 'Settings', click: () => mainWindow && mainWindow.webContents.send('open-settings') },
    { type: 'separator' },
    { label: 'Quit', click: () => {
      stopPythonBackend();
      app.quit();
    }}
  ]);
  
  tray.setToolTip('Saladbox');
  tray.setContextMenu(contextMenu);
  
  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

function setupIPC() {
  ipcMain.handle('api:chat', async (event, message, conversationId, images) => {
    printSection('Chat Request');
    printStatus('Message:', message.substring(0, 50) + (message.length > 50 ? '...' : ''));
    printStatus('Conversation:', conversationId || 'default');
    printStatus('Images:', images ? `${images.length} image(s)` : 'none');
    
    return new Promise((resolve, reject) => {
      const data = JSON.stringify({ 
        message, 
        conversation_id: conversationId || 'default',
        images: images || []
      });
      console.log('[IPC] Sending to backend:', data);
      
      const req = http.request(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        console.log('[IPC] Response status:', res.statusCode);
        let body = '';
        res.on('data', chunk => {
          body += chunk;
          console.log('[IPC] Received chunk:', chunk.length, 'bytes');
        });
        res.on('end', () => {
          try {
            const parsed = JSON.parse(body);
            console.log('[IPC] Response parsed, message length:', parsed.message?.length);
            resolve(parsed);
          } catch (e) {
            console.error('[IPC] Failed to parse response:', e);
            console.error('[IPC] Raw body:', body.substring(0, 500));
            reject(e);
          }
        });
      });
      req.on('error', (e) => {
        console.error('[IPC] Request error:', e);
        reject(e);
      });
      req.write(data);
      req.end();
    });
  });
  
  ipcMain.handle('api:models', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/models`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:tools', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/tools`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:config', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/config`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:ollama-models', async () => {
    return new Promise((resolve) => {
      const req = http.request('http://localhost:11434/api/tags', {
        method: 'GET'
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            const data = JSON.parse(body);
            resolve(data.models || []);
          } catch (e) {
            resolve([]);
          }
        });
      });
      req.on('error', () => resolve([]));
      req.setTimeout(3000, () => {
        req.destroy();
        resolve([]);
      });
      req.end();
    });
  });
  
  ipcMain.handle('api:openrouter-models', async () => {
    return new Promise((resolve) => {
      const req = https.request('https://openrouter.ai/api/v1/models', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            const data = JSON.parse(body);
            resolve(data.data || []);
          } catch (e) {
            resolve([]);
          }
        });
      });
      req.on('error', () => resolve([]));
      req.setTimeout(5000, () => {
        req.destroy();
        resolve([]);
      });
      req.end();
    });
  });
  
  ipcMain.handle('api:mcp-servers', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/mcp/servers`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:mcp-add', async (event, server) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify(server);
      const req = http.request(`${API_URL}/mcp/add`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      });
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  });
  
  ipcMain.handle('api:mcp-remove', async (event, name) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify({ name });
      const req = http.request(`${API_URL}/mcp/remove`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      });
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  });
  
  ipcMain.handle('api:mcp-toggle', async (event, name, enabled) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify({ name, enabled });
      const req = http.request(`${API_URL}/mcp/toggle`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      });
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  });
  
  ipcMain.handle('api:setup-status', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/setup/status`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:setup-run', async (event, config) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify(config);
      const req = http.request(`${API_URL}/setup/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      });
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  });
  
  // Image generation config
  ipcMain.handle('api:image-gen-config', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/image-gen/config`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
        });
      }).on('error', reject);
    });
  });

  ipcMain.handle('api:image-gen-update', async (event, config) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify(config);
      const req = http.request(`${API_URL}/image-gen/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
        });
      });
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  });

  // HuggingFace token
  ipcMain.handle('api:hf-token', async (event, token) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify({ token });
      const req = http.request(`${API_URL}/hf/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
        });
      });
      req.on('error', reject);
      req.write(data);
      req.end();
    });
  });

  ipcMain.handle('api:hf-status', async () => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/hf/status`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
        });
      }).on('error', reject);
    });
  });

  // Notification polling
  ipcMain.handle('api:notifications-poll', async () => {
    return new Promise((resolve) => {
      http.get(`${API_URL}/notifications/poll`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try { resolve(JSON.parse(body)); } catch (e) { resolve({ notifications: [] }); }
        });
      }).on('error', () => resolve({ notifications: [] }));
    });
  });

  ipcMain.handle('dialog:open-file', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile']
    });
    return result.filePaths;
  });
  
  ipcMain.handle('dialog:open-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory']
    });
    return result.filePaths;
  });
  
  ipcMain.handle('app:get-version', () => app.getVersion());
  
  ipcMain.handle('app:quit', () => {
    stopPythonBackend();
    app.quit();
  });

  ipcMain.handle('app:open-external', (event, url) => {
    if (url && (url.startsWith('https://') || url.startsWith('http://'))) {
      shell.openExternal(url);
    }
  });

  ipcMain.handle('app:get-home-dir', () => app.getPath('home'));
  
  // Conversation management
  ipcMain.handle('api:conversations', async (event, limit = 50, offset = 0) => {
    return new Promise((resolve, reject) => {
      http.get(`${API_URL}/api/dashboard/conversations?limit=${limit}&offset=${offset}`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:conversation', async (event, conversationId) => {
    return new Promise((resolve, reject) => {
      const encodedId = encodeURIComponent(conversationId);
      http.get(`${API_URL}/api/dashboard/conversations/${encodedId}`, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      }).on('error', reject);
    });
  });
  
  ipcMain.handle('api:conversation-delete', async (event, conversationId) => {
    return new Promise((resolve, reject) => {
      const data = JSON.stringify({ conversation_id: conversationId });
      const req = http.request(`${API_URL}/api/conversation/delete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            resolve({ success: true });
          }
        });
      });
      req.on('error', () => resolve({ success: true }));
      req.write(data);
      req.end();
    });
  });

  ipcMain.handle('app:get-token', () => apiToken);
}

app.whenReady().then(async () => {
  printBanner();
  
  try {
    printSection('Initializing');
    await startPythonBackend();
  } catch (error) {
    console.error('Failed to start backend:', error);
    dialog.showErrorBox('Startup Error', `Failed to start Saladbox backend: ${error.message}`);
    app.quit();
    return;
  }
  
  createWindow();
  createTray();
  setupIPC();
  setupGlobalShortcuts();
  
  printStatus('Application', 'Ready', 'success');
  console.log('');
  
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopPythonBackend();
    app.quit();
  }
});

app.on('before-quit', () => {
  printSection('Goodbye');
  stopPythonBackend();
  globalShortcut.unregisterAll();
});

function setupGlobalShortcuts() {
  // Register global shortcut to show/focus window
  const ret = globalShortcut.register('CommandOrControl+Shift+S', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore();
      }
      mainWindow.show();
      mainWindow.focus();
    }
  });
  
  if (!ret) {
    console.log('Global shortcut registration failed');
  }
}
