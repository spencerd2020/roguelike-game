"""Painter for the jungle kit: turns per-texel bake data into palette pixels.

Layers per texel: slot ramp, per-part tone, the slot's own pattern (twill weave, thatch courses, plank boards, bamboo
nodes, karst streaks and stains, lichen, moss), wear from occlusion and height, the painted top light (the sky bake),
then an ordered dither onto the ramp's swatches. Only palette swatches come out, so the sheet reads as painted.
"""
import numpy as np

RAMPS = {
    'weave':   ['#3d3220', '#5a4a2c', '#7a653a', '#9a8249', '#b89e5a', '#d0b871', '#e2cf92'],
    'thatch':  ['#2a2620', '#3e3729', '#554a35', '#6d5f43', '#857553', '#9e8c64', '#b6a47a'],
    'wood':    ['#1e1612', '#2e211a', '#433024', '#5a412f', '#71533c', '#8a6749'],
    'plank':   ['#2c2018', '#3f2e21', '#56402c', '#6d5238', '#866646', '#9e7b56'],
    'bamboo':  ['#2f3a1a', '#465626', '#5f7131', '#7a8a3c', '#98a24a', '#b7b65e', '#d2c97a'],
    'stone':   ['#2a2b2b', '#424443', '#5d5f5c', '#7a7b76', '#979791', '#b3b2aa', '#cfcdc3'],
    'moss':    ['#1c2b14', '#2a3d1a', '#3a5122', '#4d662a', '#647d33', '#7e953e'],
    'bark':    ['#2b2a26', '#403d37', '#57534a', '#706a5e', '#8a8374', '#a59d8b', '#bfb7a3'],
    'leaf':    ['#0f1c10', '#162a16', '#1f3a1c', '#2a4b22', '#376029', '#467531', '#588a3a', '#6fa046'],
    'frond':   ['#1d2e10', '#2c4416', '#3e5b1c', '#527322', '#688b2a', '#82a334', '#9fba45', '#bdd060'],
    'clay':    ['#3a2216', '#54301d', '#6e3f25', '#8a512f', '#a6653b'],
    'cloth':   ['#141a33', '#1f2a52', '#2f3d73', '#6b1d1d', '#932a24', '#bb4030', '#e3c36a'],
    'rope':    ['#2e2416', '#47381f', '#62502b', '#7e6838', '#9a8247'],
    'lacquer': ['#3a0f0c', '#5c1712', '#821f16', '#a62a1a', '#c63d22', '#d9a640'],
    'ash':     ['#262422', '#3d3a37', '#57534e', '#726c66', '#8e8780'],
    'root':    ['#1f1a15', '#2f271f', '#41362a', '#564835', '#6c5b43'],
    'dry':     ['#3a2a16', '#57401f', '#76592a', '#957236', '#b38d48', '#ccaa62'],
    'ember':   ['#ff7a2a'],
}
