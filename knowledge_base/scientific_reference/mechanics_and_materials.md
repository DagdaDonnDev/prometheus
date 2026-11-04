# Mechanics and Materials Reference

Tier 1 anchor source for the Build tab.

## Stress and Strain

    Stress σ = F / A   (force per unit area, pascals or N/mm²; 1 N/mm² = 1 MPa)
    Strain ε = ΔL / L  (change in length over original length, no units)
    Young's modulus E = σ / ε  (stiffness of the material)

These follow from Hooke's law applied per unit area and per unit length.

## Typical Material Properties (approximate)

    Material          Young's modulus     Tensile strength     Density
    Mild steel        200 GPa             400 MPa              7850 kg/m³
    Aluminium         69 GPa              90–300 MPa           2700 kg/m³
    Softwood (pine)   9–11 GPa            40–80 MPa (grain)    450–550 kg/m³
    Hardwood (oak)    11–13 GPa           50–100 MPa (grain)   600–750 kg/m³
    Concrete          25–30 GPa           2–5 MPa tension      2400 kg/m³
                                          20–40 MPa compression
    Fired brick       10–20 GPa           10–50 MPa comp.      1900 kg/m³

Concrete and masonry are strong in compression and weak in tension. Timber is far
stronger along the grain than across it.

## Factor of Safety

    Factor of safety = failure load / working load

For structures that carry people, use at least 2–3 for steel and 3–5 for timber
and masonry, because natural materials vary and loads are uncertain.

## Beams

A beam carries loads across a span by bending.

Simply supported beam, span L, single central point load F:

    Reactions at each support = F / 2  (from static equilibrium)
    Maximum bending moment M = F L / 4  (at the centre)

Simply supported beam with uniformly distributed load w per metre:

    Maximum bending moment M = w L² / 8

Bending stress at the outer fibre:

    σ = M / Z
    For a rectangular section of width b and depth d: Z = b d² / 6

Doubling the depth of a beam makes it four times as strong in bending and eight
times as stiff. Doubling the width only doubles both. Orient joists on edge.

## Columns

Short columns fail by crushing: load capacity = stress limit × area.
Long slender columns fail by buckling at loads far below their crushing strength.
Euler critical load: F_cr = π² E I / (K L)², where I is the second moment of area
(b d³ / 12 for a rectangle) and K depends on end fixing (1.0 for pinned ends).

## Levers, Pulleys and Mechanical Advantage

From conservation of energy (ignoring friction): effort × distance moved by effort
= load × distance moved by load.

    Lever: F_effort × d_effort = F_load × d_load (moments about the pivot)
    Pulley system: mechanical advantage ≈ number of rope sections supporting the load

## Friction

    Friction force F = μ N
    μ is the coefficient of friction, N is the normal force.
    Typical μ: wood on wood 0.25–0.5, rope on wood 0.5, steel on steel 0.5–0.8 (dry).

## Thermal Expansion

    ΔL = α L ΔT
    Steel α ≈ 12 × 10⁻⁶ per K. A 10 m steel bar grows about 1.2 mm per 10 °C rise.
