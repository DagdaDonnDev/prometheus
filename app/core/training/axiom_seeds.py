"""
Axiom Seeds — the concept graph the Training Path starts from
=============================================================
Every concept the derivation engine can work on is defined here.

Tiers:
  1 = Axiom. A universal law or constant. Locked at full confidence.
  2 = Direct. One logical step from tier-1 axioms.
  3 = Composite. Built from tier-2 concepts (or several branches).

Fields for each concept:
  id               unique key, also used in memory/training/graph.json
  name             plain name shown to the user
  tier             1, 2 or 3
  tabs             tabs where this concept can be asked about
  parents          concept ids this one is derived from
  statement        the law or result in one line
  keywords         phrases that match a user's question to this concept
  anchor_query     search text used against the scientific_reference KB domain
  anchor_terms     text that must appear in a retrieved chunk for the anchor
                   to count (compared with spaces removed, lower case)
  result_markers   regexes — a derived RESULT line must match one of these
  violations       (tier 1 only) regexes that mean a derivation contradicts
                   this axiom
  inputs           (optional) quantities needed to work a numeric problem
  sample_problems  worked checks a person can use to test the result
"""

CONCEPTS = [

    # ══════════════════════════════════════════════════════════════════════
    # Tier 1 — Axioms
    # ══════════════════════════════════════════════════════════════════════

    {
        "id": "conservation_of_energy", "name": "Conservation of energy", "tier": 1,
        "tabs": ["electronics", "build", "chemistry"], "parents": [],
        "statement": "Energy cannot be created or destroyed, only converted from one form to another.",
        "keywords": ["conservation of energy", "energy conserved"],
        "anchor_query": "conservation of energy cannot be created or destroyed",
        "anchor_terms": ["energycannotbecreatedordestroyed"],
        "violations": [r"\benergy (is|can be|gets) (created|destroyed)"],
    },
    {
        "id": "conservation_of_charge", "name": "Conservation of charge", "tier": 1,
        "tabs": ["electronics"], "parents": [],
        "statement": "Electric charge cannot be created or destroyed.",
        "keywords": ["conservation of charge"],
        "anchor_query": "conservation of charge cannot be created or destroyed",
        "anchor_terms": ["chargecannotbecreatedordestroyed"],
        "violations": [r"\bcharge (is|can be|gets) (created|destroyed)"],
    },
    {
        "id": "ohms_law", "name": "Ohm's law", "tier": 1,
        "tabs": ["electronics"], "parents": [],
        "statement": "V = I R",
        "keywords": ["ohm's law", "ohms law"],
        "anchor_query": "Ohm's law V = I R voltage current resistance",
        "anchor_terms": ["v=ir"],
        "violations": [r"\bv\s*=\s*i\s*/\s*r\b", r"\bv\s*=\s*r\s*/\s*i\b"],
    },
    {
        "id": "capacitance", "name": "Capacitance (Q = C V)", "tier": 1,
        "tabs": ["electronics"], "parents": [],
        "statement": "Q = C V — stored charge is proportional to voltage.",
        "keywords": ["capacitance", "q = cv"],
        "anchor_query": "capacitor stores charge Q = C V capacitance",
        "anchor_terms": ["q=cv"],
        "violations": [],
    },
    {
        "id": "conservation_of_mass", "name": "Conservation of mass", "tier": 1,
        "tabs": ["chemistry"], "parents": [],
        "statement": "In a closed system mass is neither created nor destroyed.",
        "keywords": ["conservation of mass"],
        "anchor_query": "conservation of mass neither created nor destroyed reaction",
        "anchor_terms": ["massisneithercreatednordestroyed"],
        "violations": [r"\bmass (is|can be|gets) (created|destroyed)", r"\batoms (are|can be) (created|destroyed)"],
    },
    {
        "id": "mole", "name": "The mole", "tier": 1,
        "tabs": ["chemistry"], "parents": [],
        "statement": "One mole is 6.022 × 10²³ particles; molar mass in g/mol equals formula mass.",
        "keywords": ["the mole", "avogadro", "what is a mole"],
        "anchor_query": "mole Avogadro's number molar mass",
        "anchor_terms": ["avogadro"],
        "violations": [],
    },
    {
        "id": "ideal_gas_law", "name": "Ideal gas law", "tier": 1,
        "tabs": ["chemistry"], "parents": [],
        "statement": "P V = n R T",
        "keywords": ["ideal gas law", "pv = nrt", "pv=nrt"],
        "anchor_query": "ideal gas law P V = n R T",
        "anchor_terms": ["pv=nrt"],
        "violations": [],
    },
    {
        "id": "newtons_second_law", "name": "Newton's second law", "tier": 1,
        "tabs": ["build"], "parents": [],
        "statement": "F = m a",
        "keywords": ["newton's second law", "f = ma", "f=ma"],
        "anchor_query": "Newton's second law F = m a force mass acceleration",
        "anchor_terms": ["f=ma"],
        "violations": [],
    },
    {
        "id": "static_equilibrium", "name": "Static equilibrium", "tier": 1,
        "tabs": ["build"], "parents": [],
        "statement": "At rest, the sum of forces is zero and the sum of moments is zero.",
        "keywords": ["static equilibrium", "equilibrium"],
        "anchor_query": "static equilibrium sum of forces sum of moments moment",
        "anchor_terms": ["sumofmoments=0"],
        "violations": [],
    },
    {
        "id": "hookes_law", "name": "Hooke's law", "tier": 1,
        "tabs": ["build"], "parents": [],
        "statement": "F = k x, within the elastic limit.",
        "keywords": ["hooke's law", "hookes law", "elastic limit"],
        "anchor_query": "Hooke's law F = k x elastic extension",
        "anchor_terms": ["f=kx"],
        "violations": [],
    },
    {
        "id": "spherical_earth", "name": "Spherical Earth geometry", "tier": 1,
        "tabs": ["navigation"], "parents": [],
        "statement": "The Earth is very nearly a sphere of mean radius 6,371 km.",
        "keywords": ["shape of the earth", "earth radius", "latitude and longitude"],
        "anchor_query": "shape of the Earth sphere mean radius 6,371 km latitude longitude",
        "anchor_terms": ["6,371km"],
        "violations": [r"\bearth is flat\b"],
    },
    {
        "id": "earth_rotation", "name": "Earth's rotation", "tier": 1,
        "tabs": ["navigation"], "parents": [],
        "statement": "The Earth turns 360° in about 24 hours — 15° of longitude per hour.",
        "keywords": ["earth's rotation", "earth rotation", "15 degrees per hour"],
        "anchor_query": "Earth's rotation 360 degrees 24 hours 15 degrees of longitude per hour",
        "anchor_terms": ["15°oflongitudeperhour"],
        "violations": [],
    },
    {
        "id": "celestial_pole", "name": "The celestial pole", "tier": 1,
        "tabs": ["navigation"], "parents": [],
        "statement": "Polaris sits within about 0.7° of the north celestial pole, directly above the geographic pole.",
        "keywords": ["celestial pole", "north star", "polaris"],
        "anchor_query": "Polaris north celestial pole",
        "anchor_terms": ["northcelestialpole"],
        "violations": [],
    },

    # ══════════════════════════════════════════════════════════════════════
    # Electronics — tier 2 and 3
    # ══════════════════════════════════════════════════════════════════════

    {
        "id": "electrical_power", "name": "Electrical power (P = V I)", "tier": 2,
        "tabs": ["electronics"], "parents": ["conservation_of_energy", "ohms_law"],
        "statement": "P = V I, and with Ohm's law P = I² R = V² / R.",
        "keywords": ["electrical power", "power equals", "p = vi", "p=vi", "watts",
                     "power in a circuit", "power dissipated", "power formula",
                     "power used", "power use", "power consumption", "how many watts"],
        "anchor_query": "electrical power P = V I watts",
        "anchor_terms": ["p=vi"],
        "result_markers": [r"p\s*=\s*v\s*\*?\s*i\b", r"p\s*=\s*i\s*\*?\s*v\b",
                           r"p\s*=\s*i\^?2\s*\*?\s*r", r"p\s*=\s*v\^?2\s*/\s*r"],
        "inputs": ["voltage", "current or resistance"],
        "sample_problems": [
            {"q": "A 12 V lamp draws 2 A. What power does it use?", "a": "24 W"},
            {"q": "A 10 Ω resistor carries 0.5 A. What power does it dissipate?", "a": "2.5 W"},
        ],
    },
    {
        "id": "kirchhoff_current", "name": "Kirchhoff's current law", "tier": 2,
        "tabs": ["electronics"], "parents": ["conservation_of_charge"],
        "statement": "Current into a junction equals current out of it.",
        "keywords": ["kirchhoff's current law", "kirchhoff current", "kcl",
                     "current at a junction", "current into a junction"],
        "anchor_query": "Kirchhoff's current law junction sum of currents in out",
        "anchor_terms": ["sumofcurrentsin"],
        "result_markers": [r"(current|i).{0,30}\bin\b.{0,30}(=|equals).{0,30}\bout\b",
                           r"sum of (all )?currents.{0,30}(=|equals)\s*(0|zero)"],
        "sample_problems": [
            {"q": "3 A and 2 A flow into a junction. One wire leaves. What current is in it?", "a": "5 A"},
        ],
    },
    {
        "id": "kirchhoff_voltage", "name": "Kirchhoff's voltage law", "tier": 2,
        "tabs": ["electronics"], "parents": ["conservation_of_energy"],
        "statement": "Voltages around any closed loop sum to zero.",
        "keywords": ["kirchhoff's voltage law", "kirchhoff voltage", "kvl",
                     "voltage around a loop"],
        "anchor_query": "Kirchhoff's voltage law sum of voltages around a loop",
        "anchor_terms": ["sumofvoltagesaroundaloop=0"],
        "result_markers": [r"(sum of )?(the )?voltages?.{0,40}(loop).{0,30}(=|equals|sum to)\s*(0|zero)",
                           r"(rises|supply).{0,30}(=|equals).{0,30}(drops)"],
        "sample_problems": [
            {"q": "A 9 V battery feeds two resistors in series. One drops 4 V. What does the other drop?", "a": "5 V"},
        ],
    },
    {
        "id": "rc_time_constant", "name": "RC time constant", "tier": 2,
        "tabs": ["electronics"], "parents": ["capacitance", "ohms_law"],
        "statement": "τ = R C — after one τ a charging capacitor reaches about 63%.",
        "keywords": ["time constant", "rc circuit", "capacitor charge time",
                     "how long does a capacitor take"],
        "anchor_query": "time constant resistor capacitor τ = R C",
        "anchor_terms": ["τ=rc"],
        "result_markers": [r"(τ|tau|t)\s*=\s*r\s*\*?\s*c\b"],
        "inputs": ["resistance", "capacitance"],
        "sample_problems": [
            {"q": "10 kΩ with 100 µF. What is the time constant?", "a": "1 second"},
        ],
    },
    {
        "id": "series_resistance", "name": "Resistors in series", "tier": 3,
        "tabs": ["electronics"], "parents": ["ohms_law", "kirchhoff_voltage"],
        "statement": "R_total = R1 + R2 + …",
        "keywords": ["resistors in series", "series resistance", "series resistors"],
        "anchor_query": "resistors in series R_total = R1 + R2",
        "anchor_terms": ["r_total=r1+r2"],
        "result_markers": [r"r\S*\s*=\s*r1\s*\+\s*r2"],
        "inputs": ["resistor values"],
        "sample_problems": [{"q": "100 Ω and 220 Ω in series?", "a": "320 Ω"}],
    },
    {
        "id": "parallel_resistance", "name": "Resistors in parallel", "tier": 3,
        "tabs": ["electronics"], "parents": ["ohms_law", "kirchhoff_current"],
        "statement": "1/R_total = 1/R1 + 1/R2 + …",
        "keywords": ["resistors in parallel", "parallel resistance", "parallel resistors"],
        "anchor_query": "resistors in parallel 1 / R_total = 1/R1 + 1/R2",
        "anchor_terms": ["1/r_total=1/r1+1/r2"],
        "result_markers": [r"1\s*/\s*r\S*\s*=\s*1\s*/\s*r1\s*\+\s*1\s*/\s*r2",
                           r"r\S*\s*=\s*\(?r1\s*\*?\s*r2\)?\s*/\s*\(?r1\s*\+\s*r2"],
        "inputs": ["resistor values"],
        "sample_problems": [{"q": "Two 100 Ω resistors in parallel?", "a": "50 Ω"}],
    },
    {
        "id": "voltage_divider", "name": "Voltage divider", "tier": 3,
        "tabs": ["electronics"], "parents": ["series_resistance", "ohms_law"],
        "statement": "V_out = V_in × R2 / (R1 + R2)",
        "keywords": ["voltage divider", "potential divider", "divide a voltage"],
        "anchor_query": "voltage divider V_out = V_in × R2 / (R1 + R2)",
        "anchor_terms": ["v_out=v_in×r2/(r1+r2)"],
        "result_markers": [r"v\S*\s*=\s*v\S*\s*\*?\s*r2\s*/\s*\(\s*r1\s*\+\s*r2\s*\)"],
        "inputs": ["input voltage", "R1", "R2"],
        "sample_problems": [{"q": "12 V across 1 kΩ (R1) and 2 kΩ (R2). V_out?", "a": "8 V"}],
    },
    {
        "id": "thevenin", "name": "Thévenin's theorem", "tier": 3,
        "tabs": ["electronics"], "parents": ["kirchhoff_voltage", "kirchhoff_current", "ohms_law"],
        "statement": "Any linear two-terminal circuit equals a voltage source V_th in series with R_th.",
        "keywords": ["thevenin", "thévenin", "equivalent circuit"],
        "anchor_query": "Thévenin's theorem equivalent voltage source series resistance",
        "anchor_terms": ["thévenin"],
        "result_markers": [r"(single )?(voltage )?source.{0,40}series.{0,40}resist",
                           r"v_?th.{0,40}r_?th"],
        "sample_problems": [],
    },

    # ══════════════════════════════════════════════════════════════════════
    # Chemistry — tier 2 and 3
    # ══════════════════════════════════════════════════════════════════════

    {
        "id": "mass_mole_conversion", "name": "Mass to moles (n = m / M)", "tier": 2,
        "tabs": ["chemistry"], "parents": ["mole"],
        "statement": "n = m / M",
        "keywords": ["mass to moles", "moles from mass", "how many moles", "n = m/m",
                     "molar mass"],
        "anchor_query": "moles n = mass m / molar mass M",
        "anchor_terms": ["molesn=massm/molarmassm"],
        "result_markers": [r"\bn\s*=\s*m\s*/\s*m\b", r"moles\s*=\s*mass\s*/\s*molar mass"],
        "inputs": ["mass", "substance"],
        "sample_problems": [{"q": "How many moles in 36 g of water?", "a": "about 2.0 mol"}],
    },
    {
        "id": "balanced_equations", "name": "Balancing equations", "tier": 2,
        "tabs": ["chemistry"], "parents": ["conservation_of_mass"],
        "statement": "A balanced equation has the same number of each kind of atom on both sides.",
        "keywords": ["balance an equation", "balancing equations", "balanced equation"],
        "anchor_query": "balanced equation same number of each kind of atom both sides",
        "anchor_terms": ["balancedequation"],
        "result_markers": [r"same number of (each )?(kind of |type of )?atoms?",
                           r"atoms?.{0,40}(equal|same).{0,30}(both sides|each side|products)"],
        "sample_problems": [{"q": "Balance H₂ + O₂ → H₂O.", "a": "2H₂ + O₂ → 2H₂O"}],
    },
    {
        "id": "dilution", "name": "Dilution (c1 V1 = c2 V2)", "tier": 2,
        "tabs": ["chemistry"], "parents": ["mole"],
        "statement": "c1 V1 = c2 V2 — the moles of solute stay the same when you add water.",
        "keywords": ["dilution", "dilute", "c1v1", "weaker solution"],
        "anchor_query": "dilution c1 V1 = c2 V2 concentration",
        "anchor_terms": ["c1v1=c2v2"],
        "result_markers": [r"c1\s*\*?\s*v1\s*=\s*c2\s*\*?\s*v2"],
        "inputs": ["starting concentration", "starting volume", "target concentration or volume"],
        "sample_problems": [{"q": "Dilute 1 L of 2 mol/L to 0.5 mol/L. Final volume?", "a": "4 L"}],
    },
    {
        "id": "gas_molar_volume", "name": "Molar volume of a gas", "tier": 2,
        "tabs": ["chemistry"], "parents": ["ideal_gas_law"],
        "statement": "At 0 °C and 1 atm one mole of an ideal gas occupies about 22.4 L.",
        "keywords": ["molar volume", "volume of a mole of gas", "22.4"],
        "anchor_query": "one mole of an ideal gas occupies 22.4 litres 0 °C 1 atm",
        "anchor_terms": ["22.4litres"],
        "result_markers": [r"22\.4\s*(l|litres|liters)", r"v\s*=\s*n\s*\*?\s*r\s*\*?\s*t\s*/\s*p"],
        "sample_problems": [{"q": "Volume of 2 mol of gas at 0 °C, 1 atm?", "a": "about 44.8 L"}],
    },
    {
        "id": "stoichiometry", "name": "Stoichiometry", "tier": 3,
        "tabs": ["chemistry"], "parents": ["mass_mole_conversion", "balanced_equations"],
        "statement": "Mass → moles → mole ratio from the balanced equation → moles → mass.",
        "keywords": ["stoichiometry", "how much product", "reacting masses", "mole ratio"],
        "anchor_query": "stoichiometry mole ratio balanced equation mass of product",
        "anchor_terms": ["moleratio"],
        "result_markers": [r"mole ratio", r"moles?.{0,40}ratio.{0,40}(coefficients|balanced)"],
        "inputs": ["balanced equation", "mass of a reactant"],
        "sample_problems": [{"q": "Mass of water from 4 g of H₂ burned fully?", "a": "about 36 g"}],
    },
    {
        "id": "limiting_reagent", "name": "Limiting reagent", "tier": 3,
        "tabs": ["chemistry"], "parents": ["stoichiometry"],
        "statement": "The reactant that runs out first sets the maximum yield.",
        "keywords": ["limiting reagent", "limiting reactant", "which runs out first"],
        "anchor_query": "limiting reagent runs out first maximum yield",
        "anchor_terms": ["limitingreagent"],
        "result_markers": [r"runs? out first", r"(smallest|fewest|least).{0,40}moles?.{0,40}(ratio|coefficient)"],
        "sample_problems": [],
    },

    # ══════════════════════════════════════════════════════════════════════
    # Build — tier 2 and 3
    # ══════════════════════════════════════════════════════════════════════

    {
        "id": "stress", "name": "Stress (σ = F / A)", "tier": 2,
        "tabs": ["build"], "parents": ["hookes_law"],
        "statement": "σ = F / A",
        "keywords": ["stress", "force per area", "how much load can"],
        "anchor_query": "stress σ = F / A force per unit area",
        "anchor_terms": ["σ=f/a"],
        "result_markers": [r"(σ|sigma|stress)\s*=\s*f\s*/\s*a\b"],
        "inputs": ["force", "cross-section area"],
        "sample_problems": [{"q": "10 kN on a 100 mm² rod. Stress?", "a": "100 N/mm² (100 MPa)"}],
    },
    {
        "id": "lever_moments", "name": "Levers and moments", "tier": 2,
        "tabs": ["build"], "parents": ["static_equilibrium"],
        "statement": "F_effort × d_effort = F_load × d_load about the pivot.",
        "keywords": ["lever", "moment", "pivot", "fulcrum", "crowbar"],
        "anchor_query": "lever moments pivot effort load distance moment M = F × d",
        "anchor_terms": ["momentm=f×d"],
        "result_markers": [r"f\S*\s*\*\s*d\S*\s*=\s*f\S*\s*\*\s*d\S*", r"effort.{0,30}distance.{0,30}=.{0,30}load"],
        "inputs": ["load", "distances from the pivot"],
        "sample_problems": [{"q": "500 N load 0.2 m from pivot, effort 1.0 m away. Effort?", "a": "100 N"}],
    },
    {
        "id": "mechanical_advantage", "name": "Mechanical advantage", "tier": 2,
        "tabs": ["build"], "parents": ["conservation_of_energy"],
        "statement": "Effort × effort distance = load × load distance (ignoring friction).",
        "keywords": ["mechanical advantage", "pulley", "block and tackle"],
        "anchor_query": "mechanical advantage pulley effort distance load distance",
        "anchor_terms": ["mechanicaladvantage"],
        "result_markers": [r"effort\s*\*\s*.{0,20}distance.{0,30}=\s*load", r"(ma|mechanical advantage)\s*=\s*load\s*/\s*effort",
                           r"(ma|mechanical advantage)\s*=.{0,40}(rope|sections|strands)"],
        "sample_problems": [{"q": "A 4-rope pulley lifts 800 N. Effort (no friction)?", "a": "200 N"}],
    },
    {
        "id": "beam_reactions", "name": "Beam support reactions", "tier": 2,
        "tabs": ["build"], "parents": ["static_equilibrium"],
        "statement": "A central load F on a simple beam puts F / 2 on each support.",
        "keywords": ["support reaction", "beam reaction", "load on each support"],
        "anchor_query": "simply supported beam reactions at each support F / 2",
        "anchor_terms": ["reactionsateachsupport=f/2"],
        "result_markers": [r"(r|reaction)\S*\s*=\s*f\s*/\s*2", r"half (of )?the load"],
        "sample_problems": [{"q": "2 kN at the centre of a beam. Load on each support?", "a": "1 kN"}],
    },
    {
        "id": "beam_bending", "name": "Beam bending moment", "tier": 3,
        "tabs": ["build"], "parents": ["beam_reactions", "lever_moments"],
        "statement": "Central point load: M = F L / 4. Uniform load: M = w L² / 8.",
        "keywords": ["bending moment", "beam strength", "how strong a beam", "joist", "span"],
        "anchor_query": "maximum bending moment M = F L / 4 simply supported beam",
        "anchor_terms": ["m=fl/4"],
        "result_markers": [r"m\S*\s*=\s*f\s*\*?\s*l\s*/\s*4", r"m\S*\s*=\s*w\s*\*?\s*l\^?2\s*/\s*8"],
        "inputs": ["load", "span"],
        "sample_problems": [{"q": "4 kN at the centre of a 3 m span. Max moment?", "a": "3 kN·m"}],
    },
    {
        "id": "factor_of_safety", "name": "Factor of safety", "tier": 3,
        "tabs": ["build"], "parents": ["stress"],
        "statement": "Factor of safety = failure load / working load.",
        "keywords": ["factor of safety", "safety factor", "safe load"],
        "anchor_query": "factor of safety failure load working load",
        "anchor_terms": ["factorofsafety=failureload/workingload"],
        "result_markers": [r"(factor of safety|fos|sf)\s*=\s*(failure|ultimate).{0,20}/\s*(working|allowable)"],
        "sample_problems": [{"q": "Rope breaks at 6 kN, working load 2 kN. FoS?", "a": "3"}],
    },

    # ══════════════════════════════════════════════════════════════════════
    # Navigation — tier 2 and 3
    # ══════════════════════════════════════════════════════════════════════

    {
        "id": "latitude_from_polaris", "name": "Latitude from Polaris", "tier": 2,
        "tabs": ["navigation"], "parents": ["celestial_pole", "spherical_earth"],
        "statement": "The altitude of Polaris above the horizon equals your latitude.",
        "keywords": ["latitude from polaris", "latitude from the north star",
                     "find latitude", "work out my latitude"],
        "anchor_query": "angle of Polaris above the horizon equals your latitude",
        "anchor_terms": ["equalsyourlatitude"],
        "result_markers": [r"(altitude|angle|height).{0,40}polaris.{0,40}(=|equals|is).{0,20}latitude",
                           r"latitude\s*(=|equals|is).{0,30}(altitude|angle).{0,30}polaris"],
        "sample_problems": [{"q": "Polaris is 53° above the horizon. Latitude?", "a": "about 53° N"}],
    },
    {
        "id": "longitude_from_time", "name": "Longitude from time", "tier": 2,
        "tabs": ["navigation"], "parents": ["earth_rotation"],
        "statement": "Each hour local noon differs from Greenwich noon is 15° of longitude.",
        "keywords": ["longitude from time", "find longitude", "work out my longitude",
                     "longitude using a watch"],
        "anchor_query": "longitude from time local noon UTC 15 degrees",
        "anchor_terms": ["longitude=(12:00"],
        "result_markers": [r"15\s*(°|degrees?).{0,30}(per|each|every|for each)?\s*hour",
                           r"longitude\s*=.{0,40}\*\s*15"],
        "inputs": ["time of local noon in UTC"],
        "sample_problems": [{"q": "Local noon happens at 14:00 UTC. Longitude?", "a": "30° W"}],
    },
    {
        "id": "degree_distances", "name": "Distance per degree", "tier": 2,
        "tabs": ["navigation"], "parents": ["spherical_earth"],
        "statement": "One degree of latitude ≈ 111 km; one degree of longitude ≈ 111 km × cos(latitude).",
        "keywords": ["distance per degree", "how far is a degree", "km per degree",
                     "nautical mile"],
        "anchor_query": "one degree of latitude 111 km longitude cos latitude",
        "anchor_terms": ["onedegreeoflatitude≈111km"],
        "result_markers": [r"111\s*km", r"2\s*\*?\s*(π|pi)\s*\*?\s*r\s*/\s*360"],
        "sample_problems": [{"q": "Length of 1° of longitude at 60° latitude?", "a": "about 55.5 km"}],
    },
    {
        "id": "haversine", "name": "Great-circle distance", "tier": 3,
        "tabs": ["navigation"], "parents": ["spherical_earth", "degree_distances"],
        "statement": "d = 2R · atan2(√a, √(1−a)) with the haversine term a.",
        "keywords": ["haversine", "great circle", "distance between two points",
                     "distance between two coordinates"],
        "anchor_query": "great-circle distance haversine formula",
        "anchor_terms": ["haversine"],
        "result_markers": [r"sin\^?2\s*\(\s*(δφ|dlat|Δφ|delta)", r"d\s*=\s*r\s*\*?\s*c\b", r"atan2"],
        "inputs": ["start latitude and longitude", "end latitude and longitude"],
        "sample_problems": [],
    },
    {
        "id": "dead_reckoning", "name": "Dead reckoning", "tier": 3,
        "tabs": ["navigation"], "parents": ["degree_distances"],
        "statement": "Position from heading, speed and time: north change = d cos(heading), east change = d sin(heading).",
        "keywords": ["dead reckoning", "estimate my position", "how far have i travelled"],
        "anchor_query": "dead reckoning heading speed time distance",
        "anchor_terms": ["deadreckoning"],
        "result_markers": [r"cos\s*\(?\s*(heading|θ|bearing)", r"distance\s*=\s*speed\s*\*\s*time"],
        "inputs": ["heading", "speed", "time travelled"],
        "sample_problems": [{"q": "5 km/h due east for 2 hours. Change in position?", "a": "10 km east"}],
    },
]


def concept_map():
    """Return {id: concept} for quick lookup."""
    return {c["id"]: c for c in CONCEPTS}
