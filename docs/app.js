/*
 * Two small jobs: point the download buttons at the newest release, and lean
 * the hero screenshot upright as it scrolls.
 *
 * The page is static and stays useful with neither: every button already links
 * to the releases page in the markup, and this only ever narrows that to the
 * exact asset. A private repository answers 404 here, exactly as it does for
 * the app itself, and the links are simply left alone.
 */

(function () {
  'use strict'

  var REPO = 'SimpleFoxOfficial/Hexagon-Media-Service'

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

  function setText(id, text) {
    var node = document.getElementById(id)
    if (node) node.textContent = text
  }

  function applyRelease(release) {
    var version = String(release.tag_name || '').replace(/^v/i, '')
    var assets = Array.isArray(release.assets) ? release.assets : []
    var setup = assetNamed(assets, /setup\.exe$/i)
    var portable = assetNamed(assets, /portable\.exe$/i)

    if (setup) {
      var label = version ? 'Download ' + version + ' for Windows' : 'Download for Windows'
      ;['download', 'download-2'].forEach(function (id) {
        var node = document.getElementById(id)
        if (node) node.href = setup.browser_download_url
      })
      setText('download-label', label)
      setText('download-label-2', label)

      var meta = 'Windows 10 and 11, 64-bit. ' + humanSize(setup.size) + ' installer.'
      setText('release-meta', meta)
      setText('release-meta-2', meta)
    }

    if (portable) {
      var node = document.getElementById('portable')
      if (node) {
        node.href = portable.browser_download_url
        node.textContent = 'Portable build'
      }
    }
  }

  function loadRelease() {
    if (typeof fetch !== 'function') return
    fetch('https://api.github.com/repos/' + REPO + '/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' }
    })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (release) {
        if (release) applyRelease(release)
      })
      .catch(function () {
        // Offline, rate limited, or the repository is still private. The links
        // in the markup already work.
      })
  }

  // ---------------------------------------------------------------- lean

  function leanHeroShot() {
    var shot = document.getElementById('hero-shot')
    if (!shot) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    var ticking = false
    var update = function () {
      ticking = false
      var top = shot.getBoundingClientRect().top
      var travel = window.innerHeight * 0.75
      // 1 while the shot is still below the fold, 0 once it has risen into it.
      var lean = Math.min(1, Math.max(0, top / travel))
      shot.style.setProperty('--lean', lean.toFixed(3))
    }

    var onScroll = function () {
      if (ticking) return
      ticking = true
      window.requestAnimationFrame(update)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    update()
  }

  loadRelease()
  leanHeroShot()
})()
