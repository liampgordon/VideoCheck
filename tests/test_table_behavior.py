import csv

from PyQt5.QtCore import Qt

import videocheck_qt
from videocheck_qt import VideoCheckWindow

ALPHA = "/tmp/videos/alpha.mp4"
BETA = "/tmp/videos/beta.mp4"


def fake_metadata(path, name, size="10.00 MB", size_bytes=10_000_000):
    return {
        "Path": path, "Name": name, "Size": size, "FPS": "23.98",
        "Duration": "00:01:00:00", "Resolution": "1920 x 1080",
        "Aspect Ratio": "16:9", "Video Codec": "prores",
        "Color Space": "bt709", "Audio Codec": "pcm_s16le",
        "Channels": "2", "Peak dB": "-3.0 dB",
        "_sort": {"Size": size_bytes, "FPS": 23.98, "Duration": 60.0,
                  "Channels": 2, "Peak dB": -3.0},
    }


FAKE_META = {
    ALPHA: fake_metadata(ALPHA, "alpha.mp4"),
    BETA: fake_metadata(BETA, "beta.mp4"),
}


def make_window(qtbot, monkeypatch, paths, meta=None):
    meta = meta or FAKE_META
    monkeypatch.setattr(videocheck_qt, "get_metadata", lambda p: meta[p])
    window = VideoCheckWindow()
    qtbot.addWidget(window)
    window.process_files(paths)
    qtbot.waitUntil(lambda: window.table.rowCount() == len(paths) and all(
        window.table.item(r, 1) is not None for r in range(len(paths))
    ))
    return window


def displayed_names(window):
    return [window.table.item(r, 0).text() for r in range(window.table.rowCount())]


def test_open_in_finder_targets_displayed_file_after_sort(qtbot, monkeypatch):
    window = make_window(qtbot, monkeypatch, [ALPHA, BETA])
    window.table.sortItems(0, Qt.AscendingOrder)
    assert displayed_names(window) == ["alpha.mp4", "beta.mp4"]

    window.table.selectRow(0)
    captured = {}
    monkeypatch.setattr(
        videocheck_qt.subprocess, "run",
        lambda args, **kwargs: captured.setdefault("args", args),
    )
    window.open_selected_in_finder()
    assert captured["args"][-1] == ALPHA


def test_csv_export_matches_displayed_order_after_sort(qtbot, monkeypatch, tmp_path):
    window = make_window(qtbot, monkeypatch, [ALPHA, BETA])
    window.table.sortItems(0, Qt.AscendingOrder)
    assert displayed_names(window) == ["alpha.mp4", "beta.mp4"]

    out = tmp_path / "out.csv"
    monkeypatch.setattr(
        videocheck_qt.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "")),
    )
    window.export_to_csv()

    with open(out) as f:
        rows = list(csv.reader(f))
    assert rows[0] == window.headers
    assert [r[0] for r in rows[1:]] == ["alpha.mp4", "beta.mp4"]


def test_size_column_sorts_numerically(qtbot, monkeypatch):
    meta = {
        ALPHA: fake_metadata(ALPHA, "alpha.mp4", "100.00 MB", 100_000_000),
        BETA: fake_metadata(BETA, "beta.mp4", "9.50 MB", 9_500_000),
    }
    window = make_window(qtbot, monkeypatch, [ALPHA, BETA], meta)

    size_col = window.headers.index("Size")
    window.table.sortItems(size_col, Qt.AscendingOrder)
    sizes = [window.table.item(r, size_col).text() for r in range(2)]
    assert sizes == ["9.50 MB", "100.00 MB"]


def test_backspace_deletes_selected_row(qtbot, monkeypatch):
    window = make_window(qtbot, monkeypatch, [ALPHA, BETA])
    window.table.sortItems(0, Qt.AscendingOrder)
    window.table.selectRow(0)
    qtbot.keyClick(window.table, Qt.Key_Backspace)
    assert displayed_names(window) == ["beta.mp4"]
    assert window.status_bar.currentMessage() == "Video Count: 1"


def test_delete_key_deletes_selected_row(qtbot, monkeypatch):
    window = make_window(qtbot, monkeypatch, [ALPHA, BETA])
    window.table.sortItems(0, Qt.AscendingOrder)
    window.table.selectRow(1)
    qtbot.keyClick(window.table, Qt.Key_Delete)
    assert displayed_names(window) == ["alpha.mp4"]
    assert window.status_bar.currentMessage() == "Video Count: 1"
