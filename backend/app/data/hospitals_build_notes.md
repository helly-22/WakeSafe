# hospitals.csv build notes

Built by `scripts/build_hospitals_csv.py` from CMS + MassGIS (see ml/data/raw/hospitals/MANIFEST.md).

Rows: 20 | CMS-matched: 14 | CMS-unmatched (MassGIS address kept): 6

## Columns
- `lat`,`lon`,`licensed_beds`(=MassGIS TOTAL_BEDS), unit/capability flags: all from MassGIS.
- `address`: from CMS when matched, else MassGIS.
- `staffed_beds`: NOT present in either source -> left blank, never estimated.

## Specialties provenance
Every token maps to a source column. Tokens tagged INFERRED are read off a
capability TIER field (stroke<-DPH_STROKE_TIER, trauma<-TRAUMA_LEVEL_ADULT)
rather than a plain unit count, but are still source-provided, not invented.

## Per-facility
- ma-2168 Massachusetts General Hospital (SUFFOLK): matched CMS 'MASSACHUSETTS GENERAL HOSPITAL' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2341 Brigham and Women's Hospital (SUFFOLK): matched CMS 'BRIGHAM AND WOMEN'S HOSPITAL' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2339 Baystate Medical Center (HAMPDEN): matched CMS 'BAYSTATE MEDICAL CENTER' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2307 Boston Medical Center - Menino Pavilion (SUFFOLK): matched CMS 'BOSTON MEDICAL CENTER' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2841 UMass Memorial Medical Center - University Campus (WORCESTER): matched CMS 'UMASS MEMORIAL MEDICAL CENTER/UNIVERSITY CAMPUS' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2010 Southcoast Health - St. Lukes Hospital (BRISTOL): no CMS match; MassGIS address kept | INFERRED from tier/level: stroke,trauma
- ma-2107 South Shore Hospital (NORFOLK): matched CMS 'SOUTH SHORE HOSPITAL' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2920 McLean Hospital Corporation (MIDDLESEX): matched CMS 'MCLEAN HOSPITAL CORPORATION' on name+ZIP
- ma-2342 Lahey Hospital & Medical Center - Burlington (MIDDLESEX): no CMS match; MassGIS address kept | INFERRED from tier/level: stroke,trauma
- ma-2337 Southcoast Health - Charlton (BRISTOL): matched CMS 'SOUTHCOAST HOSPITALS GROUP' on name+ZIP | INFERRED from tier/level: stroke
- ma-2124 UMass Memorial Medical Center - Memorial Campus (WORCESTER): no CMS match; MassGIS address kept | INFERRED from tier/level: stroke
- ma-2135 Cape Cod Hospital (BARNSTABLE): matched CMS 'CAPE COD HOSPITAL' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2128 Saint Vincent Hospital (WORCESTER): matched CMS 'ST VINCENT HOSPITAL' on name+ZIP | INFERRED from tier/level: stroke
- ma-2313 Berkshire Medical Center - Berkshire Campus (BERKSHIRE): matched CMS 'BERKSHIRE MEDICAL CENTER' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2075 Newton-Wellesley Hospital (MIDDLESEX): matched CMS 'NEWTON-WELLESLEY HOSPITAL' on name+ZIP | INFERRED from tier/level: stroke
- ma-2149 Mercy Medical Center Campus (HAMPDEN): no CMS match; MassGIS address kept | INFERRED from tier/level: stroke
- ma-2014 North Shore Medical Center - Salem Hospital (ESSEX): matched CMS 'NORTH SHORE MEDICAL CENTER -' on name+ZIP | INFERRED from tier/level: stroke,trauma
- ma-2007 Beverly Hospital - Beverly Campus (ESSEX): no CMS match; MassGIS address kept | INFERRED from tier/level: stroke,trauma
- ma-2311 Boston Medical Center - South (PLYMOUTH): no CMS match; MassGIS address kept | INFERRED from tier/level: stroke,trauma
- ma-2145 Holyoke Medical Center (HAMPDEN): matched CMS 'HOLYOKE MEDICAL CENTER' on name+ZIP | INFERRED from tier/level: stroke
