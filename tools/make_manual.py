"""Generate docs/Media-Downloader-Manual.pdf.

    python tools/make_manual.py

Written with reportlab so the manual regenerates from source rather than being
a binary nobody can update.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Palette taken from the app's own tokens so the manual matches the product.
INK = colors.HexColor("#1A202C")
BODY = colors.HexColor("#2C2E31")
MUTED = colors.HexColor("#484D54")
BRAND = colors.HexColor("#00AF5C")
RULE = colors.HexColor("#DDDDDD")
CODE_BG = colors.HexColor("#F4F4F3")
WARN_BG = colors.HexColor("#FDF8ED")
WARN_INK = colors.HexColor("#A44419")

MARGIN = 20 * mm


def styles():
    base = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle(
        "title", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=30, leading=34, textColor=INK, spaceAfter=4, alignment=TA_LEFT,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base["Normal"], fontSize=12.5, leading=17,
        textColor=MUTED, spaceAfter=20,
    )
    s["h1"] = ParagraphStyle(
        "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
        fontSize=17, leading=21, textColor=INK, spaceBefore=18, spaceAfter=7,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=12.5, leading=16, textColor=INK, spaceBefore=13, spaceAfter=5,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base["Normal"], fontSize=10, leading=15.5,
        textColor=BODY, spaceAfter=7,
    )
    s["muted"] = ParagraphStyle(
        "muted", parent=s["body"], fontSize=9, textColor=MUTED, spaceAfter=6,
    )
    s["code"] = ParagraphStyle(
        "code", parent=base["Code"], fontName="Courier", fontSize=9,
        leading=13, textColor=INK, backColor=CODE_BG,
        borderPadding=(7, 8, 7, 8), leftIndent=0, spaceBefore=3, spaceAfter=9,
    )
    s["warn"] = ParagraphStyle(
        "warn", parent=base["Normal"], fontSize=9.3, leading=14,
        textColor=WARN_INK, backColor=WARN_BG,
        borderPadding=(8, 9, 8, 9), spaceBefore=4, spaceAfter=10,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=base["Normal"], fontSize=9, leading=13, textColor=BODY,
    )
    s["cellhead"] = ParagraphStyle(
        "cellhead", parent=s["cell"], fontName="Helvetica-Bold", textColor=INK,
    )
    s["cellcode"] = ParagraphStyle(
        "cellcode", parent=s["cell"], fontName="Courier", fontSize=8.5,
    )
    return s


S = styles()


def para(text):
    return Paragraph(text, S["body"])


def code(text):
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(escaped.replace("\n", "<br/>"), S["code"])


def warn(text):
    return Paragraph(f"<b>Note.</b> {text}", S["warn"])


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(i, S["body"]), leftIndent=12) for i in items],
        bulletType="bullet", bulletFontSize=7, bulletOffsetY=1,
        leftIndent=13, spaceAfter=8,
    )


def steps(items):
    return ListFlowable(
        [ListItem(Paragraph(i, S["body"]), leftIndent=14) for i in items],
        bulletType="1", bulletFormat="%s.", leftIndent=16, spaceAfter=8,
    )


def table(rows, widths, code_col=None):
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, value in enumerate(row):
            if r == 0:
                style = S["cellhead"]
            elif code_col is not None and c == code_col:
                style = S["cellcode"]
            else:
                style = S["cell"]
            cells.append(Paragraph(str(value), style))
        data.append(cells)

    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CODE_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def decorate(canvas, doc):
    canvas.saveState()
    width, height = A4

    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, MARGIN - 6 * mm, width - MARGIN, MARGIN - 6 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, MARGIN - 11 * mm, "Media Downloader manual")
    canvas.drawRightString(width - MARGIN, MARGIN - 11 * mm, f"Page {doc.page}")

    if doc.page == 1:
        canvas.setFillColor(BRAND)
        canvas.rect(MARGIN, height - MARGIN - 3 * mm, 34 * mm, 2.6 * mm, stroke=0, fill=1)
    canvas.restoreState()


def build_story():
    story = []

    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("Media Downloader", S["title"]))
    story.append(Paragraph(
        "Building, installing and using the app, its engine and the browser "
        f"extension.<br/>Revised {date.today().isoformat()}.", S["subtitle"]))

    story.append(Paragraph("What this is", S["h1"]))
    story.append(para(
        "A private desktop downloader for YouTube, Reddit, Twitter/X, HDRezka and "
        "roughly 1800 other sites. Nothing is uploaded, no account is needed, and "
        "every setting stays on your machine."))
    story.append(para("It is three pieces that ship together:"))
    story.append(table([
        ["Piece", "Technology", "What it does"],
        ["Shell", "Electron", "The window and interface"],
        ["Engine", "Python", "yt-dlp, tagging, file sorting"],
        ["Extension", "Chrome MV3", "Reads HDRezka pages in your browser"],
    ], [30 * mm, 32 * mm, 78 * mm]))
    story.append(Spacer(1, 4))
    story.append(para(
        "The shell talks to the engine over a private pipe, and the engine talks to "
        "the extension over a token-protected port on 127.0.0.1. Only the interface "
        "is web technology; the downloading is all Python."))

    # ------------------------------------------------------------ prerequisites
    story.append(Paragraph("1. What you need first", S["h1"]))
    story.append(table([
        ["Requirement", "Version", "Why"],
        ["Python", "3.10 or newer", "Runs the download engine"],
        ["Node.js and npm", "18 or newer", "Runs and packages the shell"],
        ["ffmpeg", "any recent", "Merges video with audio, converts audio"],
        ["Google Chrome or Edge", "any recent", "Only needed for HDRezka"],
    ], [42 * mm, 30 * mm, 68 * mm]))
    story.append(Spacer(1, 5))
    story.append(para("Check what you already have:"))
    story.append(code("python --version\nnode --version\nffmpeg -version"))
    story.append(warn(
        "If <font face='Courier'>python</font> opens the Microsoft Store, install "
        "Python from python.org instead and tick <b>Add python.exe to PATH</b>. The "
        "Store build is sandboxed and PyInstaller cannot always read from it."))

    # -------------------------------------------------------------- installing
    story.append(Paragraph("2. Installing", S["h1"]))
    story.append(Paragraph("Engine dependencies", S["h2"]))
    story.append(code("cd \"D:\\GitHub Repos\\MediaDownloaderProject\"\n"
                      "python -m pip install -r requirements.txt"))
    story.append(Paragraph("Shell dependencies", S["h2"]))
    story.append(code("cd desktop\nnpm install"))
    story.append(warn(
        "npm 11 and newer block install scripts, so Electron's runtime download is "
        "skipped and starting it fails with <i>Electron failed to install "
        "correctly</i>. Fix it with <font face='Courier'>npm approve-scripts "
        "electron</font> followed by a reinstall. If that still fails, download "
        "<font face='Courier'>electron-v&lt;version&gt;-win32-x64.zip</font> from the "
        "Electron releases page, extract it into "
        "<font face='Courier'>node_modules/electron/dist/</font>, and put the text "
        "<font face='Courier'>electron.exe</font> into "
        "<font face='Courier'>node_modules/electron/path.txt</font>."))

    story.append(Paragraph("3. Running from source", S["h1"]))
    story.append(para("This is the normal way to use it during development:"))
    story.append(code("cd desktop\nnpm start"))
    story.append(para(
        "The window opens and the engine starts automatically as a child process. "
        "You never launch the engine yourself. Add "
        "<font face='Courier'>-- --dev</font> to open developer tools."))

    story.append(PageBreak())

    # ---------------------------------------------------------------- building
    story.append(Paragraph("4. Building executables", S["h1"]))
    story.append(para(
        "There are two builds. The engine is frozen with PyInstaller, then the shell "
        "is packaged with electron-builder and the engine is bundled inside it."))

    story.append(Paragraph("Step one: freeze the engine", S["h2"]))
    story.append(code(
        "cd \"D:\\GitHub Repos\\MediaDownloaderProject\"\n"
        "python -m PyInstaller Engine.spec --noconfirm ^\n"
        "  --distpath dist-engine --workpath build-engine"))
    story.append(para(
        "Produces <font face='Courier'>dist-engine\\mediadl-engine.exe</font>. It is "
        "a console-less program that speaks JSON over its input and output, so "
        "double-clicking it does nothing visible. That is expected."))

    story.append(Paragraph("Step two: package the shell", S["h2"]))
    story.append(code("cd desktop\nnpm run dist"))
    story.append(para(
        "Produces an installer and a portable build in "
        "<font face='Courier'>dist-desktop\\</font>. electron-builder copies "
        "<font face='Courier'>dist-engine</font> into the app's resources, and the "
        "shell prefers that frozen engine over your Python install when it finds it."))

    story.append(Paragraph("Optional: the icon", S["h2"]))
    story.append(code("python tools\\make_icon.py"))
    story.append(para(
        "Regenerates <font face='Courier'>mediadl\\resources\\app.ico</font> from the "
        "logo at seven sizes. Only needed if you change the mark."))

    story.append(Paragraph("Build reference", S["h2"]))
    story.append(table([
        ["Command", "Output"],
        ["python -m PyInstaller Engine.spec", "dist-engine\\mediadl-engine.exe"],
        ["npm run dist", "dist-desktop\\ installer and portable"],
        ["python tools\\make_icon.py", "mediadl\\resources\\app.ico"],
        ["python tools\\make_manual.py", "docs\\Media-Downloader-Manual.pdf"],
    ], [78 * mm, 62 * mm], code_col=0))

    story.append(warn(
        "A running copy locks its own executable, so a rebuild fails with a "
        "permission error that looks unrelated. Close the app first. The PowerShell "
        "build script does this for you."))

    # -------------------------------------------------------------- extension
    story.append(Paragraph("5. Installing the browser extension", S["h1"]))
    story.append(para(
        "Only needed for HDRezka. The site refuses requests that do not come from a "
        "real browser, so the page is read inside yours; the extension is the bridge "
        "between that page and the app."))
    story.append(steps([
        "Open <font face='Courier'>chrome://extensions</font> and turn on "
        "<b>Developer mode</b> (top right).",
        "Click <b>Load unpacked</b> and choose the "
        "<font face='Courier'>extension</font> folder in the project.",
        "Start the app, then go to <b>Download &rarr; HDRezka</b>. It shows an "
        "address and a pairing token.",
        "Click <b>Copy token</b>, then open the extension's <b>Options</b>, paste it, "
        "and press <b>Save and test</b>.",
        "You should see <i>Connected</i>. The app's HDRezka tab turns green too.",
    ]))
    story.append(warn(
        "The token is what stops any web page you visit from talking to the app. It "
        "is generated once and kept in your settings folder. The extension only ever "
        "contacts 127.0.0.1, never the internet."))

    story.append(PageBreak())

    # ------------------------------------------------------------------ using
    story.append(Paragraph("6. Using it", S["h1"]))

    story.append(Paragraph("Downloading from YouTube and most sites", S["h2"]))
    story.append(steps([
        "Go to the <b>Download</b> tab and pick <b>Auto detect</b> or <b>YouTube</b>.",
        "Paste one or more links, one per line. Playlists and channels expand into "
        "separate queue items on their own.",
        "Choose the mode, quality and container.",
        "Set the destination folder, then press <b>Add to queue</b>.",
    ]))
    story.append(para(
        "The view switches to <b>Queue</b>, where each item shows progress, speed and "
        "remaining time, with pause, resume, retry and reveal-in-folder controls."))

    story.append(Paragraph("The window", S["h2"]))
    story.append(para(
        "The app draws its own titlebar, so the window controls sit at the right of "
        "the top bar rather than in a separate strip. Drag the empty area to move "
        "the window, and double-click it to maximise. <b>F11</b> toggles fullscreen "
        "and <b>Esc</b> leaves it; the middle button changes to an inward-arrow icon "
        "while fullscreen, and pressing it returns to a normal window."))

    story.append(Paragraph("Downloading from HDRezka", S["h2"]))
    story.append(steps([
        "Open the film or series page in your browser and leave the tab open.",
        "In the app, go to <b>Download &rarr; HDRezka</b> and press "
        "<b>Read open HDRezka tab</b>.",
        "Pick the translation (dub) and quality. Both come from the page itself.",
        "Tick what you want in the season tree. Each season expands to its episodes, "
        "and the season checkbox selects the whole season.",
        "Press <b>Download</b>. Progress appears in the <b>Queue</b> tab.",
    ]))
    story.append(para("Selection shortcuts in the tree:"))
    story.append(bullets([
        "<b>Select all</b> ticks every episode of every season.",
        "<b>Clear</b> unticks everything.",
        "The range box accepts <font face='Courier'>1-10</font> or "
        "<font face='Courier'>3,5,7</font>, and applies to whichever seasons are "
        "expanded, or all of them if none are.",
        "A part-selected season shows a dash rather than a tick, with a "
        "<font face='Courier'>3 / 21</font> count beside it.",
    ]))
    story.append(warn(
        "HDRezka files are fetched by the browser, so they land in your Downloads "
        "folder first and the app moves them to the real destination when each one "
        "finishes. Chrome will not let an extension write anywhere else. Nothing is "
        "left behind; the staging folder is a waypoint."))

    story.append(Paragraph("Size checks and batching", S["h2"]))
    story.append(para(
        "Before anything starts, one episode is measured and multiplied by how many "
        "you selected. The figure is approximate but close, because episodes of a "
        "series are similar sizes."))
    story.append(para(
        "That total is compared against free space on the drive the browser downloads "
        "to. If a whole season would not fit, the work is split into batches "
        "automatically: a batch downloads, those files are moved to the destination, "
        "and only then does the next batch start. The staging drive therefore never "
        "holds more than one batch at a time. The Queue heading shows which batch is "
        "running and how many of its files have been filed."))

    story.append(Paragraph("What the queue is telling you", S["h2"]))
    story.append(para(
        "A browser download passes through several stages, and each one is named in "
        "the queue so a slow step is never mistaken for a broken one:"))
    story.append(table([
        ["Stage", "Meaning"],
        ["Downloading in browser", "Chrome is fetching the file. Progress is real."],
        ["Waiting for the browser to release the file",
         "The transfer finished but Chrome still holds the file. The app is checking "
         "it has stopped growing and matches the expected size."],
        ["Moving to destination",
         "Copying from the Downloads folder to your chosen folder. Progress is real. "
         "A large file across drives takes a while; this is normal."],
        ["Writing tags", "Adding title, show, season and episode metadata."],
        ["Completed", "The file is in place and verified."],
    ], [50 * mm, 90 * mm]))
    story.append(warn(
        "A file is only ever deleted from the staging folder after the copy has been "
        "verified byte for byte. If a move fails the original is left untouched, so "
        "nothing is lost. A half-written file is never left where a finished one "
        "should be."))

    story.append(Paragraph("Where files end up", S["h2"]))
    story.append(para("Series are filed by show and season:"))
    story.append(code(
        "D:\\Movies\\House M.D\\\n"
        "  House M.D.\\\n"
        "    Season 06\\\n"
        "      House M.D. 6x20 LostFilm.mp4\n"
        "      House M.D. 6x21 LostFilm.mp4"))
    story.append(para(
        "The name pattern is <font face='Courier'>show season x episode dub</font>. "
        "The dub is dropped when unknown, and the show prefers the page's original "
        "title when it has one. Change the pattern in <b>Settings</b>; a broken "
        "pattern falls back to a safe default rather than failing."))

    story.append(Paragraph("Settings worth knowing", S["h2"]))
    story.append(table([
        ["Setting", "What it does"],
        ["Simultaneous downloads", "How many run at once. Three is a sensible default."],
        ["Season folders", "Turn off to keep every episode in one flat folder."],
        ["Expand playlists", "Off means a playlist becomes one item, not many."],
        ["Use cookies from", "For age-restricted or members-only videos."],
        ["Download in chunks", "Leave on. Prevents long transfers dying at HTTP 403."],
        ["Strict container matching", "Leave off. A known cause of HTTP 403 on YouTube."],
    ], [46 * mm, 94 * mm]))

    story.append(PageBreak())

    # ---------------------------------------------------------- troubleshooting
    story.append(Paragraph("7. When something goes wrong", S["h1"]))
    story.append(para(
        "The <b>Logs</b> tab shows what the app and yt-dlp actually did, filterable "
        "by level and text. The same content is written to a rotating file:"))
    story.append(code("%APPDATA%\\MediaDownloader\\mediadl.log"))

    story.append(Paragraph("Common problems", S["h2"]))
    story.append(table([
        ["Symptom", "Cause and fix"],
        ["<i>Requested format is not available</i> on a video that plays fine",
         "yt-dlp is out of date. Run "
         "<font face='Courier'>python -m pip install --upgrade yt-dlp</font> "
         "and rebuild the engine."],
        ["Every download fails right after enabling cookies",
         "Chrome locks its cookie database while running. Close Chrome, or set "
         "<b>Use cookies from</b> back to None. The app warns and carries on "
         "without them."],
        ["HTTP 403 partway through a large download",
         "The media URL expired. It retries automatically. Keep <b>Download in "
         "chunks</b> on and <b>Strict container matching</b> off."],
        ["<i>Could not establish connection</i> from the extension",
         "The content script is not in that tab. Reload the extension at "
         "chrome://extensions, then reload the HDRezka tab once."],
        ["<i>This does not look like a HDRezka title page</i>",
         "You are on a listing or search page rather than a title, or the site "
         "changed its markup."],
        ["HDRezka returns an anti-bot page",
         "Open the title in your browser and let its check pass, then use the "
         "extension. The app cannot get past it on its own, by design."],
        ["Nothing downloads and the engine dot is red",
         "The engine did not start. Check Python is on PATH and the requirements "
         "are installed."],
        ["A download sits on <i>Moving to destination</i> for a long time",
         "It is copying between drives, which is a real copy rather than a rename. "
         "The percentage moves; leave it. Nothing is deleted until the copy is "
         "verified."],
        ["<i>Size mismatch</i> in the log and the file was not filed",
         "The browser transfer ended early. The partial file is deliberately left "
         "in the staging folder rather than filed as if it were complete. Download "
         "that episode again."],
    ], [50 * mm, 90 * mm]))

    story.append(Paragraph("Where things live", S["h2"]))
    story.append(table([
        ["What", "Where"],
        ["Settings", "%APPDATA%\\MediaDownloader\\settings.json"],
        ["Log file", "%APPDATA%\\MediaDownloader\\mediadl.log"],
        ["Pairing token", "%APPDATA%\\MediaDownloader\\bridge-token.txt"],
        ["History", "%APPDATA%\\MediaDownloader\\history.json"],
        ["Browser staging", "Downloads\\MediaDownloader\\"],
    ], [38 * mm, 102 * mm], code_col=1))

    story.append(Paragraph("8. Keeping it working", S["h1"]))
    story.append(para(
        "Sites change their players constantly, so yt-dlp goes stale faster than "
        "anything else here. When downloads that used to work start failing, update "
        "it first:"))
    story.append(code("python -m pip install --upgrade yt-dlp"))
    story.append(para(
        "Then rebuild the engine so the packaged app picks it up. The version in use "
        "is shown in the app's <b>Settings</b> panel under About."))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Download only what you have the right to download.", S["muted"]))

    return story


def main() -> int:
    out = ROOT / "docs" / "Media-Downloader-Manual.pdf"
    out.parent.mkdir(exist_ok=True)

    doc = BaseDocTemplate(
        str(out), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 4 * mm,
        title="Media Downloader manual",
        author="Media Downloader",
        subject="Building, installing and using Media Downloader",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="body",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=decorate)])
    doc.build(build_story())

    print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
