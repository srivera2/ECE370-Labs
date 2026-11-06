// ─────────────────────────────────────────────────────────────
// ECE 370/590 — Laboratory Exercise 1: The Dipole Antenna
// Save this file in ~/Plots/ so the image paths below resolve
// (Typst can't read files above the project root).
// ─────────────────────────────────────────────────────────────

#import "@local/roshan:0.2.0": *
#show: assignment.with( // article · report · assignment · memo · notes
  title: [Lab Exercise 1: The Dipole Antenna],
  authors: [Roshan Sundaram], // "Name" · ("A", "B") · ((name:, affiliation:, email:),)
  course: "ECE 370",
  date: "10/28/2026", // auto · "Oct 3, 2026" · none
  // fields: (Instructor: [..]), // any extra label/value pairs
)

// ── Helpers ──────────────────────────────────────────────────
#let plots = "Plots/Lab 1/"

#let question(num, body) = block(
  width: 100%,
  inset: 10pt,
  radius: 3pt,
  fill: luma(242),
  stroke: (left: 2pt + luma(150)),
  breakable: true,
)[*Question #num.* #body]

#let answer(body) = block(width: 100%, inset: (x: 2pt, y: 6pt))[
  *Answer.* #body
]

#let todo = text(fill: rgb("#b03a2e"))[_[Answer here.]_]

#let plot(file, caption, width: 85%) = figure(
  image(plots + file, width: width),
  caption: caption,
)

// CST menu path, e.g. #menu[Simulation → Discrete Port]
#let menu(body) = text(font: "DejaVu Sans Mono", size: 0.9em, body)

// ═════════════════════════════════════════════════════════════
= Exercise 1.1: Analytical Design

At $f = 1 "GHz"$, the free-space wavelength is

$ lambda = c/f = (2.998 times 10^8 "m/s")/(1 times 10^9 "Hz") = 299.8 "mm" $

so an exact half wave is $lambda \/ 2 = 149.9 "mm"$.

#figure(
  table(
    columns: 4,
    align: (left, center, center, left),
    stroke: 0.5pt + luma(160),
    table.header([*Parameter*], [*Symbol*], [*Value*], [*Reason*]),
    [Total length (tip to tip)], [$L$], [149.9 mm], [A half wave dipole is simple and effective, so we shall use it in this lab.],
    [Conductor], [—], [], [_[...]_],
    [Wire radius (or strip width)], [$a$ (or $w$)], [_[...]_ mm], [_[...]_],
    [Feed gap], [$g$], [_[...]_ mm], [_[match adapter terminal spacing]_],
  ),
  caption: [Initial design parameters.],
) <tab:design>

#question(1)[
  What initial dimensions would you select for a dipole resonant near 1 GHz
  and why?
]

#answer[#todo]

#question(2)[
  What input resistance do you expect at resonance, and how does this compare
  with the 50 $Omega$ impedance of the VNA?
]

#answer[#todo]

#question(3)[
  How should the antenna impedance change as the length is increased or
  decreased?
]

#answer[#todo]

#question(4)[
  How might the conductor diameter or width affect resonance and bandwidth?
]

#answer[#todo]

// ═════════════════════════════════════════════════════════════
= Exercise 1.2: CST Simulation

== Project setup

+ *New project.* #menu[File → New and Recent → New Template → Microwaves & RF/Optical
  → Antennas → Wire → Time Domain]. Units: mm, GHz, ns. Frequency range
  $0.7$ to $1.3 "GHz"$ (a narrow band keeps the mesh small, since CST sizes
  cells by the wavelength at $f_"max"$).

+ *Field monitors* (the template wizard asks; or add later from
  #menu[Simulation → Field Monitor]):
  - H-field / surface current at 0.9, 1.0, 1.1 GHz (surface current is derived
    from the H-field monitor).
  - Farfield at 1.0 GHz (for radiation efficiency later).

+ *Parameters.* In the #menu[Parameter List] at the bottom, add:
  - `L` = total length (from @tab:design)
  - `a` = wire radius
  - `g` = feed gap
  Build everything below from these names so the sweeps update the geometry.

+ *Boundaries.* #menu[Simulation → Boundaries]: all six faces *open (add
  space)*. The template already does this; confirm it, and check that the
  background adds roughly $lambda\/4$ of space around the antenna.

== Geometry (round wire)

+ *Upper arm.* #menu[Modeling → Shapes → Cylinder], press Esc to type values:
  - Orientation: Z. Outer radius `a`, inner radius 0.
  - Xcenter = Ycenter = 0. Zmin = `g/2`, Zmax = `L/2`.
  - Segments: 0 for a true circle. If you hit the 2000-element limit, set 8
    (octagonal prism), as in Exercise 4.
  - Material: PEC to start.

+ *Lower arm.* Same dialog with Zmin = `-L/2`, Zmax = `-g/2`. Name it as a
  separate solid so the two arms are not merged.

#block(inset: (left: 1em))[
  _Copper-tape alternative:_ #menu[Shapes → Brick] with X from `-w/2` to `w/2`,
  Y from 0 to `t` (tape thickness, about 0.04–0.07 mm; measure yours), Z from
  `g/2` to `L/2`, and mirrored for the other arm. Add a foam board brick
  behind it (#menu[Materials → New]: $epsilon_r approx 1.05$–$1.1$). Thin
  tape is mesh-expensive; if the cell count explodes, model it as a zero-thickness
  PEC sheet instead.
]

== Feed

+ *Discrete port by coordinates.* #menu[Simulation → Sources and Loads →
  Discrete Port]. Uncheck *Use pick* for both points:
  - Point 1: (0, 0, `g/2`). Point 2: (0, 0, `-g/2`).
  - Type: S-Parameter. Impedance: 50 $Omega$. Radius: 0.
  This bridges the two arm end faces along the axis and tracks `g` in sweeps.

+ *Realistic feed (do this after the ideal case works).* Set `g` to the actual
  spacing of the SMA screw terminals, and add the short leads from the
  terminals to the arms as extra wire segments. Record which version produced
  each plot. The coax itself sits behind the calibration plane and is not
  modeled.

== Mesh

+ #menu[Simulation → Mesh → Mesh View]. Check the cell count in the status
  bar against the license limit.
+ If over the limit, in order:
  - Segments = 8 on both cylinders.
  - #menu[Global Properties]: lower cells per wavelength; raise the minimum
    cell size.
  - Narrow the band to 0.8–1.2 GHz.
  - Symmetry planes (#menu[Simulation → Boundaries → Symmetry Planes]): YZ and
    XZ as *magnetic* ($H_t = 0$), since $vec(H)$ circles the z-directed
    current and is normal to any plane containing the wire. Drop this if CST
    complains about the port on the plane.
+ *Convergence check.* #menu[Time Domain Solver → Adaptive mesh refinement]
  on, or run twice with denser mesh and confirm the zero-reactance frequency
  moves by less than about 1%. Report this.

== Solve and read results

+ #menu[Simulation → Setup Solver]: Time Domain, accuracy $-40$ dB. Start.
  If the solver warns that energy has not decayed, increase the number of
  pulses / simulation duration.

+ *$S_11$.* #menu[1D Results → S-Parameters → S1,1]. Plot in dB and also as
  Re/Im (right-click → Plot Properties, or the #menu[1D Plot] ribbon).
  Use curve markers for the $|S_11|$ minimum and the $-10$ dB crossings.

+ *Input impedance.* #menu[1D Results → Z Parameters → Z1,1], Re and Im.
  Marker where $"Im"(Z_11)$ crosses zero: that is the zero-reactance
  frequency; read $R$ there. Cross-check one point by hand with
  $Z_"in" = 50 (1 + S_11)\/(1 - S_11)$ using full-precision marker values.

+ *Surface current.* #menu[2D/3D Results → Surface Current → h-field (f=1)].
  Show as arrows or abs, with a linear scale. For a distribution along the
  arm: #menu[Modeling → Curves → Line] from (`a`, 0, `g/2`) to
  (`a`, 0, `L/2`), then #menu[Post-Processing → Template Based
  Post-Processing → 1D → Evaluate Field on Curve] on the H-field monitor
  (tangential H at the surface equals the surface current density).

+ *Efficiency (for Q12 later).* #menu[Farfields → farfield (f=1)] reports
  Rad. efficiency. It is 100% for PEC. Change the arms to *Copper
  (annealed)*, rerun, and note the change in $R$ and efficiency.

== Parameter sweeps

+ *Length.* #menu[Simulation → Par. Sweep → New Seq. → New Par.]: `L` from
  130 to 160 mm in 5 mm steps (finer near resonance once you see it). Add
  result templates for S1,1 and Z1,1 if your version does not store them
  automatically. Overlay results with the #menu[Result Navigator].

+ *Thickness (if time).* Sweep `a` over the radii of the wire gauges
  available, holding `L` fixed. Look at the zero-reactance frequency and the
  width of the $-10$ dB band.

+ *Export.* #menu[File → Export → Touchstone] (or right-click a 1D result →
  Export → ASCII) for each case, so CST and LibreVNA data can be overlaid in
  Python with identical axes.

// #plot("S11 dB sweep L.png", [Simulated $|S_11|$ vs. frequency for several lengths.]) <fig:s11-sweep>
// #plot("Z11 re im.png", [Simulated input resistance and reactance.]) <fig:z11>
// #plot("surface current.png", [Surface current near resonance.]) <fig:current>

#question(5)[
  How closely does the simulated resonant length agree with your analytical
  estimate?
]

#answer[#todo]

#question(6)[
  What happens to the input impedance as the dipole length changes?
]

#answer[#todo]

#question(7)[
  How does the predicted bandwidth depend on conductor thickness or width?
]

#answer[#todo]

#question(8)[
  What current distribution is observed along the antenna near resonance?
]

#answer[#todo]

*Selected fabrication geometry:* _[...]_

// ═════════════════════════════════════════════════════════════
= Exercise 1.3: Fabrication

// #plot("built antenna.jpg", [As-built dipole.]) <fig:built>

#figure(
  table(
    columns: 3,
    align: (left, center, center),
    stroke: 0.5pt + luma(160),
    table.header([*Dimension*], [*Design*], [*As built*]),
    [Total length $L$], [_[...]_], [_[...]_],
    [Radius $a$ / width $w$], [_[...]_], [_[...]_],
    [Feed gap $g$], [_[...]_], [_[...]_],
    [Lead length], [_[...]_], [_[...]_],
  ),
  caption: [Design vs. as-built dimensions.],
) <tab:built>

*CST update:* if any as-built dimension differs appreciably, change the
parameters in the #menu[Parameter List] to the measured values and rerun the
single-point simulation (no sweep). Use this as the CST curve in the
measurement overlays.

// ═════════════════════════════════════════════════════════════
= Exercise 1.4: Calibration and Measurement

_[Calibration range, standards, reference plane, adapter treatment, cable-movement diagnostic.]_

// ═════════════════════════════════════════════════════════════
= Exercise 1.5: Geometry Study

_[Lengths measured, CST vs. measured shift in resonance and impedance.]_

// ═════════════════════════════════════════════════════════════
= Exercise 1.6: Comparison with Theory

#question(9)[
  How does the analytical radiation resistance compare with the simulated
  input resistance?
]

#answer[#todo]

#question(10)[
  How closely does the measured resistance agree with simulation?
]

#answer[#todo]

#question(11)[
  What physical effects could account for differences?
]

#answer[#todo]

#question(12)[
  Can the measured input resistance alone establish the antenna's radiation
  efficiency? Explain.
]

#answer[#todo]

// ═════════════════════════════════════════════════════════════
= Discussion

_[Resonant length vs. $lambda\/2$; what sets bandwidth; tape vs. round wire;
feed-cable effects; VNA accuracy and de-embedding; what theory predicts
reliably vs. what needs simulation.]_
