import sys
import os
import shutil
import subprocess
import ffmpeg
from fractions import Fraction
import csv
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidgetItem,
    QVBoxLayout, QWidget, QFileDialog, QPushButton, QHBoxLayout,
    QAction, QMenuBar, QMessageBox, QStatusBar, QTableWidget, QHeaderView,
    QLabel, QButtonGroup
)
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject, QTimer, QSize
from PyQt5.QtGui import QKeyEvent, QFont, QImage, QPixmap, QIcon

# Dynamically determine FFMPEG path for bundled or unbundled execution.
# Prefer a bundled binary sitting next to the app, but fall back to whatever
# ffmpeg is on the PATH so the audio/thumbnail features work from source too.
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

def _resolve_ffmpeg():
    bundled = os.path.join(base_path, "ffmpeg")
    if os.path.exists(bundled):
        return bundled
    return shutil.which("ffmpeg") or "ffmpeg"

FFMPEG_PATH = _resolve_ffmpeg()

APP_VERSION = "v2.1"
APP_AUTHOR = "© 2026 Liam P. Gordon"

# Thumbnails are generated once at this pixel height, then scaled down for
# display so switching between S/M/L view sizes stays crisp and instant.
THUMB_SOURCE_HEIGHT = 160

# (icon height, row height) for the Small / Medium / Large view modes.
# Small keeps a compact thumbnail so a visual reference is always available.
VIEW_SIZES = {
    "S": (28, 38),
    "M": (52, 60),
    "L": (104, 116),
}

def parse_frame_rate(rate):
    try:
        return float(Fraction(rate))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0

def parse_db(value):
    try:
        return float(str(value).split()[0])
    except (ValueError, IndexError):
        return None

def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def get_aspect_ratio(width, height):
    try:
        if width > height:
            ratio = Fraction(width, height).limit_denominator(10)
        else:
            ratio = Fraction(height, width).limit_denominator(10)
            ratio = Fraction(ratio.denominator, ratio.numerator)
        return f"{ratio.numerator}:{ratio.denominator}"
    except:
        return "N/A"

def format_hmsf(seconds, fps):
    try:
        total_frames = int(seconds * fps)
        h = total_frames // (3600 * int(fps))
        m = (total_frames % (3600 * int(fps))) // (60 * int(fps))
        s = (total_frames % (60 * int(fps))) // int(fps)
        f = total_frames % int(fps)
        return f"{h:02}:{m:02}:{s:02}:{f:02}"
    except:
        return "N/A"

def format_size(bytes):
    return f"{bytes / 1e6:.2f} MB"

def format_bitrate(bits_per_sec):
    if bits_per_sec is None:
        return "N/A"
    mbps = bits_per_sec / 1e6
    if mbps >= 1:
        return f"{mbps:.1f} Mbps"
    return f"{bits_per_sec / 1e3:.0f} kbps"

def get_peak_db(file_path):
    try:
        result = subprocess.run([
            FFMPEG_PATH, "-i", file_path,
            "-af", "volumedetect",
            "-vn", "-sn", "-dn",
            "-f", "null", "-"
        ], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        for line in result.stderr.split('\n'):
            if "max_volume" in line:
                return line.strip().split(":")[1].strip()
    except Exception as e:
        print(f"⚠️ Volume scan failed: {e}")
    return "N/A"

def generate_thumbnail(file_path, height=THUMB_SOURCE_HEIGHT):
    """Grab a representative frame and return it as a QImage (or None)."""
    for seek in ("1", "0"):
        try:
            result = subprocess.run([
                FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
                "-ss", seek, "-i", file_path,
                "-frames:v", "1",
                "-vf", f"scale=-2:{height}",
                "-f", "image2pipe", "-vcodec", "mjpeg", "-"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if result.stdout:
                image = QImage()
                if image.loadFromData(result.stdout) and not image.isNull():
                    return image
        except Exception as e:
            print(f"⚠️ Thumbnail failed on {file_path}: {e}")
    return None

def get_metadata(file_path):
    try:
        probe = ffmpeg.probe(file_path)
        format_info = probe.get('format', {})
        video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), {})
        audio_stream = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), {})

        width = video_stream.get('width')
        height = video_stream.get('height')
        fps = parse_frame_rate(video_stream.get('r_frame_rate'))
        duration_raw = float(format_info.get('duration', 0))
        duration = format_hmsf(duration_raw, fps) if fps else "N/A"

        color_space = (
            video_stream.get('color_space') or
            video_stream.get('color_primaries') or
            video_stream.get('color_transfer') or
            "N/A"
        )

        bitrate_num = parse_int(format_info.get('bit_rate'))
        size_bytes = os.path.getsize(file_path)
        peak_db = get_peak_db(file_path)

        metadata = {
            "Path": file_path,
            "Name": os.path.basename(file_path),
            "Size": format_size(size_bytes),
            "Bit Rate": format_bitrate(bitrate_num),
            "FPS": f"{fps:.2f}" if fps else "N/A",
            "Duration": duration,
            "Resolution": f"{width} x {height}" if width and height else "N/A",
            "Aspect Ratio": get_aspect_ratio(width, height),
            "Video Codec": video_stream.get('codec_name') or "N/A",
            "Color Space": color_space,
            "Audio Codec": audio_stream.get('codec_name') or "N/A",
            "Channels": str(audio_stream.get('channels')) if audio_stream.get('channels') is not None else "N/A",
            "Peak dB": peak_db,
            "_sort": {
                "Size": size_bytes,
                "Bit Rate": bitrate_num,
                "FPS": fps,
                "Duration": duration_raw,
                "Channels": audio_stream.get('channels'),
                "Peak dB": parse_db(peak_db),
            },
        }
        return metadata
    except Exception as e:
        print(f"⚠️ ffprobe failed on: {file_path} → {e}")
        return {
            "Path": file_path,
            "Name": os.path.basename(file_path),
            "Size": "Error",
            "Bit Rate": "-",
            "FPS": "-", "Duration": "-", "Resolution": "-", "Aspect Ratio": "-",
            "Video Codec": "-", "Color Space": "-", "Audio Codec": "-",
            "Channels": "-", "Peak dB": "-"
        }

SORT_KEY_ROLE = Qt.UserRole + 1

STYLESHEET = """
QMainWindow, QWidget {
    background-color: #f4f4f6;
    color: #1d1d1f;
}
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f7f7f9;
    border: 1px solid #e2e2e6;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #0a84ff;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
QHeaderView::section {
    background-color: #eeeef1;
    color: #55555c;
    padding: 7px 10px;
    border: none;
    border-right: 1px solid #e2e2e6;
    font-weight: 600;
}
QHeaderView::section:last {
    border-right: none;
}
QTableCornerButton::section {
    background-color: #eeeef1;
    border: none;
}
QPushButton {
    background-color: #ffffff;
    border: 1px solid #d3d3d8;
    border-radius: 7px;
    padding: 7px 16px;
    color: #1d1d1f;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #f0f0f3;
}
QPushButton:pressed {
    background-color: #e3e3e8;
}
QPushButton#primary {
    background-color: #0a84ff;
    border: none;
    color: #ffffff;
}
QPushButton#primary:hover {
    background-color: #0a78e6;
}
QPushButton#primary:pressed {
    background-color: #0969c9;
}
QPushButton#segment {
    background-color: #ffffff;
    border: 1px solid #d3d3d8;
    border-radius: 0px;
    padding: 6px 14px;
    min-width: 18px;
}
QPushButton#segment:checked {
    background-color: #0a84ff;
    border-color: #0a84ff;
    color: #ffffff;
}
QLabel#emptyHint {
    color: #a0a0a8;
    font-size: 15px;
}
QLabel#viewLabel {
    color: #77777f;
    font-weight: 500;
}
QStatusBar {
    color: #6a6a72;
}
QStatusBar::item {
    border: none;
}
QScrollBar:horizontal {
    height: 11px;
    background: transparent;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #c2c2ca;
    border-radius: 5px;
    min-width: 36px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #a6a6b0;
}
QScrollBar:vertical {
    width: 11px;
    background: transparent;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #c2c2ca;
    border-radius: 5px;
    min-height: 36px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #a6a6b0;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0px;
    height: 0px;
    background: none;
    border: none;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""

class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        a = self.data(SORT_KEY_ROLE)
        b = other.data(SORT_KEY_ROLE)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)

class WorkerSignals(QObject):
    result = pyqtSignal(str, dict)  # emits (file_path, metadata)

class MetadataWorker(QRunnable):
    def __init__(self, file_path, signal):
        super().__init__()
        self.file_path = file_path
        self.signals = signal

    def run(self):
        metadata = get_metadata(self.file_path)
        self.signals.result.emit(self.file_path, metadata)

class ThumbnailSignals(QObject):
    result = pyqtSignal(str, QImage)  # emits (file_path, thumbnail image)

class ThumbnailWorker(QRunnable):
    def __init__(self, file_path, signal):
        super().__init__()
        self.file_path = file_path
        self.signals = signal

    def run(self):
        image = generate_thumbnail(self.file_path)
        if image is not None:
            self.signals.result.emit(self.file_path, image)

class VideoCheckTable(QTableWidget):
    rowsDeleted = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_hint = QLabel(
            "Drag & drop video files here\n\nor use “Browse Files”",
            self.viewport(),
        )
        self.empty_hint.setObjectName("emptyHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setAttribute(Qt.WA_TransparentForMouseEvents)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.empty_hint.resize(self.viewport().size())

    def update_empty_hint(self):
        self.empty_hint.resize(self.viewport().size())
        self.empty_hint.setVisible(self.rowCount() == 0)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for index in sorted(set(i.row() for i in self.selectedIndexes()), reverse=True):
                self.removeRow(index)
            self.rowsDeleted.emit()
        else:
            super().keyPressEvent(event)

class VideoCheckWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoCheck")
        self.setAcceptDrops(True)
        self.resize(1360, 640)

        self.threadpool = QThreadPool()
        self.thumbnails = {}  # file_path -> QIcon, so view-size changes reuse them
        self.headers = [
            "Name", "Resolution", "Aspect Ratio", "Duration", "FPS",
            "Video Codec", "Size", "Bit Rate", "Color Space",
            "Audio Codec", "Channels", "Peak dB"
        ]

        self.table = VideoCheckTable(0, len(self.headers))
        self.table.rowsDeleted.connect(self.update_status)
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        default_widths = {
            "Name": 300, "Resolution": 110, "Aspect Ratio": 95,
            "Duration": 115, "FPS": 70, "Video Codec": 100, "Size": 95,
            "Bit Rate": 95, "Color Space": 110, "Audio Codec": 105,
            "Channels": 80, "Peak dB": 85,
        }
        for i, name in enumerate(self.headers):
            self.table.setColumnWidth(i, default_widths.get(name, 100))
        # Let the Name column absorb any free width (it holds the thumbnail
        # and filename, so it benefits most); the rest stay manually resizable.
        header.setSectionResizeMode(0, QHeaderView.Stretch)

        browse_button = QPushButton("Browse Files")
        browse_button.setObjectName("primary")
        browse_button.clicked.connect(self.open_file_dialog)

        open_button = QPushButton("Open in Finder")
        open_button.clicked.connect(self.open_selected_in_finder)

        export_button = QPushButton("Export to CSV")
        export_button.clicked.connect(self.export_to_csv)

        clear_button = QPushButton("Clear Table")
        clear_button.clicked.connect(self.clear_table)

        # Segmented S / M / L control for row height + thumbnail size.
        view_label = QLabel("View")
        view_label.setObjectName("viewLabel")
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        segment_row = QHBoxLayout()
        segment_row.setSpacing(0)
        for mode in ("S", "M", "L"):
            btn = QPushButton(mode)
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, m=mode: self.set_view_size(m))
            self.view_group.addButton(btn)
            segment_row.addWidget(btn)
            if mode == "M":
                btn.setChecked(True)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(browse_button)
        buttons.addWidget(open_button)
        buttons.addWidget(export_button)
        buttons.addWidget(clear_button)
        buttons.addStretch()
        buttons.addWidget(view_label)
        buttons.addLayout(segment_row)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(buttons)
        layout.addWidget(self.table)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        menubar = self.menuBar()
        help_menu = menubar.addMenu('Help')
        about_action = QAction('About VideoCheck', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        self.set_view_size("M")
        self.update_status()

    def show_about(self):
        QMessageBox.about(self, "About VideoCheck",
                          f"VideoCheck {APP_VERSION}\n{APP_AUTHOR}\nAll rights reserved.")

    def update_status(self):
        self.status_bar.showMessage(f"Video Count: {self.table.rowCount()}")
        self.table.update_empty_hint()

    def set_view_size(self, mode):
        self.view_mode = mode
        icon_h, row_h = VIEW_SIZES[mode]
        if icon_h:
            self.table.setIconSize(QSize(int(icon_h * 16 / 9), icon_h))
        else:
            self.table.setIconSize(QSize(0, 0))
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, row_h)

    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Video Files", "",
                                                "Videos (*.mp4 *.mov *.mkv *.avi)")
        if files:
            self.process_files(files)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = list({u.toLocalFile() for u in urls})
        self.process_files(files)

    def process_files(self, file_paths):
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        row_h = VIEW_SIZES[getattr(self, "view_mode", "M")][1]
        for file_path in file_paths:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            self.table.setRowHeight(row_index, row_h)
            name_item = QTableWidgetItem(os.path.basename(file_path))
            name_item.setData(Qt.UserRole, file_path)
            self.table.setItem(row_index, 0, name_item)

            signal = WorkerSignals()
            signal.result.connect(self.update_row_metadata)
            worker = MetadataWorker(file_path, signal)
            self.threadpool.start(worker)

            thumb_signal = ThumbnailSignals()
            thumb_signal.result.connect(self.update_row_thumbnail)
            thumb_worker = ThumbnailWorker(file_path, thumb_signal)
            self.threadpool.start(thumb_worker)
        self.table.setSortingEnabled(sorting)
        self.update_status()

    def update_row_metadata(self, file_path, metadata):
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if (item and item.data(Qt.UserRole) == file_path
                    and self.table.item(row, 1) is None):
                sort_keys = metadata.get("_sort", {})
                for i, key in enumerate(self.headers):
                    cell = SortableItem(str(metadata.get(key, "-")))
                    sort_key = sort_keys.get(key)
                    if sort_key is not None:
                        cell.setData(SORT_KEY_ROLE, sort_key)
                    if i == 0:
                        cell.setData(Qt.UserRole, file_path)
                        if file_path in self.thumbnails:
                            cell.setIcon(self.thumbnails[file_path])
                    self.table.setItem(row, i, cell)
                break
        self.table.setSortingEnabled(sorting)
        self.update_status()

    def update_row_thumbnail(self, file_path, image):
        icon = QIcon(QPixmap.fromImage(image))
        self.thumbnails[file_path] = icon
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == file_path:
                item.setIcon(icon)

    def path_for_row(self, row):
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def open_selected_in_finder(self):
        selected = self.table.currentRow()
        path = self.path_for_row(selected) if selected != -1 else None
        if path:
            subprocess.run(["open", "-R", path])

    def export_to_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV files (*.csv)")
        if file_path:
            with open(file_path, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(self.headers)
                for row in range(self.table.rowCount()):
                    writer.writerow([
                        self.table.item(row, col).text() if self.table.item(row, col) else ''
                        for col in range(len(self.headers))
                    ])

    def clear_table(self):
        self.table.setRowCount(0)
        self.thumbnails.clear()
        self.update_status()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    # Use the native system UI font, just a touch larger for a modern feel.
    base_font = app.font()
    base_font.setPointSize(12)
    app.setFont(base_font)
    window = VideoCheckWindow()
    window.show()
    sys.exit(app.exec_())
