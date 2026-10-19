[app]

# ── ข้อมูลแอป ────────────────────────────────────────────────────────────────
title           = QR Music Player
package.name    = qrmusicplayer
package.domain  = com.qrmusic
version         = 1.0.0

# ── ซอร์สโค้ด ────────────────────────────────────────────────────────────────
source.dir      = .
source.include_exts = py,png,jpg,jpeg,kv,ttf,atlas,json
source.exclude_dirs = .git,__pycache__,tests,output_midi,bin,.buildozer
main            = main.py

# ── Dependencies ─────────────────────────────────────────────────────────────
requirements =
    python3==3.10.12,
    hostpython3==3.10.12,
    kivy,
    Pillow,
    pyzbar,
    zbarcam,
    xcamera,
    libzbar,
    libiconv
# ── ไอคอน & Splash ──────────────────────────────────────────────────────────
presplash.color   = #F2F4FA

# ── Android Permissions ──────────────────────────────────────────────────────
android.permissions =
    CAMERA,
    READ_EXTERNAL_STORAGE,
    WRITE_EXTERNAL_STORAGE,
    INTERNET

# ── Android SDK / NDK ────────────────────────────────────────────────────────
android.minapi      = 24
android.targetapi   = 33
android.ndk         = 25b
android.ndk_api     = 24
android.archs       = arm64-v8a, armeabi-v7a

# ── Android Build ────────────────────────────────────────────────────────────
android.enable_androidx    = True
android.accept_sdk_license = True

# ── หน้าจอ ──────────────────────────────────────────────────────────────────
orientation = portrait
fullscreen  = 0

# ── App Entry ────────────────────────────────────────────────────────────────
android.entrypoint = org.kivy.android.PythonActivity

# ── P4A ─────────────────────────────────────────────────────────────────────
p4a.branch = master


[buildozer]
log_level  = 2
warn_on_root = 1
