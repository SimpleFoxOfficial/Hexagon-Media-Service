/*
 * Shared by both pages: point the download buttons at the newest release, lean
 * the hero screenshot upright as it scrolls, hold the top bar in place, and run
 * the copy buttons on the extension guide.
 *
 * The page is static and stays useful with none of it: every button already
 * links to the releases page in the markup, and this only ever narrows that to
 * the exact asset. A private repository answers 404 here, exactly as it does
 * for the app itself, and the links are simply left alone.
 */

(function () {
  'use strict'

  var REPO = 'SimpleFoxOfficial/Hexagon-Media-Service'
  var RELEASES = 'https://github.com/' + REPO + '/releases/latest'
  var GUIDE = 'extension.html'

  var t = function (key, vars) {
    return window.HMS_I18N ? window.HMS_I18N.t(key, vars) : key
  }

  var release = null

  // ------------------------------------------------------------- release

  function humanSize(bytes) {
    var units = ['B', 'KB', 'MB', 'GB']
    var value = Number(bytes) || 0
    var i = 0
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024
      i++
    }
    return (i === 0 ? Math.round(value) : value.toFixed(0)) + ' ' + units[i]
  }

  function assetNamed(assets, pattern) {
    for (var i = 0; i < assets.length; i++) {
      if (pattern.test(assets[i].name) && typeof assets[i].browser_download_url === 'string') {
        return assets[i]
      }
    }
    return null
  }

  function byId(id) {
    return document.getElementById(id)
  }

  function setText(id, text) {
    var node = byId(id)
    if (node) node.textContent = text
  }

  /** Paints whatever the page has: labels, sizes, and the asset links. */
  function paintRelease() {
    var setup = release ? release.setup : null
    var portable = release ? release.portable : null

    var label = setup && release.version
      ? t('hero.downloadVersion', { version: release.version })
      : t('hero.download')
    setText('download-label', label)
    setText('download-label-2', label)
    setText('portable-label', t('hero.portable'))

    var meta = setup ? t('hero.metaSize', { size: humanSize(setup.size) }) : t('hero.meta')
    setText('release-meta', meta)
    setText('release-meta-2', t('closer.meta'))

    if (portable) {
      var portableLink = byId('portable')
      if (portableLink) portableLink.href = portable.url
    }

    var retry = byId('retry')
    if (retry) retry.href = setup ? setup.url : RELEASES
  }

  function loadRelease() {
    if (typeof fetch !== 'function') return Promise.resolve()

    return fetch('https://api.github.com/repos/' + REPO + '/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' }
    })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (data) {
        if (!data) return
        var assets = Array.isArray(data.assets) ? data.assets : []
        var setup = assetNamed(assets, /setup\.exe$/i)
        var portable = assetNamed(assets, /portable\.exe$/i)
        release = {
          version: String(data.tag_name || '').replace(/^v/i, ''),
          setup: setup ? { url: setup.browser_download_url, size: setup.size } : null,
          portable: portable ? { url: portable.browser_download_url } : null
        }
        paintRelease()
      })
      .catch(function () {
        // Offline, rate limited, or no release yet. The markup already works.
      })
  }

  // ------------------------------------------------------------ download

  /**
   * Downloading is the moment someone is most willing to read a setup guide,
   * so the button starts the file and moves them straight to it. The download
   * is handed to a hidden anchor rather than a navigation, because navigating
   * to a binary and then away can cancel the transfer in some browsers.
   */
  function startDownload(url) {
    var link = document.createElement('a')
    link.href = url
    link.setAttribute('download', '')
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    setTimeout(function () {
      link.remove()
    }, 1000)
  }

  function wireDownloadButtons() {
    var buttons = [byId('download'), byId('download-2')]
    for (var i = 0; i < buttons.length; i++) {
      if (!buttons[i]) continue
      buttons[i].addEventListener('click', function (event) {
        var url = release && release.setup ? release.setup.url : null
        if (!url) return // no asset resolved: follow the href to the releases page

        event.preventDefault()
        startDownload(url)
        window.location.href = GUIDE + '?download=1'
      })
    }
  }

  /** On the guide page, opened by the download button: start the file. */
  function autoDownload() {
    var banner = byId('downloading')
    if (!banner) return
    if (window.location.search.indexOf('download=1') === -1) return

    banner.classList.remove('hidden')

    loadRelease().then(function () {
      if (release && release.setup) startDownload(release.setup.url)
    })

    var retry = byId('retry')
    if (retry) {
      retry.addEventListener('click', function (event) {
        if (!release || !release.setup) return
        event.preventDefault()
        startDownload(release.setup.url)
      })
    }
  }

  // ------------------------------------------------------------ copy rows

  function wireCopyButtons() {
    var buttons = document.querySelectorAll('[data-copy]')
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function (event) {
        var button = event.currentTarget
        var source = byId(button.getAttribute('data-copy'))
        if (!source) return

        var text = source.textContent
        var done = function () {
          button.textContent = t('guide.copied')
          button.classList.add('done')
          setTimeout(function () {
            button.textContent = t('guide.copy')
            button.classList.remove('done')
          }, 1400)
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () {})
          return
        }

        // Older browsers, and any page not served over https.
        var field = document.createElement('textarea')
        field.value = text
        document.body.appendChild(field)
        field.select()
        try {
          document.execCommand('copy')
          done()
        } catch (e) {
          /* nothing else to try */
        }
        field.remove()
      })
    }
  }

  // ---------------------------------------------------------------- scroll

  function onScroll() {
    var wrap = byId('top-wrap')
    if (wrap) wrap.classList.toggle('scrolled', window.scrollY > 12)

    var shot = byId('hero-shot')
    if (shot && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      var top = shot.getBoundingClientRect().top
      var travel = window.innerHeight * 0.75
      // 1 while the shot is still below the fold, 0 once it has risen into it.
      var lean = Math.min(1, Math.max(0, top / travel))
      shot.style.setProperty('--lean', lean.toFixed(3))
    }
  }

  function watchScroll() {
    var ticking = false
    var request = function () {
      if (ticking) return
      ticking = true
      window.requestAnimationFrame(function () {
        ticking = false
        onScroll()
      })
    }
    window.addEventListener('scroll', request, { passive: true })
    window.addEventListener('resize', request)
    onScroll()
  }

  // ------------------------------------------------------------------ init

  function init() {
    document.addEventListener('languagechange-hms', paintRelease)

    var langButtons = document.querySelectorAll('[data-lang]')
    for (var i = 0; i < langButtons.length; i++) {
      langButtons[i].addEventListener('click', function (event) {
        if (window.HMS_I18N) window.HMS_I18N.set(event.currentTarget.getAttribute('data-lang'))
      })
    }

    wireCopyButtons()
    wireDownloadButtons()
    watchScroll()

    if (byId('downloading')) {
      autoDownload()
    } else {
      loadRelease()
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init)
  } else {
    init()
  }
})()
