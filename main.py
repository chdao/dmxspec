import pyaudio
import numpy as np
import sacn
import time
import sys
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import argparse

maxValue = 2 ** 16


def senderSetup(ip):
    sender = sacn.sACNsender()
    sender.start()
    sender[1].destination = ip
    sender.activate_output(1)
    return sender


def parse_args(choices):
    parser = argparse.ArgumentParser(
        description="DMX WiFi Sender help", prog="DMX WiFi Sender"
    )
    parser.add_argument("--ip", help="Destination DMX server")
    parser.add_argument("--id", help="Index of the soundcard")
    parser.add_argument("--list", help="List available soundcards", action="store_true")
    parser.add_argument("--multi", help="Aplitude multiplier", default="1.5")
    parser.add_argument("--rr", help="Reverse Right Channel", action="store_false")
    parser.add_argument("--rl", help="Reverse Left Channel", action="store_true")
    parser.add_argument("-p", "--pixels", help="Length of strip", default=10)
    parser.add_argument("-f", "--frames", help="Frames for pyAudio", default=512)
    parser.add_argument("--fps", help="Frame Per Second (refresh rate)", default=30)

    return parser.parse_args()


def buildDMX(dataL, dataR, olddmx):
    dmx = {}
    peakL = (
        int(np.abs(np.max(dataL)) - int(np.min(dataL)))
        / maxValue
        * pixels
        * float(args.multi)
    )
    peakR = (
        int(np.abs(np.max(dataR)) - int(np.min(dataR)))
        / maxValue
        * pixels
        * float(args.multi)
    )
    for i in range(1, pixels + 1):
        if i <= int((pixels / 2)):
            division = pixels / 6
            if i <= int(peakL) and i <= int(pixels / 6):
                dmx[i] = {
                    "r": int((i * (100 / division)) * 2.55),
                    "g": 255,
                    "b": 0,
                }

            elif i <= int(peakL) and i > (division) and i <= (division * 2):
                dmx[i] = {
                    "r": 255,
                    "g": 255 - int(((i - division) * (100 / division)) * 2.55),
                    "b": 0,
                }
            elif i <= int(peakL) and i > (division * 2):
                dmx[i] = {
                    "r": 255,
                    "g": 0,
                    "b": 0,
                }
            else:
                dmx[i] = {
                    "r": 0,
                    "g": 0,
                    "b": 0,
                }
        else:
            if i <= (int(peakR) + (division * 3)) and i <= (int(4 * division)):
                dmx[i] = {
                    "r": int(((i - (3 * division)) * (100 / division)) * 2.55),
                    "g": 255,
                    "b": 0,
                }
            elif (
                i <= (int(peakR) + (division * 3))
                and i >= int(4 * division)
                and i < int(5 * division)
            ):
                dmx[i] = {
                    "r": 255,
                    "g": 255 - int((((i) - (4 * division)) * (100 / division)) * 2.55),
                    "b": 0,
                }
            elif i <= (int(peakR + (division * 3))) and i >= (int(5 * division)):
                dmx[i] = {
                    "r": 255,
                    "g": 0,
                    "b": 0,
                }
            else:
                dmx[i] = {
                    "r": 0,
                    "g": 0,
                    "b": 0,
                }
    return dmx


def startLED(deviceid, loopback, channels, sampleRate):
    stream = p.open(
        format=pyaudio.paInt16,
        channels=int(channels),
        rate=int(sampleRate),
        input=True,
        frames_per_buffer=defaultframes,
        input_device_index=int(deviceid),
        as_loopback=loopback,
    )
    olddmx = {}
    while True:
        data = np.frombuffer(stream.read(1024), dtype=np.int16)
        dataL = data[0::2]
        dataR = data[1::2]
        (dmx) = buildDMX(dataL, dataR, olddmx)
        dmxData = ()
        rgb = ()
        if args.rl is False:
            for i in range(int(pixels / 2), 1, -1):
                rgb = (dmx[i]["r"], dmx[i]["g"], dmx[i]["b"])
                dmxData = dmxData + rgb
        else:
            for i in range(1, int(pixels / 2) + 1):
                rgb = (dmx[i]["r"], dmx[i]["g"], dmx[i]["b"])
                dmxData = dmxData + rgb
        if args.rr is True:
            for i in range((int(pixels / 2) + 1), len(dmx)):
                rgb = (
                    dmx[i]["r"],
                    dmx[i]["g"],
                    dmx[i]["b"],
                )  # this works, no exception
                dmxData = dmxData + rgb
        else:
            for i in range(len(dmx), int(pixels / 2), -1):
                rgb = (
                    dmx[i]["r"],
                    dmx[i]["g"],
                    dmx[i]["b"],
                )
                dmxData = dmxData + rgb
        sender[1].dmx_data = dmxData
        time.sleep(1 / int(args.fps))
        olddmx = dmx


# devices = AudioUtilities.GetSpeakers()
# interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
# volume = cast(interface, POINTER(IAudioEndpointVolume))


def stopLED():
    sender.stop()


def get_soundcards(p):
    soundcards = {}
    for i in range(0, p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if p.get_host_api_info_by_index(info["hostApi"])["index"] == 1:
            soundcards[i] = {
                "name": p.get_device_info_by_index(i)["name"],
                "outChannels": p.get_device_info_by_index(i)["maxOutputChannels"],
                "inChannels": p.get_device_info_by_index(i)["maxInputChannels"],
                "sampleRate": p.get_device_info_by_index(i)["defaultSampleRate"],
            }
            soundcards["default"] = p.get_host_api_info_by_index(info["hostApi"])[
                "defaultOutputDevice"
            ]
    return soundcards


if __name__ == "__main__":
    p = pyaudio.PyAudio()
    soundcardlist = get_soundcards(p)
    args = parse_args(soundcardlist)
    defaultframes = int(args.frames)
    pixels = int(args.pixels)
    if args.list is True:
        for i in soundcardlist:
            if not i == "default":
                if i == soundcardlist["default"]:
                    print(i, soundcardlist[i]["name"], "[DEFAULT]")
                else:
                    print(i, soundcardlist[i]["name"])
        sys.exit()
    elif args.ip is None:
        print("IP address required, use --help")
        sys.exit()
    try:
        if args.id is None:
            deviceid = soundcardlist["default"]
        else:
            deviceid = int(args.id)
        sender = sacn.sACNsender()
        sender.start()
        sender.activate_output(1)
        sender[1].destination = str(args.ip)
        if soundcardlist[deviceid]["outChannels"] > 0:
            loopback = True
            channels = soundcardlist[deviceid]["outChannels"]
        else:
            loopback = False
            channels = soundcardlist[deviceid]["inChannels"]
        startLED(
            deviceid,
            loopback,
            channels,
            soundcardlist[deviceid]["sampleRate"],
        )
    except Exception as e:
        print(e)
        sender.stop()
    except:
        sender.stop()
