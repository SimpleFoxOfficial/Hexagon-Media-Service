const baseInput = document.getElementById('base')
const tokenInput = document.getElementById('token')
const msg = document.getElementById('msg')

chrome.storage.local.get(['base', 'token']).then(({ base, token }) => {
  baseInput.value = base || 'http://127.0.0.1:47615'
  tokenInput.value = token || ''
})

document.getElementById('save').addEventListener('click', async () => {
  const base = baseInput.value.trim() || 'http://127.0.0.1:47615'
  const token = tokenInput.value.trim()

  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(base)) {
    msg.textContent = 'The address must point at 127.0.0.1 on this machine.'
    msg.className = 'err'
    return
  }

  await chrome.storage.local.set({ base, token })
  msg.textContent = 'Saved. Testing...'
  msg.className = ''

  chrome.runtime.sendMessage({ type: 'ping' }, (res) => {
    if (res?.ok) {
      msg.textContent = 'Connected. You can close this page.'
      msg.className = 'ok'
    } else {
      msg.textContent = res?.error || 'Could not reach the app. Is it running?'
      msg.className = 'err'
    }
  })
})
