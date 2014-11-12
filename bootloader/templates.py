#define dummy /*
# This comment's goal is to be able to view the file as a C file as well as a Python file
# vim: ft=c
def write(filename, template, **tpl_vars):
    with open(filename, "w") as outf:
        outf.write(template % tpl_vars)

MAIN_C = """/**/
#include <Python.h>

#ifdef WIN32
// TODO verify windows includes
    #include <winsock.h>  // ntohl
#else
    #include <limits.h>  // PATH_MAX - not available on windows.
    #include <netinet/in.h>  // ntohl
    #include <sys/stat.h>  // fchmod
#endif
#include <stddef.h>  // ptrdiff_t
#include <stdio.h>

/* 
 * Use Sean's Tool Box -- public domain -- http://nothings.org/stb.h. 
 * 
 * This toolbox wraps some standard functions in a portable way and
 * contains some additional utility fuctions.
 * (string, file, utf8, etc.)
 *
 * All functions starting with 'stb_' prefix are from this toolbox.
 * To use this toolbox just do:
 *
 * #include "stb.h"
 */
#define STB_DEFINE 1
#define STB_NO_REGISTRY 1  // Disable registry functions.
#define STB_NO_STB_STRINGS 1  // Disable config read/write functions.

/* PyInstaller headers. */
#include "zlib.h"
#include "stb.h"
#include "pyi_global.h"
#include "pyi_archive.h"
#include "pyi_utils.h"

#define FOREACH_TOC(ptoc, tocstart, tocend)  for (\
    (ptoc) = (tocstart); \
    (ptoc) < (tocend); \
    (ptoc) = (TOC*)((char *)(ptoc) + ntohl((ptoc)->structlen)))

extern const int PAYLOAD_LEN;
extern const char PAYLOAD[%(len_payload)d];

typedef struct {
    COOKIE *cookie;
    TOC *toc;
    TOC *tocend;
	PyObject *marshal_loads;
	PyObject *__main__;
    char tmp_path[PATH_MAX];
    char pkg_path[PATH_MAX];
} ArchiveInfo;

/*
 * Extract an archive entry.
 * Returns pointer to the data (must be freed).
 */
unsigned char *extract(ArchiveInfo *archive_info, TOC *ptoc)
{
	unsigned char *data;
	unsigned char *tmp;

	data = (unsigned char *)malloc(ntohl(ptoc->len));
	if (data == NULL) {
		OTHERERROR("Could not allocate read buffer\\n");
		return NULL;
	}
	memcpy(data, PAYLOAD + ntohl(ptoc->pos), ntohl(ptoc->len));

	if (ptoc->cflag == '\\1') {
		tmp = decompress(data, ptoc);
		free(data);
		data = tmp;
		if (data == NULL) {
			OTHERERROR("Error decompressing %%s\\n", ptoc->name);
			return NULL;
		}
	}
	return data;
}

/*
 * Extract from the archive and copy to the filesystem.
 * The path is relative to the directory the archive is in.
 */
int extract2fs(ArchiveInfo *archive_info, TOC *ptoc)
{
	FILE *out;
	unsigned char *data = extract(archive_info, ptoc);

	out = pyi_open_target(archive_info->tmp_path, ptoc->name);

	if (out == NULL)  {
		FATALERROR("%%s could not be extracted!\\n", ptoc->name);
		return -1;
	} else {
		fwrite(data, ntohl(ptoc->ulen), 1, out);
#ifndef WIN32
		fchmod(fileno(out), S_IRUSR | S_IWUSR | S_IXUSR);
#endif
        fclose(out);
	}
	free(data);

    return 0;
}

void dump_pkg(const char *path) {
    FILE *fp;

    fp = fopen(path, "wb");
    fwrite(PAYLOAD, PAYLOAD_LEN, 1, fp);
    fclose(fp);
}

void import_module(ArchiveInfo *archive_info, TOC *ptoc) {
    unsigned char *modbuf;
    PyObject *co;
    PyObject *mod;

    modbuf = extract(archive_info, ptoc);

    /* .pyc/.pyo files have 8 bytes header. Skip it and load marshalled
     * data form the right point.
     */
    co = PyObject_CallFunction(archive_info->marshal_loads, "s#", modbuf+8, ntohl(ptoc->ulen)-8);
    mod = PyImport_ExecCodeModule(ptoc->name, co);

    /* Check for errors in loading */
    if (mod == NULL) {
        FATALERROR("mod is NULL - %%s", ptoc->name);
    }
    if (PyErr_Occurred())
    {
        PyErr_Print();
        PyErr_Clear();
    }

    free(modbuf);
}

void add_tmppath_to_syspath(ArchiveInfo *archive_info) {
    int rc;
    char cmd[PATH_MAX + 40];
    snprintf(cmd, sizeof(cmd), "import sys\\nsys.path.append(r'%%s')\\n", archive_info->tmp_path);
    rc = PyRun_SimpleString(cmd);
    if (rc != 0)
    {
        FATALERROR("Error in command: %%s\\n", cmd);
    }
}

void install_zlib(ArchiveInfo *archive_info, TOC *ptoc) {
    int rc;
    int zlibpos = ntohl(ptoc->pos);
    char cmd[PATH_MAX + 40];
    snprintf(cmd, sizeof(cmd), "sys.path.append(r'%%s?%%d')\\n", archive_info->pkg_path, zlibpos);
    rc = PyRun_SimpleString(cmd);
    if (rc != 0)
    {
        FATALERROR("Error in command: %%s\\n", cmd);
    }
}

void run_script(ArchiveInfo *archive_info, TOC *ptoc) {
    int rc;
	unsigned char *data;
	char buf[PATH_MAX];
	PyObject *__file__;

    /* Get data out of the archive.  */
    data = extract(archive_info, ptoc);
    /* Set the __file__ attribute within the __main__ module,
       for full compatibility with normal execution. */
    snprintf(buf, sizeof(buf), "%%s.py", ptoc->name);
    __file__ = PyString_FromStringAndSize(buf, strlen(buf));
    PyObject_SetAttrString(archive_info->__main__, "__file__", __file__);
    Py_DECREF(__file__);
    /* Run it */
    rc = PyRun_SimpleString((char *)data);
    /* log errors and abort */
    if (rc != 0) {
        FATALERROR("LOADER: RC: %%d from %%s\\n", rc, ptoc->name);
    }
    free(data);
}

void import_exec_module(ArchiveInfo *archive_info, TOC *ptoc) {
	unsigned char *data;
	char buf[PATH_MAX];
	PyObject *code;
    PyObject *module;

    /* Get data out of the archive.  */
    data = extract(archive_info, ptoc);
    /* Retrieve the __file__ attribute */
    snprintf(buf, sizeof(buf), "%%s.py", ptoc->name);
    /* Compile it */
    code = Py_CompileString(data, buf, Py_file_input);

    free(data);

    // This should replace the call to Py_InitModule("%(module_name)s", methods);
    module = PyImport_ExecCodeModule("%(module_name)s", code);

    Py_CLEAR(code);
}

static ArchiveInfo archive_info = { NULL, NULL, NULL, NULL, NULL, "", "" };

PyMODINIT_FUNC init%(module_name)s()
{
    TOC *ptoc;
	PyObject *marshal;
	PyObject *marshaldict;
    PyObject *prefix = PySys_GetObject("prefix");
    PyObject *tmp_prefix = PyString_FromStringAndSize(archive_info.tmp_path, strlen(archive_info.tmp_path));

    if (strlen(archive_info.tmp_path) == 0) {
        Py_FatalError("Temporary folder was not created");
    }

    pyi_setenv("_MEIPASS2", archive_info.tmp_path); //Bootstrap sets sys._MEIPASS, plugins rely on it

    snprintf(archive_info.pkg_path, sizeof(archive_info.pkg_path), "%%s%%s%(module_name)s.pkg", archive_info.tmp_path, archive_info.tmp_path[strlen(archive_info.tmp_path) - 1] == PYI_SEP ? "" : PYI_SEPSTR);
    dump_pkg(archive_info.pkg_path);

    archive_info.cookie = (COOKIE *)(PAYLOAD + PAYLOAD_LEN - sizeof(COOKIE));
    if (strncmp(archive_info.cookie->magic, "MEI\\014\\013\\012\\013\\016", 8) != 0) {
        Py_FatalError("Cookie has an invalid magic");
    }

    if (ntohl(archive_info.cookie->len) != PAYLOAD_LEN) {
        Py_FatalError("Cookie length differs from payload length");
    }
    archive_info.toc = (TOC *)(PAYLOAD + ntohl(archive_info.cookie->TOC));
    archive_info.tocend = (TOC *) (((char *)archive_info.toc) + ntohl(archive_info.cookie->TOClen));

    FOREACH_TOC (ptoc, archive_info.toc, archive_info.tocend) {
        switch (ptoc->typcd) {
        case ARCHIVE_ITEM_BINARY:
        case ARCHIVE_ITEM_DATA:
        case ARCHIVE_ITEM_ZIPFILE:
            extract2fs(&archive_info, ptoc);
            break;

        case ARCHIVE_ITEM_DEPENDENCY:
            //_extract_dependency(archive_pool, ptoc->name);
            break;
        }
    }

    add_tmppath_to_syspath(&archive_info);

	/* Get the Python function marshall.load
     * Here we collect some reference to PyObject that we don't dereference
     * Doesn't matter because the objects won't be going away anyway.
     */
	marshal = PyImport_ImportModule("marshal");
	marshaldict = PyModule_GetDict(marshal);
	archive_info.marshal_loads = PyDict_GetItemString(marshaldict, "loads");

    FOREACH_TOC (ptoc, archive_info.toc, archive_info.tocend) {
        switch (ptoc->typcd) {
        case ARCHIVE_ITEM_PYMODULE:
        case ARCHIVE_ITEM_PYPACKAGE:
            import_module(&archive_info, ptoc);
            break;

        case ARCHIVE_ITEM_PYZ:
            install_zlib(&archive_info, ptoc);
            break;
        }
    }

	archive_info.__main__ = PyImport_AddModule("__main__");

    prefix = PySys_GetObject("prefix"); Py_INCREF(prefix);
    tmp_prefix = PyString_FromString(archive_info.tmp_path);
    FOREACH_TOC (ptoc, archive_info.toc, archive_info.tocend) {
        switch (ptoc->typcd) {
        case ARCHIVE_ITEM_PYSOURCE:
            if (strncmp(ptoc->name, "%(entrymodule)s", sizeof("%(entrymodule)s"))) {
                // Temporarily change the prefix so that pyi_* files behave correctly
                PySys_SetObject("prefix", tmp_prefix);

                // Not our entry module: probably a bootstrap file
                run_script(&archive_info, ptoc);

                // Restore previous prefix so that the rest of the application behaves correctly
                PySys_SetObject("prefix", prefix);
            } else {
                // This is our entry module
                import_exec_module(&archive_info, ptoc);
            }
            break;
        }
    }
    Py_DECREF(tmp_prefix);
    Py_DECREF(prefix);
}

#ifdef WIN32
void onPydLoad();
void onPydUnload();

BOOL WINAPI DllMain(_In_ HINSTANCE hinstDLL, _In_ DWORD fdwReason, _In_ LPVOID lpvReserved) {
    switch (fdwReason) {
        case DLL_PROCESS_ATTACH: onPydLoad(); break;
        case DLL_PROCESS_DETACH: onPydUnload(); break;
    }
    return TRUE;
}
#endif

#ifdef WIN32
void onPydLoad() {
#else
void __attribute__ ((constructor)) onPydLoad() {
#endif
    if (!pyi_get_temp_path(archive_info.tmp_path)) {
        Py_FatalError("Temporary folder not created!");
    }
}

#ifdef WIN32
void onPydUnload() {
    char remover_path[PATH_MAX];
    FILE *remover = fopen(remover_path, "w");
    PROCESS_INFORMATION process_info;
    STARTUPINFO startupinfo;

    snprintf(remover_path, sizeof(remover_path), "%%s_%%s", archive_info.tmp_path, "remover.bat");
    remover = fopen(remover_path, "w");
    fprintf(remover, "@echo on\\n:loop\\nrmdir /q /s \\"%%s\\"\\nif exist \\"%%s\\" goto loop\\n( del /q /f \\"%%%%~f0\\" >nul 2>&1 & exit /b 0  )", archive_info.tmp_path, archive_info.tmp_path);
    fclose(remover);

    memset(&startupinfo, 0, sizeof(startupinfo));
    startupinfo.cb = sizeof(startupinfo);
    if (CreateProcess(NULL, remover_path, NULL, NULL, FALSE,
            NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW,
            NULL, NULL, &startupinfo, &process_info)) {
        CloseHandle(process_info.hProcess);
        CloseHandle(process_info.hThread);
    } else {
        fprintf(stderr, "Error %%d when running remover.bat\\n", GetLastError());
    }
}
#else
void __attribute__ ((destructor)) onPydUnload() {
    pyi_remove_temp_path(archive_info.tmp_path);
}
#endif
"""

PAYLOAD_C = """const char PAYLOAD[%(len_payload)d] = {
    %(payload)s
};
const int PAYLOAD_LEN = sizeof(PAYLOAD);
"""
