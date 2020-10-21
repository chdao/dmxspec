# dmxspec
VU Meter for DMX LED strips

## Description
This program will analyze what comes out of a soundcard and will display a VUMeter from it. This was developed specifically for a DMX (over wifi) LED strip.

## Usage
dmxspec.py --ip <IP of the strip> --pixels <number of LEDs>

### Options
--rr        Reverse right channel
--rl        Reverse left channel
--frames    How many frames to look at. This influences how "reactive" the VUMeter is. Lower is more.
