pyinstaller-allinone-pyd
========================

How to use this code?
---------------------

This repository contains an example of how to create a binary python module with all its dependencies embedded in it.
In order to make this magic recipe, you will need on the **building machine**:
- [PyInstaller][pyi]: `pip install pyinstaller`
- [Cython][pyx]: `pip install cython`
- One of these, depending on your operating system (Cython needs this to compile the C source):
  - gcc for Linux
  - [Visual Studio 2008][vs2008] for Windows
  - XCode for MacOS X

You then just run `pyinstaller loader.spec` and `pyinstaller my_module.spec` to build the binaries,
and you will have in the `dist` folder:
- `loader` and `my_module.so` on Linux
- `loader.exe` and `my_module.pyd` on Windows
- Probably the same as Linux on MacOS X, but I yet have to test it.

Note that there are issues with some libraries like lupa or PySFML which import relative binaries.

What are these files?
---------------------

`loader.py` is an example of a program that will be able to load such a module.
Note that it will use the `__import__` function to load the module, as PyInstaller won't detect this as a dependency.

`loader.spec` describes to PyInstaller how to build `loader` or `loader.exe` from `loader.py`.

`module.py` is an example of the contents of our module.
It contains some test functions which check that the dependencies are present and that they can be called.

`my_module.spec` describes to PyInstaller how to build the binary module.
It defines a new class `PYD` which is very similar to PyInstaller's `EXE` class in [build.py](//github.com/pyinstaller/pyinstaller/blob/master/PyInstaller/build.py#L1078)

[pyi]: //github.com/pyinstaller/pyinstaller
[pyx]: //github.com/cython/cython
[vs2008]: //go.microsoft.com/?linkid=7729279


What are the differences between `EXE` and `PYD`?
-------------------------------------------------

### Generated files

#### EXE

A pre-compiled EXE file is copied, and the CArchive is appended at its end.

#### PYD

Two C files are generated and compiled with the sources contained in the bootloader folder.
The first one contains some extraction and loading code, including the `initmy_module` function.
The second one contains a huge binary string which is the CArchive.

In `initmy_module`, `my_module` must be the same as the name of the file (`my_module.pyd` or `my_module.so`).
This is why we need to compile the shared module.

### Extracted files

#### EXE

After extraction, the EXE file will run itself again, and wait for the second process end to remove all the files.

#### PYD

When the dynamic module is loaded, the temporary folder is created.
Then, Python calls the `initmy_module` function, which will extract the binary modules to the temporary folder
and load the `module.py` module from the CArchive, but replace its name by `my_module`.
When `initmy_module` returns, `__import__` is satisfied: there is a `my_module` entry in the modules table.

When the shared module is unloaded, a destructor method is called which will remove the temporary folder.

However, on Windows, some files may be still in use, and the destruction would fail.
It is the case for example with the pybonjour library: there is a handle kept on the ctypes.pyd file.
This is why another process is ran: a temporary batch script which exits only once it has successfully removed the folder.

Beware however: the batch subprocess **will keep running** as long as the handle is not removed.
This means that if you unload the module and reload it a large amount of times within the same python process,
you will have a lot of cleanup batch processes and another lot of ctypes.pyd temporary files,
which can lead in known problems of "disk is full" and "process id table is full".
