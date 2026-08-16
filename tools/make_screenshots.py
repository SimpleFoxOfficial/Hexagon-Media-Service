"""Render documentation screenshots into docs/.

    python tools/make_screenshots.py

Populates the queue with representative sample jobs (nothing is downloaded)
and captures each screen in both light and dark.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SAMPLES = [
    ("Big Buck Bunny 60fps 4K - Blender Foundation", "YouTube", "DOWNLOADING", 62.4),
    ("Lo-fi beats to relax and study to", "YouTube Music", "PROCESSING", 100.0),
    ("r/videos - the cat does a backflip", "Reddit", "DONE", 100.0),
    ("Breaking Bad S01E02", "HDRezka", "QUEUED", 0.0),
    ("Post that no longer exists", "Twitter", "FAILED", 12.0),
    ("Documentary, paused for later", "Vimeo", "PAUSED", 38.0),
]


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from mediadl.config import Preset, Settings
    from mediadl.core.job import Job, JobState
    from mediadl.ui import fonts
    from mediadl.ui.main_window import MainWindow

    app = QApplication([])
    app.setStyle("Fusion")
    fonts.load_bundled_fonts()

    settings = Settings()
    window = MainWindow(settings)
    window.resize(1180, 820)
    window.show()
    app.processEvents()

    # Keep the queue static: these are illustrations, not real downloads.
    window.manager._paused = True
    jobs = []
    for title, source, state, progress in SAMPLES:
        job = Job(url="https://example.com/sample", preset=Preset())
        job.title, job.source = title, source
        job.state, job.progress = JobState[state], progress
        job.total_bytes = 120_000_000
        job.downloaded_bytes = int(job.total_bytes * progress / 100)
        if job.state is JobState.DOWNLOADING:
            job.speed, job.eta = 3_400_000, 73
        if job.state is JobState.FAILED:
            job.error = "HTTP Error 404: the post was removed"
        if job.state is JobState.DONE:
            job.filepath = str(Path.home() / "Downloads" / "Video" / "backflip.mp4")
        jobs.append(job)
    window.manager.add_jobs(jobs)
    app.processEvents()

    out = ROOT / "docs"
    out.mkdir(exist_ok=True)

    for mode in ("dark", "light"):
        settings.appearance.theme_mode = mode
        window.apply_theme()
        for index, name in ((0, "download"), (1, "queue"), (2, "settings"), (3, "about")):
            window._select(index)
            for _ in range(3):
                app.processEvents()
            target = out / f"screenshot-{mode}.png" if name == "queue" else out / f"{name}-{mode}.png"
            window.grab().save(str(target))
            print(f"wrote {target.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
