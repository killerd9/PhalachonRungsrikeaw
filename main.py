import os
import re
import time
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
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

# ── MIDI ──────────────────────────────────────────────────────
try:
    import mido
    from mido import MidiFile, MidiTrack, Message
    MIDO_OK = True
except ImportError:
    MIDO_OK = False

# ── Audio ─────────────────────────────────────────────────────
PYGAME_OK = False
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
# MIDI helpers
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

def dur_ticks(d: int, tpb: int = 480) -> int:
    return int(tpb * {1:4, 2:2, 4:1, 8:0.5, 16:0.25}.get(d, 1))

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

def build_midi(seq, bpm: int = 100, out_dir: str = None, inst: int = 0) -> str:
    if not MIDO_OK: raise RuntimeError("ไม่พบ mido — pip install mido")
    if out_dir is None:
        out_dir = (App.get_running_app().user_data_dir
                   if platform == 'android' else "output_midi")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"song_{int(time.time())}.mid")
    tpb = 480
    mid = MidiFile(ticks_per_beat=tpb)
    trk = MidiTrack(); mid.tracks.append(trk)
    trk.append(mido.MetaMessage('set_tempo',
                                tempo=int(60_000_000/max(bpm,1)), time=0))
    trk.append(Message('program_change',
                        program=max(0,min(127,inst)), time=0))
    for entry in seq:
        notes = entry['notes']
        ticks = dur_ticks(entry['duration'], tpb)
        vel   = entry['velocity']
        # หยุดพัก
        if notes in (['X'],['x']):
            trk.append(mido.MetaMessage('text', text='rest', time=ticks))
            continue
        midi_notes = []
        for n in notes:
            try: midi_notes.append(note_to_midi(n))
            except ValueError: pass
        if not midi_notes: continue
        for idx, mn in enumerate(midi_notes):
            trk.append(Message('note_on', note=mn, velocity=vel, time=0))
        for idx, mn in enumerate(midi_notes):
            trk.append(Message('note_off', note=mn, velocity=vel,
                               time=ticks if idx==0 else 0))
    mid.save(path)
    return path


# ==============================================================
# KV
# ==============================================================
KV = '''
#:import FadeTransition kivy.uix.screenmanager.FadeTransition

#:import Window kivy.core.window.Window

<RoundBtn@ButtonBehavior+Label>:
    font_size: 16
    bold: True
    color: (1,1,1,1)
    bg_color: (0.2,0.55,0.85,1)
    size_hint_y: None
    height: 52
    canvas.before:
        Color:
            rgba: (self.bg_color[0]*0.82, self.bg_color[1]*0.82, self.bg_color[2]*0.82, 1) if self.state=='down' else self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [14]

<ScannerScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: [20, 16, 20, 16]
        spacing: 0

        # Title - centered
        Label:
            text: "สแกน QR CODE เพลง"
            font_size: 28
            bold: True
            size_hint_y: None
            height: 64
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
                    radius: [12]

        # Space
        Widget:
            size_hint_y: None
            height: 18

        # BPM row
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: 56
            spacing: 12

            Label:
                text: "BPM"
                font_size: 22
                bold: True
                color: (0.1,0.1,0.1,1)
                size_hint_x: None
                width: 90
                halign: 'left'
                valign: 'middle'
                text_size: self.size

            TextInput:
                id: tempo_input
                text: "100"
                multiline: False
                input_filter: 'int'
                font_size: 20
                padding: [14, 14]
                background_color: (0.92,0.92,0.92,1)
                background_normal: ''

        Label:
            text: "ความเร็วเพลง(20-300)"
            color: (0.5,0.5,0.5,1)
            font_size: 13
            size_hint_y: None
            height: 24
            halign: 'left'
            text_size: self.size

        Widget:
            size_hint_y: None
            height: 10

        # Sound row
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: 56
            spacing: 12

            Label:
                text: "เสียง"
                font_size: 22
                bold: True
                color: (0.1,0.1,0.1,1)
                size_hint_x: None
                width: 90
                halign: 'left'
                valign: 'middle'
                text_size: self.size

            TextInput:
                id: inst_input
                text: "0"
                multiline: False
                input_filter: 'int'
                font_size: 20
                padding: [14, 14]
                background_color: (0.92,0.92,0.92,1)
                background_normal: ''

        Label:
            text: "น้ำหนักเสียง(0-127)"
            color: (0.5,0.5,0.5,1)
            font_size: 13
            size_hint_y: None
            height: 24
            halign: 'left'
            text_size: self.size

        # Status
        Label:
            id: status_label
            text: "พร้อมสแกน..."
            color: (0.3,0.5,0.8,1)
            bold: True
            size_hint_y: None
            height: 36
            halign: 'center'
            text_size: self.size

        # Spacer
        Widget:
            size_hint_y: 1

        # Gallery button
        RoundBtn:
            text: "เลือกรูปจากแกลลอรี่"
            bg_color: (0.58,0.28,0.78,1)
            size_hint_y: None
            height: 68
            font_size: 22
            on_press: root.open_gallery()

<PlayerScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: [22,16,22,14]
        spacing: 14

        Label:
            text: "🎵  เครื่องเล่นเพลง"
            font_size: 24
            bold: True
            size_hint_y: None
            height: 50
            color: (0.1,0.2,0.4,1)
            halign: 'left'
            text_size: self.size

        # Info card
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: 90
            padding: [14,8]
            spacing: 4
            canvas.before:
                Color:
                    rgba: (1,1,1,1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [14]

            Label:
                id: song_name_label
                text: "ยังไม่ได้โหลดเพลง"
                color: (0.35,0.35,0.35,1)
                font_size: 13
                text_size: self.width, None
                halign: 'center'
                size_hint_y: None
                height: 24

            Label:
                id: notes_preview
                text: ""
                color: (0.55,0.55,0.55,1)
                font_size: 11
                text_size: self.width, None
                halign: 'center'
                size_hint_y: None
                height: 20

            Label:
                id: time_label
                text: "0:00 / 0:00"
                font_size: 22
                bold: True
                color: (0.1,0.6,0.8,1)
                halign: 'center'

        # Progress bar
        ProgressBar:
            id: progress_bar
            max: 100
            value: 0
            size_hint_y: None
            height: 10

        # Control buttons
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: 62
            spacing: 12

            RoundBtn:
                id: play_btn
                text: "▶  เล่น"
                bg_color: (0.14,0.76,0.40,1)
                font_size: 18
                on_press: root.on_play()

            RoundBtn:
                id: pause_btn
                text: "⏸  พัก"
                bg_color: (0.92,0.58,0.06,1)
                font_size: 18
                on_press: root.on_pause()

            RoundBtn:
                id: stop_btn
                text: "⏹  หยุด"
                bg_color: (0.88,0.28,0.20,1)
                font_size: 18
                on_press: root.on_stop()

        RoundBtn:
            text: "↺  เล่นใหม่จากต้น"
            bg_color: (0.18,0.56,0.84,1)
            on_press: root.on_replay()

        # Status
        Label:
            id: status_label
            text: "พร้อมเล่น"
            color: (0.4,0.4,0.4,1)
            size_hint_y: None
            height: 36
            bold: True
            halign: 'center'
            text_size: self.size

        RoundBtn:
            text: "◀  กลับไปสแกนใหม่"
            bg_color: (0.55,0.55,0.58,1)
            size_hint_y: None
            height: 52
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
        self._set_status("พร้อมสแกน...", (0.3,0.5,0.8,1))
        Clock.schedule_once(lambda dt: self._start_camera(), 0.4)

    def on_leave(self):
        self._stop_camera()

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
                intent = Intent(Intent.ACTION_PICK)
                intent.setType('image/*')
                activity_bind(on_activity_result=self._on_activity_result)
                from android import activity  # type: ignore
                activity.start_activity_for_result(intent, 1001)
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
                # แปลง URI เป็น path
                from jnius import autoclass  # type: ignore
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                cursor = context.getContentResolver().query(uri, None, None, None, None)
                if cursor and cursor.moveToFirst():
                    idx = cursor.getColumnIndex('_data')
                    if idx >= 0:
                        filepath = cursor.getString(idx)
                        cursor.close()
                        Clock.schedule_once(lambda dt: self._process_image(filepath), 0.1)
                        return
                    cursor.close()
                # fallback: copy file to temp
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

    # ── process QR → MIDI ──────────────────────────────────────

    def _process_qr(self, data: str):
        self._set_status("กำลังสร้าง MIDI...", (0.5,0.5,0.5,1))

        def _work():
            try:
                bpm  = max(20, min(300, int(self.ids.tempo_input.text.strip() or 100)))
                inst = max(0,  min(127, int(self.ids.inst_input.text.strip() or 0)))
                seq  = parse_qr(data)
                path = build_midi(seq, bpm=bpm, inst=inst)
                Clock.schedule_once(lambda dt: self._on_ready(path, data), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_error(str(e)), 0)

        threading.Thread(target=_work, daemon=True).start()

    def _on_ready(self, path: str, raw: str):
        self._set_status("✅ สำเร็จ! กำลังเปิดเครื่องเล่น...", (0.2,0.72,0.3,1))
        player: PlayerScreen = self.manager.get_screen('player')
        player.load_song(path, raw)
        Clock.schedule_once(
            lambda dt: setattr(self.manager, 'current', 'player'), 0.8)

    def _on_error(self, msg: str):
        self._set_status(f"❌ {msg}", (0.9,0.3,0.2,1))
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
        self._midi_path   = None
        self._sound       = None
        self._playing     = False
        self._paused      = False
        self._pause_pos   = 0.0
        self._song_length = 0.0
        self._timer_ev    = None

    # ── load ───────────────────────────────────────────────────

    def load_song(self, path: str, raw: str = ""):
        self._stop_internal()
        self._midi_path = path
        self._pause_pos = 0.0
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
            self._set_status("โหลดสำเร็จ — กด ▶ เพื่อเล่น", (0.2,0.72,0.3,1))
        else:
            self._set_status("โหลดไฟล์ไม่ได้", (0.9,0.3,0.2,1))

    # ── controls ───────────────────────────────────────────────

    def on_play(self):
        if not self._midi_path or not AUDIO_OK: return
        if self._paused and self._sound:
            self._sound.play()
            self._paused  = False
            self._playing = True
            self._set_status("🎵 กำลังเล่น...", (0.18,0.56,0.84,1))
            self._start_timer()
        elif not self._playing and self._sound:
            self._sound.play()
            self._playing = True
            self._paused  = False
            self._set_status("🎵 กำลังเล่น...", (0.18,0.56,0.84,1))
            self._start_timer()

    def on_pause(self):
        if not AUDIO_OK or not self._playing or not self._sound: return
        self._sound.stop()
        self._playing = False
        self._paused  = True
        self._stop_timer()
        self._set_status("⏸ พักเพลง", (0.92,0.58,0.06,1))

    def on_stop(self):
        self._stop_internal()
        self._set_status("⏹ หยุดเพลง", (0.88,0.28,0.20,1))

    def on_replay(self):
        if not self._midi_path: return
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
        self._playing   = False
        self._paused    = False
        self._pause_pos = 0.0
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

    def _tick(self, dt):
        if not AUDIO_OK or not self._sound: return
        if self._sound.state == 'stop' and self._playing:
            self._playing   = False
            self._paused    = False
            self._pause_pos = 0.0
            self._stop_timer()
            self.ids.progress_bar.value = 100
            self._set_status("✅ เล่นจบแล้ว", (0.2,0.72,0.3,1))
            return
        self._update_time()
        self._update_progress()

    def _update_time(self):
        if AUDIO_OK and self._sound and self._playing:
            pos_s = self._sound.get_pos()
        else:
            pos_s = self._pause_pos
        if hasattr(self, 'ids') and 'time_label' in self.ids:
            self.ids.time_label.text = (
                f"{self._fmt(pos_s)} / {self._fmt(self._song_length)}"
            )

    def _update_progress(self):
        if not hasattr(self, 'ids') or 'progress_bar' not in self.ids: return
        total = max(self._song_length, 0.001)
        if AUDIO_OK and self._sound and self._playing:
            pos_s = self._sound.get_pos()
        else:
            pos_s = self._pause_pos
        self.ids.progress_bar.value = min(pos_s/total*100, 100)

    @staticmethod
    def _fmt(s: float) -> str:
        s = max(0, int(s))
        return f"{s//60}:{s%60:02d}"

    @staticmethod
    def _get_length(path: str) -> float:
        if not MIDO_OK: return 0.0
        try: return MidiFile(path).length
        except Exception: return 0.0

    def _set_status(self, text: str, color=(0.4,0.4,0.4,1)):
        self.ids.status_label.text  = text
        self.ids.status_label.color = color

    # ── lifecycle ──────────────────────────────────────────────

    def on_enter(self):
        if self._midi_path:
            self.ids.song_name_label.text = os.path.basename(self._midi_path)
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
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission  # type: ignore
                request_permissions([
                    Permission.CAMERA,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ])
            except Exception:
                pass

    def on_stop(self):
        pass

if __name__ == '__main__':
    QRScannerApp().run()
