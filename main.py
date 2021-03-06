"""
This software creates a VU meter and sends it to a DMX enabled (WiFi) LED strip.
"""
import time
import argparse
import numpy as np
import sacn


# import sys
import soundcard as sc

# from comtypes import CLSCTX_ALL
# from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from colr import color
import cursor


def parse_args(choices):
    parser = argparse.ArgumentParser(
        description="DMX WiFi Sender help", prog="DMX WiFi Sender"
    )
    parser.add_argument("--ip", help="Destination DMX server")
    parser.add_argument("--id", help="Index of the soundcard")
    parser.add_argument("--list", help="List available soundcards", action="store_true")
    parser.add_argument("--multi", type=float, help="Amplitude multiplier", default="1")
    parser.add_argument("--rr", help="Reverse Right Channel", action="store_true")
    parser.add_argument("--rl", help="Reverse Left Channel", action="store_true")
    parser.add_argument("-p", "--pixels", type=int, help="Length of strip", default=100)
    parser.add_argument(
        "-f", "--frames", type=int, help="Frames for pyAudio", default=None
    )
    parser.add_argument(
        "--fps", type=int, help="Frame Per Second (refresh rate)", default=100
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
    """
    Class handling everything related to creating the tuples of RGB for DMX
    """

    def __init__(self, **kwargs):
        self.channel_size = kwargs['pixels'] // 2
        self.section_size = self.channel_size / 6
        self.fps = kwargs['fps']
        self.brightness = kwargs['brightness']
        self.multi = kwargs['multi']
        self.pixels = kwargs['pixels']
        self.fade_multiplier = 1.15
        # Mapping channels to numbers, this is
        # to match the data taken from soundcard.
        self.channel_order = {0: kwargs['rl'], 1: kwargs['rr']}

    def build_rgb(self, peak: float, previous_dmx: dict = None):
        """
        Build the RGB sequence based on the peak.
        """
        dmx = {}
        # Get the peak (volume) value of the channel
        for i in range(self.channel_size):
            if i == 0:
                division = 1
            else:
                division = int(i // self.section_size + 1)
            if int(peak) >= i + 0.1:
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
                else:
                    dmx[i] = {
                        "r": 0,
                        "g": int(255 * (self.brightness / 100)),
                        "b": 0,
                    }
            else:
                if previous_dmx is not None:
                    dmx[i] = {
                        # Decay the LEDs off, makes transitions smoother
                        "r": int(
                            (previous_dmx[i]["r"] / self.fade_multiplier)
                        ),
                        "g": int(
                            (previous_dmx[i]["g"] / self.fade_multiplier)
                        ),
                        "b": int(
                            (previous_dmx[i]["b"] / self.fade_multiplier)
                        ),
                    }
                    # If the brightness is under 1, turn off completely.
                    for j in ["r", "g", "b"]:
                        if dmx[i][j] < 1:
                            dmx[i][j] = 0
                else:
                    # One the first run previous_dmx is empty, set all to black
                    dmx[i] = {"r": 0, "g": 0, "b": 0}
        return dmx

    def output(self, data: list, previous_dmx: dict):
        """
        Creates the tupple to send to the sender (DMX), based on the output of build_rgb
        """
        dmx_data = {}
        output_data = []

        for channel in range(0, 2):
            # Send previous dmx data. If this is the first run, it'll raise
            # a LookupError.
            peak = self.get_peak(data, channel)
            try:
                dmx_data[channel] = self.build_rgb(peak, previous_dmx[channel])
            except LookupError:
                dmx_data[channel] = self.build_rgb(peak)
            # Create a list of all the LEDs from dmx_data
            if self.channel_order[channel] is True:
                for j in range(len(dmx_data[channel]) - 1, -1, -1):
                    for rgb in ("r", "g", "b"):
                        output_data.append(dmx_data[channel][j][rgb])
            else:
                for j in dmx_data[channel]:
                    for rgb in ("r", "g", "b"):
                        output_data.append(dmx_data[channel][j][rgb])

        # Change the list to a tuple for the dmx library
        return (tuple(output_data), dmx_data)

    def get_peak(self, data, channel: int):
        """
        Get 1/10 of all the sound data and find the peak.
        """
        peak = 0
        current_channel = []
        values = data[::int(len(data) * 0.1) + 1]
        for i in values:
            current_channel.append(i[channel])
            peak = (
                np.abs(np.max(current_channel) - np.min(current_channel))
                * self.pixels
                * float(self.multi)
            )
        return peak


def start_sequence(**kwargs):
    """
    Main sequence
    """

    dmx = BuildDMX(
        pixels=kwargs['pixels'],
        fps=kwargs['fps'],
        brightness=kwargs['brightness'],
        multi=kwargs['multi'],
        rr=kwargs['rr'],
        rl=kwargs['rl'],
        ip=kwargs['ip'])
    previous_dmx: dict = {}
    recording_device = sc.get_microphone(kwargs['deviceid'], include_loopback=True)
    sender = sacn.sACNsender()
    try:
        i = 0
        while True:
            data = recording_device.record(
                samplerate=kwargs['sampleRate'],
                numframes=kwargs['defaultframes'],
                blocksize=256)
            if data is not None:
                (dmx_data, previous_dmx) = dmx.output(data, previous_dmx)
                if not sender.get_active_outputs():
                    if any(map(lambda ele: ele != 0, dmx_data)):
                        sender.activate_output(1)
                        sender[1].destination = kwargs['ip']
                        sender.start()
                else:
                    sender[1].dmx_data = dmx_data
                    if not any(map(lambda ele: ele != 0, dmx_data)):
                        # Don't deactivate too quickly. Wait a few seconds.
                        if i >= 500:
                            sender.deactivate_output(1)
                            sender.stop()
                            i = 0
                        i += 1
                terminal_led(dmx_data)
            time.sleep(0.01)
    except KeyboardInterrupt:
        sender.stop()
        cursor.show()


def terminal_led(dmx_data):
    """
    Send the LED sequence to the terminal for emulation
    """
    cursor.hide()
    vumeter = ""
    for i in range(0, len(dmx_data), 3):
        vumeter = vumeter + color("█", fore=(dmx_data[i: i + 3]))
    print("\r[" + vumeter + "]", end="")


def main():
    """
    Main program
    """
    soundcardlist = sc.all_microphones(include_loopback=True)
    args = parse_args(soundcardlist)
    pixels = int(args.pixels)
    if args.list is True:
        i = 0
        print("Default\t| Index\t| Name\n" + "-" * 50)
        while i < len(soundcardlist):
            if soundcardlist[i].id == sc.default_speaker().id:
                print("   X\t|", str(i) + "\t|", soundcardlist[i].name)
            else:
                print("\t|", str(i) + "\t|", soundcardlist[i].name)
            i += 1
        raise Exception
    elif args.ip is None:
        print("IP address required, use --help")
        raise Exception
    elif args.brightness > 100:
        print("Brightness cannot be above 100%")
        raise Exception
    if args.id is None:
        if str(sc.default_speaker().id) is None:
            print("No default speaker provided by OS, please use --list")
            raise Exception
        deviceid = str(sc.default_speaker().id)
    else:
        deviceid = str(args.id)

    start_sequence(
        deviceid=deviceid,
        sampleRate=48000,
        fps=args.fps,
        brightness=args.brightness,
        defaultframes=args.frames,
        pixels=pixels,
        multi=args.multi,
        rr=args.rr,
        rl=args.rl,
        ip=args.ip,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
