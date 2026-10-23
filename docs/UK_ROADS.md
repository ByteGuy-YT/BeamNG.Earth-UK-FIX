# UK road improvements — updated 22 October 2026

Start **Play UK roads.bat** in this folder to use the changed source and refresh the game's mod
through the existing launcher. An already built executable elsewhere does not contain these changes.
Restart the server and reload the level; existing streamed geometry and AI graphs are not updated in place.
The follow-up [screenshot issue report](UK_ROAD_SCREENSHOT_FIXES.md) maps the latest fixes to the supplied filenames.
The [UK street-details update](UK_STREET_DETAILS.md) adds mapped cameras, UK signals and signs, school/fuel
appearance and small mapped street props while retaining building dimensions.
The [second screenshot review](UK_ROUND2_FIXES.md) covers all 14 follow-up images, the replacement bridge
model, performance changes and measured limits. It supersedes the earlier bridge/performance claims.
The [motorway follow-up](UK_MOTORWAY_FIXES.md) supersedes the round-two motorway and J27 conclusions,
with full-corridor divider coverage, live collision checks and the circular-junction correction.

## Data and interpretation

The Overture download/cache, terrain grading, streamed meshes and BeamNG AI architecture remain.
The road layer cache is now `roads.3`, retaining every OSM source reference. Old source range blocks
can be reused. Enrichment reads the local `.road-data/osm.sqlite` index, containing 8,297,378 road/path
ways from the UK Geofabrik extract downloaded on 20 October 2026. It needs about 2.5 GB of disk space.
The extract's replication timestamp is 19 October 2026, 20:21:11 UTC (recorded in the local source manifest).
This includes Great Britain and Northern Ireland; no Overpass calls are made while driving.

OSM tags are joined by source way IDs and checked against geometry and orientation. Distant matches
are rejected. Multiple source ways are reconciled; changes in lane counts, widths or pavement tags
split the interpretation into stable sections, retaining real junction connectors and interpolating
only along the original centreline. The original downloaded cell is not rewritten.

`server/roadprofile.py` resolves the UK physical cross-section. `Spec.profile` supplies the same
widths/counts to paint, AI, terrain and tree clearance. `server/uk_roads.json` contains fallback
assumptions, in metres. An alternative configuration can be selected with
`BEAMNG_EARTH_UK_ROADS_CONFIG`; restart after changing it.

UK country membership uses the shipped ONS country boundaries. Airports can remain off. England,
Wales, Scotland and Northern Ireland select left-hand traffic and mph; Wales has separate handling
for mapped lit/restricted-road speed context. Conservative advisory speeds remain separate from
mapped legal limits and do not produce guessed speed-limit signs.

## Geometry and appearance

- Ordinary UK roads receive no automatic US parking lanes or 1 m paved strips on both edges.
  Unmapped primary/secondary/tertiary/unclassified carriageways start at 6.5/6.0/5.5/5.0 m.
  These are configurable estimates, not claims of surveyed width. Mapped physical widths win.
- Motorway traffic lanes default to 3.65 m. A conventional motorway gets a separate 3.3 m outer
  hard shoulder and 0.5 m inner strip. Explicit shoulder widths/presence override estimates.
  Traffic-management tags alone do not remove the shoulder: controlled motorways retain it.
  Explicit `shoulder=no` suppresses it for mapped all-lane-running sections. Mapped lane counts
  count driving lanes, independently of the shoulder.
- Hard shoulders and parking are excluded from the AI driving width. Lane counts and paint come
  from the same profile, including unequal forward/backward counts and per-lane widths.
- Sidewalk tags control independent left/right pavement presence and width. Missing urban pavements
  default to 1.8 m, or 1.5 m for residential/living streets. `sidewalk=no` and `sidewalk=separate`
  suppress an invented adjoining pavement. UK kerbs default to 0.125 m above the road edge and
  follow the graded road elevation. Roundabout centres get a 0.25 m kerb band. These dimensions
  are configurable visual estimates, not surveyed UK-wide measurements.
  Optional building measurements can constrain narrow streets; setbacks cannot inflate them.
- UK centre/lane paint is white. Dash/gap patterns are emitted as separate pieces of geometry so
  lane separators cannot become continuous white ribbons through texture handling. Ordinary
  residential streets are unmarked unless mapped otherwise. Give-way lines are on the incoming
  left-hand traffic half. Zebra crossings require mapped zebra evidence; generic junctions no longer
  acquire invented zebra crossings or random all-way stop controls. Circular mph signs replace US signs.
- Explicit roundabout tags work for irregular, large and partially loaded rings. Mapped directions
  are preserved; geometric fallback uses clockwise circulation in the UK. Incoming edges yield using
  BeamNG's existing priority mechanism. Mapped signal controls take precedence. Explicit mini-roundabout
  points receive clockwise graph arcs and a traversable painted centre, rather than a raised island.
- UK streets no longer receive invented rows of pavement trees, US hydrants or generic US-style
  town utility-pole rows. Canopy centres are not relocated onto UK pavements. Tree exclusion includes
  carriageway, pavement, clearance and position-jitter allowance. Vegetation cache version is 13 and
  includes the OSM index and UK configuration signatures, so old pavement trees are not reused.
- Mapped two-way streets override false geometric dual-carriageway inference. Unmapped one-way
  primary/trunk mainlines default to two lanes; explicit counts and consistent lane arrays win.
  These fallbacks are labelled estimates and are not applied as extra lanes to slip roads.
- Short bridge ranges are kept by physical length. Bridge approaches continue over source-way
  boundaries, and paired carriageways share clearance targets. Fill targets account for terrain
  smoothing already applied. Wide ground-road meshes sample across their interior as well as at
  the edges, keeping the rendered underpass closer to collision terrain.
- The grass exclusion mask includes blade reach and terrain-material interpolation around the
  road footprint, including motorways without pavements. Grass remains outside this corridor.

The legacy `--road-widths` option controls building-gap measurements. Mapped OSM width/lane/pavement
attributes work even when that option is off, including the BALANCED launcher defaults.

## Inspecting accuracy

`tools/inspect_uk_roads.py LAT LON --output report.geojson` exports resolved widths, directional
counts, evidence labels, diagnostics and match status. `--offline` uses cached map cells.
`--reference licensed.geojson --width-field roadwidth_average` compares unambiguously aligned
WGS84 reference road lines. No external reference geometry is silently copied into the map.
`--image ortho.png --image-bounds WEST SOUTH EAST NORTH` draws road/pavement edges on a supplied,
north-up orthophoto. It requires known geographic bounds; display zoom is not measurement resolution.

Suitable independent references are OS NGD Road Link width/confidence attributes and Transport Features
polygons for Great Britain, and OSNI network/Fusion and orthophotography for Northern Ireland.
OS Open Roads is generalised and suitable for network checks, not lane-edge ground truth.
Licensed high-resolution aerial/reference data has not been obtained in this task.

Regenerate an index with `tools/prepare_uk_roads.py extract.osm.pbf --output .road-data/osm.sqlite`.
PBF preparation needs optional pyosmium in a compatible preparation Python; the running server does
not need it. OSM XML is supported without that dependency. Stop the server before replacing the index.
`BEAMNG_EARTH_OSM_DB` can select another prepared index. Input SHA-256 hashes and ODbL attribution
are recorded inside the database. New paint/sign assets are reproducible with `tools/make_uk_road_assets.py`.

## Validation and limits

Automated UK cases cover all four nations without airports, Peak District widths, single-track roads,
unequal lanes, hard shoulders/all-lane running, independent pavements, building setbacks, tree exclusion,
give-way handedness, mini-roundabouts, reversed source geometry and preserved lane-change connectors.
Real source cells were generated around Winnats Pass, Bakewell, Baslow, the M1, Cardiff, Edinburgh and
Belfast, checking finite meshes and graph connectivity. Source/mesh smoke tests use a flat elevation
function to isolate horizontal geometry; they do not establish vertical terrain accuracy or driving behaviour.

OSM width/pavement coverage is incomplete. Missing widths remain labelled estimates. A mapped shared
single-track road is painted as shared space, but passing-place negotiations still use stock BeamNG AI.
Per-lane turn restrictions, conditional lane/access rules and shared centre turn lanes are retained as
source data where present, but are not fully enforced by the current road graph. Width changes currently
use source section boundaries rather than surveyed taper shapes. Separately mapped footways retain
the existing renderer's limitations. The stock AI also assumes uniform lane spacing within its graph
edges, even where the visible markings have unequal measured lane widths. Traffic-signal models are
now use original UK heads with the stock controller logic; see the street-details and second-review reports.

No claim is made that every UK lane, pavement or roundabout is now surveyed or verified in game.
BeamNG's local testing endpoint was unavailable, so an in-game driving/visual check remains necessary.
