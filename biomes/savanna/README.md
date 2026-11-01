# Ochre Reach: an original savanna biome

An explorable savanna for the new game, built the way Khadrel builds its hand-made assets (generator, unique atlas, per-texel
bake, palette painter, glb) but written fresh, with its own shapes, palette and buildings. Nothing here is copied from Khadrel,
Morrowind or any other game.

## What is in it

| Piece | Where it comes from |
| --- | --- |
| Sun-hat houses (three hearth houses, one great house) | `blender/savanna_kit.py` (`house`, `greathouse`), seeded |
| Granary on stone stilts, meeting shade | `granary`, `pavilion` |
| Parasol thorn trees, bottle trees | `thorn`, `bottle` |
| Granite outcrop with a balanced stone, loose boulders | `kopje`, `boulders` |
| Clay chimney mounds | `mound` |
| Ground sheets, grass, the pan, the village layout | `page/index.html` (painted on the page, seeded village) |

### The house, and why its inside matches its outside

A round drum of rammed red earth (laid in lifts, the painter marks each one) on a granite footing, closed by a clay dome with
a smoke hole over the hearth. A broad woven sun-hat floats above the dome on six or eight poles that stand in clay buttresses;
a small crown cap floats above the sun-hat's own hole. Smoke climbs from the hearth, through the dome's oculus, through the
sun-hat's ring and out under the crown, so the stacked silhouette is also the chimney.

Inside, every opening has the wall's full thickness; window grilles sit mid-wall, so they are the same bars seen from both
sides; the porch's vault is the passage you walk through; the dome's inside is sooted towards the oculus; the lower metre of
the inside wall is a clay dado under lime. The great house is bigger, with more windows, two beds and a table for guests.

### Furniture: the shared household set, retextured, never remodelled

The houses don't model their own furniture. The generator writes a `furniture` list into each house's `<name>.json`
(prop name, position and yaw in the house's frame), and the page and the Blender previews stand the studio's shared props
there: bed with blanket and bolster on the back wall, crocks, urn, sacks and basket by the door, a banded chest, firewood,
a peg rack with drying herbs, a stool, cook pot and bowl by the fire; the great house adds the trestle table, bench, cups and
jug, shelves and a wall hanging. `blender/retex_props.py` gives each shared prop a savanna palette: every texel of its
base-colour sheet is sorted by hue (wood, fired clay, indigo, madder, green, straw, neutral) and moved onto the matching
savanna ramp at the same lightness, with the kit's ordered dither. Mesh, UVs and the glow sheet stay exactly as shared.

```
python blender/retex_props.py <shared props glb dir> props/out      # then tools/glb2json.py each into page/kit/props/
```

## The asset process (Khadrel's stages, our own code)

1. **Build** closed faceted solids in bmesh. Every face carries a material slot, a part id and a node group
   (`shell`, `dome`, `roof`), so a viewer can lift the roof off.
2. **Unwrap** one unique atlas per model (Smart UV, uniform texel density). Houses and the outcrop at 4096 px, the rest
   at 2048 or 1024.
3. **Bake** in Cycles, per texel: slot and part (emit), position, normal, ambient occlusion, and sky light from above.
4. **Paint** (`blender/savanna_paint.py`): palette ramps only; per-part tone, the slot's own pattern (earth lifts, rain
   streaks, thatch courses and strands, granite joints, exfoliation and lichen, bark fissures, woven mat bands), wear from
   occlusion, the painted top light, ordered dither onto the swatches. Glow (embers) stays a flat material.
5. **Export** one glb per model with its atlas as JPEG, nodes split by group, plus `<name>.json` with sizes and markers
   (door angle, hearth, eye height inside).

Where it goes further than Khadrel: no triangle budget (houses about 5,000 to 6,000 triangles of architecture, plus the shared furniture), 4K atlases for the houses, a real interior in the same model as the exterior (Khadrel keeps separate
interior models), and every model seeded.

## Commands

```
pip install bpy==5.2.3                    # Blender as a Python module
cd blender
python savanna_kit.py --asset house --seed hearth-1 --size 4096 --out ../kit --render
./build_all.sh ../kit                     # the whole kit, two at a time
python savanna_kit.py --asset house --seed x --out /tmp/x --geom --render   # shape only, clay render
```

`--render` writes Cycles previews: `_out.png` (outside), and for houses `_in.png` (from the eye marker, hearth lit) and
`_cut.png` (roof and dome hidden).

## The page

`page/index.html` loads the kit from `page/kit/` and the walker from `page/assets/` (the modular body from the ashland
biome, not part of this kit). Add `?lite` to the address for slow machines. Village seeds live in the address hash.
