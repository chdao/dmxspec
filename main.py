import pyaudio
import numpy as np
import sacn
import time
import sys

# from comtypes import CLSCTX_ALL
# from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import argparse
from colr import color
import cursor


def parse_args(choices):
    parser = argparse.ArgumentParser(
        description="DMX WiFi Sender help", prog="DMX WiFi Sender"
    )
    parser.add_argument("--ip", help="Destination DMX server")
    parser.add_argument("--id", help="Index of the soundcard")
    parser.add_argument("--list", help="List available soundcards", action="store_true")
    parser.add_argument(
        "--multi", type=float, help="Amplitude multiplier", default="1.5"
    )
    parser.add_argument("--rr", help="Reverse Right Channel", action="store_true")
    parser.add_argument("--rl", help="Reverse Left Channel", action="store_true")
    parser.add_argument("-p", "--pixels", type=int, help="Length of strip", default=10)
    parser.add_argument(
        "-f", "--frames", type=int, help="Frames for pyAudio", default=512
    )
    parser.add_argument(
        "--fps", type=int, help="Frame Per Second (refresh rate)", default=30
    )
    parser.add_argument(
        "-b",
        "--brightness",
        type=int,
        help="Brightness",
        default=100,
        metavar="{0..100}",
    )
    return parser.parse_args()


class BuildDMX:
    def __init__(self, pixels, fps, brightness, multi, reverse_right, reverse_left):
        self.channel_size = pixels // 2
        self.section_size = self.channel_size / 6
        self.maxValue = 2 ** 16
        self.fps = fps
        self.brightness = brightness
        self.multi = multi
        self.reverse_right = reverse_right
        self.reverse_left = reverse_left
        self.pixels = pixels
        # Mapping channels to numbers, this is
        # to match the data taken from pyaudio.
        self.channel_order = {0: reverse_left, 1: reverse_right}

    def build_rgb(self, channel, peak, previous_dmx=None):
        dmx = {}
        # Get the peak (volume) value of the channel
        for i in range(self.channel_size):
            if i == 0:
                division = int(i + 1 // self.section_size + 1)
            else:
                division = int(i // self.section_size + 1)
            if int(peak) >= i + 0.01:
                # Figure out what the gradient value is for color transitions.
                # Basically a % of the position in each subdivision of the
                # channel.
                fade_value = int(
                    ((i - (self.section_size * (division - 1))) * self.section_size)
                    * 2.55
                )
                # A real VU meter should be 1/6
                # red, multiplied by the brightness %
                if division >= 6:
                    dmx[i] = {
                        "r": int(255 * (self.brightness / 100)),
                        "g": 0,
                        "b": 0,
                    }
                # 1/6 yellow (with transition to red)
                elif division >= 5:
                    dmx[i] = {
                        "r": int(255 * (self.brightness / 100)),
                        "g": int((255 - fade_value) * (self.brightness / 100)),
                        "b": 0,
                    }
                # And the rest green (with transition to yellow)
                elif division >= 4:
                    dmx[i] = {
                        "r": int(fade_value * (self.brightness / 100)),
                        "g": int(255 * (self.brightness / 100)),
                        "b": 0,
                    }
                # Pure green
                elif peak > 1:
                    dmx[i] = {
                        "r": 0,
                        "g": int(255 * (self.brightness / 100)),
                        "b": 0,
                    }
            else:
                try:
                    dmx[i] = {
                        # Decay the LEDs off, makes transitions smoother
                        "r": int((previous_dmx[i]["r"] / self.fps) * (self.fps // 1.1)),
                        "g": int((previous_dmx[i]["g"] / self.fps) * (self.fps // 1.1)),
                        "b": int((previous_dmx[i]["b"] / self.fps) * (self.fps // 1.1)),
                    }
                    # If the brightness is under 1, turn off completely.
                    for j in ["r", "g", "b"]:
                        if dmx[i][j] < 1:
                            dmx[i][j] = 0

                except Exception:
                    # One the first run previous_dmx is empty, set all to black
                    dmx[i] = {"r": 0, "g": 0, "b": 0}
        return dmx

    def output(self, data, previous_dmx):
        dmx_data = {}
        output_data = []
        for channel in range(0, 2):
            peak = (
                int(np.abs(np.max(data[channel::2])) - int(np.min(data[channel::2])))
                / self.maxValue
                * self.pixels
                * float(self.multi)
            )
            # Send previous dmx data. If this is the first rul, it'll raise LookupError.
            try:
                dmx_data[channel] = self.build_rgb(channel, peak, previous_dmx[channel])
            except LookupError:
                dmx_data[channel] = self.build_rgb(channel, peak)
        for i in dmx_data:
            if self.channel_order[i] is True:
                for j in range(len(dmx_data[i]) - 1, -1, -1):
                    for c in ("r", "g", "b"):
                        # Create a list of all the LEDs from the dmx_data
                        output_data.append(dmx_data[i][j][c])
            else:
                for j in dmx_data[i]:
                    for c in ("r", "g", "b"):
                        # Create a list of all the LEDs from the dmx_data
                        output_data.append(dmx_data[i][j][c])

        # Change the list to a tuple for the dmx library
        return (tuple(output_data), dmx_data)


def start_sequence(
    deviceid: int,
    loopback: bool,
    channels: int,
    sampleRate: int,
    fps: int,
    brightness: int,
    p: object,
    defaultframes: int,
    pixels: int,
    multi: float,
    rr: bool,
    rl: bool,
    ip: str,
) -> object:
    stream = p.open(
        format=pyaudio.paInt16,
        channels=int(channels),
        rate=int(sampleRate),
        input=True,
        frames_per_buffer=defaultframes,
        input_device_index=int(deviceid),
        as_loopback=loopback,
    )
    sender = sacn.sACNsender()
    sender.start()
    sender.activate_output(1)
    sender[1].destination = ip
    dmx = BuildDMX(pixels, fps, brightness, multi, rr, rl)
    previous_dmx = {}
    try:
        while True:
            data = np.frombuffer(stream.read(1024), dtype=np.int16)
            (dmx_data, previous_dmx) = dmx.output(data, previous_dmx)
            sender[1].dmx_data = dmx_data
            terminal_led(dmx_data)
            time.sleep(1 // fps)
    except KeyboardInterrupt:
        sender.stop()
        cursor.show()


def terminal_led(dmx_data):

    vumeter = ""
    for i in range(0, len(dmx_data), 3):
        vumeter = vumeter + color("█", fore=(dmx_data[i : i + 3]))
    print("\r[" + vumeter + "]", end="")


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


def main():
    p = pyaudio.PyAudio()
    soundcardlist = get_soundcards(p)
    args = parse_args(soundcardlist)
    defaultframes = int(args.frames)
    pixels = int(args.pixels)
    fps = int(args.fps)
    brightness = args.brightness
    if args.list is True:
        for i in soundcardlist:
            if not i == "default":
                if i == soundcardlist["default"]:
                    print(i, soundcardlist[i]["name"], "[DEFAULT]")
                else:
                    print(i, soundcardlist[i]["name"])
        raise Exception
    elif args.ip is None:
        print("IP address required, use --help")
        raise Exception
    elif args.brightness > 100:
        print("Brightness cannot be above 100%")
        raise Exception
    if args.id is None:
        deviceid = soundcardlist["default"]
    else:
        deviceid = int(args.id)

    if soundcardlist[deviceid]["outChannels"] > 0:
        loopback = True
        channels = soundcardlist[deviceid]["outChannels"]
    else:
        loopback = False
        channels = soundcardlist[deviceid]["inChannels"]
    start_sequence(
        deviceid,
        loopback,
        channels,
        soundcardlist[deviceid]["sampleRate"],
        fps,
        brightness,
        p,
        defaultframes,
        pixels,
        args.multi,
        args.rr,
        args.rl,
        args.ip,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)