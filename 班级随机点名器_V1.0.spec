# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all
import webview
root = Path(SPECPATH)
datas, binaries, hiddenimports = collect_all('openpyxl')
for name in ['index.html', 'style.css', 'integrated.css', 'app.js', 'board-model.js', 'scene.js', 'dice.js', 'probability.js', 'console.js']:
    datas.append((str(root / 'board_web' / name), 'board_web'))
for directory in ['vendor', 'assets']:
    datas.append((str(root / 'board_web' / directory), 'board_web/' + directory))
a = Analysis([str(root / 'python_app.py')], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[str(Path(webview.__file__).parent / '__pyinstaller')],
             hooksconfig={}, runtime_hooks=[], excludes=['PyQt5','PyQt6','PySide2','PySide6','gi'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='班级随机点名器_V1.0',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True, upx_exclude=[],
          runtime_tmpdir=None, console=False, disable_windowed_traceback=False)
