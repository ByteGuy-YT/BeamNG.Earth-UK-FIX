# UK signs, signals and street details — 21 October 2026

Restart **Play UK roads.bat** and reload the level. These are source changes; the launcher refreshes
the mod's assets. An executable built before this update does not contain the new code.

## Added details

- Original UK pole-mounted three-aspect traffic lights, with black heads and white backing boards.
  The red/amber/green lenses use the same instance-colour palette channels as the installed game's
  signal assets. BeamNG's `core_trafficSignals` controllers drive them, using the existing UK
  red-and-amber sequence. There are no extra projected lights or per-frame custom signal timers.
- UK give-way, stop, national-speed-limit, keep-left, roundabout-warning and school-warning assets.
  Explicit supported `traffic_sign` diagram codes place the corresponding sign; unknown codes are
  skipped. Existing circular mph signs now support one-way major roads and avoid repeated entries
  at a straight continuation with the same mapped limit.
- Yellow roadside camera housings at mapped fixed speed-camera records. The trigger uses the
  installed game's `gameplay_speedTraps.onBeamNGTrigger` logic, with limits in metres per second.
  A camera does not create a new custom enforcement loop.
- Mapped bus-stop flags and red post boxes. These are sparse, instanced details rather than
  generated rows of objects along every street.
- UK buildings no longer receive random West Coast USA fictional-company wall logos. Existing
  generic shopfront bands and mapped dimensions remain.
- Dedicated school facade texture for mapped school buildings and buildings identified inside
  school sites. It changes the wall material without changing the footprint, floor count, height
  or roof dimensions.
- Petrol-site facade treatment and the stock Italy petrol-pump asset. Known mapped canopies are
  drawn as open roof-and-column structures on their original footprint, with pumps placed inside
  sufficiently large canopies. Explicit pump nodes also use the stock asset. Shops keep their
  building geometry. A whole differently sized station prefab is not substituted for an irregular
  or unidentified building.

The [asset preview](uk-street-assets-preview.png) shows the original models and textures. It is a
geometry/texture review, not an in-game render. Stock petrol assets are loaded from the player's
installed game; game meshes and textures are not redistributed in this project.

## Placement and evidence

Junction topology remains Overture's mapped network. The prepared road index supplies mapped
signal, stop and give-way nodes, including approach direction. Reversed source geometry reverses
travel-relative node direction too. Signals near an existing junction retain their mapped setback;
an explicitly mapped signal more than 60 m from a source-section end can create a deterministic
mid-block control connector. Nearby parallel roads are not joined into new junctions.

A mapped signal controls the junction's incoming arms, excluding outbound one-way arms and short
internal links to another mapped signal. Static poles and the switchable objects use the same
road-clearance placement helper. Unknown junctions do not acquire invented traffic lights.
The current controller remains a basic two-phase approximation; protected turns, pedestrian heads,
detector timings and full real-world signal programmes have not been reconstructed.

Camera points can describe either the pole or its position projected onto the road. Road-centre
records are moved clear of the carriageway for the visible housing. Triggers cover the resolved
driving width, excluding hard shoulders. An enforcement relation's `from` member supplies travel
direction; an unambiguous one-way road can also supply it. A camera's facing bearing controls its
appearance and is not alone treated as proof of the enforced traffic direction. Unknown direction,
unknown legal limit or conditional camera limits leave a visual asset without guessed enforcement.
Average-speed pairs and red-light-camera enforcement are not added by this pass.

School and fuel identification uses explicit building classes or enclosing mapped amenity areas/
contained amenity points. It does not select an arbitrary nearby building. Canopy identification
requires a roof/carport class or a mapped canopy polygon; other fuel buildings retain closed walls.
The appearance is a contextual approximation rather than a survey of each building's facade.

## Data and performance

`.road-data/uk-context.sqlite` is a separate immutable spatial index prepared from the UK Geofabrik
extract. It covers Great Britain and Northern Ireland, with OSM attribution and the source hash
recorded in its metadata. Rebuild with:

```
python tools/prepare_uk_context.py extract.osm.pbf --output .road-data/uk-context.sqlite
```

Preparation needs pyosmium; the running server needs only its existing Python libraries and SQLite.
`BEAMNG_EARTH_UK_CONTEXT_DB` selects another index. Stop the server before replacing the database.
Its absence leaves the original map generation available. Road-node control information continues
to come from the separately prepared road index.

Runtime lookups are local R-tree queries during tile/graph generation, with a bounded 128-query
cache. There are no new requests to map services while driving. New tile props are capped at 128;
active speed-trap triggers are capped at 32 and restricted to the collidable terrain block. Triggers
are reused when unchanged and removed after leaving the block, teleporting or changing anchor.

New original prop models contain 13–120 triangles each. Small details use the existing Forest
streamer and cull at 150–400 m. Petrol pumps retain the stock asset's LODs. School/fuel wall textures
are batched into the existing building tile mesh and do not add a scene object per building.

The [validation record](uk-street-validation.json) contains automated check totals, data counts,
source-cell smoke checks and sampled tile build timings. The before/after comparison uses the same
cached road cells and native kernels; warmed medians were approximately 61–76 ms per road tile,
with changes within a few milliseconds in the sampled areas. These are generation timings, not FPS.

Live FPS, engine asset rendering and driving through the new camera triggers remain unverified:
BeamNG's local test endpoint refused the connection. No performance guarantee is inferred from
the offline checks.

## References

- [Department for Transport: Know your traffic signs](https://www.gov.uk/government/publications/know-your-traffic-signs)
- [OpenStreetMap traffic-signal mapping](https://wiki.openstreetmap.org/wiki/Tag:highway%3Dtraffic_signals)
- [OpenStreetMap fixed-camera mapping](https://wiki.openstreetmap.org/wiki/Tag:highway%3Dspeed_camera)
- [Geofabrik UK extract and coverage](https://download.geofabrik.de/europe/united-kingdom.html)
- Installed BeamNG `lua/ge/extensions/core/trafficSignals.lua` and
  `lua/ge/extensions/gameplay/speedTraps.lua`, plus the stock West Coast USA speed-trap trigger fields.
