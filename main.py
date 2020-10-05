import pyaudio
import numpy as np
import sacn
import time
import sys
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import argparse

maxValue = 2 ** 16
pixels = 110
bars = 35
defaultframes = 512


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
    return parser.parse_args()


def buildDMX(dataL, dataR, olddmx):
    dmx = {}
    peakL = np.abs(np.max(dataL) - np.min(dataL)) / maxValue * pixels * 1.5
    peakR = np.abs(np.max(dataR) - np.min(dataR)) / maxValue * pixels * 1.5
    dmxL = ()
    dmxR = ()

    for i in range(1, int(pixels / 2)):
        if i <= int(peakL) and i < int(pixels / 6):
            dmxL = dmxL + (0, 255, 0)
        elif i <= int(peakL) and i > (pixels / 6) and i < (pixels / 3):
            dmxL = dmxL + (255, 255, 0)
        elif i <= int(peakL) and i > (pixels / 3):
            dmxL = dmxL + (255, 0, 0)
        else:
            dmxL = dmxL + (0, 0, 0)
        if i <= int(peakR) and i < int(pixels / 6):
            dmxR = dmxR + (0, 255, 0)
        elif i <= int(peakR) and i > (pixels / 6) and i < (pixels / 3):
            dmxR = dmxR + (255, 255, 0)
        elif i <= int(peakR) and i > (pixels / 3):
            dmxR = dmxR + (255, 0, 0)
    j = 0
    for i in range(len(dmxL), 1, -3):
        dmx[j] = {
            "r": dmxL[i - 1],
            "g": dmxL[i - 2],
            "b": dmxL[i - 3],
        }
        j += 1
    for i in range(0, len(dmxR), 3):
        dmx[j] = {
            "r": dmxR[i],
            "g": dmxR[i + 1],
            "b": dmxR[i + 2],
        }
        j += 1
    dmx = dmxL + dmxR

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
        sender[1].dmx_data = dmx
        time.sleep(0.03)
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
        try:
            sender = sacn.sACNsender()
            sender.start()
            sender.activate_output(1)
            sender[1].destination = str(args.ip)
        except Exception as e:
            print(e)
            sender.stop()
        except:
            sender.stop()
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
