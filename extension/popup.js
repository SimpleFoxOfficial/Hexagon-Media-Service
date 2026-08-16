const $ = (id) => document.getElementById(id)
const status = $('status')
let info = null
let settings = {}

function say(text, kind = '') {
  status.textContent = text
  status.className = kind
}

const send = (type, payload = {}) =>
  new Promise((resolve) => chrome.runtime.sendMessage({ type, ...payload }, resolve))

function seasonsFor() {
  return info?.seasons || []
}

function currentSeason() {
  return Number($('season').value) || 0
}

function renderSeasons() {
  const seasons = seasonsFor()
  $('season').innerHTML = seasons
    .map((s) => `<option value="${s.season}">Season ${s.season}</option>`)
    .join('')
  if (info.season) $('season').value = String(info.season)
  renderEpisodes()
}

function renderEpisodes() {
  const season = seasonsFor().find((s) => s.season === currentSeason())
  const list = season ? season.episodes : []
  $('episodes').innerHTML = list
    .map((e) => `<span class="chip" data-ep="${e}">${e}</span>`)
    .join('')
  for (const chip of $('episodes').children) {
    chip.addEventListener('click', () => {
      chip.classList.toggle('on')
      updateButton()
    })
  }
  updateButton()
}

function selected() {
  return [...$('episodes').querySelectorAll('.chip.on')].map((c) => Number(c.dataset.ep))
}

function updateButton() {
  if (!info?.isSeries) {
    $('go').textContent = 'Download film'
    $('go').disabled = false
    return
  }
  const n = selected().length
  $('go').textContent = n ? `Download ${n} episode${n === 1 ? '' : 's'}` : 'Pick episodes'
  $('go').disabled = n === 0
}

function parseRange(text) {
  const out = new Set()
  for (const chunk of String(text).replace(/\s/g, '').split(',')) {
    if (!chunk) continue
    if (chunk.includes('-')) {
      let [a, b] = chunk.split('-').map(Number)
      if (!a || !b) continue
      if (a > b) [a, b] = [b, a]
      for (let i = a; i <= b; i++) out.add(i)
    } else if (Number(chunk)) out.add(Number(chunk))
  }
  return out
}

async function init() {
  const ping = await send('ping')
  if (!ping?.ok) {
    say(ping?.error || 'Media Downloader is not reachable. Is it running?', 'err')
    return
  }
  settings = (await send('settings'))?.result || {}

  const res = await send('describe')
  if (!res?.ok) {
    say(res.error, 'err')
    return
  }
  info = res.result

  $('title').textContent = info.title || 'HDRezka'
  $('sub').textContent = info.isSeries
    ? `Series - ${info.translators.length} translation(s)`
    : 'Film'
  $('panel').classList.remove('hidden')

  $('translator').innerHTML = info.translators
    .map((t) => `<option value="${t.id}"${t.active ? ' selected' : ''}>${t.name}</option>`)
    .join('')

  if (settings.quality) $('quality').value = settings.quality

  $('season-wrap').classList.toggle('hidden', !info.isSeries)
  $('episode-wrap').classList.toggle('hidden', !info.isSeries)

  if (info.isSeries) renderSeasons()
  else updateButton()

  say(`Saving to ${settings.destination || 'the app folder'}`)
}

$('translator').addEventListener('change', async () => {
  say('Loading episodes...')
  const res = await send('episodes', { translatorId: $('translator').value })
  if (res?.ok) {
    info.seasons = res.result
    renderSeasons()
    say('')
  } else say(res?.error || 'Could not load episodes', 'err')
})

$('season').addEventListener('change', renderEpisodes)
$('all').addEventListener('click', () => {
  for (const c of $('episodes').children) c.classList.add('on')
  updateButton()
})
$('none').addEventListener('click', () => {
  for (const c of $('episodes').children) c.classList.remove('on')
  updateButton()
})
$('range').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return
  const wanted = parseRange($('range').value)
  for (const c of $('episodes').children) {
    c.classList.toggle('on', wanted.has(Number(c.dataset.ep)))
  }
  updateButton()
})

$('go').addEventListener('click', async () => {
  $('go').disabled = true
  const translatorId = $('translator').value
  const season = currentSeason()
  const items = info.isSeries
    ? selected().map((episode) => ({
        translatorId,
        season,
        episode,
        show: info.title,
        pageUrl: info.pageUrl
      }))
    : [{ translatorId, season: 0, episode: 0, show: info.title, pageUrl: info.pageUrl }]

  say(`Resolving ${items.length} item(s)...`)
  const res = await send('download', {
    items,
    settings: { quality: $('quality').value, show: info.title }
  })

  if (!res?.ok) {
    say(res?.error || 'Failed', 'err')
    $('go').disabled = false
    return
  }
  const { started, failed } = res.result
  say(
    failed.length
      ? `Started ${started}, skipped ${failed.length}: ${failed[0]}`
      : `Started ${started} download(s). The app files them when they finish.`,
    failed.length ? 'err' : 'ok'
  )
  updateButton()
})

$('options').addEventListener('click', () => chrome.runtime.openOptionsPage())

init()
