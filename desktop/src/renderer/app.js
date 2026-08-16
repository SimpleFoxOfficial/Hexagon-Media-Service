/**
 * Renderer. No framework: the app is small enough that direct DOM updates are
 * clearer than a virtual one, and job rows are patched in place so a running
 * download does not re-render every tick.
 */

const ICONS = {
  download: 'M12 3v11M7.5 10.5 12 15l4.5-4.5M4 20h16',
  queue: 'M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01',
  settings: 'M3.5 7.5h4M12.5 7.5h8M3.5 16.5h8.5M17.5 16.5h3M10 5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M15 14a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5',
  logs: 'M13 4.5H7a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.5zM13 4.5v5h5',
  play: 'M9 6.2 18 12l-9 5.8z',
  pause: 'M9.5 6v12M14.5 6v12',
  close: 'M7 7l10 10M17 7 7 17',
  retry: 'M20 12a8 8 0 1 1-2.4-5.7M20.5 3.5v4h-4',
  folder: 'M4 7.5A1.5 1.5 0 0 1 5.5 6h3.6l2 2h7.4A1.5 1.5 0 0 1 20 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z',
  trash: 'M5 7h14M10 7V5h4v2M7.5 7l.9 12h7.2l.9-12',
  video: 'M3.5 7.5a1 1 0 0 1 1-1H15a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1zM16 10.5 20.5 7.5v9L16 13.5z',
  browser: 'M3.5 6.5a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1zM3.5 9.5h17M6 7.5h.01M8.5 7.5h.01',
  link: 'M10.6 13.4a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 1 0-5.7-5.7l-1 1M13.4 10.6a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 1 0 5.7 5.7l1-1',
  check: 'M5 12.5 9.5 17 19 7.5'
}

/** The app mark: film strip with a download arrow, tilted two degrees. */
function brandMark(size = 26) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">
    <g transform="rotate(2 12 12)">
      <rect x="3" y="4.6" width="18" height="14.8" rx="1.9" fill="currentColor"/>
      ${[0, 1, 2, 3, 4]
        .map((i) => {
          const x = (4.3 + i * 3.35).toFixed(2)
          return `<rect x="${x}" y="5.5" width="1.7" height="1.5" rx=".45" fill="var(--surface-2)"/>
                  <rect x="${x}" y="17" width="1.7" height="1.5" rx=".45" fill="var(--surface-2)"/>`
        })
        .join('')}
      <rect x="4.6" y="8.1" width="14.8" height="7.8" rx="1.1" fill="var(--color-brand)"/>
      <g stroke="var(--surface-1)" stroke-width="1.5" stroke-linecap="round"
         stroke-linejoin="round" fill="none">
        <path d="M12 9.2v4.2M9.9 11.5 12 13.7l2.1-2.2M9.4 14.9h5.2"/>
      </g>
    </g>
  </svg>`
}

function icon(name, size = 18) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"
    ><path d="${ICONS[name] || ICONS.video}"/></svg>`
}

const el = (html) => {
  const t = document.createElement('template')
  t.innerHTML = html.trim()
  return t.content.firstElementChild
}

function humanSize(bytes) {
  const n = Number(bytes) || 0
  if (!n) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = n
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`
}

const state = {
  page: 'download',
  jobs: new Map(),
  //: filename -> latest browser-download report, shown as queue rows
  browser: new Map(),
  //: one-line summary of the running batch, shown under the Queue heading
  batch: '',
  stats: {},
  settings: null,
  info: null,
  engineReady: false,
  logLines: [],
  service: 'auto'
}

// ------------------------------------------------------------------ toasts

function toast(message, kind = 'info', ms = 3600) {
  const host = document.getElementById('toasts')
  const node = el(`<div class="toast ${kind}"></div>`)
  node.textContent = message
  host.appendChild(node)
  setTimeout(() => node.remove(), ms)
}

// -------------------------------------------------------------- engine api

async function call(method, params) {
  try {
    return await window.engine.call(method, params)
  } catch (err) {
    toast(err.message || String(err), 'error', 6000)
    throw err
  }
}

// -------------------------------------------------------------------- shell

function renderShell() {
  const root = document.getElementById('root')
  root.innerHTML = ''
  root.appendChild(
    el(`
    <div class="app">
      <header class="navbar">
        <div class="brand">
          <div class="brand-mark">${brandMark(26)}</div>
          <div class="brand-name">Media Downloader</div>
        </div>
        <nav class="nav-links" id="nav"></nav>
        <div class="grow drag-region"></div>
        <div class="engine-state"><span class="dot" id="engine-dot"></span><span id="engine-text">starting engine</span></div>
        <div class="window-controls">
          <button class="win-btn" id="win-min" title="Minimise" aria-label="Minimise">
            <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0 5h10" stroke="currentColor" stroke-width="1"/></svg>
          </button>
          <button class="win-btn" id="win-max" title="Maximise" aria-label="Maximise">
            <svg width="10" height="10" viewBox="0 0 10 10"><rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1"/></svg>
          </button>
          <button class="win-btn danger" id="win-close" title="Close" aria-label="Close">
            <svg width="10" height="10" viewBox="0 0 10 10"><path d="M0 0l10 10M10 0L0 10" stroke="currentColor" stroke-width="1"/></svg>
          </button>
        </div>
      </header>
      <div class="content" id="page"></div>
    </div>
  `)
  )

  document.getElementById('win-min').addEventListener('click', () => window.win.minimize())
  document.getElementById('win-close').addEventListener('click', () => window.win.close())

  // Three distinct glyphs, drawn as real SVG. A CSS pseudo-element was used
  // before and could not be positioned reliably, so the restore state showed a
  // stray mark instead of two offset squares.
  const MAX_GLYPHS = {
    maximize: '<rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor"/>',
    restore:
      '<rect x="0.5" y="2.5" width="7" height="7" fill="none" stroke="currentColor"/>' +
      '<path d="M2.5 2.5V0.5h7v7h-2" fill="none" stroke="currentColor"/>',
    // Arrows pointing inward: leaving fullscreen.
    exitFullscreen:
      '<path d="M4 0.5v3.5H0.5M6 9.5V6h3.5" fill="none" stroke="currentColor"/>' +
      '<path d="M0.5 9.5 4 6M9.5 0.5 6 4" fill="none" stroke="currentColor"/>'
  }

  const maxBtn = document.getElementById('win-max')
  const paintMaxState = ({ maximized, fullscreen } = {}) => {
    const kind = fullscreen ? 'exitFullscreen' : maximized ? 'restore' : 'maximize'
    maxBtn.innerHTML = `<svg width="10" height="10" viewBox="0 0 10 10" stroke-width="1">${MAX_GLYPHS[kind]}</svg>`
    maxBtn.title = fullscreen ? 'Leave fullscreen' : maximized ? 'Restore' : 'Maximise'
  }

  maxBtn.addEventListener('click', async () => paintMaxState(await window.win.toggleMaximize()))
  window.win.onState(paintMaxState)
  window.win.state().then(paintMaxState)

  // Double-clicking the empty strip toggles maximise, as a titlebar should.
  document.querySelector('.drag-region').addEventListener('dblclick', async () => {
    paintMaxState(await window.win.toggleMaximize())
  })

  // F11 is the habit; without it the only way out of fullscreen is the button.
  document.addEventListener('keydown', async (e) => {
    if (e.key === 'F11') {
      e.preventDefault()
      paintMaxState(await window.win.toggleFullscreen())
    } else if (e.key === 'Escape') {
      const s = await window.win.state()
      if (s.fullscreen) paintMaxState(await window.win.toggleFullscreen())
    }
  })

  const nav = document.getElementById('nav')
  for (const [key, label, ic] of [
    ['download', 'Download', 'download'],
    ['queue', 'Queue', 'queue'],
    ['settings', 'Settings', 'settings'],
    ['logs', 'Logs', 'logs']
  ]) {
    const item = el(
      `<button class="nav-pill" data-page="${key}">${icon(ic, 17)}<span>${label}</span>
       <span class="badge brand hidden" data-badge="${key}"></span></button>`
    )
    item.addEventListener('click', () => navigate(key))
    nav.appendChild(item)
  }
}

function navigate(page) {
  state.page = page
  for (const item of document.querySelectorAll('.nav-pill')) {
    item.classList.toggle('active', item.dataset.page === page)
  }
  renderPage()
}

/** Builds the two-column grid every page sits in. Returns { column, rail }. */
function makeLayout(page, { rail = true } = {}) {
  const layout = el(`<div class="layout ${rail ? '' : 'single'}"></div>`)
  const column = el(`<div class="column"></div>`)
  layout.appendChild(column)
  let railNode = null
  if (rail) {
    railNode = el(`<aside class="rail"></aside>`)
    layout.appendChild(railNode)
  }
  page.appendChild(layout)
  return { column, rail: railNode }
}

function pageHeader({ title, subtitle, iconName, pill = '', stats = [], actions = [] }) {
  const node = el(`
    <div class="page-header">
      <div class="page-icon">${icon(iconName, 38)}</div>
      <div class="page-headings">
        <div class="page-title-row">
          <h1>${title}</h1>
          ${pill ? `<span class="page-pill">${pill}</span>` : ''}
        </div>
        <div class="page-sub">${subtitle}</div>
        <div class="page-stats"></div>
      </div>
      <div class="row" style="gap:.4rem"></div>
    </div>`)
  const statRow = node.querySelector('.page-stats')
  for (const s of stats) statRow.appendChild(el(`<span class="stat">${s}</span>`))
  const actionRow = node.lastElementChild
  for (const a of actions) actionRow.appendChild(a)
  return node
}

function renderPage() {
  const page = document.getElementById('page')
  page.innerHTML = ''

  if (state.page === 'download') renderDownload(page)
  else if (state.page === 'queue') renderQueue(page)
  else if (state.page === 'settings') renderSettings(page)
  else renderLogs(page)
}

// ----------------------------------------------------------- download page

const QUALITIES = [
  ['best', 'Best available'], ['2160', '2160p (4K)'], ['1440', '1440p'],
  ['1080', '1080p'], ['720', '720p'], ['480', '480p'], ['360', '360p'],
  ['worst', 'Smallest file']
]

/** One tab per supported service, with a highlight that slides between them. */
const SERVICES = [
  ['auto', 'Auto detect', 'settings'],
  ['youtube', 'YouTube', 'video'],
  ['hdrezka', 'HDRezka', 'browser'],
  ['reddit', 'Reddit', 'queue'],
  ['twitter', 'Twitter / X', 'link'],
  ['other', 'Everything else', 'folder']
]

/**
 * The bar owns its own highlight and survives a tab change.
 *
 * Previously a click re-rendered the whole page, which threw the bar away and
 * built a new one with the highlight already in its final place. There was
 * nothing left to animate. Now only the panel below is rebuilt, so the glider
 * is the same element throughout and actually travels.
 */
function serviceTabs(onChange) {
  const bar = el(`<div class="tab-bar"><span class="tab-glider instant"></span></div>`)
  const glider = bar.querySelector('.tab-glider')

  const slide = (button, instant) => {
    if (!button) return
    glider.classList.toggle('instant', Boolean(instant))
    glider.style.width = `${button.offsetWidth}px`
    glider.style.transform = `translateX(${button.offsetLeft}px)`
    if (instant) {
      // Force a reflow before clearing the flag, otherwise the browser
      // collapses both style changes into one frame and skips the transition.
      void glider.offsetWidth
      glider.classList.remove('instant')
    }
  }

  for (const [key, label, ic] of SERVICES) {
    const tab = el(
      `<button class="tab ${state.service === key ? 'active' : ''}">${icon(ic, 15)}${label}</button>`
    )
    tab.addEventListener('click', () => {
      if (state.service === key) return
      state.service = key

      for (const other of bar.querySelectorAll('.tab')) other.classList.remove('active')
      tab.classList.add('active')
      slide(tab, false)

      onChange(key)
    })
    bar.appendChild(tab)
  }

  // offsetLeft is only meaningful once the bar is laid out.
  requestAnimationFrame(() => slide(bar.querySelector('.tab.active') || bar.children[1], true))
  return bar
}

function renderDownload(page) {
  const { column, rail } = makeLayout(page)

  column.appendChild(
    pageHeader({
      title: 'Download',
      subtitle: 'Paste links from YouTube, Reddit, Twitter and about 1800 other sites.',
      iconName: 'download',
      pill: `${icon('folder', 12)} Local`,
      stats: [
        `${icon('queue', 14)} ${state.stats.total || 0} in queue`,
        `${icon('check', 14)} ${state.stats.done || 0} downloaded`,
        `${icon('folder', 14)} ${state.info?.paths?.downloads || ''}`
      ]
    })
  )

  // The panel is the only part that swaps, so the tab bar keeps its identity
  // and its highlight can animate between positions.
  const panelHost = el(`<div class="column" style="gap:var(--gap-lg)"></div>`)
  const railHost = rail

  column.appendChild(
    serviceTabs(() => {
      panelHost.innerHTML = ''
      if (railHost) railHost.innerHTML = ''
      renderServicePanel(panelHost, railHost)
    })
  )
  column.appendChild(panelHost)
  renderServicePanel(panelHost, railHost)
}

/** Whichever service panel is selected, rendered into `host`. */
function renderServicePanel(column, rail) {

  const inner = column

  if (state.service === 'hdrezka') {
    renderRezka(column, rail)
    return
  }
  renderRail(rail)

  const preset = state.settings?.preset || {}
  const behaviour = state.settings?.behaviour || {}

  const card = el(`
    <div class="card">
      <div class="card-head"><h2>Links</h2></div>
      <textarea id="urls" placeholder="https://www.youtube.com/watch?v=...&#10;One link per line"></textarea>
      <div class="muted" id="count">No links yet</div>
    </div>`)
  inner.appendChild(card)

  const format = el(`
    <div class="card">
      <div class="card-head"><h2>Format</h2></div>
      <div class="field-row">
        <div class="field"><label>Mode</label>
          <select id="mode">
            <option value="video">Video + audio</option>
            <option value="audio">Audio only</option>
            <option value="video_only">Video only</option>
          </select>
        </div>
        <div class="field"><label>Quality</label>
          <select id="quality">${QUALITIES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select>
        </div>
        <div class="field"><label>Container</label>
          <select id="container">
            <option value="auto">Keep original</option>
            <option value="mp4">MP4</option>
            <option value="mkv">MKV</option>
            <option value="webm">WEBM</option>
          </select>
        </div>
      </div>
    </div>`)
  inner.appendChild(format)

  const dest = el(`
    <div class="card">
      <div class="card-head"><h2>Destination</h2></div>
      <div class="row">
        <input type="text" id="dir" value="${(behaviour.download_dir || '').replace(/"/g, '&quot;')}"
               placeholder="${(state.info?.paths?.downloads || '').replace(/"/g, '&quot;')}" />
        <button class="btn" id="browse">${icon('folder')} Browse</button>
      </div>
      <div class="muted" id="target"></div>
    </div>`)
  inner.appendChild(dest)

  const actions = el(`
    <div class="row">
      <div class="grow muted" id="summary"></div>
      <button class="btn brand" id="add">${icon('download')} Add to queue</button>
    </div>`)
  inner.appendChild(actions)

  // wire up
  const urls = card.querySelector('#urls')
  const count = card.querySelector('#count')
  const add = actions.querySelector('#add')

  const readUrls = () =>
    (urls.value.match(/https?:\/\/\S+/g) || []).map((u) => u.replace(/[.,;)"']+$/, ''))

  const refresh = () => {
    const n = readUrls().length
    count.textContent = n ? `${n} link${n === 1 ? '' : 's'} detected` : 'No links yet'
    add.disabled = n === 0
  }
  urls.addEventListener('input', refresh)
  refresh()

  format.querySelector('#mode').value = preset.mode || 'video'
  format.querySelector('#quality').value = preset.quality || '1080'
  format.querySelector('#container').value = preset.video_container || 'mp4'

  const commitPreset = async () => {
    await call('settings.patch', {
      preset: {
        mode: format.querySelector('#mode').value,
        quality: format.querySelector('#quality').value,
        video_container: format.querySelector('#container').value
      }
    }).then((s) => {
      state.settings = s
    })
    updateTarget()
  }
  for (const id of ['#mode', '#quality', '#container']) {
    format.querySelector(id).addEventListener('change', commitPreset)
  }

  const updateTarget = async () => {
    const t = await call('paths.target')
    dest.querySelector('#target').textContent = `Files land in ${t.dir}`
    actions.querySelector('#summary').textContent = `${t.describe} to ${t.dir}`
  }
  updateTarget()

  dest.querySelector('#browse').addEventListener('click', async () => {
    const picked = await window.host.pickFolder(dest.querySelector('#dir').value)
    if (!picked) return
    dest.querySelector('#dir').value = picked
    state.settings = await call('settings.patch', { behaviour: { download_dir: picked } })
    updateTarget()
  })
  dest.querySelector('#dir').addEventListener('change', async (e) => {
    state.settings = await call('settings.patch', { behaviour: { download_dir: e.target.value } })
    updateTarget()
  })

  add.addEventListener('click', async () => {
    const list = readUrls()
    if (!list.length) return
    add.disabled = true
    try {
      const res = await call('queue.add', { urls: list })
      toast(`Added ${res.accepted} link(s)`, 'success')
      urls.value = ''
      refresh()
      navigate('queue')
    } finally {
      add.disabled = false
    }
  })
}

// ------------------------------------------------------------ right rail

function renderRail(rail) {
  if (!rail) return
  const info = state.info || {}
  const b = state.settings?.behaviour || {}

  const status = el(`
    <div class="card tight">
      <h3>Engine</h3>
      <div class="rail-row"><span class="k">yt-dlp</span><span class="v">${(info.components || {})['yt-dlp'] || '-'}</span></div>
      <div class="rail-row"><span class="k">HdRezkaApi</span><span class="v">${(info.components || {})['HdRezkaApi'] || '-'}</span></div>
      <div class="rail-row"><span class="k">ffmpeg</span><span class="v">${
        (info.components || {})['ffmpeg'] && (info.components || {})['ffmpeg'] !== 'NOT FOUND'
          ? 'found'
          : 'missing'
      }</span></div>
    </div>`)
  rail.appendChild(status)

  const opts = el(`
    <div class="card tight">
      <h3>Active options</h3>
      <div class="tag-row">
        <span class="tag">${b.max_concurrent || 3} at once</span>
        <span class="tag">${b.expand_playlists ? 'playlists expand' : 'single items'}</span>
        <span class="tag">${b.tv_folders ? 'season folders' : 'flat folders'}</span>
        ${b.embed_metadata ? '<span class="tag">metadata</span>' : ''}
        ${b.cookies_from_browser ? `<span class="tag">cookies: ${b.cookies_from_browser}</span>` : ''}
      </div>
    </div>`)
  rail.appendChild(opts)

  const links = el(`
    <div class="card tight">
      <h3>Shortcuts</h3>
    </div>`)
  const mk = (label, ic, fn) => {
    const b2 = el(`<button class="rail-link">${icon(ic, 15)}${label}</button>`)
    b2.addEventListener('click', fn)
    return b2
  }
  links.appendChild(mk('Downloads folder', 'folder', () => window.host.openPath(info.paths?.downloads)))
  links.appendChild(mk('Settings folder', 'folder', () => window.host.openPath(info.paths?.config)))
  links.appendChild(mk('View logs', 'logs', () => navigate('logs')))
  rail.appendChild(links)
}

// -------------------------------------------------------------- queue page

function renderQueue(page) {
  const { column, rail } = makeLayout(page)

  const toggle = el(`<button class="btn" id="toggle">${icon('pause')} Pause all</button>`)
  toggle.addEventListener('click', async () => {
    await call(state.stats.isPaused ? 'queue.startAll' : 'queue.pauseAll')
  })
  const clear = el(`<button class="btn ghost">${icon('trash')} Clear finished</button>`)
  clear.addEventListener('click', () => call('queue.clearFinished'))

  column.appendChild(
    pageHeader({
      title: 'Queue',
      subtitle: 'Everything queued, running and finished.',
      iconName: 'queue',
      pill: state.stats.isPaused ? 'Paused' : 'Live',
      stats: [`<span id="stats"></span>`],
      actions: [toggle, clear]
    })
  )

  const inner = el(`<div class="column" id="joblist" style="gap:var(--gap-md)"></div>`)
  column.appendChild(inner)

  for (const job of state.browser.values()) inner.appendChild(jobRow(browserAsJob(job)))
  for (const job of state.jobs.values()) inner.appendChild(jobRow(job))
  renderRail(rail)
  updateStats()
  updateEmpty()
}

function jobRow(job) {
  const node = el(`
    <div class="job state-${job.state}" data-id="${job.id}">
      <div class="job-thumb">${icon('video', 22)}</div>
      <div class="job-body">
        <div class="job-title"></div>
        <div class="job-meta"></div>
        <div class="bar"><span style="width:0%"></span></div>
        <div class="job-error hidden"></div>
      </div>
      <div class="job-actions"></div>
    </div>`)
  patchJob(node, job)
  return node
}

function patchJob(node, job) {
  node.className = `job state-${job.state}`

  const thumb = node.querySelector('.job-thumb')
  if (job.thumbnail && thumb.dataset.src !== job.thumbnail) {
    thumb.dataset.src = job.thumbnail
    thumb.style.backgroundImage = `url("${job.thumbnail}")`
    thumb.innerHTML = ''
  }

  node.querySelector('.job-title').textContent = job.title
  node.querySelector('.job-title').title = job.url

  const badgeKind =
    job.stageTone ||
    (job.state === 'done' || job.state === 'skipped' ? 'green'
      : job.state === 'failed' ? 'red'
      : job.isActive ? 'blue'
      : '')
  const bits = [job.sizeText, job.speedText, job.etaText].filter(Boolean)
  node.querySelector('.job-meta').innerHTML =
    `<span class="badge ${badgeKind}">${job.stateLabel}</span>` +
    `<span class="badge">${job.source || 'Link'}</span>` +
    `<span>${bits.join('  ')}</span>` +
    (job.subtitle ? `<span class="job-file" title="${job.subtitle}">${job.subtitle}</span>` : '')

  const bar = node.querySelector('.bar')
  const indeterminate =
    job.indeterminate || job.state === 'processing' || job.state === 'resolving'
  bar.classList.toggle('indeterminate', indeterminate)
  bar.firstElementChild.style.width = indeterminate ? '35%' : `${job.progress}%`
  bar.classList.toggle('hidden', job.state === 'queued' && !job.progress)

  const err = node.querySelector('.job-error')
  err.textContent = job.error || ''
  err.classList.toggle('hidden', !job.error)

  const actions = node.querySelector('.job-actions')
  actions.innerHTML = ''
  const button = (ic, title, method) => {
    const b = el(`<button class="btn ghost icon" title="${title}">${icon(ic)}</button>`)
    b.addEventListener('click', () => call(method, { id: job.id }))
    return b
  }
  // Chrome owns a browser transfer, so the engine cannot pause or retry it.
  if (!job.browser) {
    if (job.isActive) actions.appendChild(button('pause', 'Pause', 'queue.pause'))
    if (job.state === 'paused' || job.state === 'cancelled') {
      actions.appendChild(button('play', 'Resume', 'queue.resume'))
    }
    if (job.state === 'failed') actions.appendChild(button('retry', 'Retry', 'queue.retry'))
  }
  if (job.filepath) {
    const reveal = el(`<button class="btn ghost icon" title="Show in folder">${icon('folder')}</button>`)
    reveal.addEventListener('click', () => window.host.showItem(job.filepath))
    actions.appendChild(reveal)
  }
  const remove = el(`<button class="btn danger icon" title="Remove">${icon('close')}</button>`)
  remove.addEventListener('click', () => {
    if (job.browser) {
      // Chrome owns the transfer; this only clears the row from the queue.
      state.browser.delete(String(job.id).slice(2))
      document.querySelector(`.job[data-id="${CSS.escape(job.id)}"]`)?.remove()
      updateEmpty()
      return
    }
    call('queue.remove', { id: job.id })
  })
  actions.appendChild(remove)
}

/**
 * A browser-side download shown as a queue row, so everything in flight is
 * visible in one place instead of only in Chrome's own download shelf.
 */
/**
 * Every stage a browser download passes through, so the queue always says what
 * is actually happening. Waiting and moving used to be invisible, which made a
 * slow copy indistinguishable from a corrupt file.
 */
const STAGES = {
  downloading: ['Downloading in browser', 'blue', false],
  waiting: ['Waiting for the browser to release the file', 'orange', false],
  moving: ['Moving to destination', 'orange', false],
  tagging: ['Writing tags', 'orange', false],
  done: ['Completed', 'green', true],
  failed: ['Failed', 'red', true]
}

function browserAsJob(entry) {
  const stage = entry.stage || (entry.event === 'failed' ? 'failed' : 'downloading')
  const [label, tone, terminal] = STAGES[stage] || STAGES.downloading

  const received = Number(entry.received || entry.copied || 0)
  const total = Number(entry.total || 0)
  const name = String(entry.filename || '').split('/').pop()

  // A raw staging filename is unreadable in a list. Show what the item is;
  // the filename belongs underneath, once it has a final one.
  const tag = entry.season
    ? `${entry.season}x${String(entry.episode).padStart(2, '0')}`
    : ''
  const title = [entry.show || 'HDRezka download', tag].filter(Boolean).join('  ')

  let percent = Number(entry.percent || (total ? (received / total) * 100 : 0))
  let sizeText = total ? `${humanSize(received)} / ${humanSize(total)}` : humanSize(received)
  if (stage === 'waiting') {
    percent = 100
    sizeText = 'verifying the file is complete'
  } else if (stage === 'tagging') {
    percent = 100
    sizeText = ''
  } else if (stage === 'done') {
    percent = 100
  }

  return {
    id: `b:${entry.filename}`,
    url: entry.pageUrl || '',
    title,
    subtitle: entry.path ? String(entry.path).split('\\').pop() : name,
    source: 'HDRezka',
    thumbnail: '',
    state: stage === 'failed' ? 'failed' : stage === 'done' ? 'done' : 'downloading',
    stateLabel: label,
    stageTone: tone,
    progress: percent,
    sizeText,
    speedText: '',
    etaText: '',
    note: entry.season ? `${entry.season}x${String(entry.episode).padStart(2, '0')}` : '',
    filepath: stage === 'done' ? entry.path || '' : '',
    error: stage === 'failed' ? entry.error || 'the browser download failed' : '',
    isTerminal: terminal,
    isActive: !terminal,
    // Waiting and tagging have no measurable progress of their own.
    indeterminate: stage === 'waiting' || stage === 'tagging',
    browser: true
  }
}

function upsertBrowser(entry) {
  const key = String(entry.filename || entry.path || '')
  if (!key) return
  const merged = { ...(state.browser.get(key) || {}), ...entry }
  state.browser.set(key, merged)

  const job = browserAsJob(merged)
  const list = document.getElementById('joblist')
  if (!list) return
  const existing = list.querySelector(`.job[data-id="${CSS.escape(job.id)}"]`)
  if (existing) patchJob(existing, job)
  else list.insertBefore(jobRow(job), list.firstChild)
  updateEmpty()
}

function upsertJob(job) {
  state.jobs.set(job.id, job)
  const list = document.getElementById('joblist')
  if (!list) return
  const existing = list.querySelector(`.job[data-id="${job.id}"]`)
  if (existing) patchJob(existing, job)
  else list.appendChild(jobRow(job))
  updateEmpty()
}

function updateEmpty() {
  const list = document.getElementById('joblist')
  if (!list) return
  const empty = list.querySelector('.empty')
  if (state.jobs.size === 0 && !empty) {
    list.appendChild(
      el(`<div class="empty"><h3>The queue is empty</h3>
          <p>Add links from the Download page to get started.</p></div>`)
    )
  } else if (state.jobs.size > 0 && empty) {
    empty.remove()
  }
}

function updateStats() {
  const s = state.stats
  const node = document.getElementById('stats')
  if (node) {
    const bits = []
    if (s.total) bits.push(`${s.total} total`)
    if (s.active) bits.push(`${s.active} running`)
    if (s.queued) bits.push(`${s.queued} waiting`)
    if (s.done) bits.push(`${s.done} done`)
    if (s.failed) bits.push(`${s.failed} failed`)
    if (s.speed) bits.push(`${humanSize(s.speed)}/s`)
    const browserActive = [...state.browser.values()].filter(
      (e) => e.stage !== 'done' && e.stage !== 'failed'
    ).length
    if (browserActive) bits.push(`${browserActive} in browser`)
    if (state.batch) bits.push(state.batch)
    node.textContent = bits.join('   ') || 'Nothing queued'
  }
  const toggle = document.getElementById('toggle')
  if (toggle) {
    toggle.innerHTML = s.isPaused ? `${icon('play')} Resume all` : `${icon('pause')} Pause all`
  }
  const badge = document.querySelector('[data-badge="queue"]')
  if (badge) {
    const pending = (s.active || 0) + (s.queued || 0)
    badge.textContent = pending || ''
    badge.classList.toggle('hidden', !pending)
  }
}

// ----------------------------------------------------------- settings page

function renderSettings(page) {
  const { column } = makeLayout(page, { rail: false })
  column.appendChild(
    pageHeader({
      title: 'Settings',
      subtitle: 'Appearance, downloads, network and the browser bridge.',
      iconName: 'settings'
    })
  )
  const inner = column

  const b = state.settings?.behaviour || {}
  const a = state.settings?.appearance || {}

  const appearance = el(`
    <div class="card">
      <div class="card-head"><h2>Appearance</h2></div>
      <div class="field-row">
        <div class="field"><label>Theme</label>
          <select id="theme">
            <option value="dark">Dark</option><option value="light">Light</option>
          </select></div>
        <div class="field"><label>Accent</label>
          <select id="accent">
            <option value="green">Green</option><option value="blue">Blue</option>
            <option value="purple">Purple</option><option value="orange">Orange</option>
            <option value="red">Red</option>
          </select></div>
      </div>
    </div>`)
  inner.appendChild(appearance)
  appearance.querySelector('#theme').value = document.documentElement.dataset.theme
  appearance.querySelector('#accent').value = document.documentElement.dataset.accent || 'green'
  appearance.querySelector('#theme').addEventListener('change', (e) => {
    document.documentElement.dataset.theme = e.target.value
    localStorage.setItem('theme', e.target.value)
  })
  appearance.querySelector('#accent').addEventListener('change', (e) => {
    document.documentElement.dataset.accent = e.target.value
    localStorage.setItem('accent', e.target.value)
  })

  const behaviour = el(`
    <div class="card">
      <div class="card-head"><h2>Downloads</h2></div>
      <div class="field-row">
        <div class="field"><label>Simultaneous downloads</label>
          <input type="number" id="concurrent" min="1" max="8" value="${b.max_concurrent ?? 3}" /></div>
        <div class="field"><label>Speed limit (KB/s, 0 = unlimited)</label>
          <input type="number" id="rate" min="0" value="${b.rate_limit_kbps ?? 0}" /></div>
      </div>
      <label class="switch"><span>Expand playlists into separate items</span>
        <input type="checkbox" id="expand" ${b.expand_playlists ? 'checked' : ''} /><span class="track"></span></label>
      <label class="switch"><span>Series get Show / Season folders</span>
        <input type="checkbox" id="tv" ${b.tv_folders ? 'checked' : ''} /><span class="track"></span></label>
      <label class="switch"><span>Embed metadata and cover art</span>
        <input type="checkbox" id="meta" ${b.embed_metadata ? 'checked' : ''} /><span class="track"></span></label>
    </div>`)
  inner.appendChild(behaviour)

  const patch = async (values) => {
    state.settings = await call('settings.patch', { behaviour: values })
  }
  behaviour.querySelector('#concurrent').addEventListener('change', (e) =>
    patch({ max_concurrent: Number(e.target.value) })
  )
  behaviour.querySelector('#rate').addEventListener('change', (e) =>
    patch({ rate_limit_kbps: Number(e.target.value) })
  )
  behaviour.querySelector('#expand').addEventListener('change', (e) =>
    patch({ expand_playlists: e.target.checked })
  )
  behaviour.querySelector('#tv').addEventListener('change', (e) =>
    patch({ tv_folders: e.target.checked })
  )
  behaviour.querySelector('#meta').addEventListener('change', (e) =>
    patch({ embed_metadata: e.target.checked })
  )

  const cookieValue = b.cookies_from_browser || ''
  const network = el(`
    <div class="card">
      <div class="card-head"><h2>Network</h2></div>
      <div class="field"><label>Use cookies from</label>
        <select id="cookies">
          ${['', 'chrome', 'edge', 'firefox', 'brave', 'opera', 'vivaldi']
            .map((v) => `<option value="${v}">${v ? v[0].toUpperCase() + v.slice(1) : 'None'}</option>`)
            .join('')}
        </select></div>
      <div class="banner">${icon('logs', 16)}<div>Chrome and Edge lock their cookie
        database while running. If cookies cannot be read the download continues
        without them and says so in the log, rather than failing.</div></div>
    </div>`)
  inner.appendChild(network)
  network.querySelector('#cookies').value = cookieValue
  network.querySelector('#cookies').addEventListener('change', (e) =>
    patch({ cookies_from_browser: e.target.value })
  )

  const about = el(`
    <div class="card">
      <div class="card-head"><h2>About</h2></div>
      <div class="muted mono" id="components"></div>
      <div class="row">
        <button class="btn" id="open-config">${icon('folder')} Settings folder</button>
        <button class="btn" id="open-downloads">${icon('folder')} Downloads folder</button>
      </div>
    </div>`)
  inner.appendChild(about)
  if (state.info) {
    about.querySelector('#components').innerHTML = Object.entries(state.info.components || {})
      .map(([k, v]) => `${k}: ${v}`)
      .join('<br>')
    about.querySelector('#open-config').addEventListener('click', () =>
      window.host.openPath(state.info.paths.config)
    )
    about.querySelector('#open-downloads').addEventListener('click', () =>
      window.host.openPath(state.info.paths.downloads)
    )
  }
}

// --------------------------------------------------------------- logs page

function renderLogs(page) {
  const { column } = makeLayout(page, { rail: false })

  const copy = el(`<button class="btn ghost">Copy</button>`)
  copy.addEventListener('click', () => {
    navigator.clipboard.writeText(state.logLines.join('\n'))
    toast('Log copied', 'success')
  })
  const openFolder = el(`<button class="btn">${icon('folder')} Log folder</button>`)
  openFolder.addEventListener('click', () => window.host.openPath(state.info?.paths?.config))

  column.appendChild(
    pageHeader({
      title: 'Logs',
      subtitle: state.info?.paths?.log || '',
      iconName: 'logs',
      actions: [copy, openFolder]
    })
  )
  column.appendChild(el(`<div class="log" id="logview"></div>`))
  refreshLogs()
}

// ------------------------------------------------------------- hdrezka

function renderRezka(column, rail) {
  const bridge = state.bridge || {}
  const page = state.rezkaPage

  const load = el(`<button class="btn brand">${icon('browser')} Read open HDRezka tab</button>`)
  load.addEventListener('click', async () => {
    load.disabled = true
    load.textContent = 'Reading the tab...'
    try {
      state.rezkaPage = await window.engine.call('bridge.describe')
      state.rezkaPicked = new Set()
      renderPage()
    } catch (err) {
      toast(err.message || String(err), 'error', 9000)
      load.disabled = false
      load.textContent = 'Read open HDRezka tab'
    }
  })

  const behaviour = state.settings?.behaviour || {}
  const card = el(`
    <div class="card">
      <div class="card-head"><h2>Choose what to download</h2></div>
      <div class="muted">Open the title in your browser, then read it here. The page is
        read in the browser because HDRezka refuses direct requests; everything else
        is decided in this app.</div>
      <div class="field">
        <label>Destination</label>
        <div class="row">
          <input type="text" id="rz-dir" value="${(behaviour.download_dir || '').replace(/"/g, '&quot;')}"
                 placeholder="${(state.info?.paths?.downloads || '').replace(/"/g, '&quot;')}" />
          <button class="btn" id="rz-browse">${icon('folder')} Browse</button>
        </div>
        <div class="muted" id="rz-target"></div>
      </div>
    </div>`)
  card.appendChild(load)
  column.appendChild(card)

  const showTarget = async () => {
    try {
      const t = await window.engine.call('paths.target')
      card.querySelector('#rz-target').textContent = `Series land in ${t.dir}\\<show>\\Season NN`
    } catch {
      /* engine busy */
    }
  }
  showTarget()

  card.querySelector('#rz-browse').addEventListener('click', async () => {
    const picked = await window.host.pickFolder(card.querySelector('#rz-dir').value)
    if (!picked) return
    card.querySelector('#rz-dir').value = picked
    state.settings = await call('settings.patch', { behaviour: { download_dir: picked } })
    showTarget()
  })
  card.querySelector('#rz-dir').addEventListener('change', async (e) => {
    state.settings = await call('settings.patch', { behaviour: { download_dir: e.target.value } })
    showTarget()
  })

  if (page) column.appendChild(rezkaPicker(page))

  const status = bridge.connected
    ? `<div class="banner ok">${icon('check', 16)}<div>Browser extension connected.
         Open a title on HDRezka and press <b>Send to downloader</b>.</div></div>`
    : `<div class="banner">${icon('browser', 16)}<div>The browser extension is not
         connected. HDRezka blocks direct requests with a bot check, so the page is
         read inside your own browser instead. Install the extension from the
         <b>extension</b> folder, then pair it below.</div></div>`
  column.appendChild(el(status))

  const bridgeCard = el(`
    <div class="card">
      <div class="card-head"><h2>Browser bridge</h2></div>
      <div class="rail-row"><span class="k">Listening on</span>
        <span class="v mono">${bridge.url || 'not started'}</span></div>
      <div class="rail-row"><span class="k">Pairing token</span>
        <span class="v mono" id="tok">${bridge.token || '-'}</span></div>
      <div class="row">
        <button class="btn" id="copytok">${icon('link')} Copy token</button>
        <button class="btn ghost" id="openext">${icon('folder')} Extension folder</button>
      </div>
      <div class="muted">Load the folder as an unpacked extension, open its options,
        and paste the token. It only ever talks to 127.0.0.1.</div>
    </div>`)
  column.appendChild(bridgeCard)

  bridgeCard.querySelector('#copytok').addEventListener('click', () => {
    navigator.clipboard.writeText(bridge.token || '')
    toast('Token copied', 'success')
  })
  bridgeCard.querySelector('#openext').addEventListener('click', () =>
    window.host.openPath(bridge.extensionDir || '')
  )

  const captured = el(`
    <div class="card">
      <div class="card-head"><h2>Captured from the browser</h2></div>
      <div id="capture-body"><div class="muted">Nothing captured yet.</div></div>
    </div>`)
  column.appendChild(captured)
  renderCapture(captured.querySelector('#capture-body'))
  renderRail(rail)
}

/** Translation, season, episodes and quality, all decided here in the app. */
function rezkaPicker(page) {
  if (!state.rezkaPicked) state.rezkaPicked = new Set()
  const picked = state.rezkaPicked

  const card = el(`
    <div class="card">
      <div class="card-head"><h2>${page.title || 'HDRezka'}</h2>
        <span class="badge brand">${page.isSeries ? 'Series' : 'Film'}</span></div>
      <div class="field-row">
        <div class="field"><label>Translation / dub</label><select id="tr"></select></div>
        <div class="field"><label>Quality</label>
          <select id="q">${QUALITIES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></div>
        <div class="field" id="season-field"><label>Season</label><select id="ss"></select></div>
      </div>
      <div id="eps-wrap">
        <div class="row" style="margin:.2rem 0 .4rem">
          <button class="btn ghost" id="all">Select all</button>
          <button class="btn ghost" id="none">Clear</button>
          <input type="text" id="range" placeholder="1-10 or 3,5,7 (this season)" style="max-width:210px" />
          <button class="btn" id="apply">Apply</button>
        </div>
        <div class="tree" id="tree"></div>
      </div>
      <div class="row"><div class="grow muted" id="sum"></div>
        <button class="btn brand" id="go">Download</button></div>
    </div>`)

  const trSel = card.querySelector('#tr')
  const ssSel = card.querySelector('#ss')
  const qSel = card.querySelector('#q')

  const saved = state.settings?.rezka || {}
  trSel.innerHTML = (page.translators || [])
    .map((t) => `<option value="${t.id}"${t.active ? ' selected' : ''}>${t.name}</option>`)
    .join('')
  // Prefer the translation used last time, if this title still offers it.
  if (saved.translator_id && trSel.querySelector(`option[value="${saved.translator_id}"]`)) {
    trSel.value = saved.translator_id
  }
  qSel.value = saved.quality || 'best'

  // Remember both as soon as they change, not only on download.
  const remember = () =>
    call('settings.patch', {
      rezka: {
        quality: qSel.value,
        translator_id: trSel.value,
        prefer_translator_name:
          trSel.options[trSel.selectedIndex]?.textContent?.trim() || ''
      }
    }).then((s) => {
      state.settings = s
    })
  qSel.addEventListener('change', remember)
  trSel.addEventListener('change', remember)

  const seasons = () => page.seasons || []
  // Episodes may arrive as bare numbers from an older extension build.
  const epsOf = (s) => (s?.episodes || []).map((e) => (typeof e === 'object' ? e : { number: e, name: '' }))

  const drawSeasons = () => {
    ssSel.innerHTML = seasons()
      .map((s) => `<option value="${s.season}">${s.name || `Season ${s.season}`}</option>`)
      .join('')
    drawTree()
  }

  /** A folder-style tree: season rows expand, and every row has a checkbox. */
  const drawTree = () => {
    const host = card.querySelector('#tree')
    host.innerHTML = ''

    for (const s of seasons()) {
      const eps = epsOf(s)
      const open = state.rezkaOpen?.has(s.season) ?? false
      const node = el(`
        <div class="tree-season">
          <div class="tree-row">
            <button class="twist" title="Expand">${open ? '▾' : '▸'}</button>
            <label class="tree-check"><input type="checkbox" class="season-box" /></label>
            <span class="tree-label">${s.name || `Season ${s.season}`}</span>
            <span class="badge" data-count></span>
          </div>
          <div class="tree-eps ${open ? '' : 'hidden'}"></div>
        </div>`)

      const epsHost = node.querySelector('.tree-eps')
      for (const e of eps) {
        const key = `${s.season}:${e.number}`
        const row = el(`
          <label class="tree-row episode">
            <input type="checkbox" class="ep-box" />
            <span class="tree-num">${s.season}x${String(e.number).padStart(2, '0')}</span>
            <span class="tree-label">${e.name || ''}</span>
          </label>`)
        const box = row.querySelector('.ep-box')
        box.checked = picked.has(key)
        box.addEventListener('change', () => {
          box.checked ? picked.add(key) : picked.delete(key)
          refreshCounts()
          summarise()
        })
        epsHost.appendChild(row)
      }

      node.querySelector('.twist').addEventListener('click', () => {
        if (!state.rezkaOpen) state.rezkaOpen = new Set()
        state.rezkaOpen.has(s.season)
          ? state.rezkaOpen.delete(s.season)
          : state.rezkaOpen.add(s.season)
        drawTree()
      })

      node.querySelector('.season-box').addEventListener('change', (ev) => {
        for (const e of eps) {
          const key = `${s.season}:${e.number}`
          ev.target.checked ? picked.add(key) : picked.delete(key)
        }
        drawTree()
        summarise()
      })

      host.appendChild(node)
    }
    refreshCounts()
    summarise()
  }

  /** Season checkbox reflects whether all, some or none of its episodes are on. */
  const refreshCounts = () => {
    const host = card.querySelector('#tree')
    seasons().forEach((s, index) => {
      const eps = epsOf(s)
      const chosen = eps.filter((e) => picked.has(`${s.season}:${e.number}`)).length
      const node = host.children[index]
      if (!node) return
      const box = node.querySelector('.season-box')
      box.checked = chosen > 0 && chosen === eps.length
      box.indeterminate = chosen > 0 && chosen < eps.length
      const badge = node.querySelector('[data-count]')
      badge.textContent = chosen ? `${chosen} / ${eps.length}` : `${eps.length} episodes`
      badge.className = chosen ? 'badge brand' : 'badge'
    })
  }

  const summarise = () => {
    const n = page.isSeries ? picked.size : 1
    const spread = new Set([...picked].map((k) => k.split(':')[0])).size
    card.querySelector('#sum').textContent = page.isSeries
      ? n
        ? `${n} episode(s) across ${spread} season(s)`
        : 'Nothing selected'
      : 'One film'
    card.querySelector('#go').disabled = page.isSeries && n === 0
  }

  card.querySelector('#season-field').classList.add('hidden') // the tree replaces it
  card.querySelector('#eps-wrap').classList.toggle('hidden', !page.isSeries)
  if (page.isSeries) drawSeasons()
  else summarise()
  trSel.addEventListener('change', async () => {
    try {
      page.seasons = await window.engine.call('bridge.episodes', { translatorId: trSel.value })
      picked.clear()
      drawSeasons()
    } catch (err) {
      toast(err.message || String(err), 'error')
    }
  })

  card.querySelector('#all').addEventListener('click', () => {
    for (const s of seasons()) {
      for (const e of epsOf(s)) picked.add(`${s.season}:${e.number}`)
    }
    drawTree()
  })
  card.querySelector('#none').addEventListener('click', () => {
    picked.clear()
    drawTree()
  })
  card.querySelector('#apply').addEventListener('click', () => {
    const wanted = new Set()
    for (const part of card.querySelector('#range').value.replace(/\s/g, '').split(',')) {
      if (!part) continue
      if (part.includes('-')) {
        let [a, b] = part.split('-').map(Number)
        if (a && b) { if (a > b) [a, b] = [b, a]; for (let i = a; i <= b; i++) wanted.add(i) }
      } else if (Number(part)) wanted.add(Number(part))
    }
    // Applies to whichever seasons are expanded, or all of them if none are.
    const targets = state.rezkaOpen?.size
      ? seasons().filter((s) => state.rezkaOpen.has(s.season))
      : seasons()
    for (const s of targets) {
      for (const e of epsOf(s)) {
        const key = `${s.season}:${e.number}`
        wanted.has(e.number) ? picked.add(key) : picked.delete(key)
      }
    }
    drawTree()
  })

  card.querySelector('#go').addEventListener('click', async () => {
    const go = card.querySelector('#go')
    go.disabled = true
    go.textContent = 'Sending to browser...'
    const dub = trSel.options[trSel.selectedIndex]?.textContent?.trim() || ''
    // The Latin original is the better filename when the page carries one.
    const show = page.originalTitle || page.title
    const base = { translatorId: trSel.value, show, dub, pageUrl: page.pageUrl }
    const items = page.isSeries
      ? [...picked]
          .map((k) => k.split(':').map(Number))
          .sort((a, b) => a[0] - b[0] || a[1] - b[1])
          .map(([season, episode]) => ({ ...base, season, episode }))
      : [{ ...base, season: 0, episode: 0 }]

    try {
      // Measure one item first so a season that would not fit gets split into
      // batches instead of filling the staging drive.
      go.textContent = 'Checking size...'
      let estimate = {}
      try {
        estimate = await window.engine.call('bridge.estimate', {
          items,
          quality: qSel.value
        })
      } catch {
        estimate = {}
      }

      if (estimate.bytes && !estimate.fits) {
        toast(
          `About ${estimate.text} needed but only ${humanSize(estimate.freeStaging)} free. ` +
            `Splitting into ${estimate.batches} batches of ${estimate.batchSize}.`,
          'info',
          9000
        )
      }

      go.textContent = 'Sending to browser...'
      const res = await window.engine.call('bridge.download', {
        items,
        quality: qSel.value,
        show,
        batchSize: estimate.batchSize || 0
      })
      navigate('queue')
      toast(
        `${res.accepted} item(s) queued in ${res.batches} batch(es)`,
        'success',
        6000
      )
    } catch (err) {
      toast(err.message || String(err), 'error', 9000)
    }
    go.disabled = false
    go.textContent = 'Download'
  })

  return card
}

function renderCapture(host) {
  const cap = state.capture
  if (!cap) return
  host.innerHTML = ''
  host.appendChild(
    el(`<div class="col">
      <div class="row"><b>${cap.title || 'Untitled'}</b>
        <span class="badge brand">${cap.isSeries ? 'Series' : 'Film'}</span></div>
      <div class="muted">${cap.episodes?.length || 1} item(s) ready to queue</div>
    </div>`)
  )
  const add = el(`<button class="btn brand">${icon('download')} Add ${cap.episodes?.length || 1} to queue</button>`)
  add.addEventListener('click', async () => {
    add.disabled = true
    const res = await call('rezka.queueCaptured', { capture: cap })
    toast(`Queued ${res.queued} item(s)`, 'success')
    navigate('queue')
  })
  host.appendChild(add)
}

async function refreshLogs() {
  const view = document.getElementById('logview')
  if (!view) return
  try {
    const res = await window.engine.call('logs.tail', { limit: 800 })
    state.logLines = res.lines || []
  } catch {
    /* engine may be down; keep whatever we have */
  }
  view.textContent = state.logLines.join('\n') || 'Nothing logged yet.'
  view.scrollTop = view.scrollHeight
}

// ------------------------------------------------------------------ events

function setEngineState(ok, text) {
  state.engineReady = ok
  const dot = document.getElementById('engine-dot')
  const label = document.getElementById('engine-text')
  if (dot) dot.className = `dot ${ok ? 'ok' : 'bad'}`
  if (label) label.textContent = text
}

window.engine.onEvent(async (name, data) => {
  if (name === 'ready') {
    state.info = data
    setEngineState(true, `engine ${data.version}`)
    state.settings = await call('settings.get')
    const jobs = await call('queue.list')
    for (const job of jobs.jobs) state.jobs.set(job.id, job)
    state.stats = await call('queue.stats')
    state.bridge = await call('bridge.info').catch(() => null)
    renderPage()
    return
  }

  if (name === 'rezka.browserProgress') {
    upsertBrowser({ ...data, stage: data.event === 'failed' ? 'failed' : 'downloading' })
    return
  }

  // Waiting, moving and tagging all report here so the queue keeps narrating
  // after the browser hands the file over.
  if (name === 'rezka.filing') {
    upsertBrowser(data)
    return
  }

  if (name === 'rezka.batch') {
    if (data.stage === 'waiting') {
      state.batch = `Batch ${data.batch}/${data.batches}: filed ${data.filed}/${data.expected}, holding the next batch`
    } else if (data.stage === 'starting') {
      state.batch = `Batch ${data.batch} of ${data.batches} starting (${data.size} items)`
    } else if (data.stage === 'done') {
      state.batch = ''
      toast('All batches finished', 'success')
    } else if (data.stage === 'failed') {
      state.batch = ''
      toast(data.error || 'A batch failed', 'error', 8000)
    }
    updateStats()
    return
  }

  if (name === 'rezka.filed') {
    if (data.ok) {
      // The app has moved it into place; show the final path.
      for (const [key, entry] of state.browser) {
        if (!entry.path && entry.show === data.show && !entry.filed) {
          state.browser.set(key, { ...entry, event: 'filed', path: data.path, filed: true })
          upsertBrowser(state.browser.get(key))
          break
        }
      }
      toast(`Filed ${String(data.path).split('\\').pop()}`, 'success')
    } else {
      toast(data.error || 'Could not file the download', 'error', 8000)
    }
    return
  }

  if (name === 'rezka.captured') {
    state.capture = data
    toast(`Captured "${data.title}" from the browser`, 'success')
    if (state.page === 'download' && state.service === 'hdrezka') renderPage()
    return
  }

  if (name === 'job.added') {
    for (const job of data.jobs) upsertJob(job)
  } else if (name === 'job.changed') {
    upsertJob(data)
  } else if (name === 'job.removed') {
    for (const id of data.ids) {
      state.jobs.delete(id)
      document.querySelector(`.job[data-id="${id}"]`)?.remove()
    }
    updateEmpty()
  } else if (name === 'queue.stats') {
    state.stats = data
    updateStats()
  } else if (name === 'expand.finished') {
    if (data.error) toast(data.error, 'error', 7000)
  } else if (name === 'busy') {
    // progress chatter; the queue page already shows the outcome
  } else if (name === 'engine.error') {
    setEngineState(false, 'engine failed')
    toast(data.message, 'error', 12000)
  } else if (name === 'engine.exit') {
    setEngineState(false, 'engine stopped')
  }

  if (state.page === 'logs') refreshLogs()
})

window.engine.onLog((line) => {
  state.logLines.push(line)
  if (state.logLines.length > 4000) state.logLines.splice(0, 1000)
})

// ------------------------------------------------------------------ start

document.documentElement.dataset.theme = localStorage.getItem('theme') || 'dark'
document.documentElement.dataset.accent = localStorage.getItem('accent') || 'green'

renderShell()
navigate('download')
setEngineState(false, 'starting engine')
setInterval(() => {
  if (state.page === 'logs') refreshLogs()
}, 2000)
