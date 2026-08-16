'use strict'

/**
 * Owns the Python engine process and the newline-delimited JSON link to it.
 *
 * Requests get an id and resolve when the matching reply arrives; anything
 * without an id is an event and is handed to the listener. stdout is protocol
 * only, so stderr is where the engine's own logging goes.
 */

const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')

const REQUEST_TIMEOUT_MS = 120000

class EngineBridge {
  constructor({ projectRoot, onEvent, onLog }) {
    this.projectRoot = projectRoot
    this.onEvent = onEvent || (() => {})
    this.onLog = onLog || (() => {})

    this.proc = null
    this.nextId = 1
    this.pending = new Map()
    this.buffer = ''
    this.ready = false
    this.exitInfo = null
  }

  /** Frozen engine next to the packaged app, otherwise the source tree. */
  resolveCommand() {
    const frozen = path.join(process.resourcesPath || '', 'engine', 'mediadl-engine.exe')
    if (fs.existsSync(frozen)) {
      return { command: frozen, args: [], cwd: path.dirname(frozen) }
    }
    const python = process.platform === 'win32' ? 'python' : 'python3'
    return {
      command: python,
      args: ['-u', '-m', 'mediadl.daemon'],
      cwd: this.projectRoot
    }
  }

  start() {
    const { command, args, cwd } = this.resolveCommand()
    this.onLog(`starting engine: ${command} ${args.join(' ')}`)

    this.proc = spawn(command, args, {
      cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }
    })

    this.proc.stdout.setEncoding('utf-8')
    this.proc.stdout.on('data', (chunk) => this.consume(chunk))

    this.proc.stderr.setEncoding('utf-8')
    this.proc.stderr.on('data', (chunk) => {
      for (const line of String(chunk).split(/\r?\n/)) {
        if (line.trim()) this.onLog(line)
      }
    })

    // A pipe to a process that is going away emits 'error' asynchronously, and
    // an unhandled stream error takes the whole main process down with
    // "A JavaScript error occurred in the main process". Every pipe needs a
    // listener, EPIPE and ERR_STREAM_DESTROYED especially: both are normal
    // during shutdown.
    for (const stream of [this.proc.stdin, this.proc.stdout, this.proc.stderr]) {
      stream.on('error', (err) => {
        if (err && (err.code === 'EPIPE' || err.code === 'ERR_STREAM_DESTROYED')) return
        this.onLog(`engine pipe error: ${err && err.message}`)
      })
    }

    this.proc.on('error', (err) => {
      this.exitInfo = { error: String(err) }
      this.onEvent('engine.error', {
        message:
          `Could not start the engine (${command}). ` +
          'Install Python 3.10+ and the requirements, or build the engine executable.'
      })
    })

    this.proc.on('exit', (code, signal) => {
      this.ready = false
      this.exitInfo = { code, signal }
      for (const [, entry] of this.pending) {
        clearTimeout(entry.timer)
        entry.reject(new Error(`engine exited (code ${code})`))
      }
      this.pending.clear()
      this.onEvent('engine.exit', { code, signal })
    })
  }

  consume(chunk) {
    this.buffer += chunk
    let index
    while ((index = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, index).trim()
      this.buffer = this.buffer.slice(index + 1)
      if (!line) continue

      let message
      try {
        message = JSON.parse(line)
      } catch {
        this.onLog(`non-JSON on engine stdout: ${line.slice(0, 200)}`)
        continue
      }

      if (message.event) {
        if (message.event === 'ready') this.ready = true
        this.onEvent(message.event, message.data || {})
        continue
      }

      const entry = this.pending.get(message.id)
      if (!entry) continue
      clearTimeout(entry.timer)
      this.pending.delete(message.id)
      if (message.error) {
        const err = new Error(message.error)
        err.traceback = message.traceback
        entry.reject(err)
      } else {
        entry.resolve(message.result)
      }
    }
  }

  call(method, params = {}) {
    return new Promise((resolve, reject) => {
      if (!this.proc || this.proc.exitCode !== null) {
        reject(new Error('the engine is not running'))
        return
      }
      const id = this.nextId++
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`${method} timed out`))
      }, REQUEST_TIMEOUT_MS)

      this.pending.set(id, { resolve, reject, timer })
      try {
        this.proc.stdin.write(JSON.stringify({ id, method, params }) + '\n')
      } catch (err) {
        clearTimeout(timer)
        this.pending.delete(id)
        reject(err)
      }
    })
  }

  /** Idempotent: quit fires both window-all-closed and before-quit. */
  stop() {
    if (this.stopping) return
    this.stopping = true

    if (!this.proc || this.proc.exitCode !== null) return

    try {
      if (this.proc.stdin.writable) {
        this.proc.stdin.write(JSON.stringify({ method: 'app.shutdown' }) + '\n')
        this.proc.stdin.end()
      }
    } catch {
      // The engine has already gone; killing below is enough.
    }

    const timer = setTimeout(() => {
      try {
        if (this.proc && this.proc.exitCode === null) this.proc.kill()
      } catch {
        /* nothing left to kill */
      }
    }, 2500)
    // Do not hold the event loop open waiting to kill an already-dead process.
    if (timer.unref) timer.unref()
  }
}

module.exports = { EngineBridge }
