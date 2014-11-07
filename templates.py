#define dummy /*
# This comment's goal is to be able to view the file as a C file as well as a Python file
# vim: ft=c
def write(filename, template, **tpl_vars):
    with open(filename, "w") as outf:
        outf.write(template % tpl_vars)

MAIN_PYX = """
import sys

print dir(sys)
"""

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

//static PyMethodDef methods[] = {
//    {0, 0, 0, 0}
//};

extern const int PAYLOAD_LEN;
extern const char PAYLOAD[%(len_payload)d];

typedef struct {
    COOKIE *cookie;
    TOC *toc;
    TOC *tocend;
	PyObject *marshal_loads;
	PyObject *__main__;
    char tmp_path[PATH_MAX];
    char pkg_path[MAX_PATH];
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
    char cmd[MAX_PATH + 40];
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
    char cmd[MAX_PATH + 40];
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

    // This should replace the call to Py_InitModule("%(module_name)s", methods);
    module = PyImport_ExecCodeModule("%(module_name)s", code);

    Py_CLEAR(code);
}

PyMODINIT_FUNC init%(module_name)s()
{
    ArchiveInfo archive_info;
    TOC *ptoc;
	PyObject *marshal;
	PyObject *marshaldict;

    // TODO use a more generic (less windows) tmp path
    // TODO find some way to delete this folder at exit time
    pyi_get_temp_path(archive_info.tmp_path);
    mkdir(archive_info.tmp_path);
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

    FOREACH_TOC (ptoc, archive_info.toc, archive_info.tocend) {
        switch (ptoc->typcd) {
        case ARCHIVE_ITEM_PYSOURCE:
            if (strncmp(ptoc->name, "%(entrymodule)s", sizeof("%(entrymodule)s"))) {
                // Not our entry module: probably a bootstrap file
                run_script(&archive_info, ptoc);
            } else {
                // This is our entry module
                import_exec_module(&archive_info, ptoc);
            }
            break;
        }
    }

    //Py_InitModule("%(module_name)s", methods);
}
"""

PAYLOAD_C = """const char PAYLOAD[%(len_payload)d] = {
    %(payload)s
};
const int PAYLOAD_LEN = sizeof(PAYLOAD);
"""
