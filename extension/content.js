/**
 * Runs on a HDRezka page. Reads the title, translations, seasons and episodes,
 * and resolves streams on request.
 *
 * The listener is registered synchronously at top level and the library is a
 * plain global loaded by the manifest. An earlier version awaited a dynamic
 * import of an extension URL before registering, which the page's CSP blocks:
 * the listener never existed and every message failed with "Receiving end does
 * not exist".
 *
 * All of this happens in a page the browser loaded normally, so the site's bot
 * check has already been satisfied by ordinary browsing.
 */

const lib = globalThis.HDRezkaLib

async function describe() {
  if (!lib) throw new Error('The HDRezka helper did not load. Reload the tab.')

  const state = lib.readPageState()
  if (!state.postId) throw new Error('This does not look like a HDRezka title page.')

  const translators = lib.readTranslators()
  let seasons = lib.readSeasons()

  // A freshly loaded page only renders the active translation's episodes.
  if (state.isSeries && !seasons.length) {
    seasons = await lib.fetchEpisodes({
      postId: state.postId,
      translatorId: state.translatorId
    })
  }

  return {
    ...state,
    title: lib.readTitle(),
    originalTitle: lib.readOriginalTitle(),
    year: lib.readYear(),
    pageUrl: location.href,
    translators,
    seasons
  }
}

async function episodesFor(translatorId) {
  const state = lib.readPageState()
  return lib.fetchEpisodes({ postId: state.postId, translatorId })
}

/** Resolve one item to a direct URL at the requested quality. */
async function resolve({ translatorId, season, episode, quality }) {
  const state = lib.readPageState()
  const result = await lib.fetchStreams({
    postId: state.postId,
    translatorId: translatorId || state.translatorId,
    season,
    episode,
    favs: state.favs
  })

  const chosen = lib.pickQuality(result.streams, quality)
  if (!chosen) throw new Error('no quality matched')

  const picked = lib.pickUrl(chosen)
  if (!picked) throw new Error('no usable URL for that quality')

  return {
    url: picked.url,
    hls: picked.hls,
    mirrors: chosen.urls.filter((u) => u !== picked.url),
    quality: chosen.quality,
    available: result.streams.map((s) => s.quality),
    subtitles: result.subtitles,
    season: result.season,
    episode: result.episode
  }
}

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  const handlers = {
    ping: async () => ({ alive: true, href: location.href }),
    describe,
    episodesFor: () => episodesFor(message.translatorId),
    resolve: () => resolve(message)
  }
  const handler = handlers[message?.type]
  if (!handler) return false

  Promise.resolve(handler())
    .then((data) => reply({ ok: true, data }))
    .catch((err) => reply({ ok: false, error: String(err.message || err) }))
  return true
})
