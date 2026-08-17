'use strict'

/**
 * Update checking, downloading and installing, straight from the GitHub
 * releases API of the repository this app is built from.
 *
 * This is the only outbound network access the shell makes on its own behalf.
 * The renderer cannot reach the network at all - its CSP says
 * `default-src 'none'` - so every request is made here and the result is
 * handed back over IPC. Nothing is downloaded until the user asks for it.
 */

const { app } = require('electron')
const { spawn } = require('child_process')
const { createHash } = require('crypto')
const { createWriteStream } = require('fs')
const { mkdir, readFile, rm, writeFile } = require('fs/promises')
const path = require('path')
const { Readable, Transform } = require('stream')
const { pipeline } = require('stream/promises')

const DEFAULT_REPO = 'SimpleFoxOfficial/Hexagon-Media-Service'
const API_ROOT = 'https://api.github.com'
const APP_ID = 'HexagonMediaService'

const CHECK_TIMEOUT_MS = 15000
const DOWNLOAD_TIMEOUT_MS = 900000
const MAX_NOTES_CHARS = 24000
const MAX_REMEMBERED_RELEASES = 8
const QUIT_DELAY_MS = 900
const PROGRESS_INTERVAL_MS = 120

// A release asset can only ever come from GitHub itself. An asset URL that
// points anywhere else is a redirect target we did not ask for, and the
// installer is run with the user's own privileges, so it is refused.
const ALLOWED_DOWNLOAD_HOSTS = new Set([
  'github.com',
  'objects.githubusercontent.com',
  'release-assets.githubusercontent.com'
])

const EMPTY_STATE = {
  seenVersion: null,
  lastCheckIso: null,
  checkOnStart: true,
  releases: []
}

let cachedStatus = null

function repoSlug() {
  const override = process.env.HEXAGON_UPDATE_REPO
  if (!app.isPackaged && override && /^[\w.-]+\/[\w.-]+$/.test(override)) return override
  return DEFAULT_REPO
}

/**
 * The same folder the engine keeps settings.json and the log in, so everything
 * the app remembers about this machine sits in one place.
 */
function configDir() {
  const base = process.env.APPDATA
  const root = base || path.join(app.getPath('home'), '.config')
  return path.join(root, APP_ID)
}

function statePath() {
  return path.join(configDir(), 'updates.json')
}

function downloadDir() {
  return path.join(app.getPath('temp'), 'hexagon-media-service-update')
}

/**
 * How this copy was installed, which decides whether it can replace itself.
 * Only the installer build can: a running portable exe cannot overwrite its
 * own file on Windows, and a source checkout has nothing to overwrite.
 */
function updateChannel() {
  if (!app.isPackaged) return 'development'
  if (process.env.PORTABLE_EXECUTABLE_DIR) return 'portable'
  return 'installer'
}

function parseVersion(value) {
  const cleaned = String(value || '').trim().replace(/^v/i, '')
  const match = /^(\d+(?:\.\d+)*)(?:[-+](.+))?$/.exec(cleaned)
  if (!match) return null
  return { numbers: match[1].split('.').map((part) => Number(part)), pre: match[2] || '' }
}

/** -1, 0 or 1. A pre-release sorts below the plain version it is named after. */
function compareVersions(left, right) {
  const a = parseVersion(left)
  const b = parseVersion(right)
  if (!a || !b) return 0

  const length = Math.max(a.numbers.length, b.numbers.length)
  for (let index = 0; index < length; index++) {
    const difference = (a.numbers[index] || 0) - (b.numbers[index] || 0)
    if (difference !== 0) return difference < 0 ? -1 : 1
  }

  if (a.pre === b.pre) return 0
  if (a.pre === '') return 1
  if (b.pre === '') return -1
  return a.pre < b.pre ? -1 : 1
}

async function readState() {
  try {
    const parsed = JSON.parse(await readFile(statePath(), 'utf8'))
    return {
      seenVersion: typeof parsed.seenVersion === 'string' ? parsed.seenVersion : null,
      lastCheckIso: typeof parsed.lastCheckIso === 'string' ? parsed.lastCheckIso : null,
      checkOnStart: typeof parsed.checkOnStart === 'boolean' ? parsed.checkOnStart : true,
      releases: Array.isArray(parsed.releases) ? parsed.releases.filter(isReleaseInfo) : []
    }
  } catch {
    // A missing or unreadable file is a first run, not a failure.
    return { ...EMPTY_STATE, releases: [] }
  }
}

async function writeState(state) {
  try {
    await mkdir(path.dirname(statePath()), { recursive: true })
    await writeFile(statePath(), `${JSON.stringify(state, null, 2)}\n`, 'utf8')
  } catch {
    // Remembering is a convenience. A read-only profile must not break the
    // check itself.
  }
}

function isReleaseInfo(value) {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof value.version === 'string' &&
    typeof value.notes === 'string'
  )
}

/**
 * Releases are remembered at check time, so the notes are still readable after
 * the installer has restarted the app on the new version - by then GitHub may
 * be unreachable and the point of the changelog is precisely that moment.
 */
async function rememberRelease(release) {
  const state = await readState()
  const kept = state.releases.filter((entry) => entry.version !== release.version)
  await writeState({
    ...state,
    releases: [release, ...kept].slice(0, MAX_REMEMBERED_RELEASES)
  })
}

function apiHeaders() {
  return {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': `HexagonMediaService/${app.getVersion()}`
  }
}

/**
 * A private repository answers 404, exactly like a repository with no release
 * yet, and there is no way to tell them apart without a token. Both say "not
 * published"; a token would have to ship inside the installer, which is worse
 * than the ambiguity.
 */
function errorForStatus(status) {
  if (status === 404) return 'notPublished'
  if (status === 403 || status === 429) return 'rateLimited'
  return 'offline'
}

function readRelease(raw) {
  if (typeof raw !== 'object' || raw === null) return null

  const tagName = typeof raw.tag_name === 'string' ? raw.tag_name : ''
  const version = tagName.trim().replace(/^v/i, '')
  if (parseVersion(version) === null) return null

  const asset = pickInstaller(raw.assets)

  return {
    version,
    tagName,
    title: typeof raw.name === 'string' && raw.name.length > 0 ? raw.name : null,
    notes: typeof raw.body === 'string' ? raw.body.slice(0, MAX_NOTES_CHARS) : '',
    publishedIso: typeof raw.published_at === 'string' ? raw.published_at : null,
    htmlUrl:
      typeof raw.html_url === 'string' && raw.html_url.startsWith('https://')
        ? raw.html_url
        : `https://github.com/${repoSlug()}/releases`,
    downloadUrl: asset ? asset.url : null,
    downloadSizeBytes: asset ? asset.size : null
  }
}

function readAssets(raw) {
  if (!Array.isArray(raw)) return []

  const assets = []
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const name = entry.name
    const url = entry.browser_download_url
    if (typeof name !== 'string' || typeof url !== 'string') continue
    if (!isAllowedDownload(url)) continue

    assets.push({
      name,
      url,
      size: typeof entry.size === 'number' && entry.size > 0 ? entry.size : null
    })
  }
  return assets
}

/** The Setup exe, never the portable one: only the installer can replace us. */
function pickInstaller(raw) {
  const assets = readAssets(raw)
  const setup = assets.find((asset) => /setup\.exe$/i.test(asset.name))
  if (setup) return setup
  return assets.find((asset) => /\.exe$/i.test(asset.name) && !/portable/i.test(asset.name)) || null
}

function isAllowedDownload(url) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' && ALLOWED_DOWNLOAD_HOSTS.has(parsed.hostname)
  } catch {
    return false
  }
}

async function fetchRelease(route) {
  try {
    const response = await fetch(`${API_ROOT}/repos/${repoSlug()}/${route}`, {
      headers: apiHeaders(),
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS)
    })

    if (!response.ok) return { release: null, error: errorForStatus(response.status) }

    const release = readRelease(await response.json())
    return release === null ? { release: null, error: 'notPublished' } : { release, error: null }
  } catch {
    return { release: null, error: 'offline' }
  }
}

async function checkForUpdate() {
  const currentVersion = app.getVersion()
  const channel = updateChannel()
  const checkedIso = new Date().toISOString()

  const { release, error } = await fetchRelease('releases/latest')

  const state = await readState()
  await writeState({ ...state, lastCheckIso: checkedIso })

  if (release === null) {
    cachedStatus = {
      currentVersion,
      available: null,
      checkedIso,
      error,
      channel,
      checkOnStart: state.checkOnStart
    }
    return cachedStatus
  }

  await rememberRelease(release)

  cachedStatus = {
    currentVersion,
    available: compareVersions(release.version, currentVersion) > 0 ? release : null,
    checkedIso,
    error: null,
    channel,
    checkOnStart: state.checkOnStart
  }
  return cachedStatus
}

/** What is already known, without asking GitHub anything. */
async function lastStatus() {
  const state = await readState()
  if (cachedStatus) return { ...cachedStatus, checkOnStart: state.checkOnStart }

  return {
    currentVersion: app.getVersion(),
    available: null,
    checkedIso: state.lastCheckIso,
    error: null,
    channel: updateChannel(),
    checkOnStart: state.checkOnStart
  }
}

async function setCheckOnStart(value) {
  const state = await readState()
  await writeState({ ...state, checkOnStart: value === true })
  if (cachedStatus) cachedStatus = { ...cachedStatus, checkOnStart: value === true }
}

async function releaseForVersion(version) {
  const state = await readState()
  const remembered = state.releases.find((entry) => entry.version === version)
  if (remembered) return { release: remembered, error: null }

  // A tag is usually v1.2.3 but not always; try both rather than guessing.
  let lastError = null
  for (const tag of [`v${version}`, version]) {
    const { release, error } = await fetchRelease(`releases/tags/${encodeURIComponent(tag)}`)
    if (release) {
      await rememberRelease(release)
      return { release, error: null }
    }
    lastError = error
  }
  return { release: null, error: lastError }
}

async function changelogFor(version) {
  return (await releaseForVersion(version)).release
}

/**
 * The notes for the version now running, when it is newer than the version the
 * user has already been shown. `seenVersion` starting as null is what stops a
 * changelog appearing on a first ever install.
 */
async function pendingChangelog() {
  const currentVersion = app.getVersion()
  const state = await readState()

  if (state.seenVersion === null) {
    await writeState({ ...state, seenVersion: currentVersion })
    return null
  }

  if (state.seenVersion === currentVersion) return null
  if (compareVersions(currentVersion, state.seenVersion) <= 0) {
    await writeState({ ...state, seenVersion: currentVersion })
    return null
  }

  const { release, error } = await releaseForVersion(currentVersion)
  if (release !== null) return release

  // Nothing published for this version, so stop asking. A network failure is
  // left alone: the notes may exist and simply be out of reach right now.
  if (error === 'notPublished') await writeState({ ...state, seenVersion: currentVersion })
  return null
}

async function acknowledgeChangelog(version) {
  if (typeof version !== 'string' || version.length === 0) return
  const state = await readState()
  await writeState({ ...state, seenVersion: version })
}

/**
 * The sha512 electron-builder publishes for the installer, read out of the
 * latest.yml that sits beside it in the release.
 */
async function expectedHash(release, assetName) {
  try {
    const response = await fetch(
      `${API_ROOT}/repos/${repoSlug()}/releases/tags/${encodeURIComponent(release.tagName)}`,
      { headers: apiHeaders(), signal: AbortSignal.timeout(CHECK_TIMEOUT_MS) }
    )
    if (!response.ok) return null

    const record = await response.json()
    const manifest = readAssets(record.assets).find((asset) => /^latest.*\.yml$/i.test(asset.name))
    if (!manifest) return null

    const text = await (
      await fetch(manifest.url, { signal: AbortSignal.timeout(CHECK_TIMEOUT_MS) })
    ).text()

    return readManifestHash(text, assetName)
  } catch {
    return null
  }
}

/**
 * Enough of latest.yml to find one file's hash. A real YAML parser is a
 * dependency for six lines of key-value pairs written by one known producer.
 */
function readManifestHash(manifest, assetName) {
  let currentFile = null

  for (const line of manifest.split(/\r?\n/)) {
    const file = /^\s*-?\s*(?:url|path):\s*(.+?)\s*$/.exec(line)
    if (file) {
      currentFile = file[1].replace(/^["']|["']$/g, '')
      continue
    }

    const hash = /^\s*-?\s*sha512:\s*(.+?)\s*$/.exec(line)
    if (hash && currentFile === assetName) return hash[1].replace(/^["']|["']$/g, '')
  }
  return null
}

function fileNameFor(url) {
  const raw = decodeURIComponent(new URL(url).pathname.split('/').pop() || 'update.exe')
  const safe = raw.replace(/[^\w.-]/g, '_')
  return safe.toLowerCase().endsWith('.exe') ? safe : `${safe}.exe`
}

/**
 * Fetch the installer, check it against the release, and hand it to Windows.
 *
 * The app quits a moment later: the installer is what replaces these files,
 * and it kills any copy still running before it starts. Progress is reported
 * through `onProgress` rather than returned, because the download is the part
 * the user watches.
 */
async function downloadAndInstall(onProgress) {
  const status = cachedStatus || (await checkForUpdate())
  const release = status.available

  if (release === null) return { ok: false, error: status.error || 'notPublished', detail: null }
  if (release.downloadUrl === null || !isAllowedDownload(release.downloadUrl)) {
    return { ok: false, error: 'noAsset', detail: null }
  }

  const target = path.join(downloadDir(), fileNameFor(release.downloadUrl))
  let received = 0

  try {
    await rm(downloadDir(), { recursive: true, force: true })
    await mkdir(downloadDir(), { recursive: true })

    const response = await fetch(release.downloadUrl, {
      headers: { 'User-Agent': `HexagonMediaService/${app.getVersion()}` },
      signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS)
    })
    if (!response.ok || response.body === null) {
      return { ok: false, error: 'downloadFailed', detail: String(response.status) }
    }

    const declared = Number(response.headers.get('content-length') || 0)
    const total = declared > 0 ? declared : release.downloadSizeBytes || 0
    const digest = createHash('sha512')
    let lastReport = 0

    onProgress({ phase: 'downloading', receivedBytes: 0, totalBytes: total })

    // Hashing as the bytes go past means the file is never read twice, which
    // on a 100 MB installer is the difference between instant and a stall.
    const meter = new Transform({
      transform(chunk, _encoding, callback) {
        received += chunk.length
        digest.update(chunk)

        const now = Date.now()
        if (now - lastReport >= PROGRESS_INTERVAL_MS) {
          lastReport = now
          onProgress({ phase: 'downloading', receivedBytes: received, totalBytes: total })
        }
        callback(null, chunk)
      }
    })

    await pipeline(Readable.fromWeb(response.body), meter, createWriteStream(target))

    onProgress({ phase: 'downloading', receivedBytes: received, totalBytes: total })
    onProgress({ phase: 'verifying' })

    if (release.downloadSizeBytes !== null && received !== release.downloadSizeBytes) {
      return { ok: false, error: 'verifyFailed', detail: null }
    }

    const expected = await expectedHash(release, fileNameFor(release.downloadUrl))
    if (expected !== null && expected !== digest.digest('base64')) {
      return { ok: false, error: 'verifyFailed', detail: null }
    }
  } catch (error) {
    return { ok: false, error: 'downloadFailed', detail: error && error.message ? error.message : null }
  }

  await rememberRelease(release)

  try {
    // electron-builder's NSIS script reads these: --updated marks this as an
    // upgrade, /S runs it without pages, --force-run reopens the app after.
    const child = spawn(target, ['--updated', '/S', '--force-run'], {
      detached: true,
      stdio: 'ignore'
    })
    child.unref()
  } catch (error) {
    return { ok: false, error: 'launchFailed', detail: error && error.message ? error.message : null }
  }

  onProgress({ phase: 'restarting' })
  setTimeout(() => app.quit(), QUIT_DELAY_MS)

  return { ok: true, error: null, detail: null }
}

module.exports = {
  updateChannel,
  compareVersions,
  readManifestHash,
  checkForUpdate,
  lastStatus,
  setCheckOnStart,
  changelogFor,
  pendingChangelog,
  acknowledgeChangelog,
  downloadAndInstall
}
