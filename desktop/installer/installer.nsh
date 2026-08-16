; Extra installer behaviour on top of electron-builder's NSIS defaults.
;
; The goal is an installer that explains itself: a welcome page, the licence
; and component summary, a directory choice, and a finish page that offers to
; open the manual rather than just vanishing.

!macro customHeader
  ; Shown in the installer's window title and Add/Remove Programs.
  BrandingText "Media Downloader ${VERSION}"
!macroend

!macro customWelcomePage
  !define MUI_WELCOMEPAGE_TITLE "Install Media Downloader"
  !define MUI_WELCOMEPAGE_TEXT   "This will install Media Downloader ${VERSION} on your computer.$\r$\n$\r$\nIt downloads from YouTube, HDRezka, Reddit, Twitter and around 1800 other sites. Everything runs locally: no account, no telemetry, nothing uploaded.$\r$\n$\r$\nThe download engine is bundled, so Python is not required. ffmpeg is needed separately for merging and audio conversion.$\r$\n$\r$\nClose Media Downloader if it is running, then click Next."
  !insertmacro MUI_PAGE_WELCOME
!macroend

!macro customInstall
  ; A running copy would keep its own files locked and produce a confusing
  ; failure part-way through.
  DetailPrint "Checking for a running copy..."
  nsExec::Exec 'taskkill /IM "Media Downloader.exe" /F'
  Pop $0
  nsExec::Exec 'taskkill /IM "mediadl-engine.exe" /F'
  Pop $0

  DetailPrint "Installed to: $INSTDIR"
  DetailPrint "Settings will be stored in: $APPDATA\MediaDownloader"
!macroend

!macro customUnInstall
  DetailPrint "Stopping Media Downloader..."
  nsExec::Exec 'taskkill /IM "Media Downloader.exe" /F'
  Pop $0
  nsExec::Exec 'taskkill /IM "mediadl-engine.exe" /F'
  Pop $0
  DetailPrint "Your settings in $APPDATA\MediaDownloader have been left in place."
!macroend

!macro customFinishPage
  !define MUI_FINISHPAGE_TITLE "Media Downloader is installed"
  !define MUI_FINISHPAGE_TEXT  "Media Downloader ${VERSION} has been installed.$\r$\n$\r$\nTo download from HDRezka you also need the browser extension. The manual explains how to install and pair it, and covers everything else."

  !define MUI_FINISHPAGE_RUN "$INSTDIR\Media Downloader.exe"
  !define MUI_FINISHPAGE_RUN_TEXT "Start Media Downloader"

  !define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\resources\Media-Downloader-Manual.pdf"
  !define MUI_FINISHPAGE_SHOWREADME_TEXT "Open the manual"
  !define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

  !insertmacro MUI_PAGE_FINISH
!macroend
