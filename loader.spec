# -*- mode: python -*-
a = Analysis(['loader.py'])
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='loader' + (is_win and '.exe' or ''),
          debug=False,
          strip=None,
          upx=True,
          console=True,
          )

