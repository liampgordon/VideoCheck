import PySimpleGUI as sg
import ffmpeg
import os
import datetime
import subprocess
from fractions import Fraction

# ---------- Settings ----------
sg.theme('SystemDefault')

# ---------- Helpers ----------

def get_aspect_ratio_label(width, height):
    if not width or not height:
        return "N/A"
    ratio = Fraction(width, height).limit_denominator(10)
    return f"{ratio.numerator}:{ratio.denominator}"

def format_hmsf(seconds, fps):
    total_frames = int(seconds * fps)
    h = total_frames // (3600 * int(fps))
    m = (total_frames % (3600 * int(fps))) // (60 * int(fps))
    s = (total_frames % (60 * int(fps))) // int(fps)
    f = total_frames % int(fps)
    return f"{h:02}:{m:02}:{s:02}:{f:02}"

def format_size(bytes):
    return f"{bytes / 1e6:.2f} MB"

def get_metadata(file_path):
    try:
        probe = ffmpeg.probe(file_path)
        format_info = probe.get('format', {})
        video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), {})
        audio_stream = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), {})

        file_name = os.path.basename(file_path)
        file_size = format_size(os.path.getsize(file_path))

        # Dimensions
        width = video_stream.get('width')
        height = video_stream.get('height')
        resolution = f"{width} x {height}" if width and height else "N/A"

        # Duration and FPS
        duration_raw = float(format_info.get('duration', 0))
        fps = eval(video_stream.get('r_frame_rate', '0')) if video_stream.get('r_frame_rate') else 0
        duration = format_hmsf(duration_raw, fps) if fps else "N/A"

        aspect_ratio = get_aspect_ratio_label(width, height)
        video_codec = video_stream.get('codec_name', 'N/A')
        color_space = video_stream.get('color_space', 'N/A')
        audio_codec = audio_stream.get('codec_name', 'N/A')
        channels = str(audio_stream.get('channels', 'N/A'))

        return [
            file_path,  # hidden full path (for open in finder)
            file_name,
            file_size,
            f"{fps:.2f}" if fps else "N/A",
            duration,
            resolution,
            aspect_ratio,
            video_codec,
            color_space,
            audio_codec,
            channels
        ]
    except Exception as e:
        print(f"⚠️ Error reading {file_path}: {e}")
        return [file_path, os.path.basename(file_path), 'Error'] + ['-'] * 9

# ---------- Layout ----------

headings = ["Name", "Size", "FPS", "Duration", "Resolution", "Aspect Ratio",
            "Video Codec", "Color Space", "Audio Codec", "Channels"]

layout = [
    [sg.Text("📂 Drag video files here or click 'Browse Files'")],
    [sg.Input(key='FILES', enable_events=True, visible=False),
     sg.FilesBrowse('Browse Files', file_types=(("Video Files", "*.mp4 *.mov *.mkv *.avi"),))],
    [sg.Button('Sort by Name'), sg.Button('Open Selected in Finder')],
    [sg.Table(values=[],
              headings=headings,
              auto_size_columns=True,
              justification='left',
              key='TABLE',
              num_rows=20,
              expand_x=True,
              expand_y=True,
              enable_events=True,
              select_mode=sg.TABLE_SELECT_MODE_BROWSE)],
]

window = sg.Window("VideoCheck", layout, size=(1100, 600), resizable=True)

# ---------- Event Loop ----------

table_data = []

while True:
    event, values = window.read()
    if event == sg.WIN_CLOSED:
        break

    if event == 'FILES':
        file_paths = values['FILES'].split(';')
        table_data = [get_metadata(fp) for fp in file_paths]
        display_rows = [row[1:] for row in table_data]  # remove hidden full path
        window['TABLE'].update(values=display_rows)

    if event == 'Sort by Name':
        table_data.sort(key=lambda row: row[1].lower())  # sort by file name
        window['TABLE'].update(values=[row[1:] for row in table_data])

    if event == 'Open Selected in Finder':
        selected_indices = values['TABLE']
        if selected_indices:
            selected_path = table_data[selected_indices[0]][0]
            subprocess.run(["open", "-R", selected_path])  # macOS only

window.close()