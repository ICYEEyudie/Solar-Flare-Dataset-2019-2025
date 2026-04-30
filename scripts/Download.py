# -*- coding: utf-8 -*-
"""
Multi-threaded downloader for HMI SHARP 720s magnetogram data from JSOC.

Each worker processes one day:
1. Query JSOC records
2. Save daily metadata CSV
3. Download magnetogram files
4. Mark the day as DONE if download succeeds

Recommended MAX_WORKERS: 2-5.
Do not use too many workers to avoid JSOC/network rate-limit issues.
"""

from sunpy.net import attrs as a
from sunpy.net import jsoc
import astropy.units as u

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import os
import time
import json
import urllib.error


# ================= Configuration =================
EMAIL = ""  # Required by JSOC
SERIES = "hmi.sharp_720s"
SEGMENT = "magnetogram"

# Sampling interval in minutes.
# Use 96 for 96-minute cadence; use 12 for full 720s cadence.
SAMPLE_MIN = 96

# Root directory for downloaded data
SAVE_ROOT = r""

# UTC time range. End time is exclusive.
GLOBAL_START = datetime(2019, 1, 26, 0, 0, tzinfo=timezone.utc)
GLOBAL_END = datetime(2025, 12, 30, 0, 0, tzinfo=timezone.utc)

# Retry settings
MAX_RETRIES = 5
RETRY_WAIT_SEC = 10

# Number of parallel workers.
# Recommended: 2-5. Do not set too high.
MAX_WORKERS = 3

# Progress state file
STATE_FILE = os.path.join(SAVE_ROOT, "_progress.json")
# ==================================================


# Lock for safely writing shared progress file
state_lock = Lock()


def ensure_dir(path):
    """Create a directory if it does not exist."""
    os.makedirs(path, exist_ok=True)
    return path


def day_iter(t0, t1):
    """Generate daily time intervals between t0 and t1."""
    cur = t0
    while cur < t1:
        nxt = min(cur + timedelta(days=1), t1)
        yield cur, nxt
        cur = nxt


def load_state():
    """Load progress state from JSON file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_state(obj):
    """Save progress state to JSON file."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[Warning] Failed to save state file: {e}")


def already_done(day_dir):
    """Check whether a day has already been completed."""
    return os.path.exists(os.path.join(day_dir, "DONE"))


def mark_done(day_dir):
    """Create a DONE marker file for a completed day."""
    with open(os.path.join(day_dir, "DONE"), "w", encoding="utf-8") as f:
        f.write("ok\n")


def query_one_day(client, t_start, t_end):
    """Query JSOC records for one day with retry logic."""
    query = (
        a.Time(t_start, t_end),
        a.jsoc.Series(SERIES),
        a.Sample(SAMPLE_MIN * u.minute),
        a.jsoc.Segment(SEGMENT),
        a.jsoc.Notify(EMAIL),
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = client.search(*query)
            return result

        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  [Query] Network error {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SEC)

        except Exception as e:
            print(f"  [Query] Unexpected error: {e}")
            break

    return None


def fetch_with_retry(client, result, out_dir):
    """Download JSOC query results with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            files = client.fetch(result, path=out_dir)
            return files

        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  [Fetch] Network error {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SEC)

        except Exception as e:
            print(f"  [Fetch] Unexpected error: {e}")
            break

    return []


def save_daily_metadata(result, day_dir, day_str):
    """Save daily JSOC query metadata to CSV."""
    try:
        df = result.show().to_pandas()
        csv_path = os.path.join(day_dir, f"{SERIES.replace('.', '_')}_{day_str}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"  [{day_str}] Metadata saved: {csv_path} ({len(df)} records)")
        return csv_path

    except Exception as e:
        print(f"  [{day_str}] Failed to save metadata CSV: {e}")
        return None


def update_state_done(day_str):
    """Update shared progress state safely."""
    with state_lock:
        state = load_state()
        state["series"] = SERIES
        state["segment"] = SEGMENT
        state["sample_min"] = SAMPLE_MIN
        state["last_done_day"] = day_str
        save_state(state)


def process_one_day(t0, t1):
    """
    Process one day:
    query records, save metadata, download files, and mark DONE.
    """
    day_str = t0.strftime("%Y%m%d")
    day_dir = ensure_dir(os.path.join(SAVE_ROOT, day_str))

    print(f"\n=== Processing {day_str} ({t0.isoformat()} -> {t1.isoformat()}) ===")

    if already_done(day_dir):
        msg = f"[{day_str}] Skipped: DONE marker exists."
        print(msg)
        return day_str, "skipped", 0

    # Create a separate JSOC client inside each worker.
    # This avoids sharing one client object across multiple threads.
    client = jsoc.JSOCClient()

    result = query_one_day(client, t0, t1)

    if result is None or len(result) == 0:
        msg = f"[{day_str}] No records found or query failed."
        print(msg)
        return day_str, "no_records_or_query_failed", 0

    save_daily_metadata(result, day_dir, day_str)

    files = fetch_with_retry(client, result, day_dir)
    downloaded_num = len(files)

    print(f"  [{day_str}] Downloaded files: {downloaded_num} -> {day_dir}")

    if len(result) > 0 and downloaded_num > 0:
        mark_done(day_dir)
        update_state_done(day_str)
        print(f"  [{day_str}] Marked as DONE.")
        return day_str, "done", downloaded_num

    print(f"  [{day_str}] Not marked as DONE because no files were downloaded.")
    return day_str, "download_failed", downloaded_num


def main():
    """Main function for multi-threaded daily download."""
    ensure_dir(SAVE_ROOT)

    initial_state = load_state()
    initial_state["series"] = SERIES
    initial_state["segment"] = SEGMENT
    initial_state["sample_min"] = SAMPLE_MIN
    initial_state["start"] = GLOBAL_START.isoformat()
    initial_state["end"] = GLOBAL_END.isoformat()
    save_state(initial_state)

    daily_tasks = list(day_iter(GLOBAL_START, GLOBAL_END))

    print(f"Total days to process: {len(daily_tasks)}")
    print(f"Using MAX_WORKERS = {MAX_WORKERS}")

    summary = {
        "done": 0,
        "skipped": 0,
        "no_records_or_query_failed": 0,
        "download_failed": 0,
    }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_day = {
            executor.submit(process_one_day, t0, t1): t0.strftime("%Y%m%d")
            for t0, t1 in daily_tasks
        }

        for future in as_completed(future_to_day):
            day_str = future_to_day[future]

            try:
                _, status, downloaded_num = future.result()
                summary[status] = summary.get(status, 0) + 1
                print(f"[Summary] {day_str}: {status}, downloaded={downloaded_num}")

            except Exception as e:
                summary["download_failed"] = summary.get("download_failed", 0) + 1
                print(f"[Error] {day_str} failed with exception: {e}")

    print("\nAll dates have been processed.")
    print("Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()