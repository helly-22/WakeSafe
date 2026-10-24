"""Build backend/app/data/hospitals.csv from the downloaded CMS + MassGIS sources.

Inputs (already downloaded, do NOT re-download):
  ml/data/raw/hospitals/MassGIS_Massachusetts_Hospitals.csv  -- lat/lon + unit/bed/capability columns
  ml/data/raw/hospitals/Hospital_General_Information_MA.csv   -- CMS name/address (84 MA rows)

Output columns (task PART A):
  facility_id, name, address, lat, lon, specialties, licensed_beds, staffed_beds

Join strategy
-------------
MassGIS is the SPINE (it is the only source with lat/lon and unit flags). CMS is
joined on in only to confirm the facility and lend its cleaner street address;
every output row's coordinates, beds and capabilities come from MassGIS, so an
unmatched CMS row simply means we keep the MassGIS address. Match key is the
normalized facility name plus ZIP; fuzzy on name when ZIP alone is ambiguous.

Specialties
-----------
Derived ONLY from source-provided MassGIS unit/capability columns (ICU, NICU,
MATERNAL, PEDIATRIC, PSYCHIATRIC, BURN_UNIT, REHABILITATION, EMERGENCY_DEPT,
DPH_STROKE_TIER, TRAUMA_LEVEL_ADULT). Nothing is invented. Every specialty token
is traceable to a column; see SPECIALTY_MAP. Flags that are inferred-from-a-tier
(e.g. "trauma" from TRAUMA_LEVEL_ADULT) are noted in the module docstring and the
companion data/hospitals_build_notes.md, not fabricated.

licensed_beds = MassGIS TOTAL_BEDS (the licensed/physical bed count DPH lists).
staffed_beds  = NOT a source field anywhere -> left blank (empty), never guessed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "ml" / "data" / "raw" / "hospitals"
MASSGIS = RAW / "MassGIS_Massachusetts_Hospitals.csv"
CMS = RAW / "Hospital_General_Information_MA.csv"
OUT = REPO / "backend" / "app" / "data" / "hospitals.csv"
NOTES = REPO / "backend" / "app" / "data" / "hospitals_build_notes.md"

# How many facilities to keep. Task requires 12-20; we take a geographically
# spread set of acute hospitals that carry real coordinates and bed counts.
TARGET_MIN, TARGET_MAX = 12, 20

# Each entry: output specialty token -> (MassGIS column, predicate, inferred?)
# predicate(value) -> True means "this facility has this capability".
# "inferred" marks a token we READ OFF a tier/level field rather than a plain
# yes/no unit flag; it is still source-backed, just flagged for honesty.
SPECIALTY_MAP: list[tuple[str, str, object, bool]] = [
    ("emergency", "EMERGENCY_DEPT", lambda v: str(v).strip().lower() == "yes", False),
    ("icu", "ICU", lambda v: _num(v) > 0, False),
    ("ccu_cardiac", "CCU", lambda v: _num(v) > 0, False),
    ("maternity", "MATERNAL", lambda v: _num(v) > 0, False),
    ("nicu", "NICU", lambda v: _num(v) > 0, False),
    ("pediatric", "PEDIATRIC", lambda v: _num(v) > 0, False),
    ("psychiatric", "PSYCHIATRIC", lambda v: _num(v) > 0, False),
    ("burn", "BURN_UNIT", lambda v: _num(v) > 0, False),
    ("rehabilitation", "REHABILITATION", lambda v: _num(v) > 0, False),
    ("med_surg", "MED_SURG", lambda v: _num(v) > 0, False),
    # Inferred-from-tier (source-provided capability tier, mapped to a token):
    ("stroke", "DPH_STROKE_TIER", lambda v: _is_stroke(v), True),
    ("trauma", "TRAUMA_LEVEL_ADULT", lambda v: _is_trauma(v), True),
]


def _num(v) -> float:
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


def _is_stroke(v) -> bool:
    s = str(v).strip().lower()
    return s not in ("", "n/a", "nan", "none") and "stroke" in s or "thrombectomy" in s


def _is_trauma(v) -> bool:
    s = str(v).strip().lower()
    return bool(re.search(r"level\s*(i|ii|iii|1|2|3)\b", s))


def _norm(name: str) -> str:
    """Normalize a facility name for matching: lowercase, drop punctuation and
    common corporate prefixes/suffixes, collapse whitespace."""
    s = str(name).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    for noise in (
        "hospital", "medical center", "health", "the ", "inc", "campus",
        "university", "brown", "umass memorial", "memorial",
    ):
        s = s.replace(noise, " ")
    return re.sub(r"\s+", " ", s).strip()


def derive_specialties(row: pd.Series) -> tuple[list[str], list[str]]:
    """Return (specialties, inferred_tokens) for one MassGIS row."""
    specialties: list[str] = []
    inferred: list[str] = []
    for token, col, pred, is_inferred in SPECIALTY_MAP:
        if col in row and pred(row[col]):
            specialties.append(token)
            if is_inferred:
                inferred.append(token)
    return specialties, inferred


def main() -> None:
    massgis = pd.read_csv(MASSGIS, dtype=str, keep_default_na=False)
    cms = pd.read_csv(CMS, dtype=str, keep_default_na=False)

    # CMS lookup by (normalized name, zip5) for address enrichment + confirmation.
    cms = cms.rename(columns={"ZIP Code": "ZIP", "Facility Name": "CMS_NAME", "Address": "CMS_ADDR"})
    cms["zip5"] = cms["ZIP"].str.slice(0, 5)
    cms["nkey"] = cms["CMS_NAME"].map(_norm)
    cms_by_key = {(r.nkey, r.zip5): r for r in cms.itertuples()}
    cms_by_zip: dict[str, list] = {}
    for r in cms.itertuples():
        cms_by_zip.setdefault(r.zip5, []).append(r)

    # Prefer acute hospitals with coordinates and a real bed count, then spread
    # across counties so the demo isn't all-Boston.
    massgis["lat_f"] = massgis["latitude"].map(_num)
    massgis["lon_f"] = massgis["longitude"].map(_num)
    massgis["beds_f"] = massgis["TOTAL_BEDS"].map(_num)
    acute = massgis[
        (massgis["FACILITY_TYPE"].str.contains("Acute", case=False, na=False))
        & (massgis["lat_f"] != 0)
        & (massgis["lon_f"] != 0)
        & (massgis["beds_f"] > 0)
    ].copy()

    rows = []
    notes_lines = []
    matched = unmatched = 0
    seen_counties: dict[str, int] = {}
    # Sort largest-bed first within each county for recognizable anchors, but cap
    # per-county so the set stays geographically spread.
    acute = acute.sort_values("beds_f", ascending=False)
    per_county_cap = 3

    for r in acute.itertuples():
        if len(rows) >= TARGET_MAX:
            break
        county = getattr(r, "COUNTY", "") or "UNKNOWN"
        if seen_counties.get(county, 0) >= per_county_cap:
            continue

        nkey = _norm(r.FACILITY_NAME)
        zip5 = str(r.ZIP_CODE).strip()[:5]
        cms_hit = cms_by_key.get((nkey, zip5))
        if cms_hit is None:
            # fall back to fuzzy: any CMS row in the same ZIP whose normalized
            # name shares >=1 token
            cand = cms_by_zip.get(zip5, [])
            toks = set(nkey.split())
            cms_hit = next((c for c in cand if toks & set(c.nkey.split())), None)

        # City always comes from the MassGIS MUNICIPALITY column (always present
        # and title-cased), so a CMS match still gets a complete "street, city MA zip".
        city = str(getattr(r, "MUNICIPALITY", "")).strip().title()
        if cms_hit is not None:
            street = str(cms_hit.CMS_ADDR).strip()
            match_note = f"matched CMS '{cms_hit.CMS_NAME}' on name+ZIP"
            matched += 1
        else:
            street = str(r.STREET_ADDRESS).strip()
            match_note = "no CMS match; MassGIS address kept"
            unmatched += 1
        address = f"{street}, {city} MA {zip5}"

        specialties, inferred = derive_specialties(pd.Series(r._asdict()))
        row = {
            "facility_id": f"ma-{str(r.DPH_FACILITY_ID).strip()}",
            "name": str(r.FACILITY_NAME).strip(),
            "address": re.sub(r"\s+", " ", address).strip().strip(","),
            "lat": round(r.lat_f, 6),
            "lon": round(r.lon_f, 6),
            "specialties": ";".join(specialties),
            "licensed_beds": int(r.beds_f),
            "staffed_beds": "",  # not a source field -> intentionally blank
        }
        rows.append(row)
        seen_counties[county] = seen_counties.get(county, 0) + 1
        inferred_part = f" | INFERRED from tier/level: {','.join(inferred)}" if inferred else ""
        notes_lines.append(f"- {row['facility_id']} {row['name']} ({county}): {match_note}{inferred_part}")

    if len(rows) < TARGET_MIN:
        raise SystemExit(f"Only {len(rows)} facilities built; need >= {TARGET_MIN}. Check source files.")

    out_df = pd.DataFrame(rows, columns=[
        "facility_id", "name", "address", "lat", "lon",
        "specialties", "licensed_beds", "staffed_beds",
    ])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT, index=False)

    NOTES.write_text(
        "# hospitals.csv build notes\n\n"
        f"Built by `scripts/build_hospitals_csv.py` from CMS + MassGIS "
        f"(see ml/data/raw/hospitals/MANIFEST.md).\n\n"
        f"Rows: {len(rows)} | CMS-matched: {matched} | CMS-unmatched (MassGIS address kept): {unmatched}\n\n"
        "## Columns\n"
        "- `lat`,`lon`,`licensed_beds`(=MassGIS TOTAL_BEDS), unit/capability flags: all from MassGIS.\n"
        "- `address`: from CMS when matched, else MassGIS.\n"
        "- `staffed_beds`: NOT present in either source -> left blank, never estimated.\n\n"
        "## Specialties provenance\n"
        "Every token maps to a source column. Tokens tagged INFERRED are read off a\n"
        "capability TIER field (stroke<-DPH_STROKE_TIER, trauma<-TRAUMA_LEVEL_ADULT)\n"
        "rather than a plain unit count, but are still source-provided, not invented.\n\n"
        "## Per-facility\n" + "\n".join(notes_lines) + "\n"
    )

    print(f"Wrote {OUT} with {len(rows)} rows (CMS-matched {matched}, unmatched {unmatched}).")
    print(out_df.to_string(index=False, max_colwidth=40))


if __name__ == "__main__":
    main()
