Screenshots for the project page.
=================================

All four are captures of the real window at 1240x860, its default size, taken
from the packaged build rather than a development run so the version label and
the update card are the ones a user actually sees.

  download-dark.png   1240x860   hero image on the page
  queue-dark.png      1240x860   one download running, four finished
  settings-dark.png   1240x860   Downloads, Network and Updates cards
  hdrezka-dark.png    1240x642   cropped: see the warning below

How they were taken
-------------------

1. Build, then run build-output/win-unpacked/"Hexagon Media Service.exe" with
   APPDATA pointed at a scratch folder:

     $env:APPDATA = "C:\some\scratch"

   That gives the app a clean profile, so no personal download path, history or
   pairing token appears in the image, and the real settings are left alone.

2. Set the destination to something neutral (D:\Movies was used here) and, for
   the queue shot, set a speed limit in Settings so a download is still running
   when the shutter goes. 900 KB/s against a 166 MB video leaves about three
   minutes of visible progress.

3. Capture the window bounds rather than the screen. Cropping a full-screen
   grab leaves a rim of desktop, and PrintWindow returns an empty image for a
   GPU-composited Electron window. Capturing the DWM extended frame bounds with
   Graphics.CopyFromScreen is what works.

Do not photograph the pairing token
-----------------------------------

The Browser bridge card on the HDRezka tab prints the token that authorises the
local HTTP server. hdrezka-dark.png is cropped to 642px for exactly that reason.
If you retake it, crop it again.

Worth refreshing after the first release
----------------------------------------

settings-dark.png currently reads "No release has been published yet", which is
true while the repository is private and has no release. Once a release exists
the same card reads "This is the newest release", or offers the update. Retake
it then.

The downloads used here are Blender open movies (Big Buck Bunny, Sintel), which
are CC-BY, so the screenshots can be published. The files were deleted after.
