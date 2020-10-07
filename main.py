import pyaudio
import numpy as np
import sacn
import time
import sys
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import argparse
from colr import color
import cursor
cursor.hide()

maxValue = 2 ** 16


def parse_args(choices):
    parser = argparse.ArgumentParser(
        description="DMX WiFi Sender help", prog="DMX WiFi Sender"
    )
    parser.add_argument("--ip", help="Destination DMX server")
    parser.add_argument("--id", help="Index of the soundcard")
    parser.add_argument("--list", help="List available soundcards", action="store_true")
    parser.add_argument("--multi", type=float, help="Aplitude multiplier", default="1.5")
    parser.add_argument("--rr", help="Reverse Right Channel", action="store_true")
    parser.add_argument("--rl", help="Reverse Left Channel", action="store_true")
    parser.add_argument("-p", "--pixels", type=int, help="Length of strip", default=10)
    parser.add_argument("-f", "--frames", type=int, help="Frames for pyAudio", default=512)
    parser.add_argument("--fps", type=int, help="Frame Per Second (refresh rate)", default=30)
    parser.add_argument("-b", "--brightness", type=int, help="Brightness", default=100, metavar="{0..100}")
    return parser.parse_args()


class BuildDMX:
    def dict(data, previous_dmx, fps, brightness):
        dmx = {}
        channel_size = pixels // 2
        section_size = channel_size / 6
        # Get the peak (volume) value of the channel
        peak = (
                int(np.abs(np.max(data)) - int(np.min(data)))
                / maxValue
                * pixels
                * float(args.multi)
        )
        for i in range(channel_size):
            if i == 0:
                division = int(i + 1 // section_size + 1)
            else:
                division = int(i // section_size + 1)
            if int(peak) >= i + 0.01:
                # Figure out what the gradient value is for color transitions.
                # Basically a % of the position in each subdivision of the
                # channel.
                fade_value = int(((i - (section_size * (division - 1))) * section_size) * 2.55)
                # A real VU meter should be 1/6 red, multiplied by the brightness %
                if division >= 6:
                    dmx[i] = {
                        "r": int(255 * (brightness/100)),
                        "g": 0,
                        "b": 0,
                    }
                # 1/6 yellow (with transition to red)
                elif division >= 5:
                    dmx[i] = {
                        "r": int(255 * (brightness/100)),
                        "g": int((255 - fade_value) * (brightness/100)),
                        "b": 0,
                    }
                # And the rest green (with transition to yellow)
                elif division >= 4:
                    dmx[i] = {
                        "r": int(fade_value * (brightness/100)),
                        "g": int(255 * (brightness/100)),
                        "b": 0,
                    }
                # Pure green
                elif peak > 1:
                    dmx[i] = {
                        "r": 0,
                        "g": int(255 * (brightness/100)),
                        "b": 0
                    }
            else:
                try:
                    dmx[i] = {
                        # Decay the LEDs off, makes transitions smoother
                        "r": int((previous_dmx[i]['r'] / fps) * (fps // 1.1)),
                        "g": int((previous_dmx[i]['g'] / fps) * (fps // 1.1)),
                        "b": int((previous_dmx[i]['b'] / fps) * (fps // 1.1))
                    }
                except LookupError:
                    # One the first run previous_dmx is empty, set all to black
                    dmx[i] = {
                        "r": 0,
                        "g": 0,
                        "b": 0,
                    }
        return dmx

    def tuple(dmx_dict, reverse):
        dmx_data = ()
        rgb = ()
        if reverse is False:
            # Take the dict and put them into tuples.
            # The DMX (Art-Net) library needs it.
            for i in range(len(dmx_dict)):
                rgb = (
                    dmx_dict[i]["r"],
                    dmx_dict[i]["g"],
                    dmx_dict[i]["b"]
                )
                dmx_data = dmx_data + rgb
        elif reverse is True:
            # Reversing the order of the dict.
            for i in range(len(dmx_dict) - 1, -1, -1):
                rgb = (
                    dmx_dict[i]["r"],
                    dmx_dict[i]["g"],
                    dmx_dict[i]["b"]
                )
                dmx_data = dmx_data + rgb
        return dmx_data


def start_sequence(deviceid: object, loopback: object, channels: object, sampleRate: object, fps: object, brightness: object) -> object:
    stream = p.open(
        format=pyaudio.paInt16,
        channels=int(channels),
        rate=int(sampleRate),
        input=True,
        frames_per_buffer=defaultframes,
        input_device_index=int(deviceid),
        as_loopback=loopback,
    )
    old_left = {}
    old_right = {}
    while True:
        dmx_dict_left = {}
        dmx_dict_right = {}
        data = np.frombuffer(stream.read(1024), dtype=np.int16)
        data_left = data[0::2]
        data_right = data[1::2]
        # Take the data from each channel and construct a dict with the LED value of pixels / 2
        (dmx_dict_left) = BuildDMX.dict(data_left, old_left, fps, brightness)
        (dmx_dict_right) = BuildDMX.dict(data_right, old_right, fps, brightness)
        # Take the dict and apply reversing (or not) on each and return them as tuple
        dmx_tuple_left = BuildDMX.tuple(dmx_dict_left, args.rl)
        dmx_tuple_right = BuildDMX.tuple(dmx_dict_right, args.rr)
        # Send to the LED strip.
        sender[1].dmx_data = dmx_tuple_left + dmx_tuple_right
        terminal_led(dmx_tuple_left, dmx_tuple_right)
        time.sleep(1 // fps)
        old_left = dmx_dict_left
        old_right = dmx_dict_right


def terminal_led(dmx_tuple_left, dmx_tuple_right):
    for i in range(0, len(dmx_tuple_left), 3):
        print(color("█", fore=(dmx_tuple_left[i:i + 3])), end='')
    for i in range(0, len(dmx_tuple_right), 3):
        print(color("█", fore=(dmx_tuple_right[i:i + 3])), end='')
    print("]", end='')
    print("\r [", end='')




# devices = AudioUtilities.GetSpeakers()
# interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
# volume = cast(interface, POINTER(IAudioEndpointVolume))

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
    elif args.brightness > 100:
        print("Brightness cannot be above 100%")
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
        start_sequence(deviceid, loopback, channels, soundcardlist[deviceid]["sampleRate"],
            args.fps, args.brightness)
    except Exception as e:
        print("Exception:", e)
        sender.stop()
        cursor.show()
    except:
        sender.stop()
        cursor.show()
