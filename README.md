# Solar-Flare-Dataset-2019-2025

A reproducible data-construction pipeline and label release for solar flare forecasting based on HMI SHARP 720s magnetogram observations from 2019 to 2025.

## Overview

Solar flares, often accompanied by energetic charged particles and electromagnetic radiation, can affect radio communication, Global Positioning System (GPS) accuracy, satellite operations, and astronaut safety within several minutes. Therefore, developing reliable solar flare forecasting methods is important for modern society, which is increasingly supported by high-tech systems.

Solar flares are closely related to the sudden release of stored magnetic energy in the solar corona. Observed photospheric magnetic fields, including magnetogram images and magnetic parameters of sunspot groups, are widely used as inputs for solar flare forecasting models.

To complement existing studies that mainly rely on earlier solar-cycle periods or 2011–2019 data, this repository provides a reproducible pipeline for constructing a 2019–2025 HMI SHARP magnetogram dataset for solar flare forecasting. Instead of storing the full FITS archive directly in this GitHub repository, we provide data download scripts, FITS conversion scripts, label construction scripts, documentation, and the final M1.0+ flare label file through GitHub Releases.

## Data Source

The raw data are obtained from the Joint Science Operations Center (JSOC) using the `hmi.sharp_720s` data series. SHARP stands for Space-weather HMI Active Region Patch. Each SHARP record corresponds to an automatically identified solar active-region patch rather than a full-disk solar image.

The original `hmi.sharp_720s` data series has a 720-second cadence. In this repository, we focus on the `magnetogram` segment from the `hmi.sharp_720s` series. The `magnetogram` segment provides HARP-sized line-of-sight magnetogram data.

This repository should be regarded as a reproducible pipeline and label release based on official HMI SHARP data, rather than a replacement for JSOC.

## What This Repository Provides

This repository does not directly store the full HMI SHARP FITS archive because the complete magnetogram dataset is too large for a standard GitHub repository.

Instead, this repository provides:

- scripts for downloading HMI SHARP `magnetogram` FITS files and daily metadata CSV files from JSOC;
- scripts for converting FITS files to PNG images if users need image-format inputs;
- scripts for constructing M1.0+ flare labels from NOAA SWPC solar event reports;
- a final label CSV file released through GitHub Releases;
- documentation describing the dataset format.

Users can reproduce the full local dataset by running the provided download and labeling scripts.

## Dataset Coverage

- Time range: `2019-01-26` to `2025-12-30`
- Total coverage: 2,530 days
- Data series: `hmi.sharp_720s`
- Segment: `magnetogram`
- Data type: solar active-region magnetogram patches
- File format:
  - FITS files for magnetograms
  - CSV files for daily metadata
- Sampling strategy: one SHARP record sampled every 96 minutes for each active region when available

Note: The original `hmi.sharp_720s` series has a 720-second cadence, while this dataset pipeline samples records at a 96-minute interval to reduce storage and computational cost.

## Repository Structure

```text
Solar-Flare-Dataset-2019-2025/
├── README.md
├── LICENSE
├── assets/
│   └── sample_interval.png
└── scripts/
    ├── download.py
    ├── build_labels.py
    └── convert.py
```

After running the download script locally, users may obtain a local data directory similar to:

```text
HMI_SHARP_2019to2025_96m/
├── 20190126/
│   ├── hmi.sharp_720s.7334.20190126_000000_TAI.magnetogram.fits
│   ├── hmi.sharp_720s.7334.20190126_013600_TAI.magnetogram.fits
│   └── hmi_sharp_720s_20190126.csv
├── 20190127/
│   └── ...
├── flare_labels_M1_from_noaa_events.csv
└── parsed_noaa_mx_flares.csv
```

The GitHub repository stores the scripts and documentation, while the full FITS files are generated locally by users through the provided JSOC download script.

## Dataset Download

The complete HMI SHARP FITS archive is not stored directly in this repository. Users can generate the full local dataset by running the provided download script:

```bash
python scripts/download.py
```

The script downloads HMI SHARP `magnetogram` FITS files and daily JSOC metadata CSV files from the `hmi.sharp_720s` data series.

The final label CSV file is available in the GitHub Release:

- `flare_labels_M1_from_noaa_events.csv`: binary labels for M1.0+ flare prediction within 48 hours.

The label file was constructed by matching HMI SHARP records with NOAA SWPC X-ray flare events. The current label setting is:

- Minimum flare class: `M1.0`
- Prediction window: 48 hours
- NOAA active-region matching: enabled
- Total labeled records: 317,126
- Positive samples: 20,195
- Negative samples: 296,931

Users who want to rebuild the labels can run:

```bash
python scripts/build_labels.py
```

## Data Format

### Magnetogram FITS Files

Each magnetogram file follows the naming convention:

```text
hmi.sharp_720s.<HARPNUM>.<YYYYMMDD_HHMMSS>_TAI.magnetogram.fits
```

where:

- `<HARPNUM>` is the HMI Active Region Patch number, representing the tracked solar active-region patch.
- `<YYYYMMDD_HHMMSS>` is the observation time in TAI.
- `magnetogram` indicates the line-of-sight magnetogram segment.

Example:

```text
hmi.sharp_720s.7334.20190126_000000_TAI.magnetogram.fits
hmi.sharp_720s.7334.20190126_013600_TAI.magnetogram.fits
```

Adjacent records from the same active region are sampled approximately every 96 minutes in this dataset pipeline. Different active regions may have different spatial sizes, so users should resize, pad, crop, or interpolate images before training image-based deep learning models.

![Example of adjacent magnetogram records from the same active region](assets/Versus.png)

### Daily Metadata CSV Files

Each daily CSV file is generated from the JSOC query results of the `hmi.sharp_720s` data series. These CSV files are metadata tables rather than flare-label files. Each row corresponds to one SHARP observation record, mainly identified by `HARPNUM` and `T_REC`.

The CSV files contain observation time, active-region identifiers, data-quality flags, the corresponding `magnetogram` segment path, and selected SHARP magnetic parameters such as `USFLUX`, `TOTUSJH`, `TOTPOT`, `R_VALUE`, and `AREA_ACR`. These metadata can be used to link FITS files with observation records, construct flare labels, filter low-quality samples, or build tabular machine learning features.

In short, the FITS files provide the magnetogram images, while the daily CSV files provide the metadata and physical SHARP parameters needed for indexing, filtering, feature analysis, and label construction.

## FITS-to-Image Conversion

This repository provides the original magnetogram FITS files through the download script rather than pre-converted PNG/JPG image files. The reason is that FITS-to-image conversion can involve different preprocessing choices, including:

- percentile clipping
- normalization
- resizing
- padding
- interpolation
- colormap selection

These choices may affect downstream model performance. Therefore, users are encouraged to apply preprocessing methods suitable for their own research settings.

A sample conversion script is provided in:

```text
scripts/convert.py
```

Users can run:

```bash
python scripts/convert.py
```

## Label Construction

The raw JSOC SHARP data do not contain solar flare prediction labels. Labels need to be constructed by matching SHARP records with external flare event catalogs.

In this repository, labels are constructed from NOAA Space Weather Prediction Center solar event reports. These reports include X-ray flare events (`XRA`), event start time, peak time, end time, flare class, and NOAA active region number.

Recommended binary-label definition:

```text
label = 1
```

if an M1.0 or stronger X-ray flare occurs in the same NOAA active region within 48 hours after the SHARP observation time.

```text
label = 0
```

otherwise.

The label construction script is provided in:

```text
scripts/build_labels.py
```

The generated label table includes:

| Column | Description |
|---|---|
| `HARPNUM` | HMI active-region patch number |
| `NOAA_AR` / `NOAA_ARS` | NOAA active-region identifier(s) |
| `record_time_utc` | Observation time converted to UTC |
| `lookahead_hours` | Prediction window length |
| `min_flare_class` | Minimum flare class used for positive labels |
| `label` | Binary flare label |
| `matched_flare_class` | Matched M/X-class flare class, if any |
| `matched_flare_start_time` | Start time of the matched flare |
| `matched_noaa_ar` | NOAA active region of the matched flare |
| `expected_fits_name` | Expected local FITS filename |
| `local_fits_path` | Local path of the corresponding FITS file |

## Current Label Statistics

Using NOAA SWPC event files, we parsed M/X-class X-ray flare events and matched them with HMI SHARP records.

The current extracted event statistics are:

| Item | Count |
|---|---:|
| NOAA event files parsed | 2,532 |
| M/X-class XRA flare events | 1,883 |
| M-class events | 1,790 |
| X-class events | 93 |

Yearly distribution of parsed M/X-class flare events:

| Year | Number of M/X-class flares |
|---|---:|
| 2020 | 2 |
| 2021 | 29 |
| 2022 | 195 |
| 2023 | 366 |
| 2024 | 935 |
| 2025 | 356 |

The final label distribution is:

| Label | Meaning | Number of records |
|---|---|---:|
| 0 | No M1.0+ flare within the next 48 hours in the same NOAA active region | 296,931 |
| 1 | M1.0+ flare occurs within the next 48 hours in the same NOAA active region | 20,195 |

Total labeled records: `317,126`

The positive-to-negative ratio is approximately `1 : 14.7`, indicating a strong class-imbalance problem.


## Requirements

The scripts require Python 3.9+ and the following packages:

```bash
pip install sunpy astropy pandas tqdm matplotlib numpy
```

Main dependencies:

- `sunpy`: JSOC data query and download
- `astropy`: FITS file handling and time conversion
- `pandas`: metadata and label table processing
- `tqdm`: progress bars
- `matplotlib` and `numpy`: FITS-to-image conversion

## Notes and Limitations

1. This repository does not directly host the full FITS archive. Users should run the provided JSOC download script to reproduce the local dataset.
2. The original `hmi.sharp_720s` series has a 720-second cadence, while this dataset pipeline samples records at a 96-minute interval to reduce storage and computational cost.
3. Active-region patches have different spatial sizes. Users should apply consistent resizing, padding, cropping, or interpolation before training image-based models.
4. Labels are constructed by matching HMI SHARP records with NOAA SWPC X-ray flare events and are not inherent in the original JSOC SHARP data.
5. This dataset is intended for research and educational use.

## Acknowledgement

The raw HMI SHARP data are provided by the Joint Science Operations Center (JSOC) and the Solar Dynamics Observatory / Helioseismic and Magnetic Imager (SDO/HMI) team. The solar event reports used for label construction are provided by NOAA Space Weather Prediction Center (SWPC).

If you use this repository, please acknowledge JSOC, SDO/HMI, and NOAA SWPC as the original data providers.


## Citation

If you use this dataset or the accompanying scripts, please cite this repository:

```bibtex
@misc{chang2026solarflaredataset,
  title        = {Solar-Flare-Dataset-2019-2025},
  author       = {Chang, Yi},
  year         = {2026},
  howpublished = {\url{https://github.com/ICYEEyudie/Solar-Flare-Dataset-2019-2025}},
  note         = {HMI SHARP magnetogram dataset for solar flare forecasting}
}
```

Please also cite the original data providers and relevant HMI/SHARP documentation when appropriate.

## License

Please specify the license before using or redistributing this dataset.

Suggested options:

- Code: MIT License
- Dataset metadata and documentation: CC BY 4.0
- Raw HMI SHARP data: subject to the usage policies of JSOC and SDO/HMI data providers
