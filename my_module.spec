# -*- mode: python -*-
# vim: ft=python
import glob


class PYD(EXE):
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get('name', None)
        self.entrymodule = kwargs.get('entrymodule', os.path.splitext(self.name)[0])

        EXE.__init__(self, *args, **kwargs)

    def _bootloader_file(self, module_name, pkg_path):
        try:
            # use setuptools if available
            from setuptools import Distribution, Extension
            from setuptools.command.build_ext import build_ext
        except ImportError:
            from distutils.core import Distribution, Extension
            from distutils.command.build_ext import build_ext

        import Cython.Compiler.Version
        from Cython.Build import cythonize

        if os.getcwd() not in sys.path:
            sys.path.append(os.getcwd())
        import templates

        logger.info("building with Cython " + Cython.Compiler.Version.version)

        module_path = os.path.join(WORKPATH, "build" + module_name)
        if not os.path.exists(module_path):
            os.makedirs(module_path)
        files = [
            (os.path.join(module_path, module_name + ".c"), templates.MAIN_C),
            (os.path.join(module_path, "payload.c"), templates.PAYLOAD_C),
        ]

        with open(pkg_path, 'rb') as pkg_file:
            payload = pkg_file.read()

        tpl_vars = {
            'module_name': module_name,
            'payload': ',\n    '.join([
                ', '.join([
                    '0x%02x' % (ord(i),)
                    for i in payload[16*j:16*(j+1)]
                ])
                for j in range((len(payload) + 15) / 16)
             ]),
            'len_payload': len(payload),
            'entrymodule': self.entrymodule,
        }
        for path, tpl in files:
            templates.write(path, tpl, **tpl_vars)

        libraries = []
        macros = []

        bootloader_files = []
        bootloader_files += glob.glob("bootloader/zlib/*.c")
        bootloader_files += glob.glob("bootloader/common/*.c")

        if self.debug:
            macros.append(('DEBUG', None))

        if is_win:
            libraries.append('wsock32')
            macros.append(('WIN32', None))
            macros.append(('_CRT_SECURE_NO_WARNINGS', None))
            bootloader_files.append('bootloader/windows/utils.c')

        extensions = cythonize([
            Extension(module_name,
                      include_dirs=["bootloader/zlib", "bootloader/common"],
                      sources=[path for path, tpl in files] + bootloader_files,
                      libraries=libraries,
                      define_macros=macros),
        ])
        dist = Distribution({'name': module_name, 'ext_modules': extensions})
        dist.package_dir = module_path
        cmd = build_ext(dist)
        cmd.build_lib = module_path
        cmd.build_temp = module_path
        cmd.ensure_finalized()
        cmd.run()

        return os.path.join(module_path, module_name + ".pyd")

    def assemble(self):
        logger.info("building PYD from %s", os.path.basename(self.out))
        trash = []
        if not os.path.exists(os.path.dirname(self.name)):
            os.makedirs(os.path.dirname(self.name))
        outf = open(self.name, 'wb')
        exe = self._bootloader_file(os.path.splitext(os.path.basename(self.name))[0], self.pkg.name)
        if config['hasRsrcUpdate'] and (self.icon or self.versrsrc or
                                        self.resources):
            tmpnm = tempfile.mktemp()
            shutil.copy2(exe, tmpnm)
            os.chmod(tmpnm, 0755)
            if self.icon:
                icon.CopyIcons(tmpnm, self.icon)
            if self.versrsrc:
                versioninfo.SetVersion(tmpnm, self.versrsrc)
            for res in self.resources:
                res = res.split(",")
                for i in range(1, len(res)):
                    try:
                        res[i] = int(res[i])
                    except ValueError:
                        pass
                resfile = res[0]
                restype = resname = reslang = None
                if len(res) > 1:
                    restype = res[1]
                if len(res) > 2:
                    resname = res[2]
                if len(res) > 3:
                    reslang = res[3]
                try:
                    winresource.UpdateResourcesFromResFile(tmpnm, resfile,
                                                        [restype or "*"],
                                                        [resname or "*"],
                                                        [reslang or "*"])
                except winresource.pywintypes.error, exc:
                    if exc.args[0] != winresource.ERROR_BAD_EXE_FORMAT:
                        logger.exception(exc)
                        continue
                    if not restype or not resname:
                        logger.error("resource type and/or name not specified")
                        continue
                    if "*" in (restype, resname):
                        logger.error("no wildcards allowed for resource type "
                                     "and name when source file does not "
                                     "contain resources")
                        continue
                    try:
                        winresource.UpdateResourcesFromDataFile(tmpnm,
                                                             resfile,
                                                             restype,
                                                             [resname],
                                                             [reslang or 0])
                    except winresource.pywintypes.error, exc:
                        logger.exception(exc)
            trash.append(tmpnm)
            exe = tmpnm
        exe = checkCache(exe, strip=self.strip, upx=self.upx)
        self.copy(exe, outf)
        #if self.append_pkg:
        #    logger.info("Appending archive to EXE %s", self.name)
        #    self.copy(self.pkg.name, outf)
        #else:
        #    logger.info("Copying archive to %s", self.pkgname)
        #    shutil.copy2(self.pkg.name, self.pkgname)
        outf.close()
        os.chmod(self.name, 0755)
        guts = (self.name, self.console, self.debug, self.icon,
                self.versrsrc, self.resources, self.strip, self.upx,
                mtime(self.name))
        assert len(guts) == len(self.GUTS)
        _save_data(self.out, guts)
        for item in trash:
            os.remove(item)
        return 1


a = Analysis(['module.py'])
pyz = PYZ(a.pure)
pyd = PYD(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='my_module.pyd',
          entrymodule='module',
          debug=False,
          strip=None,
          upx=True,
          console=True,
          )
