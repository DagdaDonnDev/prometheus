#!/usr/bin/env python3
"""
PROMETHEUS BOOTSTRAP
====================
Run this ONCE before launching Prometheus.

Downloads all free public domain source materials,
places them in the correct knowledge_base/ directories,
then deletes itself.

Usage:
    python bootstrap.py

Requires: internet connection (only time Prometheus ever needs one)
Time:     10-30 minutes depending on connection speed
Size:     approximately 500MB-1GB of source PDFs
"""

import os
import sys
import time
import shutil
import hashlib
import urllib.request
import urllib.error
from pathlib import Path


# ── Configuration ──────────────────────────────────────────────────────────

KNOWLEDGE_BASE = Path("knowledge_base")
CHUNK_SIZE = 8192  # bytes per download chunk

# Color codes for terminal output
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── Source Manifest ────────────────────────────────────────────────────────
#
# Every source here is either:
#   - Public Domain (US Government publications, pre-1928 works)
#   - Explicitly free to reproduce (Hesperian Foundation)
#   - Freely hosted by the originating institution
#
# Format:
#   name:     Human readable title
#   urls:     List of URLs to try in order (fallbacks if first fails)
#   dest:     Subdirectory under knowledge_base/
#   filename: What to save it as locally
#   priority: 1=critical, 2=important, 3=supplementary
#   size_mb:  Approximate size (for progress display)

SOURCES = [

    # ══════════════════════════════════════════════════════════════════════
    # TIER 1 — CRITICAL (download these first)
    # ══════════════════════════════════════════════════════════════════════

    # Medical
    {
        "name": "Where There Is No Doctor",
        "urls": [
            "https://hesperian.org/wp-content/uploads/pdf/en_wtnd_2019/en_wtnd_2019.pdf",
            "https://store.hesperian.org/mm5/graphics/00000001/wtnd_english_2019.pdf",
        ],
        "dest": "where_no_doctor",
        "filename": "Where_There_Is_No_Doctor.pdf",
        "priority": 1,
        "size_mb": 12,
        "notes": "The most important medical reference for collapse. Written for untrained village health workers."
    },
    {
        "name": "Where There Is No Dentist",
        "urls": [
            "https://hesperian.org/wp-content/uploads/pdf/en_wtd_2020/en_wtd_2020.pdf",
            "https://store.hesperian.org/mm5/graphics/00000001/wtd_english.pdf",
        ],
        "dest": "where_no_dentist",
        "filename": "Where_There_Is_No_Dentist.pdf",
        "priority": 1,
        "size_mb": 8,
        "notes": "Dental infections kill. Tooth extraction, abscess, improvised tools."
    },
    {
        "name": "US Army First Aid FM 4-25.11",
        "urls": [
            "https://armypubs.army.mil/epubs/DR_pubs/DR_a/pdf/web/fm4_25x11.pdf",
            "https://www.globalsecurity.org/military/library/policy/army/fm/4-25-11/fm4_25x11.pdf",
            "https://www.bits.de/NRANEU/others/amd-us-archive/FM4-25.11(2002).pdf",
        ],
        "dest": "medical",
        "filename": "FM_4-25-11_First_Aid.pdf",
        "priority": 1,
        "size_mb": 6,
        "notes": "Military first aid. Trauma, shock, wounds, fractures, burns. Practical procedures."
    },
    {
        "name": "US Army Field Hygiene and Sanitation FM 21-10",
        "urls": [
            "https://www.globalsecurity.org/military/library/policy/army/fm/21-10/fm21-10.pdf",
            "https://www.bits.de/NRANEU/others/amd-us-archive/fm21-10.pdf",
        ],
        "dest": "medical",
        "filename": "FM_21-10_Field_Hygiene_Sanitation.pdf",
        "priority": 1,
        "size_mb": 4,
        "notes": "Disease prevention. More lives saved by sanitation than medicine."
    },

    # Survival
    {
        "name": "US Army Survival Manual FM 3-05.70",
        "urls": [
            "https://www.bits.de/NRANEU/others/amd-us-archive/fm3-05-70%282002%29.pdf",
            "https://www.globalsecurity.org/military/library/policy/army/fm/3-05-70/fm3-05-70.pdf",
        ],
        "dest": "army_fm_3_05_70",
        "filename": "FM_3-05-70_Survival.pdf",
        "priority": 1,
        "size_mb": 15,
        "notes": "Gold standard survival manual. All environments, field medicine, signaling, water, food."
    },
    {
        "name": "US Army Survival Manual FM 21-76 (1970 edition)",
        "urls": [
            "https://www.survivorlibrary.com/library/fm_21-76_survival_1970.pdf",
        ],
        "dest": "army_fm_3_05_70",
        "filename": "FM_21-76_Survival_1970.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Earlier edition — different content, complementary coverage."
    },

    # Nuclear
    {
        "name": "Nuclear War Survival Skills — Cresson Kearny",
        "urls": [
            "https://www.oism.org/nwss/nwss.pdf",
            "https://archive.org/download/NuclearWarSurvivalSkills/NuclearWarSurvivalSkills.pdf",
        ],
        "dest": "nuclear_survival",
        "filename": "Nuclear_War_Survival_Skills.pdf",
        "priority": 1,
        "size_mb": 10,
        "notes": "Oak Ridge National Laboratory tested. Real numbers, real shelter specs, KFM meter construction."
    },

    # Water
    {
        "name": "US Army Water Supply and Purification FM 10-52",
        "urls": [
            "https://www.globalsecurity.org/military/library/policy/army/fm/10-52/fm10-52.pdf",
        ],
        "dest": "water_purification",
        "filename": "FM_10-52_Water_Supply_Purification.pdf",
        "priority": 1,
        "size_mb": 5,
        "notes": "Military water procurement and purification. Extremely detailed field procedures."
    },

    # ══════════════════════════════════════════════════════════════════════
    # TIER 2 — IMPORTANT
    # ══════════════════════════════════════════════════════════════════════

    # Blacksmithing
    {
        "name": "Practical Blacksmithing Volume 1 (Richardson, 1889)",
        "urls": [
            "https://www.survivorlibrary.com/library/practical_blacksmithing_vol1_1889.pdf",
            "https://archive.org/download/practicalblacksmithingvol1/practical_blacksmithing_vol1.pdf",
        ],
        "dest": "blacksmithing",
        "filename": "Practical_Blacksmithing_Vol1.pdf",
        "priority": 1,
        "size_mb": 15,
        "notes": "Complete blacksmithing from scratch. Forge construction, tool making, techniques."
    },
    {
        "name": "Practical Blacksmithing Volume 2 (Richardson, 1889)",
        "urls": [
            "https://www.survivorlibrary.com/library/practical_blacksmithing_vol2_1889.pdf",
            "https://archive.org/download/practicalblacksmithingvol2/practical_blacksmithing_vol2.pdf",
        ],
        "dest": "blacksmithing",
        "filename": "Practical_Blacksmithing_Vol2.pdf",
        "priority": 1,
        "size_mb": 15,
        "notes": "Advanced blacksmithing — welding, tempering, complex projects."
    },
    {
        "name": "Practical Blacksmithing Volume 3 (Richardson, 1889)",
        "urls": [
            "https://www.survivorlibrary.com/library/practical_blacksmithing_vol3_1889.pdf",
        ],
        "dest": "blacksmithing",
        "filename": "Practical_Blacksmithing_Vol3.pdf",
        "priority": 2,
        "size_mb": 15,
        "notes": "Complete the set — specialized tools and advanced projects."
    },

    # Farming
    {
        "name": "Farm Mechanics (Worthen, 1922)",
        "urls": [
            "https://www.survivorlibrary.com/library/farm_mechanics_1922.pdf",
            "https://archive.org/download/farmmechanics00wort/farmmechanics00wort.pdf",
        ],
        "dest": "farming",
        "filename": "Farm_Mechanics_1922.pdf",
        "priority": 1,
        "size_mb": 10,
        "notes": "Pre-electricity farm machinery, tools, construction, repair."
    },
    {
        "name": "Ten Acres Enough (Morris, 1864)",
        "urls": [
            "https://www.gutenberg.org/files/35241/35241-pdf.pdf",
            "https://archive.org/download/tenacresenough00morrgoog/tenacresenough00morrgoog.pdf",
        ],
        "dest": "farming",
        "filename": "Ten_Acres_Enough_1864.pdf",
        "priority": 2,
        "size_mb": 5,
        "notes": "Small farm self-sufficiency — practical, honest, detailed."
    },
    {
        "name": "Home Vegetable Gardening (Watts, 1911)",
        "urls": [
            "https://www.survivorlibrary.com/library/home_vegetable_gardening_1911.pdf",
            "https://archive.org/download/homevegetablegard00watt/homevegetablegard00watt.pdf",
        ],
        "dest": "farming",
        "filename": "Home_Vegetable_Gardening_1911.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Complete vegetable cultivation without modern inputs."
    },
    {
        "name": "Feeds and Feeding (Henry, 1908)",
        "urls": [
            "https://www.survivorlibrary.com/library/feeds_and_feeding_1908.pdf",
            "https://archive.org/download/feedsfeeding00henruoft/feedsfeeding00henruoft.pdf",
        ],
        "dest": "farming",
        "filename": "Feeds_and_Feeding_1908.pdf",
        "priority": 2,
        "size_mb": 12,
        "notes": "Animal husbandry and nutrition — horses, cattle, sheep, pigs, poultry."
    },
    {
        "name": "Beekeeping for Beginners (1917)",
        "urls": [
            "https://www.survivorlibrary.com/library/beekeeping_for_beginners_1917.pdf",
            "https://archive.org/download/beekeepingforbe00philgoog/beekeepingforbe00philgoog.pdf",
        ],
        "dest": "farming",
        "filename": "Beekeeping_1917.pdf",
        "priority": 2,
        "size_mb": 5,
        "notes": "Bees provide honey (medicine + food + trade), wax, and crop pollination."
    },

    # Food Preservation
    {
        "name": "Canning and Preserving (Cabot, 1914)",
        "urls": [
            "https://www.survivorlibrary.com/library/canning_and_preserving_1914.pdf",
            "https://archive.org/download/canningpreservin00cabolrich/canningpreservin00cabolrich.pdf",
        ],
        "dest": "food_preservation",
        "filename": "Canning_and_Preserving_1914.pdf",
        "priority": 1,
        "size_mb": 6,
        "notes": "Food preservation before refrigeration. All methods including pressure canning."
    },
    {
        "name": "Home Production of Vinegar and Fermented Products (1900)",
        "urls": [
            "https://www.survivorlibrary.com/library/home_production_of_vinegar_1900.pdf",
        ],
        "dest": "food_preservation",
        "filename": "Fermentation_and_Vinegar_1900.pdf",
        "priority": 1,
        "size_mb": 4,
        "notes": "Fermentation, vinegar, pickling, lacto-fermentation, alcohol production."
    },
    {
        "name": "Drying and Curing Meats (USDA, 1917)",
        "urls": [
            "https://archive.org/download/dryingcuringmeat00unitrich/dryingcuringmeat00unitrich.pdf",
        ],
        "dest": "food_preservation",
        "filename": "Drying_Curing_Meats_1917.pdf",
        "priority": 1,
        "size_mb": 3,
        "notes": "Smoking, salt curing, drying — preserving meat without refrigeration."
    },

    # Chemistry
    {
        "name": "Henley's Twentieth Century Formulas (1916)",
        "urls": [
            "https://www.survivorlibrary.com/library/henleys_twentieth_century_formulas_1916.pdf",
            "https://archive.org/download/henleystwentieth00henl/henleystwentieth00henl.pdf",
        ],
        "dest": "chemistry",
        "filename": "Henleys_Formulas_1916.pdf",
        "priority": 1,
        "size_mb": 20,
        "notes": "10,000+ practical formulas. Inks, glues, medicines, explosives, dyes, preservatives."
    },
    {
        "name": "The Chemistry of Common Life (Johnston, 1855)",
        "urls": [
            "https://archive.org/download/chemistryofcommo01john/chemistryofcommo01john.pdf",
        ],
        "dest": "chemistry",
        "filename": "Chemistry_of_Common_Life_1855.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Practical chemistry from first principles. Food, water, air, fermentation, medicine."
    },
    {
        "name": "Explosives and Propellants (Rinkenbach, 1920)",
        "urls": [
            "https://archive.org/download/explosivesandpro00rink/explosivesandpro00rink.pdf",
        ],
        "dest": "chemistry",
        "filename": "Explosives_Propellants_1920.pdf",
        "priority": 2,
        "size_mb": 6,
        "notes": "Historical reference — mining, construction, clearing. Public domain."
    },

    # Soap
    {
        "name": "Soap Making Past and Present (1908)",
        "urls": [
            "https://www.survivorlibrary.com/library/soap_making_past_and_present_1908.pdf",
            "https://archive.org/download/soapmakingpastan00lewk/soapmakingpastan00lewk.pdf",
        ],
        "dest": "soap_making",
        "filename": "Soap_Making_Past_and_Present_1908.pdf",
        "priority": 1,
        "size_mb": 5,
        "notes": "Complete soap making. Lye production from ash, all fats, all methods."
    },

    # Construction
    {
        "name": "Practical Carpentry (Wheeler, 1907)",
        "urls": [
            "https://www.survivorlibrary.com/library/practical_carpentry_1907.pdf",
            "https://archive.org/download/practicalcarpen00whee/practicalcarpen00whee.pdf",
        ],
        "dest": "build",
        "filename": "Practical_Carpentry_1907.pdf",
        "priority": 2,
        "size_mb": 10,
        "notes": "Hand tool woodworking and construction. Pre-power tools."
    },
    {
        "name": "Masonry and Concrete Construction (1917)",
        "urls": [
            "https://www.survivorlibrary.com/library/masonry_and_concrete_construction_1917.pdf",
            "https://archive.org/download/masonryconcretec00mast/masonryconcretec00mast.pdf",
        ],
        "dest": "build",
        "filename": "Masonry_Concrete_Construction_1917.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Stone, brick and concrete — permanent durable construction."
    },
    {
        "name": "Plumbing and Sanitation (1908)",
        "urls": [
            "https://www.survivorlibrary.com/library/plumbing_and_sanitation_1908.pdf",
        ],
        "dest": "build",
        "filename": "Plumbing_Sanitation_1908.pdf",
        "priority": 1,
        "size_mb": 6,
        "notes": "Sanitation without modern infrastructure. Critical for community disease prevention."
    },
    {
        "name": "Straw Bale Construction (1902 Nebraska)",
        "urls": [
            "https://archive.org/download/strawbalehouses00sear/strawbalehouses00sear.pdf",
        ],
        "dest": "build",
        "filename": "Straw_Bale_Construction.pdf",
        "priority": 3,
        "size_mb": 3,
        "notes": "Extremely fast, cheap, insulating shelter construction method."
    },

    # Electronics and Power
    {
        "name": "Electricity for the Farm (1915)",
        "urls": [
            "https://www.survivorlibrary.com/library/electricity_for_the_farm_1915.pdf",
            "https://archive.org/download/electricityforf00unkngoog/electricityforf00unkngoog.pdf",
        ],
        "dest": "electronics",
        "filename": "Electricity_for_the_Farm_1915.pdf",
        "priority": 1,
        "size_mb": 6,
        "notes": "Small scale electrical generation from water and wind. Pre-grid methods."
    },
    {
        "name": "Steam Engines and Boilers (1905)",
        "urls": [
            "https://www.survivorlibrary.com/library/steam_engines_and_boilers_1905.pdf",
            "https://archive.org/download/steamenginesboil00unkngoog/steamenginesboil00unkngoog.pdf",
        ],
        "dest": "electronics",
        "filename": "Steam_Engines_Boilers_1905.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Mechanical power before electrical. Key transitional rebuild technology."
    },
    {
        "name": "Wireless Telegraphy and Telephony (1916)",
        "urls": [
            "https://archive.org/download/wirelesstelegrap00miss/wirelesstelegrap00miss.pdf",
        ],
        "dest": "electronics",
        "filename": "Wireless_Telegraphy_1916.pdf",
        "priority": 2,
        "size_mb": 5,
        "notes": "Building radio from first principles. Pre-transistor but foundational."
    },
    {
        "name": "Storage Batteries (1910)",
        "urls": [
            "https://archive.org/download/storagebatteries00unkngoog/storagebatteries00unkngoog.pdf",
        ],
        "dest": "electronics",
        "filename": "Storage_Batteries_1910.pdf",
        "priority": 2,
        "size_mb": 6,
        "notes": "Lead acid battery construction and maintenance from scratch."
    },

    # Navigation
    {
        "name": "Navigation and Nautical Astronomy (1918)",
        "urls": [
            "https://archive.org/download/navigationnautic00burguoft/navigationnautic00burguoft.pdf",
        ],
        "dest": "navigation",
        "filename": "Navigation_Nautical_Astronomy_1918.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Star navigation, celestial fixes, latitude and longitude without GPS."
    },
    {
        "name": "Field Engineering (US Army, 1905)",
        "urls": [
            "https://archive.org/download/fieldengineering00unkngoog/fieldengineering00unkngoog.pdf",
        ],
        "dest": "navigation",
        "filename": "Field_Engineering_US_Army_1905.pdf",
        "priority": 2,
        "size_mb": 10,
        "notes": "Military field navigation, map reading, terrain analysis, surveying."
    },

    # Plants
    {
        "name": "American Medicinal Plants (Millspaugh, 1892)",
        "urls": [
            "https://archive.org/download/americanmedicina00mill/americanmedicina00mill.pdf",
        ],
        "dest": "plants_temperate",
        "filename": "American_Medicinal_Plants_1892.pdf",
        "priority": 1,
        "size_mb": 20,
        "notes": "Comprehensive medicinal plant guide with illustrations. North American focus."
    },
    {
        "name": "British Herbal Medicine (1877)",
        "urls": [
            "https://archive.org/download/britishherbalmedi00lindrich/britishherbalmedi00lindrich.pdf",
        ],
        "dest": "plants_temperate",
        "filename": "British_Herbal_Medicine_1877.pdf",
        "priority": 2,
        "size_mb": 12,
        "notes": "European medicinal plants — identification, uses, preparation."
    },
    {
        "name": "Edible Wild Plants (Medsger, 1939)",
        "urls": [
            "https://archive.org/download/ediblewildplants00meds/ediblewildplants00meds.pdf",
        ],
        "dest": "plants_temperate",
        "filename": "Edible_Wild_Plants_1939.pdf",
        "priority": 1,
        "size_mb": 8,
        "notes": "North American edible plants with identification. Extremely practical."
    },

    # ══════════════════════════════════════════════════════════════════════
    # TIER 3 — SUPPLEMENTARY
    # ══════════════════════════════════════════════════════════════════════

    {
        "name": "Woodcraft and Indian Lore (Seton, 1912)",
        "urls": [
            "https://www.gutenberg.org/files/20772/20772-pdf.pdf",
            "https://archive.org/download/woodcraftindianl00setorich/woodcraftindianl00setorich.pdf",
        ],
        "dest": "survival",
        "filename": "Woodcraft_and_Indian_Lore_1912.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Bushcraft, shelter, fire, tracking, nature reading. Written from indigenous practice."
    },
    {
        "name": "Handbook of Travel (Galton, 1872)",
        "urls": [
            "https://archive.org/download/artoftravelor00galtuoft/artoftravelor00galtuoft.pdf",
        ],
        "dest": "survival",
        "filename": "Art_of_Travel_Galton_1872.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Victorian exploration survival — crossing unknown terrain, making camp, finding water."
    },
    {
        "name": "Boy Scout Handbook (1911 original)",
        "urls": [
            "https://archive.org/download/theboyScouthandb00boysrich/theboyScouthandb00boysrich.pdf",
        ],
        "dest": "survival",
        "filename": "Boy_Scout_Handbook_1911.pdf",
        "priority": 2,
        "size_mb": 8,
        "notes": "Original Scouting handbook. Comprehensive practical skills, first aid, camping."
    },
    {
        "name": "Tanning Leather and Furs (1919)",
        "urls": [
            "https://archive.org/download/tannerleatherandfurs/tannerleatherandfurs.pdf",
            "https://www.survivorlibrary.com/library/tanning_1919.pdf",
        ],
        "dest": "survivor_library",
        "filename": "Tanning_Leather_Furs_1919.pdf",
        "priority": 2,
        "size_mb": 4,
        "notes": "Brain tanning, bark tanning, fur preparation. Essential pre-synthetic clothing."
    },
    {
        "name": "Papermaking by Hand (1916)",
        "urls": [
            "https://archive.org/download/papermakinghist00huntuoft/papermakinghist00huntuoft.pdf",
        ],
        "dest": "survivor_library",
        "filename": "Papermaking_1916.pdf",
        "priority": 3,
        "size_mb": 5,
        "notes": "Making paper from plant fiber. Critical for record keeping and knowledge preservation."
    },
    {
        "name": "Printing for Schools and Clubs (1917)",
        "urls": [
            "https://archive.org/download/printingforschoo00osborich/printingforschoo00osborich.pdf",
        ],
        "dest": "survivor_library",
        "filename": "Printing_1917.pdf",
        "priority": 3,
        "size_mb": 4,
        "notes": "Movable type printing. Knowledge multiplication — one of civilization's key unlocks."
    },
    {
        "name": "Weather Forecasting (US Weather Bureau, 1916)",
        "urls": [
            "https://archive.org/download/weatherforecasti00unit/weatherforecasti00unit.pdf",
        ],
        "dest": "weather_patterns",
        "filename": "Weather_Forecasting_1916.pdf",
        "priority": 2,
        "size_mb": 5,
        "notes": "Reading weather without instruments. Cloud types, pressure signs, natural indicators."
    },
    {
        "name": "Soil Survey Methods (USDA, 1906)",
        "urls": [
            "https://archive.org/download/soilsurveymethod00unkngoog/soilsurveymethod00unkngoog.pdf",
        ],
        "dest": "soil_maps",
        "filename": "Soil_Survey_Methods_1906.pdf",
        "priority": 2,
        "size_mb": 5,
        "notes": "Reading land for agriculture without satellite imagery. Soil identification."
    },
]


# ── Download Engine ────────────────────────────────────────────────────────

class Downloader:

    def __init__(self):
        self.success = []
        self.failed  = []
        self.skipped = []

    def run(self):
        self._print_header()
        self._ensure_dirs()

        # Sort by priority
        sources = sorted(SOURCES, key=lambda s: s["priority"])

        total = len(sources)
        for i, source in enumerate(sources, 1):
            print(f"\n[{i}/{total}] {BOLD}{source['name']}{RESET}")
            print(f"         → knowledge_base/{source['dest']}/{source['filename']}")
            print(f"         ~ {source.get('size_mb', '?')} MB")
            self._download_source(source)

        self._print_summary()
        self._self_destruct()

    def _ensure_dirs(self):
        """Create all destination directories."""
        dirs = set(s["dest"] for s in SOURCES)
        for d in dirs:
            (KNOWLEDGE_BASE / d).mkdir(parents=True, exist_ok=True)

    def _download_source(self, source: dict):
        dest_path = KNOWLEDGE_BASE / source["dest"] / source["filename"]

        # Skip if already downloaded
        if dest_path.exists() and dest_path.stat().st_size > 1024:
            print(f"         {YELLOW}↷ Already exists — skipping{RESET}")
            self.skipped.append(source["name"])
            return

        # Try each URL in order
        for url in source["urls"]:
            print(f"         Trying: {url[:70]}...")
            if self._fetch(url, dest_path, source.get("size_mb", 0)):
                print(f"         {GREEN}✓ Downloaded successfully{RESET}")
                self.success.append(source["name"])
                return
            else:
                # Clean up partial download
                if dest_path.exists():
                    dest_path.unlink()

        print(f"         {RED}✗ All URLs failed — add manually{RESET}")
        print(f"         Notes: {source.get('notes', '')}")
        self.failed.append(source["name"])

    def _fetch(self, url: str, dest: Path, size_mb: int) -> bool:
        """Download a file with progress display."""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; PrometheusBootstrap/1.0; "
                    "Educational/SurvivalReference)"
                )
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(dest, "wb") as f:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self._print_progress(downloaded, total)

            print()  # newline after progress bar

            # Verify file is not empty or an error page
            if dest.stat().st_size < 1024:
                return False

            # Quick PDF validation
            if dest.suffix.lower() == ".pdf":
                with open(dest, "rb") as f:
                    header = f.read(5)
                if header != b"%PDF-":
                    return False

            return True

        except urllib.error.HTTPError as e:
            print(f"\n         HTTP {e.code}")
            return False
        except urllib.error.URLError as e:
            print(f"\n         Connection error: {e.reason}")
            return False
        except Exception as e:
            print(f"\n         Error: {e}")
            return False

    def _print_progress(self, downloaded: int, total: int):
        """Print a simple progress bar."""
        if total > 0:
            pct = min(100, int(downloaded / total * 100))
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            mb = downloaded / 1024 / 1024
            print(f"\r         [{bar}] {pct}% ({mb:.1f} MB)", end="", flush=True)
        else:
            mb = downloaded / 1024 / 1024
            print(f"\r         Downloading... {mb:.1f} MB", end="", flush=True)

    def _print_header(self):
        print(f"""
{BOLD}{'='*60}
⚡ PROMETHEUS BOOTSTRAP
{'='*60}{RESET}

This script will download all free public domain source
materials for the Prometheus knowledge base.

Sources: {len(SOURCES)} documents
All sources are public domain or explicitly free to use.

This is the only time Prometheus needs internet access.
After this, everything runs completely offline forever.

{'='*60}
""")
        input("Press Enter to begin downloading...")

    def _print_summary(self):
        total_size = sum(
            (KNOWLEDGE_BASE / s["dest"] / s["filename"]).stat().st_size
            for s in SOURCES
            if (KNOWLEDGE_BASE / s["dest"] / s["filename"]).exists()
        )

        print(f"""
{BOLD}{'='*60}
DOWNLOAD COMPLETE
{'='*60}{RESET}

{GREEN}✓ Downloaded:  {len(self.success)}{RESET}
{YELLOW}↷ Skipped:     {len(self.skipped)} (already existed){RESET}
{RED}✗ Failed:      {len(self.failed)}{RESET}

Total size: {total_size / 1024 / 1024:.0f} MB

""")

        if self.failed:
            print(f"{RED}Failed sources (add manually):{RESET}")
            for name in self.failed:
                print(f"  • {name}")
            print()

        print(f"""{BOLD}Next steps:{RESET}
  1. Run the ingestion pipeline:
     {BLUE}python ingest.py{RESET}

  2. Launch Prometheus:
     {BLUE}ollama serve &
     python main.py{RESET}

""")

    def _self_destruct(self):
        """Delete this script after successful completion."""
        print(f"{YELLOW}Deleting bootstrap script (no longer needed)...{RESET}")
        try:
            script_path = Path(__file__).resolve()
            # Schedule deletion after process exits
            # On Unix: use a small shell command
            if sys.platform != "win32":
                os.system(f'(sleep 1 && rm -f "{script_path}") &')
            else:
                # Windows: use a batch file trick
                bat = script_path.parent / "_cleanup.bat"
                bat.write_text(
                    f'@echo off\n'
                    f'timeout /t 2 /nobreak >nul\n'
                    f'del /f /q "{script_path}"\n'
                    f'del /f /q "%~f0"\n'
                )
                os.startfile(str(bat))

            print(f"{GREEN}✓ Bootstrap complete. This script will self-delete.{RESET}")
        except Exception:
            # Self-delete failed — just tell user
            print(f"Note: Could not self-delete. You can manually delete: bootstrap.py")


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Prometheus bootstrap — download all knowledge sources"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all sources without downloading"
    )
    parser.add_argument(
        "--priority",
        type=int,
        choices=[1, 2, 3],
        help="Only download sources at this priority level"
    )
    parser.add_argument(
        "--dest",
        type=str,
        help="Only download sources going to this destination folder"
    )
    args = parser.parse_args()

    if args.list:
        print(f"\n{BOLD}Prometheus Source Manifest{RESET}")
        print(f"{'='*60}")
        current_priority = 0
        labels = {1: "CRITICAL", 2: "IMPORTANT", 3: "SUPPLEMENTARY"}
        for s in sorted(SOURCES, key=lambda x: x["priority"]):
            if s["priority"] != current_priority:
                current_priority = s["priority"]
                print(f"\n{BOLD}── Tier {current_priority}: {labels[current_priority]} ──{RESET}")
            size = s.get("size_mb", "?")
            print(f"  [{size:>3} MB] {s['name']}")
            print(f"           → {s['dest']}/{s['filename']}")
            print(f"           {s.get('notes', '')}")
        total_mb = sum(s.get("size_mb", 0) for s in SOURCES)
        print(f"\nTotal estimated size: ~{total_mb} MB")
        sys.exit(0)

    # Filter sources if requested
    sources_to_run = SOURCES
    if args.priority:
        sources_to_run = [s for s in SOURCES if s["priority"] == args.priority]
    if args.dest:
        sources_to_run = [s for s in sources_to_run if s["dest"] == args.dest]

    if sources_to_run != SOURCES:
        SOURCES.clear()
        SOURCES.extend(sources_to_run)

    downloader = Downloader()
    downloader.run()
