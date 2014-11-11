def test_pybonjour():
    import pybonjour
    print pybonjour.DNSServiceConstructFullName(regtype="_test._tcp", domain="local")

def test_pysfml():
    import sfml

    for video_mode in sfml.VideoMode.get_fullscreen_modes():
        print (video_mode.width, video_mode.height, video_mode.bpp)

def test_lupa():
    import lupa
    from lupa import LuaRuntime

    lua = LuaRuntime(unpack_returned_tuples=True)
    print lua.eval('1+1')

    lua_func = lua.eval('function(f, n) return f(n) end')
    def py_add1(n): return n+1
    print lua_func(py_add1, 2)

    print lua.eval('python.eval(" 2 ** 2 ")') == 4
    print lua.eval('python.builtins.str(4)') == '4'

def test():
    import sys
    import traceback

    tests = {
        'pybonjour': test_pybonjour,
        'PySFML':    test_pysfml,
        'lupa':      test_lupa,
    }

    class FakeStdout:
        def __init__(self):
            self.text = ''

        def write(self, text):
            self.text += text

    real_stdout = sys.stdout
    real_stderr = sys.stderr
    for name in tests:
        print "Testing %s" % (name,),
        fake_stdout = sys.stdout = sys.stderr = FakeStdout()
        try:
            tests[name]()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            print "OK"
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            print "KO"
            sys.stdout.write(traceback.format_exc())
        sys.stdout.write(fake_stdout.text)
        print
