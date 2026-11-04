"""
Printable Emergency Reference Generator
========================================
Generates a compact PDF of the most critical survival knowledge.
Formatted for printing and laminating.
6 double-sided pages. Fits in a wallet or pocket.

Usage:
    python generate_reference.py
    Or from within the app: Settings → Generate Print Reference
"""

import os
import sys
from pathlib import Path
from datetime import datetime


OUTPUT_PATH = "Prometheus_Emergency_Reference.pdf"


# ── Reference content ──────────────────────────────────────────────────────
# Hard-coded critical content — does not depend on knowledge base
# So it works even before ingestion is complete

REFERENCE_CONTENT = {

    "page1": {
        "title": "IMMEDIATE PRIORITIES",
        "subtitle": "First 72 hours — do these in order",
        "sections": [
            {
                "heading": "The Rule of 3s",
                "content": [
                    "3 minutes without air → death",
                    "3 hours in extreme cold without shelter → death",
                    "3 days without water → death",
                    "3 weeks without food → death",
                    "Act in this order: breathing → shelter → water → food",
                ]
            },
            {
                "heading": "Water — Find It Now",
                "content": [
                    "Follow animal trails at dawn/dusk → water",
                    "Green vegetation in dry area → water below",
                    "Dry riverbeds: dig outer bend 30-60cm",
                    "Collect morning dew with cloth before 9am",
                    "ALWAYS purify: boil 1 min (3 min above 2000m)",
                    "Chemical: 2 drops bleach per litre, wait 30 min",
                ]
            },
            {
                "heading": "Shelter — Before Nightfall",
                "content": [
                    "Insulate FROM GROUND — ground steals heat fastest",
                    "Debris hut: lean branches, pile leaves 1m thick",
                    "Cave entrance only — cold air sinks, sleep higher",
                    "Desert: shade during day, move at night",
                    "Any roof + walls beats open air always",
                ]
            },
            {
                "heading": "Fire — Three Methods",
                "content": [
                    "Bow drill: spindle + fireboard + tinder bundle",
                    "Flint + steel: strike into char cloth / tinder",
                    "Lens: sunlight → tinder (clear day only)",
                    "Tinder: dry grass, bark shreds, dead leaves",
                    "Protect from wind — cup hands, build windbreak first",
                ]
            },
        ]
    },

    "page2": {
        "title": "MEDICAL EMERGENCIES",
        "subtitle": "Life-threatening situations — act immediately",
        "sections": [
            {
                "heading": "Stop Bleeding",
                "content": [
                    "Direct pressure: push HARD, hold 15 min, do not peek",
                    "Pack wound with cloth if gaping",
                    "Tourniquet (limbs only): 5cm above wound, note time",
                    "Tighten until bleeding stops — will hurt — do it anyway",
                    "Do NOT remove tourniquet in field",
                    "Yarrow herb packed in wound = natural styptic",
                ]
            },
            {
                "heading": "Shock",
                "content": [
                    "Signs: pale/cold skin, rapid weak pulse, confusion",
                    "Lay flat, elevate legs 30cm (no spinal injury)",
                    "Keep warm — cold worsens shock dramatically",
                    "ORS if conscious: 1L water + 6tsp sugar + ½tsp salt",
                    "Treat the cause: stop bleeding, cool burns",
                ]
            },
            {
                "heading": "Wound Care",
                "content": [
                    "Wash hands first — always",
                    "Flush wound with 1L clean water under pressure",
                    "Do NOT close: bites, punctures, infected wounds",
                    "Close clean cuts: butterfly strips from tape",
                    "Honey = excellent wound dressing (antimicrobial)",
                    "Watch daily: spreading redness = infection = urgent",
                    "Red lines FROM wound = blood poisoning = emergency",
                ]
            },
            {
                "heading": "Improvised Medicines",
                "content": [
                    "Willow bark tea: pain + fever (= natural aspirin)",
                    "Garlic raw: broad spectrum antibiotic — 3x daily",
                    "Honey: wound dressing + sore throat + energy",
                    "Turmeric paste: anti-inflammatory on wounds",
                    "Plantain leaf (lawn weed): chew, apply to stings",
                    "ORS: 1L water + 6tsp sugar + ½tsp salt (diarrhoea/dehydration)",
                ]
            },
        ]
    },

    "page3": {
        "title": "NAVIGATION",
        "subtitle": "Find direction and location without GPS",
        "sections": [
            {
                "heading": "Find North — Daytime",
                "content": [
                    "SHADOW STICK (most reliable):",
                    "  Push stick in ground. Mark shadow tip (A).",
                    "  Wait 20 min. Mark new tip (B).",
                    "  A→B points WEST→EAST. Stand: left=A, right=B → facing North",
                    "",
                    "SUN METHOD: rises ≈East, sets ≈West, noon=South (NH)",
                    "WATCH: hour hand at sun, bisect to 12 = South (NH)",
                ]
            },
            {
                "heading": "Find North — Nighttime",
                "content": [
                    "POLARIS (Northern Hemisphere only):",
                    "  Find Big Dipper (7 stars, ladle shape)",
                    "  Two outer cup stars — extend line upward × 5",
                    "  That star = Polaris = True North",
                    "  Its height above horizon = your latitude",
                    "",
                    "SOUTHERN CROSS (Southern Hemisphere):",
                    "  Extend long axis × 4.5 = due South point",
                ]
            },
            {
                "heading": "Natural Signs",
                "content": [
                    "Moss densest on NORTH side of trees (NH)",
                    "Tree rings wider on SOUTH side (more sun, NH)",
                    "Snow melts first on south-facing slopes (NH)",
                    "Rivers: follow downstream → settlements → coast",
                    "Birds fly low and straight toward water at dusk",
                    "Ants build mounds on south side of trees (NH)",
                ]
            },
            {
                "heading": "Distress Signals",
                "content": [
                    "Universal: 3 of anything (fires, shots, whistles)",
                    "SOS morse: ···---··· (3 short, 3 long, 3 short)",
                    "Ground signal X = need medical help (10m+ size)",
                    "Mirror flash: visible 50+ km on clear day",
                    "Smoke: green/wet fuel = dark smoke (daytime)",
                    "Fire: bright + dry fuel (nighttime)",
                ]
            },
        ]
    },

    "page4": {
        "title": "FOOD AND PLANTS",
        "subtitle": "What to eat — and what will kill you",
        "sections": [
            {
                "heading": "Universal Edibility Test",
                "content": [
                    "When you cannot identify a plant:",
                    "1. Smell: strong unpleasant = likely toxic",
                    "2. Skin test: rub on wrist, wait 15 min",
                    "3. Lip test: touch to lip, wait 3 min",
                    "4. Mouth test: chew small piece, wait 15 min (do not swallow)",
                    "5. Swallow small amount, wait 8 hours",
                    "ANY burning/nausea: spit out, do not eat",
                    "One plant at a time — 24hr between new tests",
                ]
            },
            {
                "heading": "Safe Everywhere (Temperate)",
                "content": [
                    "Dandelion: entire plant edible raw or cooked",
                    "Nettles: cook to remove sting, very nutritious",
                    "Cattail: pollen, shoots, roots all edible",
                    "Acorns: leach in water 24hr, then eat/grind",
                    "Blackberries / raspberries: safe if aggregate berry",
                    "Pine needles: tea only (vitamin C) — not bulk eating",
                ]
            },
            {
                "heading": "DEADLY LOOKALIKES",
                "content": [
                    "Wild carrot vs HEMLOCK (deadly):",
                    "  Hemlock: purple blotches on stem, musty smell",
                    "Wild garlic vs LILY OF THE VALLEY (deadly):",
                    "  Crush leaf — no garlic smell = NOT safe",
                    "Elderberry vs POKEWEED (toxic):",
                    "  Pokeweed: single trunk, magenta stem",
                    "Chanterelle vs JACK-O-LANTERN (toxic):",
                    "  Jack-o-lantern: glows faintly at night",
                    "RULE: If uncertain — DO NOT EAT",
                ]
            },
            {
                "heading": "Hunting and Trapping",
                "content": [
                    "Figure-4 deadfall: sticks + heavy rock, bait centre",
                    "Snare: wire loop 10cm diameter, 10cm off ground",
                    "Set snares on trails, near water, at burrow entrances",
                    "Check every 4-6 hours",
                    "All birds are edible. All insects are edible (cook).",
                    "All mammals edible. Cook all meat thoroughly.",
                    "Do NOT eat: liver of large Arctic animals (vit A toxic)",
                ]
            },
        ]
    },

    "page5": {
        "title": "FIRE, TOOLS AND MATERIALS",
        "subtitle": "Making things from nothing",
        "sections": [
            {
                "heading": "Making Tools — Stone Age Start",
                "content": [
                    "Flint/chert: dark glassy rock that sparks with steel",
                    "  Found: chalk regions, riverbeds, limestone areas",
                    "  Knap by striking edge with harder stone at angle",
                    "  Creates cutting edge sharper than surgical steel",
                    "Bone: boil first, dry, then carve with stone tool",
                    "Wood hardening: char tip in fire (not flame), scrape",
                    "Cordage: twist plant fibres in opposite directions",
                    "  Nettles, bark strips, roots, animal sinew all work",
                ]
            },
            {
                "heading": "Soap — Essential for Survival",
                "content": [
                    "Soap prevents infection. Make it as soon as possible.",
                    "1. Leach wood ash with rainwater → brown lye solution",
                    "2. Test: egg floats coin-sized area above surface",
                    "3. Mix 3 parts fat to 1 part lye (by volume)",
                    "4. Stir constantly until thick (trace) — 30-120 min",
                    "5. Pour into mould. Wait 48hrs. Cure 4 WEEKS minimum",
                    "Saponin shortcut: boil soapwort roots in water",
                ]
            },
            {
                "heading": "Blacksmithing Basics",
                "content": [
                    "Any metal can be worked with fire + hammer + anvil",
                    "Anvil: any large flat hard metal surface",
                    "Forge: clay-lined hole with bellows (or blow tube)",
                    "Iron glows: red=warm, orange=workable, yellow=hot",
                    "Quench in water to harden, reheat slowly to temper",
                    "Salvage: car springs (high carbon steel) = best knives",
                    "Files are already hardened steel — break for chisels",
                ]
            },
            {
                "heading": "Electricity Basics",
                "content": [
                    "Generator: copper coil rotating in magnetic field",
                    "  = any motor run backwards makes electricity",
                    "Car alternator + bicycle wheel + belt = power",
                    "Solar: any salvaged panel + charge controller + battery",
                    "Battery: lead plates + sulfuric acid (car battery acid)",
                    "Test voltage: LED lights at 2V+, multimeter if available",
                    "Radio: crystal radio needs no power at all to receive",
                ]
            },
        ]
    },

    "page6": {
        "title": "REBUILDING AND COMMUNITY",
        "subtitle": "From survival to civilisation",
        "sections": [
            {
                "heading": "Priority Order for Rebuilding",
                "content": [
                    "WEEK 1: Water system, shelter, fire, food supply",
                    "MONTH 1: Soap, medicine, crops planted, tools made",
                    "MONTH 3: Metal working, pottery, food preservation",
                    "MONTH 6: Permanent structures, trade, governance",
                    "YEAR 1: Education system, written records, power",
                    "Each stage enables the next — do not skip ahead",
                ]
            },
            {
                "heading": "Soap First — Then Everything",
                "content": [
                    "Soap saves more lives than any other technology",
                    "Cholera, typhoid, dysentery: all preventable by handwashing",
                    "Make soap within first month — it is the unlock",
                    "Teach everyone: wash hands before food, after toilet",
                    "Boil water + soap = 90% of preventable deaths prevented",
                ]
            },
            {
                "heading": "Group Organisation",
                "content": [
                    "Immediately assign: water, food, medical, security, build",
                    "Skills inventory: who knows what? List everything",
                    "Decisions: consensus for daily, vote for major",
                    "Conflict: address early, small conflicts become fatal",
                    "Record everything in writing from day one",
                ]
            },
            {
                "heading": "Psychological Survival",
                "content": [
                    "Isolation kills as surely as injury — find people",
                    "Routine creates stability when everything is unstable",
                    "Mark days — keeping count is an act of hope",
                    "Make something with your hands every day",
                    "Grief is normal — process it, do not suppress it",
                    "Small wins matter — celebrate them",
                    "You are more capable than you believe. This is survivable.",
                ]
            },
        ]
    },

}


# ── PDF Generation ─────────────────────────────────────────────────────────

def generate_pdf(output_path: str = OUTPUT_PATH):
    """Generate the printable reference PDF."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.colors import (
            HexColor, black, white, grey
        )
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, PageBreak
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        _generate_with_reportlab(output_path)

    except ImportError:
        print("reportlab not installed. Installing...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip",
                       "install", "reportlab", "--break-system-packages"],
                      capture_output=True)
        try:
            _generate_with_reportlab(output_path)
        except Exception as e:
            print(f"Could not generate PDF: {e}")
            _generate_text_fallback(output_path.replace(".pdf", ".txt"))


def _generate_with_reportlab(output_path: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer,
        Table, TableStyle, PageBreak, KeepTogether
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    # Colours
    AMBER    = HexColor("#F0A500")
    DARK     = HexColor("#1A1A1A")
    DARKGREY = HexColor("#2A2A2A")
    MIDGREY  = HexColor("#666666")
    LIGHT    = HexColor("#E8E8E8")
    WARNING  = HexColor("#8B0000")

    # Styles
    styles = {
        "page_title": ParagraphStyle(
            "PageTitle",
            fontSize=20, fontName="Helvetica-Bold",
            textColor=white, spaceAfter=2*mm,
        ),
        "page_subtitle": ParagraphStyle(
            "PageSubtitle",
            fontSize=9, fontName="Helvetica",
            textColor=LIGHT, spaceAfter=4*mm,
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            fontSize=10, fontName="Helvetica-Bold",
            textColor=AMBER, spaceBefore=3*mm, spaceAfter=1*mm,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            fontSize=8, fontName="Helvetica",
            textColor=LIGHT, leftIndent=3*mm,
            spaceBefore=0.5*mm, spaceAfter=0.5*mm,
            leading=10,
        ),
        "warning": ParagraphStyle(
            "Warning",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=HexColor("#FF6666"),
            leftIndent=3*mm, spaceBefore=0.5*mm,
        ),
    }

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=10*mm, bottomMargin=10*mm,
    )

    story = []

    for page_key, page_data in REFERENCE_CONTENT.items():
        # Page header
        header_data = [[
            Paragraph(f"⚡ PROMETHEUS — {page_data['title']}",
                     styles["page_title"]),
            Paragraph(page_data["subtitle"], styles["page_subtitle"]),
        ]]
        header_table = Table(header_data, colWidths=[190*mm])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), DARK),
            ("TOPPADDING",    (0,0), (-1,-1), 4*mm),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2*mm),
            ("LEFTPADDING",   (0,0), (-1,-1), 4*mm),
            ("RIGHTPADDING",  (0,0), (-1,-1), 4*mm),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [DARKGREY]),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 3*mm))

        # Sections in two columns
        left_sections = page_data["sections"][:2]
        right_sections = page_data["sections"][2:]

        def build_section(section):
            items = []
            items.append(Paragraph(section["heading"], styles["section_heading"]))
            for line in section["content"]:
                if not line:
                    items.append(Spacer(1, 1*mm))
                    continue
                style = styles["warning"] if "DEADLY" in line or "deadly" in line or "RULE:" in line else styles["bullet"]
                prefix = "• " if not line.startswith(" ") and not line.startswith("  ") else ""
                items.append(Paragraph(prefix + line, style))
            return items

        left_content = []
        for s in left_sections:
            left_content.extend(build_section(s))

        right_content = []
        for s in right_sections:
            right_content.extend(build_section(s))

        # Two column layout
        from reportlab.platypus import Frame, NextPageTemplate
        col_data = [[left_content, right_content]]

        # Pad to equal length
        max_len = max(len(left_content), len(right_content))
        left_content  += [Spacer(1, 1*mm)] * (max_len - len(left_content))
        right_content += [Spacer(1, 1*mm)] * (max_len - len(right_content))

        col_table = Table(
            [[left_content, right_content]],
            colWidths=[93*mm, 93*mm],
            hAlign="LEFT"
        )
        col_table.setStyle(TableStyle([
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING",   (0,0), (-1,-1), 2*mm),
            ("RIGHTPADDING",  (0,0), (-1,-1), 2*mm),
            ("TOPPADDING",    (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("LINEAFTER",     (0,0), (0,-1), 0.5, MIDGREY),
            ("BACKGROUND",    (0,0), (-1,-1), DARK),
        ]))
        story.append(col_table)

        # Footer
        footer_style = ParagraphStyle(
            "Footer", fontSize=7, textColor=MIDGREY,
            alignment=1  # center
        )
        generated = datetime.now().strftime("%Y-%m-%d")
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(
            f"Prometheus Emergency Reference | Generated {generated} | "
            f"Print double-sided, laminate for waterproofing",
            footer_style
        ))

        if page_key != list(REFERENCE_CONTENT.keys())[-1]:
            story.append(PageBreak())

    # Build PDF
    doc.build(story)
    size = Path(output_path).stat().st_size / 1024
    print(f"✓ Generated: {output_path} ({size:.0f} KB)")
    print(f"  Print double-sided on 3 sheets of paper")
    print(f"  Laminate for waterproofing")


def _generate_text_fallback(output_path: str):
    """Plain text fallback if reportlab unavailable."""
    lines = ["PROMETHEUS EMERGENCY REFERENCE\n", "=" * 60 + "\n\n"]

    for page_data in REFERENCE_CONTENT.values():
        lines.append(f"\n{page_data['title'].upper()}\n")
        lines.append(f"{page_data['subtitle']}\n")
        lines.append("-" * 40 + "\n")

        for section in page_data["sections"]:
            lines.append(f"\n{section['heading']}\n")
            for line in section["content"]:
                if line:
                    lines.append(f"  • {line}\n")

        lines.append("\n" + "=" * 60 + "\n")

    Path(output_path).write_text("".join(lines))
    print(f"✓ Generated text fallback: {output_path}")


if __name__ == "__main__":
    print("Generating Prometheus Emergency Reference PDF...")
    generate_pdf()
    print(f"\nSave to: {OUTPUT_PATH}")
    print("Print double-sided on 3 sheets. Laminate for waterproofing.")
