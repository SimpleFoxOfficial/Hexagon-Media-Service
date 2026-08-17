/**
 * Orchestrates downloads and talks to the local app.
 *
 * Three constraints shape this:
 *
 * 1. Chrome only writes inside its own Downloads folder, so files stage there
 *    and the app moves them to the real destination afterwards.
 * 2. The browser cannot download HLS. A quality that only offers .m3u8 is sent
 *    to the app instead, where yt-dlp handles the playlist and ffmpeg joins the
 *    segments. Handing an .m3u8 to chrome.downloads saves the playlist text and
 *    reports success, which looks exactly like a download that never finishes.
 * 3. This is an MV3 service worker, so it is killed whenever Chrome feels like
 *    it - a few seconds after the last event, and after five minutes whatever
 *    happens. Nothing may live only in memory, and no unit of work may take
 *    longer than a tick.
 *
 * The third one is why the queue looks the way it does. A season used to run in
 * one long loop that waited for a free slot between episodes; the worker died
 * inside that wait, taking the loop and the in-memory record of what was in
 * flight with it. Chrome carried on with the three downloads it had already
 * been given and nothing ever started the rest, while the app sat waiting for a
 * reply that was never coming. The queue now lives in storage and is advanced
 * one step at a time by `tick`, so the worker can die between any two steps and
 * the next alarm picks up exactly where it left off.
 *
 * The app is the only place anything is configured. It queues commands here and
 * this polls for them, so season and episode choices can be made in the app.
 */

const DEFAULT_BASE = 'http://127.0.0.1:47615'
const STAGING = 'MediaDownloader'
const POLL_MS = 1500
const QUEUE_KEY = 'queue'

/** Nothing is queued, or the last run finished. */
const IDLE = 'idle'
/** Items are staged and waiting for the user to press start. */
const STAGED = 'staged'
const RUNNING = 'running'
/** Running, but there is no HDRezka tab to resolve the next item from. */
const WAITING_PAGE = 'waiting-page'
const DONE = 'done'
const CANCELLED = 'cancelled'

const EMPTY_QUEUE = { status: IDLE, items: [], settings: {}, message: '', show: '' }

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

// -------------------------------------------------------------- queue state

async function readQueue() {
  const stored = await chrome.storage.local.get(QUEUE_KEY)
  const queue = stored[QUEUE_KEY]
  if (!queue || !Array.isArray(queue.items)) return { ...EMPTY_QUEUE, items: [] }
  return { ...EMPTY_QUEUE, ...queue }
}

async function writeQueue(queue) {
  await chrome.storage.local.set({ [QUEUE_KEY]: queue })
  return queue
}

function summarise(queue) {
  const counts = { pending: 0, active: 0, done: 0, failed: 0 }
  for (const item of queue.items) counts[item.state] = (counts[item.state] || 0) + 1
  return {
    status: queue.status,
    message: queue.message || '',
    show: queue.show || '',
    total: queue.items.length,
    pending: counts.pending,
    active: counts.active,
    done: counts.done,
    failed: counts.failed,
    errors: queue.items.filter((i) => i.error).map((i) => `${label(i)}: ${i.error}`).slice(0, 8)
  }
}

function label(item) {
  return item.season ? `S${item.season}E${String(item.episode).padStart(2, '0')}` : 'film'
}

/** Tell the app where the queue stands. Never throws: the app may be closed. */
async function report(queue) {
  await api('/queue-state', {
    method: 'POST',
    body: JSON.stringify(summarise(queue))
  }).catch(() => {})
}

// --------------------------------------------------------------------- tabs

/**
 * Any loaded HDRezka tab will do, focused or not - the content script does not
 * care which window it is in, and requiring focus would mean the user could not
 * use their browser while a season downloads. A discarded tab is woken by the
 * injection in `ensureInjected`.
 */
async function findTab() {
  const tabs = await chrome.tabs.query({
    url: [
      '*://*.rezka.ag/*',
      '*://rezka.ag/*',
      '*://*.hdrezka.ag/*',
      '*://hdrezka.ag/*',
      '*://*.hdrezka.me/*',
      '*://*.rezka.co/*'
    ]
  })
  if (!tabs.length) return null

  // A tab that has finished loading is likelier to answer straight away, and
  // the active one is likeliest of all to be the title the user is looking at.
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true })
  const ranked = tabs.slice().sort((a, b) => score(b, activeTab) - score(a, activeTab))
  return ranked[0]?.id ?? null
}

function score(tab, activeTab) {
  let points = 0
  if (tab.id === activeTab?.id) points += 4
  if (tab.status === 'complete') points += 2
  if (!tab.discarded) points += 1
  return points
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

/** For the one-shot commands, which have nothing to fall back on. */
async function requireTab() {
  const tabId = await findTab()
  if (tabId === null) throw new Error('Open a HDRezka title page in a tab first.')
  return tabId
}

// -------------------------------------------------------------------- space

/** Is there room on the staging drive right now? */
async function hasSpace(minFree) {
  if (!minFree) return true
  try {
    const space = await api('/space')
    return Boolean(space.ok)
  } catch {
    return true // app unreachable; let the download attempt fail normally
  }
}

// --------------------------------------------------------------------- tick

let ticking = false

/**
 * One step of work, short enough to finish before the worker is killed.
 *
 * Everything it needs is read from storage and written back, so it does not
 * matter how many times the worker dies in between.
 */
async function tick() {
  if (ticking) return
  ticking = true
  try {
    await step()
  } catch (err) {
    console.error('queue tick failed', err)
  } finally {
    ticking = false
  }
}

async function step() {
  let queue = await readQueue()
  if (queue.status !== RUNNING && queue.status !== WAITING_PAGE) return

  let changed = await reapFinished(queue)

  const limit = Math.max(1, Number(queue.settings.maxConcurrent) || 3)
  const minFree = Number(queue.settings.minFreeBytes) || 0

  while (inFlight(queue) < limit) {
    const next = queue.items.find((item) => item.state === 'pending')
    if (!next) break

    if (!(await hasSpace(minFree))) {
      // Files are still being moved off the staging drive. Stop for now and
      // let the next tick look again.
      break
    }

    const tabId = await findTab()
    if (tabId === null) {
      // The page is gone. Keep everything staged and say so; the next tick
      // retries, so simply reopening the title is enough to carry on.
      if (queue.status !== WAITING_PAGE) {
        queue.status = WAITING_PAGE
        queue.message =
          'Open the HDRezka page for this title again and the queue will carry on by itself.'
        await writeQueue(queue)
        await report(queue)
      }
      return
    }

    if (queue.status === WAITING_PAGE) {
      queue.status = RUNNING
      queue.message = ''
      changed = true
    }

    await startItem(queue, next, tabId)
    changed = true
    // Written before the next item is considered: if the worker is killed
    // between handing a download to Chrome and recording it, the item would
    // still say "pending" and the same episode would be started twice.
    await writeQueue(queue)
  }

  if (!queue.items.some((item) => item.state === 'pending' || item.state === 'active')) {
    queue.status = DONE
    queue.message = ''
    changed = true
  }

  if (changed) {
    await writeQueue(queue)
    await report(queue)
  }

  // A restarted worker has no interval running, so anything still downloading
  // would report no progress until the next download event happened to fire.
  if (inFlight(queue) > 0) startProgressPolling()
}

function inFlight(queue) {
  return queue.items.filter((item) => item.state === 'active').length
}

/**
 * Bring the queue back in step with Chrome's own download list.
 *
 * This is what makes a worker restart survivable: the record of what was in
 * flight is the download id stored against each item, not a Map that dies with
 * the worker.
 */
async function reapFinished(queue) {
  const activeItems = queue.items.filter((item) => item.state === 'active' && item.downloadId)
  if (!activeItems.length) return false

  let changed = false
  for (const item of activeItems) {
    const [entry] = await chrome.downloads.search({ id: item.downloadId })
    if (!entry) {
      item.state = 'failed'
      item.error = 'the browser lost the download'
      changed = true
      continue
    }
    if (entry.state === 'complete') {
      item.state = 'done'
      changed = true
      await api('/complete', {
        method: 'POST',
        body: JSON.stringify({
          ...item.job,
          path: entry.filename || '',
          bytes: entry.fileSize || entry.totalBytes || 0
        })
      }).catch(() => {})
    } else if (entry.state === 'interrupted') {
      item.state = 'failed'
      item.error = entry.error || 'interrupted'
      changed = true
      await api('/progress', {
        method: 'POST',
        body: JSON.stringify({ event: 'failed', ...item.job, error: item.error })
      }).catch(() => {})
    }
  }
  return changed
}

async function startItem(queue, item, tabId) {
  const quality = queue.settings.quality || 'best'

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
    item.state = 'failed'
    item.error = String(err.message || err)
    return
  }

  const job = {
    show: queue.show || item.show,
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
          title: job.show,
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
      item.state = 'done'
      item.job = job
    } catch (err) {
      item.state = 'failed'
      item.error = String(err.message || err)
    }
    return
  }

  const filename = buildName({ ...job, ext: extensionOf(resolved.url) })
  try {
    const downloadId = await chrome.downloads.download({
      url: resolved.url,
      filename,
      conflictAction: 'uniquify',
      saveAs: false // never prompt; the app decides where files end up
    })
    item.state = 'active'
    item.downloadId = downloadId
    item.job = { ...job, filename }
    await api('/progress', {
      method: 'POST',
      body: JSON.stringify({ event: 'started', filename, ...job })
    }).catch(() => {})
  } catch (err) {
    item.state = 'failed'
    item.error = String(err.message || err)
  }
}

// ---------------------------------------------------------------- progress

let progressTimer = null

function startProgressPolling() {
  if (progressTimer) return
  progressTimer = setInterval(async () => {
    const queue = await readQueue()
    const activeItems = queue.items.filter((item) => item.state === 'active' && item.downloadId)
    if (!activeItems.length) {
      clearInterval(progressTimer)
      progressTimer = null
      return
    }
    for (const item of activeItems) {
      const [entry] = await chrome.downloads.search({ id: item.downloadId })
      if (!entry || entry.state !== 'in_progress') continue
      await api('/progress', {
        method: 'POST',
        body: JSON.stringify({
          event: 'progress',
          ...item.job,
          received: entry.bytesReceived || 0,
          total: entry.totalBytes || 0
        })
      }).catch(() => {})
    }
  }, POLL_MS)
}

// A finished download frees a slot, so the queue moves on immediately rather
// than waiting for the next alarm.
chrome.downloads.onChanged.addListener(async (delta) => {
  if (!delta.state && !delta.error) return
  await tick()
  startProgressPolling()
})

// ------------------------------------------------------------ queue control

async function queueItems(command) {
  const items = (command.items || []).map((item, index) => ({
    id: index,
    translatorId: item.translatorId,
    season: item.season,
    episode: item.episode,
    show: item.show || '',
    dub: item.dub || '',
    pageUrl: item.pageUrl || '',
    state: 'pending',
    downloadId: null,
    error: '',
    job: null
  }))

  const queue = {
    ...EMPTY_QUEUE,
    items,
    settings: command.settings || {},
    show: command.show || '',
    status: command.start ? RUNNING : STAGED,
    message: ''
  }

  await writeQueue(queue)
  await report(queue)
  if (command.start) {
    tick()
    startProgressPolling()
  }
  return summarise(queue)
}

async function startQueue() {
  const queue = await readQueue()
  if (!queue.items.length) return summarise(queue)
  if (queue.status === DONE || queue.status === CANCELLED) {
    // Start again from whatever did not finish last time.
    for (const item of queue.items) {
      if (item.state === 'failed') {
        item.state = 'pending'
        item.error = ''
      }
    }
  }
  queue.status = RUNNING
  queue.message = ''
  await writeQueue(queue)
  await report(queue)
  tick()
  startProgressPolling()
  return summarise(queue)
}

/** Stop the queue and cancel whatever Chrome is still transferring. */
async function cancelQueue() {
  const queue = await readQueue()
  for (const item of queue.items) {
    if (item.state === 'active' && item.downloadId) {
      await chrome.downloads.cancel(item.downloadId).catch(() => {})
      item.state = 'failed'
      item.error = 'cancelled'
    } else if (item.state === 'pending') {
      item.state = 'failed'
      item.error = 'cancelled'
    }
  }
  queue.status = CANCELLED
  queue.message = ''
  await writeQueue(queue)
  await report(queue)
  return summarise(queue)
}

async function clearQueue() {
  const queue = await writeQueue({ ...EMPTY_QUEUE, items: [] })
  await report(queue)
  return summarise(queue)
}

// ------------------------------------------------------- commands from app

/** Ask the CDN how big one item is, without downloading it. */
async function measure(command) {
  const tabId = await requireTab()
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
  if (command.type === 'queue') return queueItems(command)
  if (command.type === 'start') return startQueue()
  if (command.type === 'cancel') return cancelQueue()
  if (command.type === 'clear') return clearQueue()
  if (command.type === 'status') return summarise(await readQueue())

  if (command.type === 'describe') return tabMessage(await requireTab(), { type: 'describe' })
  if (command.type === 'episodes') {
    return tabMessage(await requireTab(), {
      type: 'episodesFor',
      translatorId: command.translatorId
    })
  }
  // Kept so an older app build still works: queue everything and start at once.
  if (command.type === 'download') {
    return queueItems({ ...command, start: true })
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

/**
 * The alarm is what makes this survive the worker being killed: setInterval
 * dies with the worker, an alarm wakes it back up.
 */
chrome.alarms.create('poll', { periodInMinutes: 1 / 60 })
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== 'poll') return
  pollCommands()
  tick()
})
setInterval(() => {
  pollCommands()
  tick()
}, 2000)

// A restarted worker should pick the queue straight back up.
chrome.runtime.onStartup.addListener(() => tick())
chrome.runtime.onInstalled.addListener(() => tick())

// ------------------------------------------------------------ popup calls

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  const run = async () => {
    if (message.type === 'ping') return api('/ping')
    if (message.type === 'settings') return api('/settings')
    if (message.type === 'describe') return handleCommand({ type: 'describe' })
    if (message.type === 'status') return handleCommand({ type: 'status' })
    if (message.type === 'cancel') return cancelQueue()
    if (message.type === 'episodes') {
      return handleCommand({ type: 'episodes', translatorId: message.translatorId })
    }
    if (message.type === 'download') {
      const settings = await api('/settings')
      return queueItems({
        items: message.items,
        settings: { ...settings, ...message.settings },
        show: message.show || '',
        start: true
      })
    }
    throw new Error(`unknown request ${message.type}`)
  }

  run()
    .then((result) => reply({ ok: true, result }))
    .catch((err) => reply({ ok: false, error: String(err.message || err) }))
  return true
})
