# -*- coding: utf-8 -*-
r"""
Build M/X-class solar flare labels from local NOAA SWPC event files.

Input:
    NOAA event files

    HMI SHARP metadata and FITS files

Output:
    flare_labels_M1_from_noaa_events.csv
    parsed_noaa_mx_flares.csv

Label definition:
    label = 1 if an M1.0+ or X-class XRA flare occurs in the same NOAA active region
              within 48 hours after the HMI SHARP observation time.
    label = 0 otherwise.

Notes:
    - NOAA event files may use 4-digit NOAA region numbers, e.g. 2733.
    - HMI SHARP metadata may use 5-digit NOAA region numbers, e.g. 12733.
    - This script automatically matches both full number and last 4 digits.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from astropy.time import Time
from tqdm import tqdm


# ====================== Configuration ======================

HMI_ROOT = Path(r"")
NOAA_EVENT_DIR = Path(r"")

OUTPUT_LABEL_CSV = HMI_ROOT / "flare_labels_M1_from_noaa_events.csv"
OUTPUT_FLARE_CSV = HMI_ROOT / "parsed_noaa_mx_flares.csv"

LOOKAHEAD_HOURS = 48
MIN_FLARE_CLASS = "M1.0"

# Recommended: True.
# If final labels are all 0, temporarily set to False to test time-window matching.
MATCH_NOAA_AR = True

# If True, rows without matched local FITS path will be removed.
# Keep False first to avoid deleting valid metadata rows due to filename mismatch.
REQUIRE_LOCAL_FITS = False

# ===========================================================


def parse_goes_class(goes_class: str) -> float:
    """
    Convert GOES flare class to numeric intensity.

    A1.0 = 1e-8
    B1.0 = 1e-7
    C1.0 = 1e-6
    M1.0 = 1e-5
    X1.0 = 1e-4
    """
    if not isinstance(goes_class, str):
        return 0.0

    text = goes_class.strip().upper()
    match = re.match(r"^([ABCMX])([0-9]+(?:\.[0-9]+)?)$", text)

    if not match:
        return 0.0

    letter = match.group(1)
    value = float(match.group(2))

    scale = {
        "A": 1e-8,
        "B": 1e-7,
        "C": 1e-6,
        "M": 1e-5,
        "X": 1e-4,
    }

    return scale[letter] * value


def normalize_noaa_ar_variants(ar_value: int) -> List[int]:
    """
    Generate possible NOAA active-region number variants.

    Example:
        2733  -> [2733, 12733, 22733]
        12733 -> [2733, 12733, 22733]
    """
    try:
        ar = int(ar_value)
    except Exception:
        return []

    if ar <= 0:
        return []

    last4 = ar % 10000

    variants = {
        ar,
        last4,
        10000 + last4,
        20000 + last4,
    }

    return sorted(v for v in variants if v > 0)


def parse_jsoc_time(value) -> Optional[pd.Timestamp]:
    """
    Parse JSOC time values into UTC pandas Timestamp.

    Common T_REC format:
        2019.01.26_00:00:00_TAI
    """
    if pd.isna(value):
        return None

    text = str(value).strip()

    try:
        if text.endswith("_TAI"):
            clean = text.replace("_TAI", "")
            clean = clean.replace(".", "-").replace("_", "T")
            dt = Time(clean, scale="tai").utc.datetime
            return pd.Timestamp(dt).tz_localize("UTC")

        clean = text.replace(".", "-").replace("_", "T")
        ts = pd.to_datetime(clean, utc=True, errors="coerce")

        if pd.isna(ts):
            return None

        return ts

    except Exception:
        return None


def get_record_time(row: pd.Series) -> Optional[pd.Timestamp]:
    """
    Get observation time from one HMI SHARP metadata row.
    """
    for col in ["T_REC", "T_OBS", "DATE__OBS", "DATE-OBS"]:
        if col in row.index:
            ts = parse_jsoc_time(row[col])
            if ts is not None and not pd.isna(ts):
                return ts

    return None


def extract_noaa_ars_from_metadata(row: pd.Series) -> List[int]:
    """
    Extract NOAA active region numbers from SHARP metadata.
    """
    candidates = []

    for col in ["NOAA_AR", "NOAA_ARS"]:
        if col in row.index and not pd.isna(row[col]):
            candidates.append(str(row[col]))

    text = " ".join(candidates)
    numbers = re.findall(r"\d+", text)

    ars = []

    for num in numbers:
        try:
            value = int(num)
            if value > 0:
                ars.extend(normalize_noaa_ar_variants(value))
        except Exception:
            continue

    return sorted(set(ars))


def construct_expected_fits_name(
    row: pd.Series,
    record_time: pd.Timestamp,
) -> Optional[str]:
    """
    Construct expected FITS filename from HARPNUM and T_REC.

    Typical filename:
        hmi.sharp_720s.<HARPNUM>.<YYYYMMDD_HHMMSS>_TAI.magnetogram.fits
    """
    if "HARPNUM" not in row.index or pd.isna(row["HARPNUM"]):
        return None

    try:
        harpnum = int(row["HARPNUM"])
    except Exception:
        return None

    if "T_REC" in row.index and not pd.isna(row["T_REC"]):
        text = str(row["T_REC"]).strip()

        if text.endswith("_TAI"):
            clean = text.replace("_TAI", "")
            clean = clean.replace(".", "")
            clean = clean.replace(":", "")

            try:
                date_part, time_part = clean.split("_")
                return f"hmi.sharp_720s.{harpnum}.{date_part}_{time_part}_TAI.magnetogram.fits"
            except ValueError:
                pass

    fallback_time = record_time.strftime("%Y%m%d_%H%M%S")
    return f"hmi.sharp_720s.{harpnum}.{fallback_time}_TAI.magnetogram.fits"


def load_metadata_files(metadata_root: Path) -> pd.DataFrame:
    """
    Load all daily HMI SHARP metadata CSV files.
    """
    csv_files = sorted(metadata_root.rglob("hmi_sharp_720s_*.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No hmi_sharp_720s_*.csv files found under {metadata_root}")

    dataframes = []

    for csv_file in tqdm(csv_files, desc="Loading metadata CSV files"):
        try:
            df = pd.read_csv(csv_file)
            df["metadata_csv"] = str(csv_file.resolve())
            dataframes.append(df)
        except Exception as error:
            print(f"[Warning] Failed to read {csv_file}: {error}")

    if not dataframes:
        raise RuntimeError("No metadata CSV files could be loaded.")

    metadata = pd.concat(dataframes, ignore_index=True)
    print(f"Loaded {len(metadata)} metadata records from {len(csv_files)} CSV files.")

    return metadata


def build_fits_index(fits_root: Path) -> Dict[str, str]:
    """
    Build an index from FITS filename to full local path.
    """
    print(f"Scanning FITS files under: {fits_root}")

    fits_files = list(fits_root.rglob("*.fits"))
    fits_index = {file.name: str(file.resolve()) for file in fits_files}

    print(f"Found {len(fits_index)} FITS files.")

    return fits_index


def get_local_noaa_event_files(event_dir: Path) -> List[Path]:
    """
    Get local NOAA SWPC event files.
    """
    if not event_dir.exists():
        raise FileNotFoundError(f"NOAA event directory does not exist: {event_dir}")

    patterns = [
        "*events.txt",
        "*event.txt",
        "*events*.txt",
        "*event*.txt",
    ]

    files = []

    for pattern in patterns:
        files.extend(event_dir.rglob(pattern))

    files = sorted(set(files))

    if not files:
        raise FileNotFoundError(f"No NOAA event txt files found under: {event_dir}")

    print(f"Found {len(files)} NOAA event files.")

    return files


def parse_file_date_from_header_or_name(event_file: Path) -> Optional[pd.Timestamp]:
    """
    Parse event date from NOAA file header or filename.

    Header example:
        :Date: 2019 01 25

    Filename example:
        20190125events.txt
    """
    try:
        with event_file.open("r", encoding="latin-1", errors="ignore") as f:
            for line in f:
                match = re.search(r":Date:\s+(\d{4})\s+(\d{2})\s+(\d{2})", line)
                if match:
                    return pd.Timestamp(
                        year=int(match.group(1)),
                        month=int(match.group(2)),
                        day=int(match.group(3)),
                    )
    except Exception:
        pass

    match = re.search(r"(\d{8})", event_file.name)

    if match:
        return pd.to_datetime(match.group(1), format="%Y%m%d", errors="coerce")

    return None


def parse_event_hhmm(file_date: pd.Timestamp, hhmm_raw: str) -> Optional[pd.Timestamp]:
    """
    Convert NOAA event HHMM string into UTC timestamp.

    Some NOAA lines may use prefixes such as A1038.
    """
    if not isinstance(hhmm_raw, str):
        return None

    text = hhmm_raw.strip()

    if text == "////":
        return None

    # Remove a leading letter such as A1038.
    text = re.sub(r"^[A-Z]", "", text)

    if not re.match(r"^\d{4}$", text):
        return None

    hour = int(text[:2])
    minute = int(text[2:])

    if hour > 23 or minute > 59:
        return None

    return pd.Timestamp(file_date).tz_localize("UTC").replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def parse_noaa_event_file_for_mx(event_file: Path) -> pd.DataFrame:
    """
    Parse one NOAA SWPC event file and extract M/X-class XRA flare events.

    Typical lines:

    With plus flag:
        7900 + 0106 0111 0116 G15 5 XRA 1-8A B1.7 6.7E-05 2733

    Without plus flag:
        7910 0207 0224 0227 G15 5 XRA 1-8A B1.4 1.4E-04 2733

    We identify XRA first, then read Begin/Max/End as:
        Begin = parts[xra_idx - 5]
        Max   = parts[xra_idx - 4]
        End   = parts[xra_idx - 3]
    """
    file_date = parse_file_date_from_header_or_name(event_file)

    if file_date is None or pd.isna(file_date):
        print(f"[Warning] Cannot determine date for file: {event_file}")
        return pd.DataFrame()

    try:
        with event_file.open("r", encoding="latin-1", errors="ignore") as f:
            lines = f.readlines()
    except Exception as error:
        print(f"[Warning] Failed to read {event_file}: {error}")
        return pd.DataFrame()

    rows = []
    min_intensity = parse_goes_class(MIN_FLARE_CLASS)

    for line in lines:
        raw_line = line.strip()

        if not raw_line:
            continue

        if raw_line.startswith("#") or raw_line.startswith(":"):
            continue

        parts = raw_line.split()

        if "XRA" not in parts:
            continue

        try:
            xra_idx = parts.index("XRA")
        except ValueError:
            continue

        if xra_idx < 5:
            continue

        begin_raw = parts[xra_idx - 5]
        peak_raw = parts[xra_idx - 4]
        end_raw = parts[xra_idx - 3]

        flare_start_time = parse_event_hhmm(file_date, begin_raw)
        flare_peak_time = parse_event_hhmm(file_date, peak_raw)
        flare_end_time = parse_event_hhmm(file_date, end_raw)

        if flare_start_time is None:
            continue

        flare_class = None

        for token in parts[xra_idx + 1:]:
            token_clean = token.strip().upper()

            if re.match(r"^[ABCMX][0-9]+(?:\.[0-9]+)?$", token_clean):
                flare_class = token_clean
                break

        if flare_class is None:
            continue

        flare_intensity = parse_goes_class(flare_class)

        # Keep only M1.0+ or X-class flares.
        if flare_intensity < min_intensity:
            continue

        flare_noaa_ar = 0

        # Reg# is usually the last integer token in the line.
        for token in reversed(parts):
            if re.match(r"^\d{3,6}$", token):
                try:
                    flare_noaa_ar = int(token)
                    break
                except Exception:
                    pass

        variants = normalize_noaa_ar_variants(flare_noaa_ar)

        rows.append(
            {
                "flare_start_time": flare_start_time,
                "flare_peak_time": flare_peak_time,
                "flare_end_time": flare_end_time,
                "flare_class": flare_class,
                "flare_intensity": flare_intensity,
                "flare_noaa_ar_raw": flare_noaa_ar,
                "flare_noaa_ar_last4": flare_noaa_ar % 10000 if flare_noaa_ar > 0 else 0,
                "flare_noaa_ar_variants": ";".join(map(str, variants)),
                "source_file": str(event_file.resolve()),
                "raw_line": raw_line,
            }
        )

    return pd.DataFrame(rows)


def parse_all_noaa_mx_events(event_files: List[Path]) -> pd.DataFrame:
    """
    Parse all local NOAA event files and return M/X-class XRA flare events.
    """
    dataframes = []

    for event_file in tqdm(event_files, desc="Parsing NOAA event files"):
        df = parse_noaa_event_file_for_mx(event_file)

        if not df.empty:
            dataframes.append(df)

    if not dataframes:
        raise RuntimeError(
            "No M/X-class XRA flare events were parsed. "
            "Check the event files or temporarily set MIN_FLARE_CLASS = 'C1.0' for debugging."
        )

    flare_df = pd.concat(dataframes, ignore_index=True)

    flare_df = flare_df.drop_duplicates(
        subset=["flare_start_time", "flare_class", "flare_noaa_ar_raw"]
    )

    flare_df = flare_df.sort_values("flare_start_time").reset_index(drop=True)

    return flare_df


def build_flare_lookup(flare_df: pd.DataFrame) -> Dict[int, pd.DataFrame]:
    """
    Build flare lookup table by NOAA active-region variants.
    """
    lookup: Dict[int, List[pd.DataFrame]] = {}

    for _, row in flare_df.iterrows():
        variants_text = str(row.get("flare_noaa_ar_variants", ""))
        variants = []

        for token in variants_text.split(";"):
            token = token.strip()
            if token.isdigit():
                variants.append(int(token))

        raw_ar = int(row.get("flare_noaa_ar_raw", 0))
        variants.extend(normalize_noaa_ar_variants(raw_ar))
        variants = sorted(set(v for v in variants if v > 0))

        for ar in variants:
            if ar not in lookup:
                lookup[ar] = []
            lookup[ar].append(row.to_frame().T)

    final_lookup = {}

    for ar, row_dfs in lookup.items():
        df = pd.concat(row_dfs, ignore_index=True)
        df = df.sort_values("flare_start_time").reset_index(drop=True)
        final_lookup[ar] = df

    return final_lookup


def label_one_record(
    record_time: pd.Timestamp,
    noaa_ars: List[int],
    flare_lookup: Dict[int, pd.DataFrame],
    all_flare_df: pd.DataFrame,
) -> Tuple[int, Optional[str], Optional[str], Optional[int]]:
    """
    Assign M/X-class flare label to one HMI SHARP record.
    """
    window_end = record_time + pd.Timedelta(hours=LOOKAHEAD_HOURS)

    if MATCH_NOAA_AR:
        if not noaa_ars:
            return 0, None, None, None

        candidate_dfs = []

        for ar in noaa_ars:
            if ar in flare_lookup:
                candidate_dfs.append(flare_lookup[ar])

        if not candidate_dfs:
            return 0, None, None, None

        search_df = pd.concat(candidate_dfs, ignore_index=True)

    else:
        search_df = all_flare_df

    candidates = search_df[
        (search_df["flare_start_time"] > record_time)
        & (search_df["flare_start_time"] <= window_end)
    ]

    if candidates.empty:
        return 0, None, None, None

    candidates = candidates.sort_values(
        ["flare_intensity", "flare_start_time"],
        ascending=[False, True],
    )

    strongest = candidates.iloc[0]
    earliest = candidates.sort_values("flare_start_time").iloc[0]

    return (
        1,
        str(strongest["flare_class"]),
        str(earliest["flare_start_time"]),
        int(strongest["flare_noaa_ar_raw"]),
    )


def build_labels(
    metadata: pd.DataFrame,
    flare_df: pd.DataFrame,
    fits_index: Dict[str, str],
) -> pd.DataFrame:
    """
    Build flare labels for all HMI SHARP metadata records.
    """
    flare_lookup = build_flare_lookup(flare_df)

    useful_features = [
        "USFLUX",
        "MEANGAM",
        "MEANGBT",
        "MEANGBZ",
        "MEANGBH",
        "MEANJZD",
        "TOTUSJZ",
        "MEANALP",
        "MEANJZH",
        "TOTUSJH",
        "ABSNJZH",
        "SAVNCPP",
        "MEANPOT",
        "TOTPOT",
        "MEANSHR",
        "SHRGT45",
        "R_VALUE",
        "AREA_ACR",
        "QUALITY",
        "OFFDISK",
    ]

    rows = []

    for _, row in tqdm(metadata.iterrows(), total=len(metadata), desc="Building labels"):
        record_time = get_record_time(row)

        if record_time is None:
            continue

        noaa_ars = extract_noaa_ars_from_metadata(row)

        expected_fits_name = construct_expected_fits_name(row, record_time)
        local_fits_path = fits_index.get(expected_fits_name) if expected_fits_name else None

        if REQUIRE_LOCAL_FITS and local_fits_path is None:
            continue

        label, flare_class, flare_time, matched_noaa_ar = label_one_record(
            record_time=record_time,
            noaa_ars=noaa_ars,
            flare_lookup=flare_lookup,
            all_flare_df=flare_df,
        )

        output = {
            "HARPNUM": row.get("HARPNUM", None),
            "NOAA_AR": row.get("NOAA_AR", None),
            "NOAA_ARS": row.get("NOAA_ARS", None),
            "record_time_utc": record_time,
            "lookahead_hours": LOOKAHEAD_HOURS,
            "min_flare_class": MIN_FLARE_CLASS,
            "label": label,
            "matched_flare_class": flare_class,
            "matched_flare_start_time": flare_time,
            "matched_noaa_ar": matched_noaa_ar,
            "expected_fits_name": expected_fits_name,
            "local_fits_path": local_fits_path,
            "metadata_csv": row.get("metadata_csv", None),
        }

        for feature in useful_features:
            if feature in row.index:
                output[feature] = row[feature]

        rows.append(output)

    return pd.DataFrame(rows)


def main() -> None:
    print("========== Build M/X Flare Labels from Local NOAA Events ==========")
    print(f"HMI root: {HMI_ROOT}")
    print(f"NOAA event directory: {NOAA_EVENT_DIR}")
    print(f"Output flare CSV: {OUTPUT_FLARE_CSV}")
    print(f"Output label CSV: {OUTPUT_LABEL_CSV}")
    print(f"Minimum flare class: {MIN_FLARE_CLASS}")
    print(f"Lookahead hours: {LOOKAHEAD_HOURS}")
    print(f"Match NOAA AR: {MATCH_NOAA_AR}")
    print(f"Require local FITS: {REQUIRE_LOCAL_FITS}")
    print("==================================================================")

    metadata = load_metadata_files(HMI_ROOT)

    event_files = get_local_noaa_event_files(NOAA_EVENT_DIR)

    flare_df = parse_all_noaa_mx_events(event_files)

    OUTPUT_FLARE_CSV.parent.mkdir(parents=True, exist_ok=True)
    flare_df.to_csv(OUTPUT_FLARE_CSV, index=False, encoding="utf-8-sig")

    print(f"\nParsed M/X-class XRA flare events: {len(flare_df)}")
    print(f"Saved parsed flare event table to: {OUTPUT_FLARE_CSV}")

    print("\nFlare class distribution:")
    print(flare_df["flare_class"].str[0].value_counts(dropna=False))

    print("\nYearly M/X flare counts:")
    flare_df["year"] = pd.to_datetime(flare_df["flare_start_time"], utc=True).dt.year
    print(flare_df.groupby("year").size())

    fits_index = build_fits_index(HMI_ROOT)

    labeled_df = build_labels(
        metadata=metadata,
        flare_df=flare_df,
        fits_index=fits_index,
    )

    if labeled_df.empty:
        raise RuntimeError("Labeled dataframe is empty. Please check metadata parsing.")

    OUTPUT_LABEL_CSV.parent.mkdir(parents=True, exist_ok=True)
    labeled_df.to_csv(OUTPUT_LABEL_CSV, index=False, encoding="utf-8-sig")

    print("\n========== Labeling Completed ==========")
    print(f"Saved label table to: {OUTPUT_LABEL_CSV}")
    print(f"Total labeled records: {len(labeled_df)}")

    print("\nLabel distribution:")
    print(labeled_df["label"].value_counts(dropna=False))

    missing_fits = labeled_df["local_fits_path"].isna().sum()
    print(f"\nRecords without matched local FITS file: {missing_fits}")

    positive_count = int(labeled_df["label"].sum())
    print(f"Positive samples: {positive_count}")

    if positive_count == 0:
        print("\n[Warning] No positive labels were found.")
        print("Possible reasons:")
        print("1. NOAA_AR matching is too strict.")
        print("2. SHARP metadata NOAA_AR differs from NOAA Reg# in event files.")
        print("3. The selected period has few M/X flares.")
        print("4. Try setting MATCH_NOAA_AR = False to test time-window matching.")
        print("5. Try setting MIN_FLARE_CLASS = 'C1.0' to debug the pipeline.")

    print("========================================")


if __name__ == "__main__":
    main()