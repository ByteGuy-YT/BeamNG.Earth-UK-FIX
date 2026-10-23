# Second screenshot review — 21 October 2026

**Motorway/J27 correction:** see [the motorway follow-up](UK_MOTORWAY_FIXES.md). The checks below missed
the deepest motorway troughs and tested nearby standard roundabouts instead of the main J27 circular junction.

Restart **Play UK roads.bat**, then restart BeamNG so it loads the refreshed mod. Both server and mod
changed. Previously generated terrain, navigation, signals and camera triggers need rebuilding.
An older packaged executable does not contain these source changes.

Every image in `compressedImages(2)` is addressed below, including the real-life references. Images
describe the requested result; they are not proof of an in-game result. Building footprints, heights,
floor counts and roofs have not been rescaled.

## Replacement bridge approach

The earlier clearance logic raised approaches above a DEM surface that could already include an
embankment. That produced extra hills while terrain still protruded through decks. The new UK model
separates upper road, lower route and terrain. Short upper spans follow the robust trend outside the
crossing, rather than its DEM trench. Longer spans up to 1 km use smoothed profiles with consistent
approach heights; longer viaducts retain the existing solver.

Lower-road clearance follows the connected network across source sections, rather than ending in a
small pit at a feature boundary. Upper approaches follow the network too, and own their corridor so
their lateral fill cannot produce a bump on a lower motorway. The same full-width excavation is used
by visible and physical terrain; the deck provides collision over the cavity.

Aligned OSM ground/bridge/tunnel sections override conflicting generic layer flags. Multiple subway
intervals are sorted and merged, retaining the ground road between them. Height lookup distinguishes
separate spans belonging to the same source road. These are shared rules, without coordinate patches
for J26, J27 or the A610. Source coverage and DEM resolution still limit accuracy.

## Image-by-image changes

1. **`speed cameras not using beam logic and also on motorways there should be gantries.png`**
   Dynamic cameras now set stock `BeamNGTrigger.loadMode = 1` before registration, following the
   installed game's dynamic-trigger implementation. They use `gameplay_speedTraps`, directional
   driving-lane triggers, limits in metres per second, and a disabled, shadowless flash light driven
   by the stock callback. Motorway housings use mapped gantries or a lightweight inferred gantry at a
   mapped camera when the structure is missing. The sampled M1 payload contains two directional
   cameras at 31.2928 m/s (70 mph). Actual activation still requires an engine test; a visible camera
   does not establish that enforcement works. Unknown-direction cameras and red-light-only records
   are not given invented speed enforcement.

2. **`STILL A PROBLEM WITH A610 THERE SHOULD BE A TUNNEL FOR THE PATH UNDERNEATH.png`**
   The source contains a pedestrian subway here. Its crossings create short upper deck sections on
   both carriageways and a slip road, with a separate path floor, concrete walls and roof below.
   The actual-data audit finds one mapped subway and three additional short deck sections without
   explicit bridge tags. Walls and roof are batched into the existing colliding deck mesh. This
   replaces draping the upper road through the path's trench.

3. **`STILL GOT ISSUE near J26 with bridge, please dont JUST fix this one we need a blanket bridge fix.png`**
   Uses the replacement shared model. Full-width terrain exclusion addresses patches poking through
   asphalt, not just the centreline height. Four sampled motorway spans at this site pass the deck
   clearance and approach-join checks.

4. **`still wrong amount of lanes on CERTAIN exit and ON ramps to dual carridgeways and motorways NOT ALL.png`**
   Lane recovery also reads `destination:lanes`, `destination:ref:lanes` and `access:lanes`, alongside
   explicit lanes and turn lanes. Changes remain source sections when roads are merged. A two-entry
   destination array can restore a two-lane slip road without widening every ramp. Missing lane
   evidence still requires an estimate; an unlocated screenshot cannot establish every exact count.

5. **`big weird humps in motorway at j26, it needs to folloow geometry, please look at the image ive included of G-Maps for reference, remember we need this fix everywhere.png`**
   The upper motorway no longer gains an additive clearance hill. Lower-route clearance and terrain
   excavation are separate. Four sampled J26 decks have approximately 1.0–1.5% grades. Network-based
   lower cuts also avoid abrupt recovery at source seams.

6. **`carparks have the correct road layout which is BRILLIANT however, theres no tarmac in between or parking bays (also shops like this morrisons in eastwood have no designs).png`**
   Mapped surface-parking polygons now produce visible tarmac between aisles and bounded bay paint.
   Asphalt masks exclude grass and scattered bushes/rocks, including mapped lots missing from the
   other source. Real canopy-derived trees remain. Underground, multi-storey and explicitly unpaved
   lots are excluded. Mapped supermarkets receive facade treatment; mapped Morrisons buildings use
   an original fascia/glazing texture on the existing walls. Eastwood identifies two building pieces
   and both parking materials. Bays are generated within mapped footprints, not surveyed spaces;
   paint is capped at 300 bays per tile. The audit's 518 figure means candidate parking positions.

7. **`floating traffic lights.png`**
   Pole and stop-point heights sample their own positions after grading, instead of sharing one
   junction height across a slope. Kerb lift is added only where a pavement exists. Reused heads
   rebuild when ground height changes. Section-level mapped signal controls are also recognized.
   A slope regression checks the pole's own position.

8. **`half way between 27 and 26 massive hill and a bridge which is UNREALISTIC.png`**
   Kennel Lane uses the same upper/lower separation. Both sampled motorway decks follow about 1.3%
   grades with joins within about 3.3 cm. This removes the automatic extra hill; it does not establish
   survey accuracy for the surrounding landscape.

9. **`IRL J26.png` — reference used.**
   The continuous mainline grade and modest crossing structure informed rejection of the former
   added hill. Existing horizontal road geometry is preserved while the crossing floors are
   separated. Measurements were not invented from perspective pixels.

10. **`junction 27 going wrong way this must be for other roundabouts too!.png`**
    Bridge portions now participate in roundabout-ring detection. Resolved one-way rings clear
    reverse lanes in the server graph, and the Lua importer prevents reverse lane characters on
    one-way edges. The J27 audit samples 59 ring edges with zero reverse lanes. Live AI circulation
    still needs observation after reloading the new graph.

11. **`motorway gantry (this one has speed camera) also not central reservation.png` — reference used.**
    Added low-poly overhead gantries, black lane panels and camera housings. Mapped gantry endpoints
    control the span where available. Actual opposing motorway corridors are paired for a low
    concrete central barrier, keeping unrelated one-way streets separate. Gantries and barriers are
    batched into existing meshes, not separate scene objects per panel/segment. Variable-speed
    panels remain unlit; this does not simulate a traffic-management feed.

12. **`real life underwood main road for reference, note bushes, pavement etc, also not elecricity poles.png` — reference used.**
    The narrow dark pavement, low kerb, modest lights and property hedges informed the treatment.
    UK pavements use a fine asphalt texture rather than oversized pale slabs. Smaller streets get
    shorter lamps. Mapped hedge lines add capped instanced shrubs outside roads and pavements.
    Random US utility poles remain excluded. Missing pole/hedge locations are not invented.

13. **`roads on the whole are alot better in width but i still think curbs and widths need tweeking, this is main road underwood, COMPARE IT TO REAL LIFE.png`**
    Estimated tertiary/unclassified pavements narrow from 1.8 m to 1.5 m; explicit widths retain
    precedence. Added asphalt paving and 6.5 m small-street lamps. The kerb remains 0.125 m. Buildings
    and roads are not globally rescaled to match a different camera perspective. Exact property
    walls and garden planting remain dependent on mapping.

14. **`some bridges still have issues this is junction 27, this needs a rethink. ALSO JUNCTION 27 ROUNDABOUT HAS TRAFFIC GOING BOTH WAYS.png`**
    Combines full-width deck/terrain separation and connected approaches with corrected ring
    direction. Both sampled bridge approaches pass the join check. Terrain protrusions and reverse
    traffic have separate causes and checks.

## Performance and verification

Driving-time streaming target is 2 ms instead of 4 ms; deferred engine work charges the budget after
2 ms instead of 5 ms. Forest changes shrink from 750 to 300 per active batch, and the touched-shape
population budget falls from 4,000 to 2,000. Density and viewing range stay the same. The tradeoff is
slower initial detail population. Loading mode retains its separate budget.

Gantries, medians, subway shells and parking paint share existing tile meshes. Cameras use events,
with at most 32 live triggers and idle flash lights disabled. Hedge additions are capped at 128 per
tile, and bay paint is bounded separately. Median projection/height sampling is batched; ownership
queries use spatial buckets. There are no new per-frame map-data queries.

**No FPS improvement has been measured.** `uk-round2-performance.json` records flat-height CPU
generation benchmarks, not rendering, physics or frame times. Corrected motorway geometry and added
furniture still cost more to generate than before; other sampled streets are close to the previous
cost. `uk-round2-validation.json` records real-DEM first/repeated tile timings too. First builds at
complex crossings can take several seconds while neighbouring profiles are prepared. Smaller engine
batches reduce work admitted per frame; they do not remove background work or guarantee no pop-in.

- 402 Python regression tests passed; 630 Lua assertions passed across cameras, navigation, governor,
  trees and road streaming.
- `tools/validate_uk_round2.py` passed at J26, Kennel Lane, J27, the A610 subway, M1 cameras and Eastwood
  Morrisons using actual cached roads and DEM. It checks finite meshes, deck joins under 12 cm,
  sampled terrain clearance and large ground-road grade spikes. Sampled joins are within 6.1 cm.
- The expanded attributed UK context index contains 2,030,628 records from the same OSM extract.
- BeamNG's testing endpoint continued refusing connections, including retries after the user offered
  to enable it. Camera activation, AI motion, visual appearance and frame times have **not** been
  verified in the running game.

The source is ready for an engine verification pass after restarting the launcher/game. Missing
mapping, long viaducts, exact taper geometry, surveyed bay layouts and individual property detail
remain limits. These checks do not establish that every UK location is correct.
