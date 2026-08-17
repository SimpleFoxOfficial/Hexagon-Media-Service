/**
 * Orchestrates downloads and talks to the local app.
 *
 * Two constraints shape this:
 *
 * 1. Chrome only writes inside its own Downloads folder, so files stage there
 *    and the app moves them to the real destination afterwards.
 * 2. The browser cannot download HLS. A quality that only offers .m3u8 is sent
 *    to the app instead, where yt-dlp handles the playlist and ffmpeg joins the
 *    segments. Handing an .m3u8 to chrome.downloads saves the playlist text and
 *    reports success, which looks exactly like a download that never finishes.
 *
 * The app is the only place anything is configured. It queues commands here and
 * this polls for them, so season and episode choices can be made in the app.
 */

const DEFAULT_BASE = 'http://127.0.0.1:47615'
const STAGING = 'MediaDownloader'
const POLL_MS = 1500

const active = new Map() // downloadId -> job

async function config() {
  const { base, token } = await chrome.storage.local.get(['base', 'token'])
  return { base: base || DEFAULT_BASE, token: token || '' }
}

async function api(path, options = {}) {
  const { base, token } = await config()
  if (!token) throw new Error('No pairing token set. Open the extension options.')

  const response = await fetch(base + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Bridge-Token': token }
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`app replied ${response.status}: ${detail.slice(0, 160)}`)
  }
  return response.json()
}

function sanitise(name) {
  return String(name).replace(/[<>:"/\\|?*]/g, '').replace(/\s+/g, ' ').trim().slice(0, 150)
}

/**
 * Staging name only. The app renames to its own template when it files the
 * file, so this just has to be readable and collision-free.
 */
function buildName({ show, season, episode, dub, ext }) {
  const safeShow = sanitise(show) || 'HDRezka'
  const safeDub = sanitise(dub || '')
  const stem =
    season > 0 && episode > 0
      ? `${safeShow} ${season}x${String(episode).padStart(2, '0')}${safeDub ? ` ${safeDub}` : ''}`
      : safeShow
  return `${STAGING}/${safeShow}/${stem}.${ext || 'mp4'}`
}

function extensionOf(url) {
  const match = String(url).split('?')[0].match(/\.([a-z0-9]{2,4})$/i)
  return match ? match[1].toLowerCase() : 'mp4'
}

/** Any HDRezka tab will do; the content script works on whichever is open. */
async function findTab() {
  const tabs = await chrome.tabs.query({
    url: ['*://*.rezka.ag/*', '*://*.hdrezka.ag/*', '*://*.hdrezka.me/*', '*://*.rezka.co/*']
  })
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true })
  const preferred = tabs.find((t) => t.id === activeTab?.id) || tabs[0]
  if (!preferred?.id) throw new Error('Open a HDRezka title page in a tab first.')
  return preferred.id
}

/**
 * Content scripts are only injected into pages loaded after the extension was
 * installed or reloaded, so an already-open tab has nothing listening and
 * sendMessage fails with "Receiving end does not exist". Inject on demand and
 * retry rather than making the user reload the tab.
 */
async function ensureInjected(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: 'ping' })
    return
  } catch {
    // nothing listening yet
  }

  await chrome.scripting.executeScript({
    target: { tabId },
    files: ['lib/hdrezka.js', 'content.js']
  })

  // Give the freshly injected listener a moment to register.
  for (let attempt = 0; attempt < 10; attempt++) {
    try {
      await chrome.tabs.sendMessage(tabId, { type: 'ping' })
      return
    } catch {
      await new Promise((r) => setTimeout(r, 100))
    }
  }
  throw new Error(
    'The helper could not run on that tab. Make sure it is a HDRezka title page, ' +
      'then reload it.'
  )
}

async function tabMessage(tabId, message) {
  await ensureInjected(tabId)
  const reply = await chrome.tabs.sendMessage(tabId, message)
  if (!reply?.ok) throw new Error(reply?.error || 'the page could not be read')
  return reply.data
}

/** Wait until fewer than `limit` downloads are in flight. */
async function waitForSlot(limit) {
  while (active.size >= limit) {
    await new Promise((r) => setTimeout(r, 700))
  }
}

/** Wait until the staging drive has room, reporting why we are stalled. */
async function waitForSpace(minFree) {
  for (let attempt = 0; ; attempt++) {
    let space
    try {
      space = await api('/space')
    } catch {
      return // app unreachable; let the download attempt fail normally
    }
    if (space.ok || !minFree) return

    if (attempt % 10 === 0) {
      await api('/progress', {
        method: 'POST',
        body: JSON.stringify({
          event: 'waiting-space',
          filename: '',
          free: space.free,
          freeText: space.freeText
        })
      }).catch(() => {})
    }
    // Files are still being moved off the drive; give that a chance to help.
    await new Promise((r) => setTimeout(r, 3000))
  }
}

async function runBatch({ items, settings }) {
  const tabId = await findTab()
  const quality = settings.quality || 'best'
  const limit = Math.max(1, Number(settings.maxConcurrent) || 3)
  const minFree = Number(settings.minFreeBytes) || 0
  const result = { started: 0, handedToApp: 0, failed: [] }

  for (const item of items) {
    // The browser runs these itself, so the limit has to be enforced here.
    // Previously every item was started immediately and a season could fill
    // the disk before anything was moved off it.
    await waitForSlot(limit)
    await waitForSpace(minFree)

    const tag = item.season ? `S${item.season}E${item.episode}` : 'film'
    let resolved
    try {
      resolved = await tabMessage(tabId, {
        type: 'resolve',
        translatorId: item.translatorId,
        season: item.season,
        episode: item.episode,
        quality
      })
    } catch (err) {
      result.failed.push(`${tag}: ${err.message || err}`)
      continue
    }

    const show = settings.show || item.show
    const common = {
      show,
      dub: item.dub || '',
      season: resolved.season,
      episode: resolved.episode,
      quality: resolved.quality,
      pageUrl: item.pageUrl || ''
    }

    // HLS goes to the app: only yt-dlp can turn a playlist into a video file.
    if (resolved.hls) {
      try {
        await api('/capture', {
          method: 'POST',
          body: JSON.stringify({
            title: show,
            pageUrl: item.pageUrl || '',
            isSeries: resolved.season > 0,
            queue: true,
            items: [
              {
                url: resolved.url,
                quality: resolved.quality,
                season: resolved.season,
                episode: resolved.episode
              }
            ]
          })
        })
        result.handedToApp++
      } catch (err) {
        result.failed.push(`${tag}: ${err.message || err}`)
      }
      continue
    }

    const filename = buildName({ ...common, ext: extensionOf(resolved.url) })
    try {
      const downloadId = await chrome.downloads.download({
        url: resolved.url,
        filename,
        conflictAction: 'uniquify',
        saveAs: false // never prompt; the app decides where files end up
      })
      active.set(downloadId, { ...common, filename })
      result.started++
      await api('/progress', {
        method: 'POST',
        body: JSON.stringify({ event: 'started', filename, ...common })
      }).catch(() => {})
    } catch (err) {
      result.failed.push(`${tag}: ${err.message || err}`)
    }
  }

  if (result.started) startProgressPolling()
  return result
}

// ---------------------------------------------------------------- progress

let progressTimer = null

function startProgressPolling() {
  if (progressTimer) return
  progressTimer = setInterval(async () => {
    if (!active.size) {
      clearInterval(progressTimer)
      progressTimer = null
      return
    }
    const entries = await chrome.downloads.search({ state: 'in_progress' })
    for (const entry of entries) {
      const job = active.get(entry.id)
      if (!job) continue
      await api('/progress', {
        method: 'POST',
        body: JSON.stringify({
          event: 'progress',
          ...job,
          received: entry.bytesReceived || 0,
          total: entry.totalBytes || 0
        })
      }).catch(() => {})
    }
  }, POLL_MS)
}

chrome.downloads.onChanged.addListener(async (delta) => {
  const job = active.get(delta.id)
  if (!job) return

  if (delta.state?.current === 'complete') {
    active.delete(delta.id)
    const [entry] = await chrome.downloads.search({ id: delta.id })
    await api('/complete', {
      method: 'POST',
      body: JSON.stringify({
        ...job,
        path: entry?.filename || '',
        bytes: entry?.fileSize || entry?.totalBytes || 0
      })
    }).catch(() => {})
  } else if (delta.error?.current) {
    active.delete(delta.id)
    await api('/progress', {
      method: 'POST',
      body: JSON.stringify({ event: 'failed', ...job, error: delta.error.current })
    }).catch(() => {})
  }
})

// ------------------------------------------------------- commands from app

/** Ask the CDN how big one item is, without downloading it. */
async function measure(command) {
  const tabId = await findTab()
  const resolved = await tabMessage(tabId, {
    type: 'resolve',
    translatorId: command.item.translatorId,
    season: command.item.season,
    episode: command.item.episode,
    quality: command.quality
  })

  if (resolved.hls) return { bytes: 0, hls: true, quality: resolved.quality }

  // A ranged GET is more widely allowed than HEAD on media CDNs.
  const response = await fetch(resolved.url, {
    method: 'GET',
    headers: { Range: 'bytes=0-0' }
  })
  const range = response.headers.get('Content-Range') || ''
  const fromRange = Number((range.match(/\/(\d+)\s*$/) || [])[1] || 0)
  const fromLength = Number(response.headers.get('Content-Length') || 0)
  try {
    response.body?.cancel()
  } catch {
    /* already closed */
  }

  return {
    bytes: fromRange || (fromLength > 1 ? fromLength : 0),
    quality: resolved.quality
  }
}

async function handleCommand(command) {
  if (command.type === 'measure') return measure(command)

  const tabId = await findTab()
  if (command.type === 'describe') return tabMessage(tabId, { type: 'describe' })
  if (command.type === 'episodes') {
    return tabMessage(tabId, { type: 'episodesFor', translatorId: command.translatorId })
  }
  if (command.type === 'download') {
    return runBatch({ items: command.items, settings: command.settings || {} })
  }
  throw new Error(`unknown command ${command.type}`)
}

async function pollCommands() {
  let pending
  try {
    pending = await api('/commands')
  } catch {
    return // app closed or not paired yet
  }

  for (const command of pending?.commands || []) {
    let payload
    try {
      payload = { id: command.id, ok: true, result: await handleCommand(command) }
    } catch (err) {
      payload = { id: command.id, ok: false, error: String(err.message || err) }
    }
    await api('/result', { method: 'POST', body: JSON.stringify(payload) }).catch(() => {})
  }
}

chrome.alarms.create('poll', { periodInMinutes: 1 / 60 })
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'poll') pollCommands()
})
setInterval(pollCommands, 2000)

// ------------------------------------------------------------ popup calls

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  const run = async () => {
    if (message.type === 'ping') return api('/ping')
    if (message.type === 'settings') return api('/settings')
    if (message.type === 'describe') return handleCommand({ type: 'describe' })
    if (message.type === 'episodes') {
      return handleCommand({ type: 'episodes', translatorId: message.translatorId })
    }
    if (message.type === 'download') {
      const settings = await api('/settings')
      return runBatch({ items: message.items, settings: { ...settings, ...message.settings } })
    }
    throw new Error(`unknown request ${message.type}`)
  }

  run()
    .then((result) => reply({ ok: true, result }))
    .catch((err) => reply({ ok: false, error: String(err.message || err) }))
  return true
})
