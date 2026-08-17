/**
 * The handful of primitives every part of the interface builds on: an icon
 * set, an element factory, a size formatter and the toast host.
 *
 * These used to live at the top of app.js. They moved out when the update
 * dialog arrived, because it needs the same ones and duplicating them would
 * have meant two icon sets drifting apart.
 */

export const ICONS = {
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
  check: 'M5 12.5 9.5 17 19 7.5',
  // An arrow dropping into a tray: the app replacing itself.
  update: 'M12 3.5v9M8.5 9 12 12.5 15.5 9M4.5 15v3.5a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V15',
  history: 'M4.5 12a7.5 7.5 0 1 0 2.3-5.4M4.5 5v3.6h3.6M12 7.8v4.4l3 1.8',
  external: 'M14 4h6v6M20 4l-8.4 8.4M18 14.5V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4.5'
}

export function icon(name, size = 18) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"
    ><path d="${ICONS[name] || ICONS.video}"/></svg>`
}

export const el = (html) => {
  const t = document.createElement('template')
  t.innerHTML = html.trim()
  return t.content.firstElementChild
}

export function humanSize(bytes) {
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

/**
 * A date from GitHub, written the way a person would say it.
 *
 * The locale is pinned rather than taken from the machine: the interface is
 * written in English, and toLocaleDateString(undefined) prints a Russian month
 * name on a Russian Windows, halfway through an English sentence.
 */
export function humanDate(iso, withTime = false) {
  if (!iso) return ''
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return ''

  const date = when.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
  if (!withTime) return date
  return `${date} at ${when.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`
}

export function toast(message, kind = 'info', ms = 3600) {
  const host = document.getElementById('toasts')
  const node = el(`<div class="toast ${kind}"></div>`)
  node.textContent = message
  host.appendChild(node)
  setTimeout(() => node.remove(), ms)
}
