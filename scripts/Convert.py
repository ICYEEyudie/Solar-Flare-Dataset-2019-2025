# -*- coding: utf-8 -*-
"""
Batch convert HMI SHARP FITS files to PNG images.

The script recursively scans all FITS files under the input folder,
converts each FITS image to a PNG image, and preserves the original
subfolder structure.
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from tqdm import tqdm


# ====================== Configuration ======================

INPUT_ROOT = Path(r"")
OUTPUT_ROOT = Path(r"")

# Output image format
OUTPUT_EXT = ".png"

# Percentile clipping for visualization.
# This makes magnetograms easier to view by reducing the effect of extreme values.
LOWER_PERCENTILE = 1
UPPER_PERCENTILE = 99

# Set to True if you want to overwrite existing PNG files.
OVERWRITE = False

# ===========================================================


def normalize_fits_data(data: np.ndarray) -> np.ndarray:
    """
    Normalize FITS image data to the range [0, 1].

    Args:
        data: 2D FITS image array.

    Returns:
        Normalized 2D array in [0, 1].
    """
    data = np.asarray(data, dtype=np.float32)

    # Replace invalid values with NaN first.
    data[~np.isfinite(data)] = np.nan

    if np.all(np.isnan(data)):
        return np.zeros_like(data, dtype=np.float32)

    # Percentile clipping for robust visualization.
    vmin = np.nanpercentile(data, LOWER_PERCENTILE)
    vmax = np.nanpercentile(data, UPPER_PERCENTILE)

    if vmax <= vmin:
        return np.zeros_like(data, dtype=np.float32)

    data = np.clip(data, vmin, vmax)
    data = (data - vmin) / (vmax - vmin)

    # Replace remaining NaN values with 0.
    data = np.nan_to_num(data, nan=0.0)

    return data


def read_fits_image(fits_path: Path) -> np.ndarray:
    """
    Read image data from a FITS file.

    Args:
        fits_path: Path to the FITS file.

    Returns:
        2D image array.

    Raises:
        ValueError: If no valid 2D image data is found.
    """
    with fits.open(fits_path, memmap=False) as hdul:
        for hdu in hdul:
            if hdu.data is None:
                continue

            data = hdu.data

            # Some FITS files may contain extra dimensions.
            # Squeeze them to get a 2D image when possible.
            data = np.squeeze(data)

            if data.ndim == 2:
                return data

    raise ValueError(f"No valid 2D image data found in {fits_path}")


def convert_one_fits_to_png(fits_path: Path, output_path: Path) -> bool:
    """
    Convert one FITS file to PNG.

    Args:
        fits_path: Input FITS file path.
        output_path: Output PNG file path.

    Returns:
        True if conversion succeeds, False otherwise.
    """
    try:
        data = read_fits_image(fits_path)
        image = normalize_fits_data(data)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.imsave(
            output_path,
            image,
            cmap="gray",
            vmin=0,
            vmax=1,
        )

        return True

    except Exception as error:
        print(f"[Warning] Failed to convert {fits_path}: {error}")
        return False


def main() -> None:
    """
    Main function for batch FITS-to-PNG conversion.
    """
    if not INPUT_ROOT.exists():
        raise FileNotFoundError(f"Input folder does not exist: {INPUT_ROOT}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    fits_files = sorted(INPUT_ROOT.rglob("*.fits"))

    print("========== Batch FITS to PNG Conversion ==========")
    print(f"Input root: {INPUT_ROOT}")
    print(f"Output root: {OUTPUT_ROOT}")
    print(f"Total FITS files found: {len(fits_files)}")
    print("==================================================")

    if not fits_files:
        print("No FITS files found.")
        return

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for fits_path in tqdm(fits_files, desc="Converting FITS files"):
        relative_path = fits_path.relative_to(INPUT_ROOT)

        output_path = OUTPUT_ROOT / relative_path
        output_path = output_path.with_suffix(OUTPUT_EXT)

        if output_path.exists() and not OVERWRITE:
            skipped_count += 1
            continue

        success = convert_one_fits_to_png(fits_path, output_path)

        if success:
            success_count += 1
        else:
            failed_count += 1

    print("\n========== Conversion Completed ==========")
    print(f"Successful conversions: {success_count}")
    print(f"Skipped existing images: {skipped_count}")
    print(f"Failed conversions: {failed_count}")
    print(f"Output folder: {OUTPUT_ROOT}")
    print("==========================================")


if __name__ == "__main__":
    main()