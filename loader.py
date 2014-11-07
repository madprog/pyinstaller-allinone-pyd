import os

my_module = __import__('my_module')

if 'test' in dir(my_module):
    my_module.test()
