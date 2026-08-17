/**
 * Release notes, rendered rather than injected.
 *
 * The text comes off the network, so nothing here ever touches innerHTML: a
 * small markdown subset is parsed into blocks and each one is built as real
 * elements with textContent. HTML comments and tags are stripped, and only an
 * https link becomes clickable - through the main process, since a renderer
 * cannot navigate anywhere anyway.
 */

const INLINE =
  /(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\([^)\s]+\))|(https?:\/\/[^\s)<>]+)/g

export function releaseNotes(text, emptyText = 'This release came with no notes.') {
  const host = document.createElement('div')
  host.className = 'notes'

  const blocks = parseBlocks(text || '')
  if (blocks.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'muted'
    empty.textContent = emptyText
    host.appendChild(empty)
    return host
  }

  for (const block of blocks) host.appendChild(renderBlock(block))
  return host
}

function renderBlock(block) {
  if (block.kind === 'heading') {
    const node = document.createElement(block.level <= 2 ? 'h4' : 'h5')
    inline(block.text, node)
    return node
  }

  if (block.kind === 'list') {
    const node = document.createElement(block.ordered ? 'ol' : 'ul')
    for (const item of block.items) {
      const li = document.createElement('li')
      inline(item, li)
      node.appendChild(li)
    }
    return node
  }

  if (block.kind === 'quote') {
    const node = document.createElement('blockquote')
    inline(block.lines.join(' '), node)
    return node
  }

  if (block.kind === 'code') {
    const node = document.createElement('pre')
    node.textContent = block.text
    return node
  }

  if (block.kind === 'rule') return document.createElement('hr')

  const node = document.createElement('p')
  inline(block.lines.join(' '), node)
  return node
}

function parseBlocks(text) {
  const lines = text
    .replace(/\r\n/g, '\n')
    .replace(/<!--[\s\S]*?-->/g, '')
    .split('\n')
  const blocks = []

  let paragraph = []
  let quote = []
  let list = null

  const flush = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: 'paragraph', lines: paragraph })
      paragraph = []
    }
    if (quote.length > 0) {
      blocks.push({ kind: 'quote', lines: quote })
      quote = []
    }
    if (list) {
      blocks.push({ kind: 'list', ordered: list.ordered, items: list.items })
      list = null
    }
  }

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]

    if (/^\s*```/.test(line)) {
      flush()
      const body = []
      index++
      while (index < lines.length && !/^\s*```/.test(lines[index])) {
        body.push(lines[index])
        index++
      }
      if (body.length > 0) blocks.push({ kind: 'code', text: body.join('\n') })
      continue
    }

    if (line.trim() === '') {
      flush()
      continue
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flush()
      blocks.push({ kind: 'rule' })
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      flush()
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() })
      continue
    }

    const quoted = /^\s*>\s?(.*)$/.exec(line)
    if (quoted) {
      if (paragraph.length > 0 || list) flush()
      quote.push(quoted[1])
      continue
    }

    const item = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/.exec(line)
    if (item) {
      if (paragraph.length > 0 || quote.length > 0) flush()
      const ordered = item[2] !== undefined
      if (list && list.ordered !== ordered) flush()
      if (!list) list = { ordered, items: [] }
      list.items.push(stripTags(item[3].trim()))
      continue
    }

    // A wrapped continuation line belongs to the item above it, not to a new
    // paragraph; GitHub release notes are full of them.
    if (list) {
      const last = list.items.length - 1
      if (last >= 0) {
        list.items[last] = `${list.items[last]} ${line.trim()}`
        continue
      }
    }

    if (quote.length > 0) flush()
    paragraph.push(stripTags(line.trim()))
  }

  flush()
  return blocks
}

function stripTags(text) {
  return text.replace(/<\/?[a-zA-Z][^>]*>/g, '').trim()
}

/** Appends the inline spans of `text` to `parent` as elements and text nodes. */
function inline(text, parent) {
  let cursor = 0

  INLINE.lastIndex = 0
  for (let match = INLINE.exec(text); match !== null; match = INLINE.exec(text)) {
    if (match.index > cursor) parent.appendChild(document.createTextNode(text.slice(cursor, match.index)))
    cursor = match.index + match[0].length

    const token = match[0]

    if (token.startsWith('`')) {
      parent.appendChild(wrap('code', token.slice(1, -1)))
      continue
    }
    if (token.startsWith('**') || token.startsWith('__')) {
      parent.appendChild(wrap('strong', token.slice(2, -2)))
      continue
    }
    if (token.startsWith('*')) {
      parent.appendChild(wrap('em', token.slice(1, -1)))
      continue
    }

    if (token.startsWith('[')) {
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token)
      parent.appendChild(link ? externalLink(link[2], link[1]) : document.createTextNode(token))
      continue
    }

    parent.appendChild(externalLink(token, shortenUrl(token)))
  }

  if (cursor < text.length) parent.appendChild(document.createTextNode(text.slice(cursor)))
}

function wrap(tag, text) {
  const node = document.createElement(tag)
  node.textContent = text
  return node
}

function externalLink(url, label) {
  // Anything that is not plain https stays as text: a javascript: or file:
  // target in release notes has no business being one click away.
  if (!url.startsWith('https://')) return document.createTextNode(label)

  const node = document.createElement('button')
  node.type = 'button'
  node.className = 'link'
  node.textContent = label
  node.addEventListener('click', () => window.host.openExternal(url))
  return node
}

/** A bare URL reads better as a pull request number or a hostname and path. */
function shortenUrl(url) {
  const pull = /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/(\d+)$/.exec(url)
  if (pull) return `#${pull[1]}`

  try {
    const parsed = new URL(url)
    return `${parsed.hostname.replace(/^www\./, '')}${parsed.pathname === '/' ? '' : parsed.pathname}`
  } catch {
    return url
  }
}
