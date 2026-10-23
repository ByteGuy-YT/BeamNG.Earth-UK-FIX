# UK road screenshot fixes — 21 October 2026

The changes are in the shared UK road generation, grading, paint and vegetation rules. There are
no coordinate-specific road patches. The supplied image filenames below identify the reported
issues; the Street View images provide visual comparisons, not measured lane-edge surveys.

Start **Play UK roads.bat** from the project folder, restart the server and reload the level.
An existing executable elsewhere will not contain these source changes. The launcher refreshes
the mod when its contents differ. Existing streamed geometry and AI graphs need a fresh session.
The downloaded map and elevation caches do not need a blanket deletion.

## Reported issues and changes

| Supplied filename | General change |
| --- | --- |
| `not usable bridge m1 between J27 + J26.png` | Bridge ranges now survive short spans on long source roads. Nearby endpoints use a physical snap distance. Approaches continue across source sections; adjacent carriageways share clearance targets before their decks are merged. |
| `weird road textures and mesh under SOME motorways.png` | Wide draped road meshes sample elevation through the interior at intervals no greater than 2 m across the road. The old edge-only triangles could span over lower collision terrain and hide part of a vehicle. |
| `again another example of bridge issue this one is on a610 on the way to riply.png` | Mapped bridge tags and section boundaries remain distinct. Major-road approaches receive continuous fill, using absolute clearance targets instead of adding the raw-terrain lift twice. |
| `example of broken pavement in ripley.png` | Pavement cross-sections fit their actual width, preventing folded or reversed triangles. Kerb curves and runs sample the graded road surface after joining and simplification. |
| `example of broken rounabout ripley police station, again mainly pavement.png` | Narrow island kerbs replace the invented 1.2 m paved ring. Corner widths respect the adjoining side's pavement. The entire pavement slab is considered when excluding it from another road. |
| `incorrect amount of lanes entering a38 roundabout on a610.png` | Explicit lane counts and consistent turn/change/width lane arrays provide lane evidence. One-way primary/trunk mainlines with no count use a labelled two-lane estimate. Source-way lane changes are preserved. |
| `main road underwood totally wrong, only 1 lane tall pavements.png` | Matched OSM roads with normal two-way operation override false dual-carriageway inference caused by nearby bends of the same street. Carriageways keep both directions; UK kerbs default to 0.125 m above the road edge. |
| `mansfield road coming from junction 27 of m1 only 1 thin lane instead of 2.png` | One-way major-road fallback changes from one narrow lane to two lanes, with explicit mapped counts taking precedence. AI, visible lane widths and terrain use the same profile. |
| `one lane instead of 2 and traffic going wrong way at junction 27 m1.png` | The corrected major-road profiles reach the AI graph with directional lane counts and mapped oneway orientation. This is covered by synthetic graph checks; live traffic at the photographed junction remains to be checked in game. |
| `pavements should follow roads and not be so tall.png` | Pavement elevations are sampled along the kerb at up to 2 m spacing, including corners and islands. UK kerbs use the lower configurable height, and pavement joins retain compatible widths. |
| `road + pavement seems weirdly scaled compared to irl NG16 5FN underwood.png` | Residential/living-street pavements default to 1.5 m per side instead of 1.8 m. Ordinary two-way residential roads no longer receive an invented centreline. Mapped widths override defaults. |
| `road too thin + floating pavement in ripley.png` | Correct two-way interpretation prevents false one-lane narrowing. Pavements follow road-edge height rather than a sparse line interpolated across hills and sags. |
| `HUGE dips in SOME dual carridgeways (this one is the A610 just off the motorway island heading to langly mill).png` | Physically short bridge sections are retained; connected approach fill crosses source boundaries. Clearance targets account for existing smoothed terrain fill. This addresses the shared causes; it does not establish surveyed elevations at every crossing. |
| `I LOVE the grass but often overlays onto roads.png` | Grass masks cover the full resolved pavement/road corridor plus blade/interpolation clearance. Rounded mask ends avoid grass at section joins. Vegetation cache version 13 regenerates exclusions while keeping surrounding grass. |
| `lanes not wide enough on SOME rounabouts for example this one is 2 lanes into a very thin one lane on a610 at evri in langly mill.png` | Major roundabout fallback width follows the approach's two-lane interpretation; explicit counts win. Single-lane roundabouts have a wider configurable circulation fallback, while island kerbs occupy a much narrower band. |
| `motorway missing lanes + graphics.png` | Lane changes within combined source ways remain separate. Lane separators are real dashed pieces on both carriageways and bridge decks. Interior road elevation samples address wide floating surface triangles. |
| `motorway only 4 lanes and ai using hard shoulder.png` | Four mapped M1 driving lanes remain four driving lanes, with a separate outer shoulder and solid traffic-edge line. Traffic-management tags no longer suppress that shoulder. The AI corridor excludes shoulder width. |

The first sentence of the request also reports solid lane separators. The paint change applies to
every generated UK dashed lane separator, give-way dash and mapped zebra stripe, including fixed
bridge paint. Solid traffic-edge lines remain continuous.

## Supplied real-life references

| Reference filename | Comparison used |
| --- | --- |
| `real life bluebell close.png` | Unmarked residential carriageway and modest adjoining pavement; the image itself labels Fairview Avenue. |
| `real life j27 roundabout.png` | Curving approach, low kerbs and grass island. |
| `real life m1.png` | Separate driving lanes, dashed separators and shoulder edge. |
| `real life main road underwood.png` | Two-way village street, centre dashes and low kerbs. |
| `REAL LIFE mansfield road.png` | Two-lane divided carriageway and a separate grass median. |
| `real life road in riply.png` | Two-way Nottingham Road and pavements following the carriageway. |
| `real life roundabout outside police station ripley.png` | Low island kerbs and road-following splitter geometry. |
| `real life a610.png` | Two-lane divided road, dashed lane separators and grass retained off the carriageway. |

The [OSM traffic-management documentation](https://wiki.openstreetmap.org/wiki/Key:active_traffic_management)
distinguishes traffic management from shoulder absence. The
[Highways England evaluation of M1 J25–28 widening](https://assets.publishing.service.gov.uk/media/5c7801caed915d29e1eca910/POPE_M1_J25-28_FYA_Report.pdf)
describes controlled operation and a hard shoulder, including narrowed sections at bridges. These
support retaining a default shoulder rather than removing it just because a motorway has traffic
management. Exact shoulder widths still require mapped width evidence.

## Validation

318 automated checks passed across road profiles, meshes, grading, approaches, surface masks,
AI graph direction, traffic, furniture, islands, vegetation, map enrichment, tunnels, parking,
worker output, pavement collision and CDAE output. The new screenshot regression suite varies
geometry and terrain rather than encoding fixes for the named locations.

Actual cached source data was also generated around Underwood, Ripley, the A610 Langley Mill
roundabout and the M1. The [plan-view preview](uk-road-geometry-preview.png) was inspected for
horizontal geometry and markings. It deliberately uses flat terrain to isolate those checks;
it is not an in-game screenshot or a test of bridge clearance.

Separate checks using cached zoom-15 elevation and the real grading/deck code sampled bridges
near M1 J26, between J26/J27, at J27 and on the A610 railway crossing. The
[validation record](uk-road-validation.json) contains the measured generated grades and endpoint
height differences. These are properties of the generated model, not real-world survey results.

## Remaining limits

BeamNG's local testing endpoint was unavailable. Live driving, traffic at the photographed
junctions and final appearance in BeamNG have not been verified in this pass.

OSM lane and pavement width coverage is incomplete. Unmapped dimensions, the major-road
two-lane fallback, pavement widths and kerb dimensions remain labelled/configurable estimates.
No licensed lane-edge or high-resolution elevation survey was obtained. Lane changes use source
section boundaries; surveyed tapers, driveways and dropped kerbs are not reconstructed everywhere.
Dynamic shoulder opening and conditional turn/access restrictions are not fully modelled by the
current AI graph. These general fixes do not imply every road in the UK has been individually checked.
