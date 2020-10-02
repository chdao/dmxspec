import pyaudio
import numpy as np
import sacn
import time
import signal
import os
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import wx

maxValue = 2**16
pixels = 110
bars = 35
defaultframes = 512



#Use module
p = pyaudio.PyAudio()

device_id = 17


#Open stream
stream = p.open(format = pyaudio.paInt16,
                channels = 2,
                rate = 48000,
                input = True,
                frames_per_buffer = defaultframes,
                input_device_index = 17,
                as_loopback = True)

sender = sacn.sACNsender()  # provide an IP-Address to bind to if you are using Windows and want to use multicast
sender.start()  # start the sending thread
sender.activate_output(1)  # start sending out data in the 1st universe

sender[1].destination = "10.2.20.240"

devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))


def buildDMX(dataL, dataR):
    volumelvl = volume.GetMasterVolumeLevel()
    peakL = np.abs(np.max(dataL)-np.min(dataL))/maxValue*pixels*1.5
    peakR = np.abs(np.max(dataR)-np.min(dataR))/maxValue*pixels*1.5
    dmxL = ()
    dmxR = ()
    for i in range(1, int(pixels/2)):
        if i <= int(peakL) and i < int(pixels/6):
            dmxL = dmxL + (0,127,0) # reversed color
        elif i <= int(peakL) and i > (pixels/6) and i < (pixels/3) :
            dmxL = dmxL + (0,127,127) # reversed color
        elif i <= int(peakL) and i > (pixels/3):
            dmxL = dmxL + (0,0,127) # reversed color
        else:
            dmxL = dmxL + (0,0,0)
        if i <= int(peakR) and i < int(pixels/6):
            dmxR = dmxR + (0,127,0)
        elif i <= int(peakR) and i > (pixels/6) and i < (pixels/3) :
            dmxR = dmxR + (127,127,0)
        elif i <= int(peakR) and i > (pixels/3):
            dmxR = dmxR + (127,0,0)
    dmxL = dmxL[::-1]
    dmx = dmxL + dmxR

    return(dmx)

def main():
    while True:
        data = np.fromstring(stream.read(1024),dtype=np.int16)
        dataL = data[0::2]
        dataR = data[1::2]
        time.sleep(0.01)
        (dmx) = buildDMX(dataL, dataR)
        sender[1].dmx_data = dmx
        app.MainLoop()
        frame.Show(True)
        app.MainLoop()
        


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(e)
        sender.stop()
    except:
        sender.stop()
