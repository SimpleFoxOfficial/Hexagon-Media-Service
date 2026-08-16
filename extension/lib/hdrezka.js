/**
 * HDRezka protocol, implemented from the site's own network behaviour.
 *
 * Original implementation. HDrezka Grabber is GPL-3.0 and none of its code is
 * reused here; only the publicly observable request shapes are, which are facts
 * about the site rather than anyone's expression.
 *
 * Everything runs inside a page the browser already loaded, so the bot check
 * has been satisfied by normal browsing and no part of this works around it.
 */

/** The player is initialised with the post and translator ids as literals. */
function readPageState(doc = document) {
  const html = doc.documentElement.innerHTML

  const series = html.match(/initCDNSeriesEvents\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/)
  const movie = html.match(/initCDNMoviesEvents\(\s*(\d+)\s*,\s*(\d+)/)

  let postId = null
  let translatorId = null
  let season = 0
  let episode = 0
  let isSeries = false

  if (series) {
    isSeries = true
    postId = series[1]
    translatorId = series[2]
    season = Number(series[3]) || 0
    episode = Number(series[4]) || 0
  } else if (movie) {
    postId = movie[1]
    translatorId = movie[2]
  }

  if (!postId) {
    const meta = doc.querySelector('#post_id, input[name="post_id"]')
    if (meta) postId = meta.value || meta.getAttribute('value')
  }

  const favs = (html.match(/['"]favs['"]\s*[:=]\s*['"]([^'"]+)['"]/) || [])[1] || ''

  return { postId, translatorId, season, episode, isSeries, favs }
}

function readTitle(doc = document) {
  const node = doc.querySelector('.b-post__title h1, h1[itemprop="name"], h1')
  return (node ? node.textContent : doc.title).replace(/\s+/g, ' ').trim()
}

function readOriginalTitle(doc = document) {
  const node = doc.querySelector('.b-post__origtitle, [itemprop="alternativeHeadline"]')
  return node ? node.textContent.trim() : ''
}

function readYear(doc = document) {
  const match = (doc.body.textContent || '').match(/\b(19|20)\d{2}\b/)
  return match ? match[0] : ''
}

/** Translations offered for this title, in page order. */
function readTranslators(doc = document) {
  const out = []
  for (const node of doc.querySelectorAll('.b-translator__item')) {
    const id = node.getAttribute('data-translator_id')
    if (!id) continue
    out.push({
      id,
      name: (node.getAttribute('title') || node.textContent || '').replace(/\s+/g, ' ').trim(),
      active: node.classList.contains('active')
    })
  }
  if (!out.length) {
    const state = readPageState(doc)
    if (state.translatorId) out.push({ id: state.translatorId, name: 'Default', active: true })
  }
  return out
}

/** Season titles, where the page names them rather than numbering them. */
function readSeasonNames(doc = document) {
  const names = new Map()
  for (const node of doc.querySelectorAll('.b-simple_season__item, [data-tab_id]')) {
    const id = Number(node.getAttribute('data-tab_id') || node.getAttribute('data-season_id'))
    if (!id) continue
    const text = (node.textContent || '').replace(/\s+/g, ' ').trim()
    if (text) names.set(id, text)
  }
  return names
}

/**
 * Seasons with their episodes. Episode titles come from the list markup; the
 * site writes them as "1 series" or the real title depending on the release,
 * so the number is kept separately and the label is only ever decoration.
 */
function readSeasons(doc = document) {
  const seasons = new Map()
  const seasonNames = readSeasonNames(doc)

  for (const node of doc.querySelectorAll('.b-simple_episode__item, [data-episode_id]')) {
    const s = Number(node.getAttribute('data-season_id'))
    const e = Number(node.getAttribute('data-episode_id'))
    if (!s || !e) continue
    if (!seasons.has(s)) seasons.set(s, new Map())

    const label = (node.getAttribute('title') || node.textContent || '')
      .replace(/\s+/g, ' ')
      .trim()
    const existing = seasons.get(s).get(e)
    if (!existing || (!existing.name && label)) {
      seasons.get(s).set(e, { number: e, name: label })
    }
  }

  return [...seasons.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([season, eps]) => ({
      season,
      name: seasonNames.get(season) || `Season ${season}`,
      episodes: [...eps.values()].sort((a, b) => a.number - b.number)
    }))
}

/**
 * The stream list is returned obfuscated: a "#h" marker, then base64 with junk
 * blocks spliced in. Removing the junk and decoding yields "[quality]url" pairs.
 */
function decodeStreamList(raw) {
  if (typeof raw !== 'string' || !raw) return ''
  let text = raw.trim()
  if (!text.startsWith('#')) return text

  text = text.replace(/^#\w?/, '')
  // Junk blocks are a "//_//" marker followed by non-base64 filler.
  text = text.replace(/\/\/_\/\/[^A-Za-z0-9+/=]*/g, '')
  text = text.replace(/[^A-Za-z0-9+/=]/g, '')

  try {
    const binary = atob(text)
    // The payload is UTF-8; atob gives latin1, so widen it back.
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0))
    return new TextDecoder('utf-8').decode(bytes)
  } catch {
    return ''
  }
}

/** "[1080p]https://a.mp4 or https://b.mp4,[720p]..." -> [{quality, urls}] */
function parseStreams(decoded) {
  const out = []
  if (!decoded) return out
  for (const chunk of decoded.split(',')) {
    const match = chunk.match(/\[([^\]]+)\]\s*(.+)/)
    if (!match) continue
    const urls = match[2]
      .split(/\s+or\s+/i)
      .map((u) => u.trim())
      .filter((u) => /^https?:\/\//.test(u))
    if (urls.length) out.push({ quality: match[1].trim(), urls })
  }
  // Highest resolution first.
  const height = (q) => Number((q.match(/(\d{3,4})/) || [])[1] || 0)
  return out.sort((a, b) => height(b.quality) - height(a.quality))
}

async function ajax(path, body) {
  const response = await fetch(`${location.origin}${path}?t=${Date.now()}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest'
    },
    body: new URLSearchParams(body).toString()
  })
  if (!response.ok) throw new Error(`site replied ${response.status}`)
  return response.json()
}

/** Resolve one film or episode into its available qualities. */
async function fetchStreams({ postId, translatorId, season, episode, favs }) {
  const isEpisode = Number(season) > 0 && Number(episode) > 0
  const payload = isEpisode
    ? {
        id: postId,
        translator_id: translatorId,
        season: String(season),
        episode: String(episode),
        favs: favs || '',
        action: 'get_stream'
      }
    : {
        id: postId,
        translator_id: translatorId,
        favs: favs || '',
        action: 'get_movie'
      }

  const data = await ajax('/ajax/get_cdn_series/', payload)
  if (!data || data.success === false) {
    throw new Error(data?.message || 'the site refused the stream request')
  }

  const streams = parseStreams(decodeStreamList(data.url))
  if (!streams.length) throw new Error('no playable qualities were returned')

  return {
    streams,
    subtitles: parseSubtitles(data.subtitle),
    season: isEpisode ? Number(season) : 0,
    episode: isEpisode ? Number(episode) : 0
  }
}

function parseSubtitles(raw) {
  const out = []
  if (typeof raw !== 'string' || !raw) return out
  for (const chunk of raw.split(',')) {
    const match = chunk.match(/\[([^\]]+)\]\s*(https?:\/\/\S+)/)
    if (match) out.push({ label: match[1].trim(), url: match[2].trim() })
  }
  return out
}

/** Episode list for a translator, for seasons not currently rendered. */
async function fetchEpisodes({ postId, translatorId }) {
  const data = await ajax('/ajax/get_episodes/', {
    id: postId,
    translator_id: translatorId,
    action: 'get_episodes'
  })
  if (!data?.episodes) return []

  const doc = new DOMParser().parseFromString(String(data.episodes), 'text/html')
  return readSeasons(doc)
}

/**
 * Choose which URL of a quality to fetch.
 *
 * Each quality usually carries both a progressive .mp4 and an HLS .m3u8. The
 * browser's download API can only fetch a plain file, so handed an .m3u8 it
 * saves the few-kilobyte playlist and reports success. The mp4 is therefore
 * strongly preferred, and an HLS-only quality is flagged so the caller can
 * hand it to the app, whose yt-dlp does understand HLS.
 */
function pickUrl(stream) {
  if (!stream || !stream.urls?.length) return null
  const mp4 = stream.urls.find((u) => /\.mp4(\?|$)/i.test(u.split('?')[0]))
  if (mp4) return { url: mp4, hls: false }

  const hls = stream.urls.find((u) => /\.m3u8(\?|$)/i.test(u.split('?')[0]))
  if (hls) return { url: hls, hls: true }

  return { url: stream.urls[0], hls: false }
}

/** Pick the closest available quality at or below the requested height. */
function pickQuality(streams, wanted) {
  if (!streams.length) return null
  if (!wanted || wanted === 'best') return streams[0]
  if (wanted === 'worst') return streams[streams.length - 1]

  const target = Number(wanted)
  if (!target) return streams[0]
  const height = (q) => Number((q.match(/(\d{3,4})/) || [])[1] || 0)
  return streams.find((s) => height(s.quality) <= target) || streams[streams.length - 1]
}

// Exposed as a global: a content script runs as a classic script, and a
// dynamic import of an extension URL is blocked by most pages' CSP.

// Exposed as a global: a content script is a classic script, and a dynamic
// import of an extension URL is blocked by most pages' CSP.
globalThis.HDRezkaLib = {
  readPageState, readTitle, readOriginalTitle, readYear, readTranslators,
  readSeasons, readSeasonNames, decodeStreamList, parseStreams, fetchStreams, fetchEpisodes,
  pickUrl, pickQuality
};
