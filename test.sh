#!/bin/sh -xe
pyinstaller loader.spec
pyinstaller my_module.spec
#( cd dist && ./loader )
