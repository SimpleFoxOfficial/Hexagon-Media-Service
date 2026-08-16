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
