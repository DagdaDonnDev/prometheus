# Electronics Reference — Foundational Laws

Tier 1 anchor source for the Electronics tab.

## Ohm's Law

The current through a conductor is directly proportional to the voltage across it,
for a conductor at constant temperature.

    V = I R
    V is voltage in volts (V), I is current in amperes (A), R is resistance in ohms (Ω).
    Rearranged: I = V / R, R = V / I.

Ohm's law holds for resistors and metal wires. It does not hold for diodes, LEDs,
transistors or lamps whose filament heats up — these are non-ohmic.

## Electrical Power

Power is the rate at which electrical energy is converted.

    P = V I
    Combined with Ohm's law: P = I² R and P = V² / R.
    Power in watts (W). Energy in joules: E = P t. Energy in watt-hours: Wh = W × hours.

## Kirchhoff's Current Law (KCL)

The total current flowing into a junction equals the total current flowing out.
This follows from conservation of charge.

    Sum of currents in = sum of currents out

## Kirchhoff's Voltage Law (KVL)

Around any closed loop in a circuit, the sum of voltage rises equals the sum of
voltage drops. This follows from conservation of energy.

    Sum of voltages around a loop = 0

## Resistors in Series and Parallel

Series (one path, same current through each):

    R_total = R1 + R2 + R3 ...

Parallel (several paths, same voltage across each):

    1 / R_total = 1/R1 + 1/R2 + 1/R3 ...
    For two resistors: R_total = (R1 × R2) / (R1 + R2)

## Voltage Divider

Two resistors in series across a supply V_in. The voltage across R2 is:

    V_out = V_in × R2 / (R1 + R2)

Derived from Ohm's law and KVL. Only accurate when the load draws little current
compared with the divider current.

## Capacitance

A capacitor stores charge. Charge is proportional to voltage.

    Q = C V
    C in farads (F). Energy stored: E = ½ C V².
    Time constant of a resistor-capacitor circuit: τ = R C (seconds).
    After one τ a charging capacitor reaches about 63% of the supply voltage.
    After 5τ it is effectively fully charged (over 99%).

## Inductance

An inductor resists changes in current.

    V = L dI/dt
    Energy stored: E = ½ L I².
    Time constant of a resistor-inductor circuit: τ = L / R.

## Thévenin's Theorem

Any linear circuit with voltage sources and resistors, seen from two terminals,
behaves exactly like a single voltage source V_th in series with a single resistance R_th.
V_th is the open-circuit voltage at the terminals. R_th is the resistance seen at the
terminals with all independent voltage sources replaced by short circuits.

## Batteries

Cells in series add voltages, capacity (Ah) stays the same.
Cells in parallel keep the same voltage, capacities add.
Typical nominal voltages: lead-acid 2.0 V per cell (12 V battery = 6 cells),
alkaline 1.5 V, NiMH 1.2 V, lithium-ion 3.6–3.7 V.

## Safety Constants

Currents above about 30 mA through the chest can cause fatal heart fibrillation.
Mains voltage (110–240 V AC) is always potentially lethal.
Capacitors can hold a dangerous charge after power is removed — discharge through a resistor.
