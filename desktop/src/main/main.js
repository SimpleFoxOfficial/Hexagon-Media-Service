'use strict'

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron')
const path = require('path')
const { EngineBridge } = require('./bridge')

const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..')
const isDev = process.argv.includes('--dev')

let window = null
let bridge = null
let quitting = false

// Electron shows a modal "A JavaScript error occurred in the main process" for
// any uncaught throw, which is a terrible way to learn about a stray shutdown
// error. Log instead; a real bug still shows up in the log with its stack.
process.on('uncaughtException', (err) => {
  console.error('uncaught exception in main:', err)
  if (window && !window.isDestroyed()) {
    window.webContents.send('engine:log', `main process error: ${err && err.message}`)
  }
})
process.on('unhandledRejection', (reason) => {
  console.error('unhandled rejection in main:', reason)
})

function send(channel, payload) {
  if (window && !window.isDestroyed()) {
    window.webContents.send(channel, payload)
  }
}

function createWindow() {
  window = new BrowserWindow({
    width: 1240,
    height: 860,
    minWidth: 940,
    minHeight: 620,
    show: false,
    backgroundColor: '#16181c',
    autoHideMenuBar: true,
    // The window draws its own titlebar so it matches the interface rather
    // than sitting under a grey Windows strip.
    frame: false,
    title: 'Media Downloader',
    icon: path.join(PROJECT_ROOT, 'mediadl', 'resources', 'app.ico'),
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  window.once('ready-to-show', () => window.show())
  // Fullscreen fires its own events; without them the button keeps the wrong
  // glyph after F11 or a double-click on the titlebar.
  for (const event of ['maximize', 'unmaximize', 'enter-full-screen', 'leave-full-screen']) {
    window.on(event, () => send('window:state', windowState()))
  }
  window.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'))
  if (isDev) window.webContents.openDevTools({ mode: 'detach' })

  // Anything that wants a new window is an external link; hand it to the OS
  // browser rather than opening an unrestricted Electron window.
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
}

function startEngine() {
  bridge = new EngineBridge({
    projectRoot: PROJECT_ROOT,
    onEvent: (name, data) => send('engine:event', { name, data }),
    onLog: (line) => send('engine:log', line)
  })
  bridge.start()
}

app.whenReady().then(() => {
  startEngine()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

function shutdown() {
  if (quitting) return
  quitting = true
  try {
    if (bridge) bridge.stop()
  } catch (err) {
    console.error('error stopping the engine:', err)
  }
}

app.on('window-all-closed', () => {
  shutdown()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', shutdown)

// ------------------------------------------------------------------ IPC

ipcMain.handle('engine:call', async (_event, { method, params }) => {
  if (!bridge) throw new Error('the engine is not running')
  try {
    return { ok: true, result: await bridge.call(method, params || {}) }
  } catch (err) {
    return { ok: false, error: String(err.message || err), traceback: err.traceback }
  }
})

function windowState() {
  if (!window || window.isDestroyed()) return { maximized: false, fullscreen: false }
  return { maximized: window.isMaximized(), fullscreen: window.isFullScreen() }
}

ipcMain.handle('window:control', (_event, action) => {
  if (!window || window.isDestroyed()) return windowState()

  if (action === 'minimize') {
    window.minimize()
  } else if (action === 'maximize') {
    // Fullscreen is a separate state from maximised: unmaximize() does
    // nothing while fullscreen, so the button appeared dead. Leaving
    // fullscreen is what the user means when they press it there.
    if (window.isFullScreen()) window.setFullScreen(false)
    else if (window.isMaximized()) window.unmaximize()
    else window.maximize()
  } else if (action === 'fullscreen') {
    window.setFullScreen(!window.isFullScreen())
  } else if (action === 'close') {
    window.close()
  }

  return windowState()
})

ipcMain.handle('window:state', () => windowState())

ipcMain.handle('shell:openPath', async (_event, target) => {
  if (!target) return false
  await shell.openPath(target)
  return true
})

ipcMain.handle('shell:showItem', async (_event, target) => {
  if (!target) return false
  shell.showItemInFolder(target)
  return true
})

ipcMain.handle('shell:openExternal', async (_event, url) => {
  if (/^https?:\/\//i.test(url || '')) await shell.openExternal(url)
  return true
})

ipcMain.handle('dialog:pickFolder', async (_event, current) => {
  const result = await dialog.showOpenDialog(window, {
    properties: ['openDirectory', 'createDirectory'],
    defaultPath: current || undefined
  })
  return result.canceled ? null : result.filePaths[0]
})
