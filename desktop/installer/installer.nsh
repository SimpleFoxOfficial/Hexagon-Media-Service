; Extra installer behaviour on top of electron-builder's NSIS defaults.
;
; The goal is an installer that explains itself: a welcome page, the licence
; and component summary, a directory choice, and a finish page that offers to
; open the manual rather than just vanishing.

!macro customHeader
  ; Shown in the installer's window title and Add/Remove Programs.
  BrandingText "Hexagon Media Service ${VERSION}"
!macroend

!macro customWelcomePage
  !define MUI_WELCOMEPAGE_TITLE "Install Hexagon Media Service"
  !define MUI_WELCOMEPAGE_TEXT   "This will install Hexagon Media Service ${VERSION} on your computer.$\r$\n$\r$\nIt downloads from YouTube, HDRezka, Reddit, Twitter and around 1800 other sites. Everything runs locally: no account, no telemetry, nothing uploaded.$\r$\n$\r$\nThe download engine is bundled, so Python is not required. ffmpeg is needed separately for merging and audio conversion.$\r$\n$\r$\nClose Hexagon Media Service if it is running, then click Next."
  !insertmacro MUI_PAGE_WELCOME
!macroend

!macro customInstall
  ; A running copy would keep its own files locked and produce a confusing
  ; failure part-way through.
  DetailPrint "Checking for a running copy..."
  nsExec::Exec 'taskkill /IM "Hexagon Media Service.exe" /F'
  Pop $0
  nsExec::Exec 'taskkill /IM "mediadl-engine.exe" /F'
  Pop $0

  ; Detect a Chromium browser for the extension. Inlined rather than kept in a
  ; Function, because electron-builder compiles this script for the uninstaller
  ; too, where a free-standing installer Function is unreferenced and NSIS
  ; treats that warning as an error.
  StrCpy $1 ""
  ReadRegStr $0 HKLM "SOFTWARE\Clients\StartMenuInternet\Google Chrome\shell\open\command" ""
  StrCmp $0 "" +3
    StrCpy $1 "Google Chrome"
    Goto browserfound

  ReadRegStr $0 HKLM "SOFTWARE\Clients\StartMenuInternet\Microsoft Edge\shell\open\command" ""
  StrCmp $0 "" +3
    StrCpy $1 "Microsoft Edge"
    Goto browserfound

  ReadRegStr $0 HKLM "SOFTWARE\Clients\StartMenuInternet\Brave\shell\open\command" ""
  StrCmp $0 "" +2
    StrCpy $1 "Brave"

  browserfound:
  StrCmp $1 "" 0 +3
    DetailPrint "No Chromium browser detected; the extension can be added later."
    Goto browserdone
  DetailPrint "Detected browser: $1"
  browserdone:

  DetailPrint "Extension files: $INSTDIR\resources\extension"
  DetailPrint "Installed to: $INSTDIR"
  DetailPrint "Settings will be stored in: $APPDATA\HexagonMediaService"
!macroend

!macro customUnInstall
  DetailPrint "Stopping Hexagon Media Service..."
  nsExec::Exec 'taskkill /IM "Hexagon Media Service.exe" /F'
  Pop $0
  nsExec::Exec 'taskkill /IM "mediadl-engine.exe" /F'
  Pop $0
  DetailPrint "Your settings in $APPDATA\MediaDownloader have been left in place."
!macroend

!macro customFinishPage
  !define MUI_FINISHPAGE_TITLE "Hexagon Media Service is installed"
  !define MUI_FINISHPAGE_TEXT  "Hexagon Media Service ${VERSION} has been installed.$\r$\n$\r$\nDownloading from HDRezka needs the browser extension. Tick the box below to open the extension folder and your browser's extensions page; drag the folder onto that page to add it, then pair it from Download > HDRezka.$\r$\n$\r$\nEverything else works without it."

  !define MUI_FINISHPAGE_RUN "$INSTDIR\Hexagon Media Service.exe"
  !define MUI_FINISHPAGE_RUN_TEXT "Start Hexagon Media Service"

  ; Chromium will not let an installer silently side-load an unpacked
  ; extension, and forcing one in through enterprise policy would be a
  ; security decision that is not ours to make. Opening the folder is the
  ; honest halfway point: one drag onto the extensions page finishes it.
  !define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\resources\extension"
  !define MUI_FINISHPAGE_SHOWREADME_TEXT "Open the browser extension folder"
  !define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

  !define MUI_FINISHPAGE_LINK "Open the manual"
  !define MUI_FINISHPAGE_LINK_LOCATION "$INSTDIR\resources\Hexagon-Media-Service-Manual.pdf"

  !insertmacro MUI_PAGE_FINISH
!macroend
