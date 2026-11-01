# Ambermere Fen

An original wetland biome: tea-dark amber water, sphagnum hummocks in rust, ochre and lime, sedge and cotton-grass,
bladder lilies, pitcher plants and sundews, and pale **tallow trees** carrying flat tiers of rust-gold needles. The fen
folk cut peat from the raised bog in terraces, dry it in leaning footings, and build **round houses of peat blocks** on
wattle-ringed islands (crannogs) in the mere, roofed in bark shingles round an open smoke hole, joined by log boardwalks.

What it deliberately is not: no giant mushrooms or glowing fungus, no mangroves or twisted roots, no murky green fog,
no stilt shacks, no frogfolk. The palette is its own (`blender/painter.py`, `PAL`).

## Layout

- `blender/kit.py` modelling primitives (closed, chamfered solids tagged with a part id, a material slot and a grain
  direction), UV (hidden faces get no atlas area), the Cycles bake of every field the painter needs, glb export.
- `blender/painter.py` turns the bake into palette pixels: fields painted in model space (no seams), per-part tone,
  per-material wear (silvered timber outside, brown and sooty inside, lichen on the roof, slime on the treads), light
  from above, ordered dither through palette ramps. Atlases save as indexed PNGs.
- `blender/house.py` the round houses (small, medium, tall with a loft). Interiors are built from the same pieces as
  the outside: the door and windows are real openings through the wall, the smoke hole is the open crown of the roof,
  the tall house's upper windows light its loft.
- `blender/flora.py` tallow trees (swept tubes plus alpha-cut needle cards), snags, lilies, pitchers, sundew hummocks,
  sedge tussocks, boulders.
- `blender/props.py` boardwalk, lantern post, dugout, peat bank with drying footings, eel trap.
- `blender/build.py` builds, bakes, paints and exports. `page/index.html` is the explorable page (three.js); its
  `assets/` folder takes the glbs plus the walker's `body.json` and `hair.json`.

## Build

Needs Blender 5.x as a Python module (`pip install bpy==5.2.3`), numpy and Pillow.

```
python blender/build.py OUT --only house_tall,tallow_a        # model, bake, paint, export
python blender/build.py OUT --only house_tall --geom          # quick preview, no bake
python blender/build.py OUT --only house_tall --repaint       # repaint from the saved bake (no Blender bake)
```

A house bakes at 4,096 px in about 6 to 10 minutes on four cores; small props take seconds.
The village in the page is seeded: the same seed always lays out the same village.
