/**
 * The update and changelog surface: the pill in the navbar, the card on the
 * settings page and the dialog both of them open.
 *
 * All the work happens in the main process; this file only asks and paints.
 * Anything that shows a release keeps itself registered for repaint while it
 * is on screen, so a check finishing updates whatever the user is looking at
 * without the page having to know an update system exists.
 */

import { el, icon, toast, humanSize, humanDate } from './dom.js'
import { releaseNotes } from './release-notes.js'

export const updates = {
  version: '',
  //: the last UpdateStatus from the main process
  status: null,
  checking: false,
  //: non-null while a download is running, which also means "do not close"
  progress: null,
  error: null,
  //: the release whose notes the changelog dialog shows
  changelog: null
}

const ERRORS = {
  offline: 'Could not reach GitHub. Check your connection and try again.',
  notPublished: 'No release has been published yet.',
  rateLimited: 'GitHub is rate limiting this machine. Try again in a few minutes.',
  noAsset: 'That release has no installer attached to it.',
  downloadFailed: 'The download did not finish.',
  verifyFailed: 'The downloaded file did not match the release. Nothing was installed.',
  launchFailed: 'The installer could not be started.'
}

const PHASES = {
  checking: 'Checking...',
  verifying: 'Checking the download...',
  restarting: 'Starting the installer...'
}

const painters = new Set()

/** Repaint everything on screen that shows update state. */
function notify() {
  paintUpdateSlot()
  for (const entry of [...painters]) {
    if (!entry.node.isConnected) {
      painters.delete(entry)
      continue
    }
    entry.paint()
  }
}

function whileConnected(node, paint) {
  const entry = { node, paint }
  painters.add(entry)
  return node
}

// ------------------------------------------------------------------- start

export async function startUpdates() {
  window.updates.onProgress((progress) => {
    updates.progress = progress
    paintProgress()
  })

  updates.version = await window.updates.version().catch(() => '')

  // The stored preference decides whether launch touches the network at all.
  // Without it this only reports what the last check found.
  const known = await window.updates.status(false).catch(() => null)
  updates.status = known
  notify()
  // Not awaited: a slow or unreachable GitHub must not hold up the changelog
  // below, which needs no network once the release has been remembered.
  if (known && known.checkOnStart) void checkUpdates(true)

  // Notes for a version that installed itself while the app was closed.
  const pending = await window.updates.changelog(null).catch(() => null)
  if (pending) {
    updates.changelog = pending
    openDialog('changelog')
  }
}

export async function checkUpdates(force) {
  updates.checking = true
  notify()
  try {
    updates.status = await window.updates.status(force === true)
  } catch {
    updates.status = null
  } finally {
    updates.checking = false
    notify()
  }
}

async function setAutoCheck(value) {
  await window.updates.setAutoCheck(value)
  if (updates.status) updates.status = { ...updates.status, checkOnStart: value }
  notify()
}

// -------------------------------------------------------------- navbar pill

/**
 * Painted into the slot the navbar leaves for it. It only exists when there is
 * something to say, so the strip stays quiet the rest of the time.
 */
export function paintUpdateSlot() {
  const slot = document.getElementById('update-slot')
  if (!slot) return

  const available = updates.status && updates.status.available
  slot.innerHTML = ''
  if (!available) return

  const pill = el(
    `<button class="nav-update" title="Update to ${available.version}">${icon('update', 15)}
     <span>Update ${available.version}</span></button>`
  )
  pill.addEventListener('click', () => openDialog('update'))
  slot.appendChild(pill)
}

// ------------------------------------------------------------ settings card

export function updatesCard() {
  const card = el(`
    <div class="card">
      <div class="card-head"><h2>Updates</h2></div>
      <div class="col" id="update-body"></div>
    </div>`)
  const body = card.querySelector('#update-body')

  const paint = () => {
    const status = updates.status || {}
    const available = status.available || null
    body.innerHTML = ''

    body.appendChild(
      el(`<div class="rail-row"><span class="k">Installed version</span>
          <span class="v mono">${updates.version || '-'}</span></div>`)
    )

    const line = el(`<div class="update-line"></div>`)
    line.classList.toggle('good', Boolean(available))
    line.textContent = updates.checking
      ? 'Checking...'
      : available
        ? `Version ${available.version} is available`
        : status.error
          ? ERRORS[status.error] || ERRORS.offline
          : status.checkedIso
            ? 'This is the newest release.'
            : 'Not checked yet'
    body.appendChild(line)

    const row = el(`<div class="row" style="flex-wrap:wrap"></div>`)

    const check = el(
      `<button class="btn"${updates.checking ? ' disabled' : ''}>${icon('retry')} Check now</button>`
    )
    check.addEventListener('click', () => checkUpdates(true))
    row.appendChild(check)

    if (available) {
      const install = el(
        `<button class="btn brand">${icon('update')} Update to ${available.version}</button>`
      )
      install.addEventListener('click', () => openDialog('update'))
      row.appendChild(install)
    }

    const notes = el(`<button class="btn ghost">${icon('history')} View changelog</button>`)
    notes.addEventListener('click', () => showChangelog())
    row.appendChild(notes)
    body.appendChild(row)

    if (status.checkedIso && !updates.checking) {
      body.appendChild(el(`<div class="muted">Last checked ${humanDate(status.checkedIso, true)}</div>`))
    }

    const auto = el(`
      <label class="switch"><span>Check for updates when the app starts</span>
        <input type="checkbox"${status.checkOnStart === false ? '' : ' checked'} />
        <span class="track"></span></label>`)
    auto.querySelector('input').addEventListener('change', (e) => setAutoCheck(e.target.checked))
    body.appendChild(auto)
    body.appendChild(
      el(`<div class="muted">One request to the GitHub releases API on launch. Nothing is
          downloaded until you ask for it.</div>`)
    )

    if (status.channel === 'portable') {
      body.appendChild(
        el(`<div class="banner">${icon('logs', 16)}<div>This is the portable build, so it
            cannot replace itself. Open the release page and download the new portable
            file.</div></div>`)
      )
    } else if (status.channel === 'development') {
      body.appendChild(
        el(`<div class="banner">${icon('logs', 16)}<div>Running from source, so installing
            an update is disabled. Checking and the changelog still work.</div></div>`)
      )
    }
  }

  paint()
  return whileConnected(card, paint)
}

/** The notes for the running version, fetched on demand if not remembered. */
async function showChangelog() {
  const release =
    updates.changelog && updates.changelog.version === updates.version
      ? updates.changelog
      : updates.version
        ? await window.updates.changelog(updates.version).catch(() => null)
        : null

  if (!release) {
    toast('No changelog is available for this version.', 'error')
    return
  }
  updates.changelog = release
  openDialog('changelog')
}

// -------------------------------------------------------------------- dialog

let dialog = null

export function openDialog(mode) {
  const release = mode === 'changelog' ? updates.changelog : updates.status && updates.status.available
  if (!release) return
  closeDialog(true)

  updates.error = null
  updates.progress = null

  const status = updates.status || {}
  const canInstall =
    mode === 'update' && status.channel === 'installer' && release.downloadUrl !== null

  const backdrop = el(`<div class="backdrop"></div>`)
  const node = el(`
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-head">
        <h2 class="grow"></h2>
        <button class="btn ghost icon" id="x" title="Close">${icon('close')}</button>
      </div>
      <div class="modal-body">
        <div class="tag-row" id="chips"></div>
        <div id="notes"></div>
        <div id="hint"></div>
        <div class="col hidden" id="progress">
          <div class="muted" id="phase"></div>
          <div class="bar"><span style="width:0%"></span></div>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn ghost" id="open">${icon('external')} Open the release page</button>
        <div class="grow"></div>
        <button class="btn" id="later"></button>
      </div>
    </div>`)
  backdrop.appendChild(node)

  node.querySelector('h2').textContent =
    mode === 'update' ? `Update to ${release.version}` : `What is new in ${release.version}`

  const chips = node.querySelector('#chips')
  if (release.title && release.title !== release.version) {
    const chip = el(`<span class="tag"></span>`)
    chip.textContent = release.title
    chips.appendChild(chip)
  }
  if (release.publishedIso) {
    const chip = el(`<span class="tag"></span>`)
    chip.textContent = `Released ${humanDate(release.publishedIso)}`
    chips.appendChild(chip)
  }
  if (mode === 'update' && release.downloadSizeBytes) {
    const chip = el(`<span class="tag"></span>`)
    chip.textContent = `${humanSize(release.downloadSizeBytes)} download`
    chips.appendChild(chip)
  }
  chips.classList.toggle('hidden', chips.children.length === 0)

  node.querySelector('#notes').appendChild(releaseNotes(release.notes))

  const hint = node.querySelector('#hint')
  if (mode === 'update' && status.channel === 'portable') {
    hint.appendChild(
      el(`<div class="banner">${icon('logs', 16)}<div>This is the portable build, so it cannot
          replace itself. Download the new portable file from the release page.</div></div>`)
    )
  } else if (mode === 'update' && status.channel === 'development') {
    hint.appendChild(
      el(`<div class="banner">${icon('logs', 16)}<div>Running from source, so installing an
          update is disabled.</div></div>`)
    )
  } else if (canInstall) {
    hint.appendChild(
      el(`<div class="muted">The app closes while the installer runs and reopens on the new
          version. Your settings, history and downloads are kept.</div>`)
    )
  }

  const later = node.querySelector('#later')
  later.textContent = mode === 'update' && canInstall ? 'Later' : 'Close'
  later.addEventListener('click', () => closeDialog())
  node.querySelector('#x').addEventListener('click', () => closeDialog())
  node.querySelector('#open').addEventListener('click', () => window.host.openExternal(release.htmlUrl))

  let install = null
  if (canInstall) {
    install = el(`<button class="btn brand">${icon('update')} Download and install</button>`)
    install.addEventListener('click', () => startInstall())
    node.querySelector('.modal-foot').appendChild(install)
  }

  // A click on the sheet itself must not reach the backdrop behind it.
  node.addEventListener('click', (e) => e.stopPropagation())
  backdrop.addEventListener('click', () => closeDialog())

  const onKey = (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      closeDialog()
    }
  }
  document.addEventListener('keydown', onKey, true)

  dialog = { mode, release, node, backdrop, onKey, install }
  document.body.appendChild(backdrop)
  paintProgress()
}

function closeDialog(silent) {
  if (!dialog) return
  // The installer is already running; closing the window it reports into would
  // leave the user watching nothing happen.
  if (!silent && updates.progress) return

  if (!silent && dialog.mode === 'changelog') {
    const version = updates.version || dialog.release.version
    if (version) window.updates.acknowledge(version)
  }

  document.removeEventListener('keydown', dialog.onKey, true)
  dialog.backdrop.remove()
  dialog = null
  updates.progress = null
  updates.error = null
}

async function startInstall() {
  updates.error = null
  updates.progress = { phase: 'checking' }
  paintProgress()

  try {
    const result = await window.updates.install()
    if (result.ok) return
    updates.progress = null
    updates.error = result.error
  } catch {
    updates.progress = null
    updates.error = 'downloadFailed'
  }
  paintProgress()
}

/** Patched rather than rebuilt, so the bar animates instead of blinking. */
function paintProgress() {
  if (!dialog) return
  const { node, install } = dialog
  const progress = updates.progress
  const busy = progress !== null

  const wrap = node.querySelector('#progress')
  wrap.classList.toggle('hidden', !busy)

  if (busy) {
    const determinate = progress.phase === 'downloading' && progress.totalBytes > 0
    const percent = determinate ? Math.round((progress.receivedBytes / progress.totalBytes) * 100) : 0

    node.querySelector('#phase').textContent = determinate
      ? `Downloading... ${percent}% of ${humanSize(progress.totalBytes)}`
      : progress.phase === 'downloading'
        ? 'Downloading...'
        : PHASES[progress.phase] || 'Working...'

    const bar = node.querySelector('.bar')
    bar.classList.toggle('indeterminate', !determinate)
    bar.firstElementChild.style.width = determinate ? `${percent}%` : '35%'
  }

  const failed = node.querySelector('#failed')
  if (failed) failed.remove()
  if (updates.error) {
    const banner = el(`<div class="banner error" id="failed">${icon('logs', 16)}<div></div></div>`)
    banner.querySelector('div').textContent = ERRORS[updates.error] || ERRORS.downloadFailed
    node.querySelector('.modal-body').appendChild(banner)
  }

  for (const button of node.querySelectorAll('button')) button.disabled = busy
  if (install) install.disabled = busy
}
