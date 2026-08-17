'use strict'

/**
 * The only surface the renderer gets. It cannot reach Node, the filesystem or
 * the engine process directly; everything crosses through these named calls.
 */

const { contextBridge, ipcRenderer } = require('electron')

const eventListeners = new Set()
const logListeners = new Set()

ipcRenderer.on('engine:event', (_e, payload) => {
  for (const fn of eventListeners) {
    try {
      fn(payload.name, payload.data)
    } catch (err) {
      console.error('event listener failed', err)
    }
  }
})

ipcRenderer.on('engine:log', (_e, line) => {
  for (const fn of logListeners) {
    try {
      fn(line)
    } catch {
      /* ignore */
    }
  }
})

contextBridge.exposeInMainWorld('engine', {
  /** Call an engine method. Rejects with the engine's message on failure. */
  async call(method, params) {
    const reply = await ipcRenderer.invoke('engine:call', { method, params })
    if (!reply.ok) {
      const err = new Error(reply.error)
      err.traceback = reply.traceback
      throw err
    }
    return reply.result
  },

  onEvent(fn) {
    eventListeners.add(fn)
    return () => eventListeners.delete(fn)
  },

  onLog(fn) {
    logListeners.add(fn)
    return () => logListeners.delete(fn)
  }
})

const stateListeners = new Set()
ipcRenderer.on('window:state', (_e, payload) => {
  for (const fn of stateListeners) {
    try {
      fn(payload)
    } catch {
      /* ignore */
    }
  }
})

contextBridge.exposeInMainWorld('win', {
  minimize: () => ipcRenderer.invoke('window:control', 'minimize'),
  toggleMaximize: () => ipcRenderer.invoke('window:control', 'maximize'),
  toggleFullscreen: () => ipcRenderer.invoke('window:control', 'fullscreen'),
  close: () => ipcRenderer.invoke('window:control', 'close'),
  state: () => ipcRenderer.invoke('window:state'),
  onState(fn) {
    stateListeners.add(fn)
    return () => stateListeners.delete(fn)
  }
})

contextBridge.exposeInMainWorld('host', {
  openPath: (target) => ipcRenderer.invoke('shell:openPath', target),
  showItem: (target) => ipcRenderer.invoke('shell:showItem', target),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  pickFolder: (current) => ipcRenderer.invoke('dialog:pickFolder', current)
})

const updateListeners = new Set()
ipcRenderer.on('update:progress', (_e, progress) => {
  for (const fn of updateListeners) {
    try {
      fn(progress)
    } catch {
      /* ignore */
    }
  }
})

/**
 * The releases API is reached from the main process only; this surface hands
 * back what it found. The renderer never opens a connection of its own.
 */
contextBridge.exposeInMainWorld('updates', {
  version: () => ipcRenderer.invoke('app:version'),
  /** force: ask GitHub. Otherwise report whatever the last check found. */
  status: (force) => ipcRenderer.invoke('update:status', force === true),
  install: () => ipcRenderer.invoke('update:install'),
  /** null asks for the notes of the running version, if they are still unseen. */
  changelog: (version) => ipcRenderer.invoke('update:changelog', version || null),
  acknowledge: (version) => ipcRenderer.invoke('update:acknowledge', version),
  setAutoCheck: (value) => ipcRenderer.invoke('update:autoCheck', value === true),
  onProgress(fn) {
    updateListeners.add(fn)
    return () => updateListeners.delete(fn)
  }
})
