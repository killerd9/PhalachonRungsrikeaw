import os
import re
import time
import math
import wave
import struct
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.utils import platform
from kivy.uix.screenmanager import Screen, ScreenManager, FadeTransition
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar

from kivy.core.text import LabelBase, DEFAULT_FONT
try:
    LabelBase.register(DEFAULT_FONT, 'ChakraPetch-Bold.ttf')
except Exception:
    pass

Window.clearcolor = (0.95, 0.96, 0.98, 1)
if platform not in ('android', 'ios'):
    Window.size = (480, 820)

# ── Audio ─────────────────────────────────────────────────────
try:
    from kivy.core.audio import SoundLoader
    AUDIO_OK = True
except Exception:
    AUDIO_OK = False

# ── Camera (ZBarCam) ──────────────────────────────────────────
try:
    from kivy_garden.zbarcam import ZBarCam
    ZBARCAM_OK = True
except ImportError:
    ZBARCAM_OK = False

# ── อ่านรูปจากแกลลอรี่ ───────────────────────────────────────
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    from PIL import Image as PILImage
    PYZBAR_PIL_OK = True
except ImportError:
    PYZBAR_PIL_OK = False


# ==============================================================
# Note helpers
# ==============================================================
_SEMITONE = {
    'C':0,'C#':1,'DB':1,'D':2,'D#':3,'EB':3,'E':4,
    'F':5,'F#':6,'GB':6,'G':7,'G#':8,'AB':8,
    'A':9,'A#':10,'BB':10,'B':11,
}
_NOTE_RE = re.compile(r'^([A-Ga-g][#bB]?)(\d)$')

def note_to_midi(s: str) -> int:
    m = _NOTE_RE.match(s.strip())
    if not m: raise ValueError(f"โน้ตไม่ถูกต้อง: '{s}'")
    name = m.group(1).upper()
    # normalize flat
    flat = {'CB':'B','DB':'C#','EB':'D#','FB':'E','GB':'F#','AB':'G#','BB':'A#'}
    name = flat.get(name, name)
    sem = _SEMITONE.get(name)
    if sem is None: raise ValueError(f"ไม่รู้จักโน้ต '{name}'")
    midi_num = 12*(int(m.group(2))+1) + sem
    if not (0 <= midi_num <= 127): raise ValueError(f"MIDI ออกนอกช่วง: {midi_num}")
    return midi_num

def midi_to_freq(n: int) -> float:
    return 440.0 * (2.0 ** ((n - 69) / 12.0))

_DUR_BEATS = {
    1: 4.0, 
    2: 2.0, 
    4: 1.0, 
    6: 0.666,  # เพิ่มสำหรับค่า 6 (เช่น โน้ตหารสาม / Triplet)
    8: 0.5, 
    16: 0.25,
    32: 0.125  # เพิ่มสำหรับค่า 32 (เขบ็ต 3 ชั้น)
}

def parse_qr(data: str, default_dur: int = 4, vel: int = 90):
    data = data.strip()
    if not data: raise ValueError("ข้อมูลว่างเปล่า")
    items = [x.strip() for x in data.split(',') if x.strip()]
    seq = []
    if any(':' in it for it in items):          # format ใหม่  C4:4
        for it in items:
            if ':' not in it: continue
            np_, dp_ = it.split(':', 1)
            dur = int(dp_.strip()) if dp_.strip().isdigit() else default_dur
            notes = [n.strip().upper() for n in np_.split('+') if n.strip()]
            seq.append({'notes': notes, 'duration': dur, 'velocity': vel})
    else:                                       # format เก่า  C4,4
        i = 0
        while i < len(items):
            raw = items[i]
            if i+1 < len(items) and items[i+1].isdigit():
                dur = int(items[i+1]); i += 2
            else:
                dur = default_dur; i += 1
            notes = [n.strip().upper() for n in raw.split('+') if n.strip()]
            seq.append({'notes': notes, 'duration': dur, 'velocity': vel})
    if not seq: raise ValueError("ไม่พบโน้ตใน QR")
    return seq


# ==============================================================
# WAV synth
# ── แทนที่ MIDI เดิมทั้งหมด: SoundLoader ของ Kivy บน Android
#    ไม่มี MIDI synthesizer ในตัว เล่นไฟล์ .mid ตรงๆ ไม่ได้ (นี่คือ
#    สาเหตุที่เพลงไม่เล่น) จึงสังเคราะห์เสียงเองเป็น .wav แทน
#    ซึ่งเล่นได้ชัวร์ทุกแพลตฟอร์ม และไม่ต้องพึ่งไลบรารีภายนอกเลย
# ==============================================================
SAMPLE_RATE = 22050  # พอเพียงสำหรับเสียงโน้ตเดี่ยว/คอร์ด และเบาต่อ CPU มือถือ

def _render_note(freq: float, dur_sec: float, vel: int) -> list:
    n = max(1, int(SAMPLE_RATE * dur_sec))
    amp = (max(1, min(127, vel)) / 127.0) * 0.35
    attack  = max(1, int(0.01 * SAMPLE_RATE))
    release = max(1, int(min(0.05, dur_sec * 0.3) * SAMPLE_RATE))
    buf = [0.0] * n
    for i in range(n):
        t = i / SAMPLE_RATE
        # รวมฮาร์มอนิกเล็กน้อยให้เสียงมีมิติกว่า sine เดี่ยว
        val = (math.sin(2*math.pi*freq*t)
               + 0.5*math.sin(2*math.pi*freq*2*t)
               + 0.25*math.sin(2*math.pi*freq*3*t)) / 1.75
        if i < attack:
            env = i / attack
        elif i > n - release:
            env = max(0.0, (n - i) / release)
        else:
            env = 1.0
        buf[i] = val * amp * env
    return buf

def synth_wav(seq, bpm: int = 100, out_dir: str = None) -> str:
    if out_dir is None:
        out_dir = (App.get_running_app().user_data_dir
                   if platform == 'android' else "output_wav")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"song_{int(time.time())}.wav")

    beat_sec = 60.0 / max(20, min(300, bpm))
    samples: list = []

    for entry in seq:
        dur_sec = beat_sec * _DUR_BEATS.get(entry['duration'], 1.0)
        notes = entry['notes']
        # หยุดพัก
        if notes in (['X'], ['x']):
            samples.extend([0.0] * int(SAMPLE_RATE * dur_sec))
            continue
        bufs = []
        for n in notes:
            try:
                mn = note_to_midi(n)
            except ValueError:
                continue
            bufs.append(_render_note(midi_to_freq(mn), dur_sec, entry['velocity']))
        if not bufs:
            samples.extend([0.0] * int(SAMPLE_RATE * dur_sec))
            continue
        # รวมเสียงทุกโน้ตในคอร์ดเข้าด้วยกัน (เล่นพร้อมกัน)
        length = max(len(b) for b in bufs)
        mixed = [0.0] * length
        for b in bufs:
            for i, v in enumerate(b):
                mixed[i] += v
        peak = max((abs(x) for x in mixed), default=1.0)
        if peak > 1.0:            # กันเสียงล้น(clip)ตอนคอร์ดหลายโน้ตพร้อมกัน
            mixed = [x / peak for x in mixed]
        samples.extend(mixed)

    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            v = max(-1.0, min(1.0, s))
            frames += struct.pack('<h', int(v * 32767))
        wf.writeframes(bytes(frames))

    return path


# ==============================================================
# KV
# ==============================================================
KV = '''
#:import FadeTransition kivy.uix.screenmanager.FadeTransition
#:import Window kivy.core.window.Window
#:import dp kivy.metrics.dp

<RoundBtn@ButtonBehavior+Label>:
    font_size: dp(16)
    bold: True
    color: (1,1,1,1)
    bg_color: (0.2,0.55,0.85,1)
    size_hint_y: None
    height: dp(52)
    canvas.before:
        Color:
            rgba: (self.bg_color[0]*0.82, self.bg_color[1]*0.82, self.bg_color[2]*0.82, 1) if self.state=='down' else self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

<ScannerScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(20), dp(16), dp(20), dp(16)]
        spacing: 0

        # Title - centered
        Label:
            text: "สแกน QR CODE เพลง"
            font_size: dp(28)
            bold: True
            size_hint_y: None
            height: dp(64)
            color: (0.1,0.1,0.1,1)
            halign: 'center'
            valign: 'middle'
            text_size: self.size

        # Camera area
        BoxLayout:
            id: camera_box
            size_hint_y: None
            height: Window.height * 0.42
            canvas.before:
                Color:
                    rgba: (0.08,0.08,0.10,1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(12)]

        # Space
        Widget:
            size_hint_y: None
            height: dp(18)

        # BPM row
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(56)
            spacing: dp(12)

            Label:
                text: "BPM"
                font_size: dp(22)
                bold: True
                color: (0.1,0.1,0.1,1)
                size_hint_x: None
                width: dp(90)
                halign: 'left'
                valign: 'middle'
                text_size: self.size

            TextInput:
                id: tempo_input
                text: "100"
                multiline: False
                input_filter: 'int'
                font_size: dp(20)
                padding: [dp(14), dp(14)]
                background_color: (0.92,0.92,0.92,1)
                background_normal: ''

        Label:
            text: "ความเร็วเพลง(20-300)"
            color: (0.5,0.5,0.5,1)
            font_size: dp(13)
            size_hint_y: None
            height: dp(24)
            halign: 'left'
            text_size: self.size

        Widget:
            size_hint_y: None
            height: dp(10)

        # Sound row
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(56)
            spacing: dp(12)

            Label:
                text: "เสียง"
                font_size: dp(22)
                bold: True
                color: (0.1,0.1,0.1,1)
                size_hint_x: None
                width: dp(90)
                halign: 'left'
                valign: 'middle'
                text_size: self.size

            TextInput:
                id: inst_input
                text: "90"
                multiline: False
                input_filter: 'int'
                font_size: dp(20)
                padding: [dp(14), dp(14)]
                background_color: (0.92,0.92,0.92,1)
                background_normal: ''

        Label:
            text: "น้ำหนักเสียง(0-127)"
            color: (0.5,0.5,0.5,1)
            font_size: dp(13)
            size_hint_y: None
            height: dp(24)
            halign: 'left'
            text_size: self.size

        # Status
        Label:
            id: status_label
            text: "พร้อมสแกน..."
            color: (0.3,0.5,0.8,1)
            bold: True
            font_size: dp(15)
            size_hint_y: None
            height: max(dp(36), self.texture_size[1] + dp(12))
            halign: 'center'
            valign: 'middle'
            text_size: self.width, None

        # Spacer
        Widget:
            size_hint_y: 1

        # Gallery button
        RoundBtn:
            text: "เลือกรูปจากแกลลอรี่"
            bg_color: (0.58,0.28,0.78,1)
            size_hint_y: None
            height: dp(68)
            font_size: dp(22)
            on_press: root.open_gallery()

<PlayerScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(22), dp(16), dp(22), dp(14)]
        spacing: dp(14)

        Label:
            text: "เครื่องเล่นเพลง"
            font_size: dp(26)
            bold: True
            size_hint_y: None
            height: dp(50)
            color: (0.1,0.2,0.4,1)
            halign: 'left'
            text_size: self.size

        # Info card
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(100)
            padding: [dp(14), dp(10)]
            spacing: dp(6)
            canvas.before:
                Color:
                    rgba: (1,1,1,1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(14)]

            Label:
                id: song_name_label
                text: "ยังไม่ได้โหลดเพลง"
                color: (0.35,0.35,0.35,1)
                font_size: dp(14)
                text_size: self.width, None
                halign: 'center'
                size_hint_y: None
                height: dp(26)

            Label:
                id: notes_preview
                text: ""
                color: (0.55,0.55,0.55,1)
                font_size: dp(12)
                text_size: self.width, None
                halign: 'center'
                size_hint_y: None
                height: dp(22)

            Label:
                id: time_label
                text: "0:00 / 0:00"
                font_size: dp(24)
                bold: True
                color: (0.1,0.6,0.8,1)
                halign: 'center'

        # Progress bar
        ProgressBar:
            id: progress_bar
            max: 100
            value: 0
            size_hint_y: None
            height: dp(10)

        Widget:
            size_hint_y: None
            height: dp(6)

        # Control buttons
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(64)
            spacing: dp(12)

            RoundBtn:
                id: play_btn
                text: "> เล่น"
                bg_color: (0.14,0.76,0.40,1)
                font_size: dp(19)
                on_press: root.on_play()

            RoundBtn:
                id: pause_btn
                text: "|| พัก"
                bg_color: (0.92,0.58,0.06,1)
                font_size: dp(19)
                on_press: root.on_pause()

            RoundBtn:
                id: stop_btn
                text: "[] หยุด"
                bg_color: (0.88,0.28,0.20,1)
                font_size: dp(19)
                on_press: root.on_stop()

        RoundBtn:
            text: "<< เล่นใหม่จากต้น"
            bg_color: (0.18,0.56,0.84,1)
            size_hint_y: None
            height: dp(56)
            font_size: dp(18)
            on_press: root.on_replay()

        # ยืดหยุ่น: ดันสถานะ/ปุ่มย้อนกลับให้กระจายเต็มพื้นที่หน้าจอ แทนที่จะกองแน่นด้านบน
        Widget:
            size_hint_y: 1

        # Status
        Label:
            id: status_label
            text: "พร้อมเล่น"
            color: (0.4,0.4,0.4,1)
            size_hint_y: None
            height: max(dp(36), self.texture_size[1] + dp(12))
            font_size: dp(15)
            bold: True
            halign: 'center'
            valign: 'middle'
            text_size: self.width, None

        RoundBtn:
            text: "<< กลับไปสแกนใหม่"
            bg_color: (0.55,0.55,0.58,1)
            size_hint_y: None
            height: dp(54)
            font_size: dp(17)
            on_press: root.go_back()
'''

Builder.load_string(KV)


# ==============================================================
# ScannerScreen
# ==============================================================
class ScannerScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._processing = False
        self._cam = None

    # ── lifecycle ──────────────────────────────────────────────

    def on_enter(self):
        self._processing = False
        self._set_status("กำลังตรวจสอบสิทธิ์กล้อง...", (0.3,0.5,0.8,1))
        Clock.schedule_once(lambda dt: self._ensure_permission_then_camera(), 0.3)

    def on_leave(self):
        self._stop_camera()

    # ── permission (แก้ปัญหา "กล้องใช้งานไม่ได้") ───────────────
    # เดิม: ขอสิทธิ์แบบไม่รอผล แล้วเปิดกล้องทันทีตามเวลา จึงมักเปิด
    # ก่อนผู้ใช้กด "อนุญาต" บน dialog เสร็จ ทำให้เปิดกล้องไม่ติด
    # ใหม่: เช็ค/ขอสิทธิ์ก่อน แล้วเปิดกล้อง "หลังได้รับอนุญาตจริง" เท่านั้น

    def _ensure_permission_then_camera(self):
        if platform != 'android':
            self._start_camera()
            return
        try:
            from android.permissions import (   # type: ignore
                check_permission, request_permissions, Permission
            )
            if check_permission(Permission.CAMERA):
                self._start_camera()
                return

            def _on_result(permissions, results):
                if results and any(results):
                    Clock.schedule_once(lambda dt: self._start_camera(), 0.2)
                else:
                    self._set_status(
                        "ไม่ได้รับสิทธิ์กล้อง — เปิดสิทธิ์กล้องในตั้งค่าแอป หรือใช้ปุ่ม 'เลือกรูปจากแกลลอรี่' แทนได้",
                        (0.9,0.3,0.2,1)
                    )

            self._set_status("กำลังขอสิทธิ์กล้อง...", (0.5,0.5,0.5,1))
            request_permissions(
                [Permission.CAMERA, Permission.READ_EXTERNAL_STORAGE,
                 Permission.WRITE_EXTERNAL_STORAGE],
                _on_result
            )
        except Exception as e:
            self._set_status(f"ตรวจสอบสิทธิ์ไม่ได้: {e}", (0.9,0.3,0.2,1))
            self._start_camera()

    # ── camera ─────────────────────────────────────────────────

    def _start_camera(self):
        if self._cam is not None:
            return
        if not ZBARCAM_OK:
            self._set_status(
                "ไม่พบ ZBarCam — ใช้ปุ่ม 'เลือกรูป' แทนได้",
                (0.85, 0.45, 0.1, 1)
            )
            return
        try:
            # หมายเหตุ: ZBarCam เวอร์ชันปัจจุบันไม่มี property 'camera_index' แล้ว
            # (เคยมีใน garden.zbarcam รุ่นเก่า) ใช้ค่า default ของกล้องไปก่อน
            cam = ZBarCam()
            cam.bind(symbols=self._on_symbols)
            self.ids.camera_box.add_widget(cam)
            self._cam = cam
            Clock.schedule_once(lambda dt: setattr(cam, 'play', True), 0.3)
            self._set_status("เปิดกล้องแล้ว — ชี้ไปที่ QR Code", (0.2,0.72,0.3,1))
        except Exception as e:
            self._set_status(f"เปิดกล้องไม่ได้: {e}", (0.9,0.3,0.2,1))

    def _stop_camera(self):
        if self._cam:
            try: self._cam.play = False
            except Exception: pass
            try: self.ids.camera_box.remove_widget(self._cam)
            except Exception: pass
            self._cam = None

    def _on_symbols(self, zbarcam, symbols):
        if not symbols or self._processing:
            return
        self._processing = True
        try:
            data = symbols[0].data.decode('utf-8')
        except Exception:
            data = str(symbols[0].data)
        self._stop_camera()
        Clock.schedule_once(lambda dt: self._process_qr(data), 0.05)

    # ── gallery ────────────────────────────────────────────────

    def open_gallery(self):
        """เปิดแกลลอรี่ Android โดยตรง"""
        if platform == 'android':
            try:
                from android.activity import bind as activity_bind  # type: ignore
                from jnius import autoclass  # type: ignore
                Intent = autoclass('android.content.Intent')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                intent = Intent(Intent.ACTION_PICK)
                intent.setType('image/*')
                activity_bind(on_activity_result=self._on_activity_result)
                current_activity = PythonActivity.mActivity
                current_activity.startActivityForResult(intent, 1001)
                self._set_status("กำลังเปิดแกลลอรี่...", (0.5,0.5,0.5,1))
            except Exception as e:
                self._set_status(f"เปิดแกลลอรี่ไม่ได้: {e}", (0.9,0.3,0.2,1))
        else:
            # Desktop fallback
            self._open_gallery_filechooser()

    def _on_activity_result(self, request_code, result_code, data):
        """รับผลจาก Android gallery"""
        from android.activity import unbind as activity_unbind  # type: ignore
        activity_unbind(on_activity_result=self._on_activity_result)
        RESULT_OK = -1
        if request_code == 1001 and result_code == RESULT_OK and data:
            try:
                uri = data.getData()
                from jnius import autoclass  # type: ignore
                context = autoclass('org.kivy.android.PythonActivity').mActivity

                # วิธีที่ 1: ลองอ่าน path ผ่านคอลัมน์ _data (ใช้ได้บาง provider เท่านั้น)
                filepath = None
                try:
                    cursor = context.getContentResolver().query(uri, None, None, None, None)
                    if cursor and cursor.moveToFirst():
                        idx = cursor.getColumnIndex('_data')
                        if idx >= 0:
                            filepath = cursor.getString(idx)
                        cursor.close()
                except Exception:
                    filepath = None

                if filepath and os.path.exists(filepath):
                    Clock.schedule_once(lambda dt: self._process_image(filepath), 0.1)
                    return

                # วิธีที่ 2 (ค่าเริ่มต้นที่ใช้ได้แน่นอนบน Android 10+/scoped storage):
                # คัดลอกไฟล์จาก content:// URI มาไว้ในโฟลเดอร์ชั่วคราวของแอปเอง
                import tempfile
                inp_stream = context.getContentResolver().openInputStream(uri)
                tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                buf = bytearray(4096)
                while True:
                    n = inp_stream.read(buf)
                    if n <= 0: break
                    tmp.write(bytes(buf[:n]))
                tmp.close()
                inp_stream.close()
                Clock.schedule_once(lambda dt: self._process_image(tmp.name), 0.1)
            except Exception as e:
                self._set_status(f"อ่านรูปไม่ได้: {e}", (0.9,0.3,0.2,1))
        else:
            self._set_status("ยกเลิกการเลือกรูป", (0.5,0.5,0.5,1))

    def _open_gallery_filechooser(self):
        """Fallback สำหรับ desktop"""
        from kivy.uix.filechooser import FileChooserIconView
        content = BoxLayout(orientation='vertical', spacing=6, padding=6)
        fc = FileChooserIconView(filters=['*.png','*.jpg','*.jpeg','*.bmp'])
        fc.path = os.path.expanduser('~')
        content.add_widget(fc)
        btn_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
        cancel_btn = Button(text="ยกเลิก", background_color=(0.75,0.25,0.25,1))
        select_btn = Button(text="เลือกรูปนี้", background_color=(0.2,0.72,0.4,1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(select_btn)
        content.add_widget(btn_row)
        pop = Popup(title="เลือกรูป QR Code", content=content,
                    size_hint=(0.93,0.88), auto_dismiss=False)
        def _select(*_):
            if not fc.selection: return
            pop.dismiss()
            Clock.schedule_once(lambda dt: self._process_image(fc.selection[0]), 0.1)
        select_btn.bind(on_press=_select)
        cancel_btn.bind(on_press=pop.dismiss)
        pop.open()

    def _process_image(self, filepath: str):
        if not PYZBAR_PIL_OK:
            self._set_status("ไม่พบ pyzbar/Pillow", (0.9,0.3,0.2,1))
            return
        self._processing = True
        self._stop_camera()
        self._set_status("กำลังอ่านรูปภาพ...", (0.5,0.5,0.5,1))
        try:
            img = PILImage.open(filepath).convert('RGB')
            decoded = pyzbar_decode(img)
            if decoded:
                data = decoded[0].data.decode('utf-8')
                self._process_qr(data)
            else:
                self._set_status("ไม่พบ QR Code ในรูปนี้", (0.9,0.3,0.2,1))
                self._processing = False
                Clock.schedule_once(lambda dt: self._start_camera(), 1.5)
        except Exception as e:
            self._set_status(f"อ่านรูปไม่ได้: {e}", (0.9,0.3,0.2,1))
            self._processing = False
            Clock.schedule_once(lambda dt: self._start_camera(), 1.5)

    # ── process QR → เสียง ──────────────────────────────────────

    def _process_qr(self, data: str):
        self._set_status("กำลังสร้างเสียงเพลง...", (0.5,0.5,0.5,1))

        def _work():
            try:
                bpm = max(20, min(300, int(self.ids.tempo_input.text.strip() or 100)))
                vel = max(1, min(127, int(self.ids.inst_input.text.strip() or 90)))
                seq = parse_qr(data)
                for e in seq:
                    e['velocity'] = vel
                path = synth_wav(seq, bpm=bpm)
                Clock.schedule_once(lambda dt: self._on_ready(path, data), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_error(str(e)), 0)

        threading.Thread(target=_work, daemon=True).start()

    def _on_ready(self, path: str, raw: str):
        self._set_status("สำเร็จ! กำลังเปิดเครื่องเล่น...", (0.2,0.72,0.3,1))
        player: PlayerScreen = self.manager.get_screen('player')
        player.load_song(path, raw)
        Clock.schedule_once(
            lambda dt: setattr(self.manager, 'current', 'player'), 0.8)

    def _on_error(self, msg: str):
        self._set_status(f"เกิดข้อผิดพลาด: {msg}", (0.9,0.3,0.2,1))
        self._processing = False
        Clock.schedule_once(lambda dt: self._start_camera(), 2.0)

    def _set_status(self, text: str, color=(0.3,0.5,0.8,1)):
        self.ids.status_label.text  = text
        self.ids.status_label.color = color


# ==============================================================
# PlayerScreen
# ==============================================================
class PlayerScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._song_path        = None
        self._sound            = None
        self._playing          = False
        self._paused           = False
        self._elapsed_at_pause = 0.0   # ตำแหน่งเพลง (วินาที) ตอนที่พัก/หยุดไว้
        self._play_started_wall = None  # time.time() ตอนเริ่ม/เล่นต่อ
        self._song_length      = 0.0
        self._timer_ev         = None

    # ── load ───────────────────────────────────────────────────

    def load_song(self, path: str, raw: str = ""):
        self._stop_internal()
        self._song_path = path
        self._elapsed_at_pause  = 0.0
        self._play_started_wall = None
        self._paused    = False

        self.ids.song_name_label.text = os.path.basename(path)
        try:
            toks = [t.strip() for t in raw.split(',') if t.strip()]
            prev = "  ".join(toks[:14])
            if len(toks) > 14: prev += f"  …(+{len(toks)-14})"
            self.ids.notes_preview.text = prev
        except Exception:
            self.ids.notes_preview.text = ""

        if not AUDIO_OK:
            self._set_status("ไม่รองรับเสียง", (0.9,0.3,0.2,1))
            return

        self._sound = SoundLoader.load(path)
        if self._sound:
            self._song_length = self._sound.length
            self._update_time()
            self.ids.progress_bar.value = 0
            self._set_status("โหลดสำเร็จ — กด เล่น เพื่อฟัง", (0.2,0.72,0.3,1))
        else:
            self._set_status("โหลดไฟล์ไม่ได้", (0.9,0.3,0.2,1))

    # ── controls ───────────────────────────────────────────────

    def on_play(self):
        if not self._song_path or not AUDIO_OK or not self._sound: return
        if self._paused:
            self._sound.play()
            # Kivy Sound.stop() รีเซ็ตตำแหน่งเป็น 0 เสมอ ตอนเล่นต่อจากพัก
            # จึงต้อง seek กลับไปที่ตำแหน่งเดิมด้วยตัวเอง
            try:
                self._sound.seek(self._elapsed_at_pause)
            except Exception:
                pass
            self._play_started_wall = time.time()
            self._paused  = False
            self._playing = True
            self._set_status("กำลังเล่น...", (0.18,0.56,0.84,1))
            self._start_timer()
        elif not self._playing:
            self._sound.play()
            self._elapsed_at_pause   = 0.0
            self._play_started_wall = time.time()
            self._playing = True
            self._paused  = False
            self._set_status("กำลังเล่น...", (0.18,0.56,0.84,1))
            self._start_timer()

    def on_pause(self):
        if not AUDIO_OK or not self._playing or not self._sound: return
        self._elapsed_at_pause = self._current_pos()
        self._sound.stop()
        self._playing = False
        self._paused  = True
        self._play_started_wall = None
        self._stop_timer()
        self._update_time()
        self._set_status("พักเพลง", (0.92,0.58,0.06,1))

    def on_stop(self):
        self._stop_internal()
        self._set_status("หยุดเพลง", (0.88,0.28,0.20,1))

    def on_replay(self):
        if not self._song_path: return
        self._stop_internal()
        Clock.schedule_once(lambda dt: self.on_play(), 0.1)

    def go_back(self):
        self._stop_internal()
        self.manager.current = 'scanner'

    # ── internal helpers ───────────────────────────────────────

    def _stop_internal(self):
        self._stop_timer()
        if self._sound:
            try: self._sound.stop()
            except Exception: pass
        self._playing           = False
        self._paused             = False
        self._elapsed_at_pause   = 0.0
        self._play_started_wall  = None
        self._update_time()
        if hasattr(self, 'ids') and 'progress_bar' in self.ids:
            self.ids.progress_bar.value = 0

    def _start_timer(self):
        self._stop_timer()
        self._timer_ev = Clock.schedule_interval(self._tick, 0.4)

    def _stop_timer(self):
        if self._timer_ev:
            self._timer_ev.cancel()
            self._timer_ev = None

    def _current_pos(self) -> float:
        """ตำแหน่งปัจจุบันของเพลง (วินาที) คำนวณเองด้วย wall-clock
        แทนการเรียก Sound.get_pos() เพราะบน Android (audio backend SDL2)
        get_pos() มักคืนค่า 0 เสมอ ทำให้ตัวเลขเวลาไม่ขยับเลย"""
        if self._playing and self._play_started_wall is not None:
            pos = self._elapsed_at_pause + (time.time() - self._play_started_wall)
        else:
            pos = self._elapsed_at_pause
        if self._song_length > 0:
            pos = min(pos, self._song_length)
        return max(0.0, pos)

    def _tick(self, dt):
        if not AUDIO_OK or not self._sound: return
        pos = self._current_pos()
        # เพลงเล่นจบเอง (state เปลี่ยนเป็น stop โดยที่เราไม่ได้สั่งเอง)
        song_finished = self._sound.state == 'stop' and self._playing
        if song_finished or (self._song_length > 0 and pos >= self._song_length - 0.05):
            self._playing            = False
            self._paused             = False
            self._elapsed_at_pause   = 0.0
            self._play_started_wall  = None
            self._stop_timer()
            self.ids.progress_bar.value = 100
            self.ids.time_label.text = f"{self._fmt(self._song_length)} / {self._fmt(self._song_length)}"
            self._set_status("เล่นจบแล้ว", (0.2,0.72,0.3,1))
            return
        self._update_time()
        self._update_progress()

    def _update_time(self):
        if hasattr(self, 'ids') and 'time_label' in self.ids:
            pos_s = self._current_pos()
            self.ids.time_label.text = (
                f"{self._fmt(pos_s)} / {self._fmt(self._song_length)}"
            )

    def _update_progress(self):
        if not hasattr(self, 'ids') or 'progress_bar' not in self.ids: return
        total = max(self._song_length, 0.001)
        pos_s = self._current_pos()
        self.ids.progress_bar.value = min(pos_s/total*100, 100)

    @staticmethod
    def _fmt(s: float) -> str:
        s = max(0, int(s))
        return f"{s//60}:{s%60:02d}"

    def _set_status(self, text: str, color=(0.4,0.4,0.4,1)):
        self.ids.status_label.text  = text
        self.ids.status_label.color = color

    # ── lifecycle ──────────────────────────────────────────────

    def on_enter(self):
        if self._song_path:
            self.ids.song_name_label.text = os.path.basename(self._song_path)
        self._update_time()

    def on_leave(self):
        self._stop_internal()


# ==============================================================
# App
# ==============================================================
class QRScannerApp(App):
    def build(self):
        self.title = "QR Music Player"
        sm = ScreenManager(transition=FadeTransition())
        sm.add_widget(ScannerScreen(name='scanner'))
        sm.add_widget(PlayerScreen(name='player'))
        return sm

    def on_start(self):
        # การขอสิทธิ์กล้อง (พร้อม callback) ทำอยู่ใน ScannerScreen._ensure_permission_then_camera()
        # แล้ว ตรงนี้ขอแค่สิทธิ์ storage ไว้ล่วงหน้าเผื่อใช้ตอนเลือกรูปจากแกลลอรี่
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission  # type: ignore
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ])
            except Exception:
                pass
            # บังคับให้เสียงออกลำโพงหลัก (media/loudspeaker) แทนลำโพงเล็ก/หูฟัง
            # แก้ปัญหา: บาง Android เข้าโหมด "communication" ทำให้เสียงเบาผิดที่
            try:
                from jnius import autoclass  # type: ignore
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Context = autoclass('android.content.Context')
                AudioManager = autoclass('android.media.AudioManager')
                activity = PythonActivity.mActivity
                audio_manager = activity.getSystemService(Context.AUDIO_SERVICE)
                audio_manager.setMode(AudioManager.MODE_NORMAL)
                audio_manager.setSpeakerphoneOn(True)
            except Exception:
                pass

    def on_stop(self):
        pass

if __name__ == '__main__':
    QRScannerApp().run()
