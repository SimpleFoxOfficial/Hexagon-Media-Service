# Desktop shell

The interface is web (HTML/CSS/JS in Electron); the engine stays Python. One
app to look at, two technologies inside.

```bash
cd desktop && npm start
```

Electron spawns `python -u -m mediadl.daemon` and talks newline-delimited JSON
to it over stdin/stdout. The renderer never touches Node, the filesystem or the
engine directly: everything crosses `preload.js` through named calls, under a
CSP that blocks remote scripts.

## Layout

```
src/main/main.js      window, IPC, shell integration
src/main/bridge.js    spawns the engine, frames the JSON protocol
src/preload/          the only surface the renderer gets
src/renderer/         index.html, app.js, styles/
```

`styles/tokens.css` carries Modrinth's design tokens (numbered surfaces,
semantic colour ramps with 10%/25% variants, radius scale). Theme and accent
are `data-theme` / `data-accent` attributes on `<html>`, so restyling is a token
swap rather than a component rewrite.

## Protocol

```
-> {"id":1,"method":"queue.add","params":{"urls":["https://..."]}}
<- {"id":1,"result":{"accepted":1}}
<- {"event":"job.changed","data":{...}}
```

Methods live in `Daemon._methods` in `mediadl/daemon.py`. stdout is protocol
only; the engine's own logging goes to stderr and the rotating log file.

## If Electron will not install

npm 11 blocks postinstall scripts, so the runtime download is skipped and you
get "Electron failed to install correctly". Approve it, or fetch the runtime
directly:

```bash
npm approve-scripts electron
```

Failing that, download `electron-v<version>-win32-x64.zip` from the Electron
releases page, extract it into `node_modules/electron/dist/`, and put
`electron.exe` in `node_modules/electron/path.txt`.
