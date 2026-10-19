import os
import re
from datetime import datetime

import qrcode
from qrcode.exceptions import DataOverflowError

from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock

# ==========================================
# ตั้งค่าฟอนต์ภาษาไทย และหน้าต่าง
# ==========================================
from kivy.core.text import LabelBase, DEFAULT_FONT

# โฟลเดอร์ของสคริปต์นี้ — ใช้อ้างอิงไฟล์ต่างๆ แทน cwd
# (ไม่งั้นถ้ารันจากโฟลเดอร์อื่น จะหาฟอนต์ไม่เจอ / QR ไปเซฟผิดที่)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_CANDIDATES = [
    os.path.join(BASE_DIR, 'ChakraPetch-Bold.ttf'),            # ฟอนต์หลักของโปรเจกต์
    'C:/Windows/Fonts/tahoma.ttf',                              # Windows (รองรับไทย)
    'C:/Windows/Fonts/LeelawUI.ttf',                            # Windows (Leelawadee UI)
    '/System/Library/Fonts/Supplemental/Ayuthaya.ttf',          # macOS
    '/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf',  # Linux
    '/system/fonts/NotoSansThai-Regular.ttf',                   # Android
]


def register_thai_font():
    """ลงทะเบียนฟอนต์ไทยเป็นฟอนต์เริ่มต้น คืนค่า True ถ้าสำเร็จ"""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                LabelBase.register(DEFAULT_FONT, path)
                return True
            except Exception as e:
                print(f"[WARN] โหลดฟอนต์ {path} ไม่สำเร็จ: {e}")
    print("[WARN] ไม่พบฟอนต์ภาษาไทย — ข้อความไทยอาจแสดงเป็นกล่องสี่เหลี่ยม "
          "(วาง ChakraPetch-Bold.ttf ไว้ข้างไฟล์นี้)")
    return False


register_thai_font()

Window.size = (480, 820)
Window.clearcolor = (0.95, 0.96, 0.98, 1)  # พื้นหลังสว่าง

# ==========================================
# KV Layout (UI โฉมใหม่)
# ==========================================
KV = '''
<SmoothButton@ButtonBehavior+Label>:
    font_size: 14
    bold: True
    color: (1, 1, 1, 1)
    bg_color: (0.2, 0.55, 0.85, 1)
    size_hint_y: None
    height: 45
    canvas.before:
        Color:
            rgba: self.bg_color if self.state == 'normal' else (self.bg_color[0]*0.8, self.bg_color[1]*0.8, self.bg_color[2]*0.8, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [8]

<GenerateScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: 15
        spacing: 10

        # ── Title ──
        Label:
            text: "สร้าง QR Code โน้ตเพลง"
            font_size: 24
            bold: True
            size_hint_y: None
            height: 40
            color: (0.1, 0.2, 0.4, 1)

        # ── Preview ลำดับโน้ต ──
        BoxLayout:
            size_hint_y: None
            height: 75
            padding: 5
            canvas.before:
                Color:
                    rgba: (1, 1, 1, 1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [8]
            TextInput:
                id: sequence_input
                hint_text: "พิมพ์หรือวางโน้ตที่นี่ เช่น C4:4,E4+G4:2,X:8"
                multiline: True
                write_tab: False
                use_bubble: True
                use_handles: True
                font_size: 14
                foreground_color: (0.2, 0.2, 0.2, 1)
                background_normal: ''
                background_active: ''
                background_color: (1, 1, 1, 1)
                cursor_color: (0.2, 0.55, 0.85, 1)

        # ── Status ──
        Label:
            id: status_label
            text: "ขั้นตอน 1: เลือกโน้ต (เลือกหลายตัว=คอร์ด, X=หยุดพัก)"
            font_size: 14
            bold: True
            size_hint_y: None
            height: 44
            color: (0.2, 0.6, 0.86, 1)
            text_size: self.width, self.height
            halign: 'left'
            valign: 'middle'

        # ── ส่วนเลือกโน้ต ──
        Label:
            text: "เลือกตัวโน้ต (แตะหลายตัว = เล่นพร้อมกันเป็นคอร์ด):"
            font_size: 14
            size_hint_y: None
            height: 20
            color: (0.4, 0.4, 0.4, 1)
            text_size: self.width, self.height
            halign: 'left'
            valign: 'middle'

        ScrollView:
            size_hint_y: None
            height: 160
            canvas.before:
                Color:
                    rgba: (0.9, 0.9, 0.9, 1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [8]
            GridLayout:
                id: notes_grid
                cols: 7
                spacing: 5
                padding: 5
                size_hint_y: None
                height: self.minimum_height

        # ── ส่วนเลือกจังหวะ ──
        Label:
            text: "เลือกความยาวจังหวะ:"
            font_size: 14
            size_hint_y: None
            height: 20
            color: (0.4, 0.4, 0.4, 1)
            text_size: self.width, self.height
            halign: 'left'
            valign: 'middle'

        GridLayout:
            id: dur_grid
            cols: 5
            spacing: 5
            size_hint_y: None
            height: 45

        # ── ปุ่มควบคุม ──
        BoxLayout:
            orientation: 'horizontal'
            spacing: 10
            size_hint_y: None
            height: 45

            SmoothButton:
                text: "ยกเลิกล่าสุด"
                bg_color: (0.95, 0.61, 0.07, 1) # สีส้ม
                on_press: root.undo_last()

            SmoothButton:
                text: "ล้างทั้งหมด"
                bg_color: (0.9, 0.3, 0.23, 1) # สีแดง
                on_press: root.clear_all()

        # ── ปุ่มสร้าง QR ──
        SmoothButton:
            text: "สร้าง QR Code"
            bg_color: (0.18, 0.8, 0.44, 1) # สีเขียว
            font_size: 18
            height: 55
            on_press: root.make_qr()

        # ── ภาพ QR ──
        Image:
            id: qr_image
            size_hint: (1, 1)

        # ── ข้อมูล QR path ──
        Label:
            id: path_label
            text: "พร้อมใช้งาน"
            font_size: 12
            size_hint_y: None
            height: 20
            color: (0.5, 0.5, 0.5, 1)
            text_size: self.width, self.height
            halign: 'center'
            valign: 'middle'
            shorten: True
            shorten_from: 'left'
'''

Builder.load_string(KV)

# ลำดับโน้ตจากต่ำไปสูง (X = หยุดพัก อยู่ท้ายสุด)
NOTE_LIST = [
    'C3', 'C#3', 'D3', 'D#3', 'E3', 'F3', 'F#3',
    'G3', 'G#3', 'A3', 'A#3', 'B3', 'C4', 'C#4',
    'D4', 'D#4', 'E4', 'F4', 'F#4', 'G4', 'G#4',
    'A4', 'A#4', 'B4', 'C5', 'C#5', 'D5', 'D#5',
    'E5', 'F5', 'F#5', 'G5', 'G#5', 'A5', 'A#5',
    'B5', 'X'
]
NOTE_ORDER = {n: i for i, n in enumerate(NOTE_LIST)}

_VALID_NAMES = {'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'}
_FLAT_TO_SHARP = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}


def parse_sequence_text(text):
    """แปลงสตริงโน้ต เช่น "C4:4,E4+G4:2.,X:8" เป็น [(chord, dur), ...]
    รับช่องว่าง/ขึ้นบรรทัดใหม่ได้ ตัวพิมพ์เล็กได้ และแปลงแฟลตเป็นชาร์ปให้
    ถ้ารูปแบบผิดจะ raise ValueError พร้อมข้อความบอกตำแหน่งที่ผิด"""
    items = []
    for token in re.sub(r"\s+", "", text).split(","):
        if not token:
            continue
        name, _, dur = token.partition(":")
        dur = dur or "4"
        if not re.fullmatch(r"\d+\.?", dur) or float(dur.rstrip(".")) <= 0:
            raise ValueError(f"ความยาวโน้ตไม่ถูกต้อง: '{token}'")

        if name.upper() == "X":
            chord = "X"
        else:
            notes = []
            for part in name.split("+"):
                m = re.fullmatch(r"([A-Ga-g])([#b]?)(\d)", part)
                if not m:
                    raise ValueError(f"ชื่อโน้ตไม่ถูกต้อง: '{part or token}'")
                letter, acc, octave = m.group(1).upper(), m.group(2), m.group(3)
                note = letter + acc
                if acc == "b":
                    note = _FLAT_TO_SHARP.get(note)
                if note not in _VALID_NAMES:
                    raise ValueError(f"ไม่รู้จักโน้ต: '{part}'")
                notes.append(note + octave)
            chord = "+".join(notes)
        items.append((chord, dur))
    return items


# ==========================================
# หน้าจอหลัก: สร้าง QR Code โน้ตเพลง
# ==========================================
class GenerateScreen(Screen):
    NORMAL_COLOR = (1, 1, 1, 1)
    NORMAL_TEXT_COLOR = (0.1, 0.1, 0.1, 1)
    REST_COLOR = (0.9, 0.3, 0.3, 1)
    REST_TEXT_COLOR = (1, 1, 1, 1)
    SELECTED_COLOR = (0.18, 0.8, 0.44, 1)  # สีเขียว = กำลังถูกเลือกอยู่ (รอทำคอร์ด)
    SELECTED_TEXT_COLOR = (1, 1, 1, 1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pending_notes = []  # โน้ตที่เลือกไว้ ณ ขณะนี้ (หลายตัว = คอร์ด)
        self.note_buttons = {}   # เก็บ reference ปุ่มแต่ละตัว เพื่อ toggle สี
        self.sequence = []
        self._syncing = False    # กัน loop ตอนโปรแกรมเป็นคนตั้งข้อความในช่องเอง
        self.last_qr_path = None
        Clock.schedule_once(self._setup_grids, 0)

    def _setup_grids(self, dt):
        # ── ช่องโน้ต: พิมพ์/วางแล้วอ่านเข้า sequence ทันที ──
        self.ids.sequence_input.bind(text=self._on_sequence_text)

        # ── ตั้งค่าการย่อภาพ QR ให้พอดีกรอบ (รองรับทั้ง Kivy ใหม่และเก่า) ──
        qr_img = self.ids.qr_image
        if 'fit_mode' in qr_img.properties():
            qr_img.fit_mode = 'contain'
        else:
            qr_img.allow_stretch = True
            qr_img.keep_ratio = True

        # ── สร้างปุ่มโน้ต ──
        notes_grid = self.ids.notes_grid
        for n in NOTE_LIST:
            is_rest = (n == 'X')
            btn = Button(
                text=n,
                font_size=12,
                background_normal='',
                background_color=self.REST_COLOR if is_rest else self.NORMAL_COLOR,
                color=self.REST_TEXT_COLOR if is_rest else self.NORMAL_TEXT_COLOR,
                size_hint=(1, None), height=40
            )
            btn.bind(on_press=self.select_note)
            notes_grid.add_widget(btn)
            self.note_buttons[n] = btn

        # ── สร้างปุ่มจังหวะ ──
        duration_map = {
            '1(กลม)': '1',
            '2(ครึ่ง)': '2',
            '4(ดำ)': '4',
            '8(เขบ็ต1)': '8',
            '16(เขบ็ต2)': '16',
        }
        dur_grid = self.ids.dur_grid
        for label_text, val in duration_map.items():
            btn = Button(
                text=label_text,
                font_size=12,
                background_normal='',
                background_color=(0.2, 0.6, 0.86, 1),
                color=(1, 1, 1, 1)
            )
            btn.bind(on_press=lambda inst, v=val: self.select_duration(v))
            dur_grid.add_widget(btn)

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────
    def _update_sequence_label(self):
        """อัปเดตข้อความในช่องโน้ตให้ตรงกับ sequence (รูปแบบเดียวกับที่ใส่ใน QR)"""
        self._syncing = True
        try:
            self.ids.sequence_input.text = ",".join(f"{n}:{d}" for n, d in self.sequence)
        finally:
            self._syncing = False

    def _on_sequence_text(self, instance, text):
        """ผู้ใช้พิมพ์/วางข้อความในช่องโน้ต -> อ่านเป็น sequence"""
        if self._syncing:
            return
        try:
            self.sequence = parse_sequence_text(text)
        except ValueError as e:
            # ยังพิมพ์ไม่เสร็จ/รูปแบบผิด: เก็บ sequence เดิมไว้ก่อน แล้วแจ้งเตือน
            self._set_status(str(e), color=(0.9, 0.3, 0.23, 1))
            return
        if self.sequence:
            self._set_status(f"อ่านโน้ตได้ {len(self.sequence)} ชุด -> กดสร้าง QR Code ได้เลย",
                             color=(0.18, 0.8, 0.44, 1))
        else:
            self._set_status("เลือกตัวโน้ต (แตะหลายตัว = คอร์ด, X=หยุดพัก)")

    def _set_status(self, msg, color=(0.2, 0.6, 0.86, 1)):
        self.ids.status_label.text = msg
        self.ids.status_label.color = color

    def _set_note_selected(self, note, selected):
        btn = self.note_buttons.get(note)
        if btn is None:
            return
        if selected:
            btn.background_color = self.SELECTED_COLOR
            btn.color = self.SELECTED_TEXT_COLOR
        elif note == 'X':
            btn.background_color = self.REST_COLOR
            btn.color = self.REST_TEXT_COLOR
        else:
            btn.background_color = self.NORMAL_COLOR
            btn.color = self.NORMAL_TEXT_COLOR

    def _clear_pending_notes(self):
        for n in self.pending_notes:
            self._set_note_selected(n, False)
        self.pending_notes = []

    # ──────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────
    def select_note(self, instance):
        note = instance.text

        if note == 'X':
            # หยุดพัก (X) เล่นพร้อมกับโน้ตอื่นไม่ได้ -> เลือก X เดี่ยวๆ เสมอ
            already_selected = (self.pending_notes == ['X'])
            self._clear_pending_notes()
            if not already_selected:      # แตะ X ซ้ำ = ยกเลิกการเลือก (เหมือนโน้ตอื่น)
                self.pending_notes = ['X']
                self._set_note_selected('X', True)
        else:
            # ถ้ามี X ค้างอยู่ ให้ล้างออกก่อน เพราะจะเปลี่ยนไปเลือกโน้ตจริงแทน
            if 'X' in self.pending_notes:
                self._set_note_selected('X', False)
                self.pending_notes.remove('X')

            if note in self.pending_notes:
                # แตะซ้ำ = เอาออกจากคอร์ดที่กำลังเลือก
                self.pending_notes.remove(note)
                self._set_note_selected(note, False)
            else:
                self.pending_notes.append(note)
                self._set_note_selected(note, True)
                # เรียงจากเสียงต่ำไปสูง เพื่อให้คอร์ดเดียวกันได้ข้อมูลเหมือนกันเสมอ
                self.pending_notes.sort(key=NOTE_ORDER.get)

        if self.pending_notes:
            display = "+".join(self.pending_notes)
            if self.pending_notes == ['X']:
                hint = "เลือกจังหวะเพื่อบันทึก"
            else:
                hint = "แตะเพิ่มเพื่อทำคอร์ด หรือเลือกจังหวะเพื่อบันทึก"
            self._set_status(
                f"เลือก '{display}' แล้ว -> {hint}",
                color=(0.18, 0.8, 0.44, 1)  # สีเขียว
            )
        else:
            self._set_status(
                "เลือกตัวโน้ต (แตะหลายตัว = คอร์ด, X=หยุดพัก)",
                color=(0.2, 0.6, 0.86, 1)
            )

    def select_duration(self, value):
        if not self.pending_notes:
            self._set_status("กรุณาเลือกตัวโน้ตก่อน!", color=(0.9, 0.3, 0.23, 1))  # สีแดง
            return

        chord = "+".join(self.pending_notes)
        self.sequence.append((chord, value))
        self._clear_pending_notes()
        self._update_sequence_label()
        self._set_status(
            f"บันทึกแล้ว {len(self.sequence)} ชุดโน้ต -> เลือกโน้ตถัดไป",
            color=(0.2, 0.6, 0.86, 1)  # สีฟ้า
        )

    def undo_last(self):
        if self.pending_notes:
            self._clear_pending_notes()
            self._set_status("ยกเลิกการเลือกโน้ตแล้ว", color=(0.95, 0.61, 0.07, 1))
        elif self.sequence:
            removed = self.sequence.pop()
            self._update_sequence_label()
            self._set_status(f"ลบ '{removed[0]}:{removed[1]}' ออกแล้ว", color=(0.95, 0.61, 0.07, 1))
        else:
            self._set_status("ไม่มีอะไรให้ยกเลิก", color=(0.9, 0.3, 0.23, 1))

    def clear_all(self):
        self.sequence.clear()
        self._clear_pending_notes()
        self._update_sequence_label()
        self.ids.qr_image.source = ''
        self.ids.path_label.text = ''
        self.last_qr_path = None
        self._set_status("ล้างข้อมูลทั้งหมดแล้ว", color=(0.9, 0.3, 0.23, 1))

    def make_qr(self):
        try:
            self.sequence = parse_sequence_text(self.ids.sequence_input.text)
        except ValueError as e:
            self._show_popup("โน้ตในช่องไม่ถูกต้อง", str(e))
            return

        if not self.sequence:
            self._show_popup("ข้อผิดพลาด", "กรุณาเพิ่มโน้ตอย่างน้อย 1 ตัวก่อนสร้าง QR Code")
            return

        if self.pending_notes:
            self._show_popup(
                "แจ้งเตือน",
                f"คุณเลือกโน้ต '{'+'.join(self.pending_notes)}' ค้างไว้\nกรุณาเลือกจังหวะ หรือกดยกเลิกก่อนสร้าง QR"
            )
            return

        # รูปแบบข้อมูล: "C4:4,E4+G4:2,X:8"  (, = คั่นชุดโน้ต, + = คอร์ด, X = พัก)
        data = ",".join(f"{n}:{d}" for n, d in self.sequence)

        qr_folder = os.path.join(BASE_DIR, "output_qr")
        os.makedirs(qr_folder, exist_ok=True)

        # ใส่มิลลิวินาทีด้วย กันชื่อไฟล์ซ้ำเมื่อกดสร้างหลายครั้งในวินาทีเดียวกัน
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        file_name = os.path.join(qr_folder, f"song_qr_{timestamp}.png")

        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(file_name)

            self.ids.qr_image.source = file_name
            self.ids.qr_image.reload()

            self.last_qr_path = file_name
            self.ids.path_label.text = f"บันทึกที่: {file_name}"
            self._set_status(
                f"สร้าง QR สำเร็จ! ({len(self.sequence)} ชุดโน้ต)",
                color=(0.18, 0.8, 0.44, 1)
            )

        except DataOverflowError:
            self._show_popup(
                "ข้อมูลยาวเกินไป",
                "โน้ตมากเกินกว่าที่ QR Code หนึ่งใบจะเก็บได้\nกรุณาแบ่งเพลงเป็นหลายใบ"
            )
        except Exception as e:
            self._show_popup("เกิดข้อผิดพลาด", str(e))

    def _show_popup(self, title, message):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        lbl = Label(text=message, halign='center', valign='middle', color=(1, 1, 1, 1))
        # ให้ข้อความตัดบรรทัดตามความกว้างจริงของ popup
        lbl.bind(size=lambda inst, size: setattr(inst, 'text_size', size))
        content.add_widget(lbl)
        ok_btn = Button(
            text="ตกลง", size_hint=(1, None), height=45,
            background_normal='', background_color=(0.2, 0.55, 0.85, 1)
        )
        content.add_widget(ok_btn)

        # ไม่ต้องระบุ title_font: Popup ใช้ DEFAULT_FONT ที่ลงทะเบียนไว้แล้ว
        popup = Popup(title=title, content=content, size_hint=(0.85, None), height=220)
        ok_btn.bind(on_press=popup.dismiss)
        popup.open()


# ==========================================
# เริ่มต้นแอป
# ==========================================
class QRMakerApp(App):
    def build(self):
        self.title = "QR Music Maker"
        sm = ScreenManager()
        sm.add_widget(GenerateScreen(name='generate'))
        return sm


if __name__ == '__main__':
    QRMakerApp().run()