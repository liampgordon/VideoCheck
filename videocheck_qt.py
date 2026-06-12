import sys
import os
import subprocess
import ffmpeg
from fractions import Fraction
import csv
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidgetItem,
    QVBoxLayout, QWidget, QFileDialog, QPushButton, QHBoxLayout,
    QAction, QMenuBar, QMessageBox, QStatusBar, QTableWidget, QHeaderView
)
from PyQt5.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QKeyEvent, QFont

# Dynamically determine FFMPEG path for bundled or unbundled execution
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)
FFMPEG_PATH = os.path.join(base_path, "ffmpeg")

APP_VERSION = "v1.0"
APP_AUTHOR = "© 2025 Liam P. Gordon"

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

        size_bytes = os.path.getsize(file_path)
        peak_db = get_peak_db(file_path)

        metadata = {
            "Path": file_path,
            "Name": os.path.basename(file_path),
            "Size": format_size(size_bytes),
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
            "FPS": "-", "Duration": "-", "Resolution": "-", "Aspect Ratio": "-",
            "Video Codec": "-", "Color Space": "-", "Audio Codec": "-",
                "Channels": "-", "Peak dB": "-"
            }

SORT_KEY_ROLE = Qt.UserRole + 1

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

class VideoCheckTable(QTableWidget):
    rowsDeleted = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFont(QFont("Arial", 8))

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
        self.resize(1300, 600)

        self.threadpool = QThreadPool()
        self.headers = [
            "Name", "Size", "FPS", "Duration", "Resolution", "Aspect Ratio",
            "Video Codec", "Color Space", "Audio Codec", "Channels", "Peak dB"
        ]

        self.table = VideoCheckTable(0, len(self.headers))
        self.table.rowsDeleted.connect(self.update_status)
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        open_button = QPushButton("Open in Finder")
        open_button.clicked.connect(self.open_selected_in_finder)

        browse_button = QPushButton("Browse Files")
        browse_button.clicked.connect(self.open_file_dialog)

        export_button = QPushButton("Export to CSV")
        export_button.clicked.connect(self.export_to_csv)

        clear_button = QPushButton("Clear Table")
        clear_button.clicked.connect(self.clear_table)

        buttons = QHBoxLayout()
        buttons.addWidget(browse_button)
        buttons.addWidget(open_button)
        buttons.addWidget(export_button)
        buttons.addWidget(clear_button)

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.table)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status()

        menubar = self.menuBar()
        help_menu = menubar.addMenu('Help')
        about_action = QAction('About VideoCheck', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_about(self):
        QMessageBox.about(self, "About VideoCheck",
                          f"VideoCheck {APP_VERSION}\n{APP_AUTHOR}\nAll rights reserved.")

    def update_status(self):
        self.status_bar.showMessage(f"Video Count: {self.table.rowCount()}")

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
        for file_path in file_paths:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            name_item = QTableWidgetItem(os.path.basename(file_path))
            name_item.setData(Qt.UserRole, file_path)
            self.table.setItem(row_index, 0, name_item)

            signal = WorkerSignals()
            signal.result.connect(self.update_row_metadata)
            worker = MetadataWorker(file_path, signal)
            self.threadpool.start(worker)
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
                    self.table.setItem(row, i, cell)
                break
        self.table.setSortingEnabled(sorting)
        self.update_status()

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
        self.update_status()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoCheckWindow()
    window.show()
    sys.exit(app.exec_())
