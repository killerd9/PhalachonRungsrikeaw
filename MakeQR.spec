# -*- mode: python ; coding: utf-8 -*-
import os
try:
    from kivy_deps import sdl2, glew
    dep_trees = [Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)]
except Exception:
    dep_trees = []

datas = []
if os.path.exists('ChakraPetch-Bold.ttf'):
    datas.append(('ChakraPetch-Bold.ttf', '.'))

a = Analysis(
    ['MakeQR.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['qrcode', 'PIL', 'win32timezone'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MakeQR',
    console=False,          # ไม่โชว์หน้าต่างดำ (ถ้าต้องดู error ให้เปลี่ยนเป็น True)
    # icon='icon.ico',      # ถ้ามีไอคอน เอา # ออก
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *dep_trees,
    name='MakeQR',
)
