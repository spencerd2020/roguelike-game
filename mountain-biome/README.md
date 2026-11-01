# Vanehold Pass: an original mountain biome

A high pass above a sea of cloud. Peaks of banded slate, rose and cream stone stepped into strata ledges, snow on the
heights, a gold alpine meadow, a glacial tarn, a gorge with a stream and a rope bridge, a lookout tower on a terraced
crag, and a village of wind-wheel stone houses round a flagged square. Every model, texture and the ground itself is
generated in code and baked in Blender. Nothing comes from another game.

## What makes it ours (and not Morrowind's mountains)

- **Banded stone.** The mountain is layered slate, dusty rose and cream strata. Cliffs read as stripes that dip a little
  to the east; the same three strata build the houses, so the village looks quarried from the hill behind it.
- **High and bright.** Clear blue sky, snow above 52 m, a gold meadow with violet and white flowers, a turquoise tarn,
  and cloud below the edge of the world to the south. No ash, no red sky, no mushroom trees, no giant insects.
- **Wind-wheel houses.** Steep slate roofs on a real timber frame, coursed banded-stone walls, and a sailed wind wheel on
  the west gable whose axle runs through the wall to a drive wheel in the loft. Each house is furnished inside.
- **Cloud pines.** A leaning bare trunk with needles held in flat, stacked pads.

## How the assets are made (the Khadrel hand-built process, done again for this game)

The steps follow Khadrel's hand-built asset pipeline (design-process.md, version 2.0): closed chamfered solids with a part
name per primitive, a unique atlas, a per-texel bake, a numpy painter that paints through palette ramps with
ramp-constrained error diffusion, and the light painted in. Everything here is new code with its own palette. Where it
goes further:

| Step | Here |
| --- | --- |
| Geometry | `blender/mkit.py`: chamfered boxes, beams, prisms, slabs, faceted rocks, tubes; each face tagged with slot, part id and grain axis |
| Hidden faces | `bake.cull_hidden` deletes faces pressed against a neighbour or inside another solid (tested at the centre and every corner, so a face that is only partly covered stays) |
| Atlas | `bake.unwrap`: our own packer. Islands are connected faces of one part facing one way, projected along that direction with u along the grain, rounded to whole pixels and shelf-packed at the largest density that fits |
| Bake | Cycles: position, true normal, part/slot/edge (a Bevel-node edge mask), grain axis, AO, and diffuse light from a sky that is bright overhead, a high sun and the asset's own lamps (hearths, hanging lamps), with real bounce light inside the rooms |
| Paint | `blender/paint.py`: per-material painters (banded coursed stone, flagstones, silvered larch outside and smoke-darkened honey timber inside, slate shingles with lichen rosettes, iron with rust, wool, rope, bark, needle pads, quartz) and soot above the hearth; C error diffusion (`dither.c`) |
| Export | glTF with the atlas as an indexed-colour PNG (every texel is a swatch, so it is exact), positions and UVs quantised to 16 bits (KHR_mesh_quantization), flat normals from screen-space derivatives |

Interiors match exteriors because they are the same geometry: walls are one block thick, every opening is snapped to
the stone courses, the hearth hood rises into the chimney stack you see on the east gable, the loft sits on the tie beams
you see from outside, the windows' mica panes glow from both sides, and the door stands open.

## Furniture: the shared household set, retextured

The houses use the game's shared furniture (the household props set), never their own: a plank bed, a trestle table and
two benches, a banded chest, a stool, open shelves, a horn lantern and a candlestick, and a bench outside the door.
`blender/retexture.py` keeps each model's mesh and UVs exactly and repaints only its texture: every texel is sorted by
hue into timber, iron, wool, red or blue cloth, brass or flame, and its brightness is carried onto the matching Vanehold
ramp (honey larch, blue-black iron, madder, woad) through the same error diffusion. The house generator only names
where each piece stands; the bake stands the real models in the room so their shadows and occlusion land on the floor
and walls, and the page places the same models at the same marks.

## Files

- `blender/build.py`: build one asset. `python blender/build.py house --seed brannoch --out OUT --size 4096 --samples 24`
  (also `tower --seed windwatch`, `pine --seed cirr|hask|ollum --size 1024`, `props --seed vanehold --size 2048`).
  `--repaint` reuses the saved bake and mesh and only paints and exports (about two minutes); `--geom` stops after the
  geometry and prints the triangle count.
- `blender/assets/vane.py`: the building grammar (courses, openings, lintels, windows, doors, roof frame, roof cover,
  gable boards, wind wheel). `house.py`, `tower.py`, `pine.py`, `props.py` use it.
- `blender/terrain.py`: heightfield, layout and zones; `ground_paint.py` paints the ground; `terrain_bake.py` places
  every baked model on the terrain and bakes the ground's light with them standing in it.
  `python blender/terrain.py --assets OUT --out TERRAIN --size 4096 --light 2048`
- `blender/retexture.py`: `python blender/retexture.py --src /mnt/project-files/props/glb --out FUR bed table bench chest
  shelf lantern candlestick stool`; then build houses with `--furniture FUR` and assemble with `--furniture FUR`.
- `assemble.py`: gathers everything into `web/assets` for the page. `web/index.html`: the explorable page (three.js).

Needs `pip install bpy==5.2.3 numpy pillow` and a C compiler. Timings on a 4-core cloud box: a house at 4096 px about
17 minutes, the tower about the same, a pine one minute, the props kit three minutes, the terrain bake about ten.

## Numbers

- House: about 85,000 triangles, 2,470 parts, 4,096 px atlas (about 75 px per metre). Three seeded variants.
- Tower: about 88,000 triangles. Pines: about 2,000. Props kit: about 10,000 for twelve props.
- Terrain: 260 m square on a 0.5 m grid (540,000 triangles), ground painted at 4,096 px (16 px per metre).
