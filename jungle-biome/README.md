# Mistfang Karst: a dense monsoon-jungle biome

An original jungle biome for Spencer's new game. It is set in a limestone valley full of mist, in the spirit of a dense
Vietnamese jungle. Khadrel's woods (the goblin wood: temperate beech and alder, bracken, bluebells) was the reference
for the process, not for the look. Everything here is different and new:

- **The land.** Karst towers stand out of the mist. Rainforest giants rise on plank buttresses. Under them is a packed
  middle canopy of round-crowned trees and palm clumps. There are banyans, bamboo groves, bananas, elephant-ear taro and
  tree ferns. A jade river with stones runs past, a bamboo water wheel turns in it, and flooded rice terraces step up
  the slope. The paths are red laterite.
- **The village is seeded.** It has stilt houses and one longhouse with tall hip-and-gablet thatch roofs, granaries on
  posts with rat guards, a spirit shrine in the plaza, and banana and taro gardens.
- **Every house is hollow, and its inside matches its outside.**
  - The woven walls show their thickness in every opening.
  - The door at the porch end and the propped shutter windows are the same holes inside and out.
  - The rafters, purlins and ridge are visible from inside.
  - The clay hearth box has a smoke rack over it, and the smoke leaves through the gablet vents under the carved horns.
- **Furniture is the shared props set,** retextured to teak, rattan, madder, indigo and hemp. Nothing is remodelled.
  Blender's room planner places each piece against a wall, clear of the door, the hearth and the windows. The loose props
  are physics bodies with their real weights, as in the ashland biome. In "Walk in yourself", E lifts, F throws and a
  click knocks.

## Pipeline (cloud Blender, `blender/`)

This follows the same stages as the other biome threads and Khadrel's asset process. Every model is built in code,
baked, and painted.

1. `jungle_kit.py --asset <kind> --seed <seed> --size <atlas px>` builds faceted bmesh solids. Each face is tagged with
   its material slot and part.
2. It unwraps the model to one unique atlas.
3. Cycles bakes material ids, position, normal, AO and sky light into that atlas.
4. `jungle_paint.py` turns the bakes into palette pixels:
   - slot ramps and per-part tone
   - patterns: twill weave, thatch courses, plank boards, bamboo nodes, karst streaks, moss and lichen
   - soot inside the houses
   - Bayer dither
5. The result is exported as a glb split into `shell` / `roof` / `wheel` nodes, plus an info json. The info json holds
   the colliders, prop surfaces, markers and the room plan.
6. `fix_seams.py` dilates the atlas islands, so there are no seams.

Other scripts:

- `build_all.sh` builds the whole kit, two models at a time.
- `retexture_props.py` remaps the shared props' texture sheets. It never touches their geometry.
- `furniture_surfaces.py` casts rays through each furniture piece. It writes the surfaces props can stand on and the
  collider boxes.
- `glb_to_page.py` converts a glb into glTF JSON plus image files for the published page.
- `render_preview.py` renders the preview images (outside, inside, and a cut-away with the furniture in place).

Kit kinds: `stilthouse`, `longhouse`, `granary`, `shrine`, `waterwheel`, `emergent`, `midtree`, `palm`, `banyan`,
`bamboo`, `banana`, `taro`, `treefern`, `karst`, `boulders`. There is no triangle cap.

## Page (`web/index.html`)

The page uses three.js 0.128 and cannon 0.6.2. It loads `kit/<name>.json` plus `.info.json`, `props/<id>.json`,
`props/furniture.json` and `props/props.json`, and the modular-body walker from `assets/`. Add `?lite` to the URL on a
slow machine.

## Files

The built kit (glb and info json), the converted page assets and every preview render are in the project files under
`jungle-biome/`. They are not in git. A few small renders are in `renders/`. Live page: https://claude.ai/artifact/WcMytEPBomKs6thE9nevPM
