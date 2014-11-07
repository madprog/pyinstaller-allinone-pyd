import sfml

def test():
    for i in range(sf.VideoMode.GetModesCount()):
        video_mode = sf.VideoMode.GetMode(i)
        print (video_mode.Width, video_mode.Height, video_mode.BitsPerPixel)
