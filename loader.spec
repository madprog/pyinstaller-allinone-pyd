# -*- mode: python -*-
a = Analysis(['loader.py'])
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='loader.exe',
          debug=False,
          strip=None,
          upx=True,
          console=True,
          )

