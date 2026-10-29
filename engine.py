"""
engine.py
=========
Universal Spreadsheet & Survey Data Cleaning and Statistical Analysis Engine.
Powers the Streamlit Data Cleaning Studio (`app.py`) and reproducible batch scripts.

Includes:
- Complete forensic reconstruction of KFL/CPE Survey (Andersson & Malm 2025 benchmark)
- Universal Structural & Multi-Table Reconstruction (Auto headers, stacked tables, multi-sheet consolidation, summary row stripping)
- Cell-level parsing (Disguised missing sentinels, currency/percentages/European decimals, Likert 5 & 7 point scales)
- Psychometric Quality Control (Straightliner / careless response detection, Cronbach's alpha + "alpha if item deleted", reverse-coding)
- Statistical Analysis Engine (Correlation matrices, PCA/Factor loadings, OLS multiple regression, group comparisons)
- Dual-Engine Reproducibility (Auto-codebook, Python & R script generation)
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import io
import os
import re
import subprocess
import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# 1. Scale & Item Dictionaries
# ---------------------------------------------------------------------------

# Expanded Universal Likert Scale Dictionary
# Standardized to 0-5 or 1-5 or 1-7 depending on scale type
LIKERT_TEXT_MAP = {
    # Frequency (0 - 5 scale, matching KFL/CPE and classic organizational scales)
    "does not apply at all": 0,
    "stämmer inte alls": 0,
    "never": 0,
    "aldrig": 0,
    "seldom applies": 1,
    "stämmer sällan": 1,
    "rarely": 1,
    "sällan": 1,
    "now and then": 1,
    "då och då": 1,
    "applies sometimes": 2,
    "stämmer ibland": 2,
    "sometimes": 2,
    "ibland": 2,
    "applies fairly often": 3,
    "stämmer ganska ofta": 3,
    "fairly often": 3,
    "ganska ofta": 3,
    "mostly": 3,
    "applies often": 4,
    "stämmer ofta": 4,
    "often": 4,
    "ofta": 4,
    "applies all the time": 5,
    "stämmer hela tiden": 5,
    "all the time": 5,
    "always": 5,
    "alltid": 5,

    # Agreement (1 - 5 and 1 - 7 scale)
    "strongly disagree": 1,
    "instämmer inte alls": 1,
    "helt oense": 1,
    "disagree": 2,
    "instämmer inte": 2,
    "tar delvis avstånd": 2,
    "somewhat disagree": 3,
    "instämmer delvis inte": 3,
    "neither agree nor disagree": 4,
    "neutral": 4,
    "varken eller": 4,
    "somewhat agree": 5,
    "instämmer delvis": 5,
    "agree": 6,
    "instämmer": 6,
    "strongly agree": 7,
    "instämmer helt": 7,
    "helt enig": 7,

    # 5-point Agreement short variants
    "disagree strongly": 1,
    "agree strongly": 5,

    # Satisfaction (1 - 5)
    "very dissatisfied": 1,
    "mycket missnöjd": 1,
    "dissatisfied": 2,
    "missnöjd": 2,
    "neither satisfied nor dissatisfied": 3,
    "varken nöjd eller missnöjd": 3,
    "satisfied": 4,
    "nöjd": 4,
    "very satisfied": 5,
    "mycket nöjd": 5,

    # Quality (1 - 5)
    "very poor": 1,
    "mycket dålig": 1,
    "poor": 2,
    "dålig": 2,
    "fair": 3,
    "godtagbar": 3,
    "good": 4,
    "bra": 4,
    "excellent": 5,
    "utmärkt": 5,

    # Boolean
    "yes": 1,
    "ja": 1,
    "true": 1,
    "sant": 1,
    "no": 0,
    "nej": 0,
    "false": 0,
    "falskt": 0,
}

# Sentinels representing disguised missing values
SENTINEL_VALUES = {
    "n/a", "na", "n.a.", "nan", "none", "null", "-", "--", ".", "...",
    "?", "???", "missing", "saknas", "ej svar", "inte svarat",
    "don't know", "dont know", "vet ej", "vet inte", "unsure", "osäker",
    "999", "-99", "99", "9999", "-999",
}

# Summary row indicators (normalized word roots and prefixes)
SUMMARY_KEYWORDS = [
    "total", "subtotal", "grand total", "sum", "average", "avg", "mean",
    "median", "count", "totalt", "summa", "medeltal", "genomsnitt", "sammanfattning",
    "source", "källa", "note", "notes", "noter", "anmärkning", "copyright", "footnote", "footnotes",
]

# KFL Model Constants
KFL_F1_ITEMS = ["KFL54", "KFL4", "KFL38", "KFL26", "KFL43", "KFL57"]
KFL_F2_RAW_ITEMS = ["KFL86", "KFL84", "KFL90", "KFL89", "KFL78", "KFL74"]
KFL_F3_RAW_ITEMS = ["KFL51", "KFL10", "KFL42", "KFL23", "KFL31", "KFL88"]
CPE_CHANGE_ITEMS = ["CPE4", "CPE5", "CPE7", "CPE9", "CPE15"]
CPE_PRODUCTION_ITEMS = ["CPE3", "CPE8", "CPE10", "CPE11", "CPE13"]
CPE_EMPLOYEE_ITEMS = ["CPE1", "CPE2", "CPE6", "CPE12", "CPE14"]

GENDER_LABELS = {1: "Male", 2: "Female"}
AGE_LABELS = {
    1: "16-25 years", 2: "26-35 years", 3: "36-45 years",
    4: "46-55 years", 5: "56-65 years", 6: "65+ years"
}
EDU_LABELS = {
    1: "Compulsory school", 2: "Upper secondary school",
    3: "Higher education (1-3 years)", 4: "Higher education (4+ years)",
    5: "Other post-secondary / Other"
}
MGR_LABELS = {
    0: "Not a manager (Employee)", 1: "Top manager",
    2: "Middle manager", 3: "First-line / Group manager",
    4: "Other managerial position"
}
EMP_LABELS = {
    1: "Permanent (Full-time)", 2: "Fixed-term / Part-time",
    3: "Project / Hourly / Other"
}
TENURE_LABELS = {
    1: "1-2 years", 2: "3-5 years", 3: "6-8 years", 4: "9-10 years",
    5: "11-15 years", 6: "16-20 years", 7: "21+ years"
}
ORG_SIZE_LABELS = {
    1: "1-9", 2: "10-49", 3: "50-99", 4: "100-199", 5: "200-499",
    6: "500-999", 7: "1000-1999", 8: "2000-4999", 9: "5000+",
    0: "Other / Do not know"
}


# ---------------------------------------------------------------------------
# 2. Universal Parsing & Auto-Repair Utilities
# ---------------------------------------------------------------------------

def clean_text_hygiene(val):
    """Strip leading/trailing whitespace, non-breaking spaces (\xa0), line breaks, and excessive internal spaces."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.integer, np.floating)) and not isinstance(val, bool):
        return val
    s = str(val).replace('\xa0', ' ').replace('\r', ' ').replace('\n', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s if s else np.nan


def fix_excel_date_range(val):
    """
    Restore string ranges like '1-9', '6-10', '11-15' that Excel auto-converted to datetime.
    Also handles ISO datetime strings like '2025-01-09 00:00:00'.
    """
    if pd.isna(val):
        return np.nan
    if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
        return f"{val.month}-{val.day}"
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return np.nan
    m = re.match(r"^20\d\d-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2))}"
    return s


def parse_numeric_cell(val):
    """
    Universal numeric parser:
    Handles currency ($1,200.50, 1.200,50 kr, €45, 150 GBP, CAD 250), percentages (25.5%),
    European comma decimals, space thousands separators (1 234,56), accounting negative
    parentheses ($50.00), and Likert text conversion.
    """
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.number)):
        return float(val)
    if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
        return np.nan

    s = clean_text_hygiene(val)
    if not s:
        return np.nan

    s_low = s.lower()
    if s_low in SENTINEL_VALUES:
        return np.nan

    if s_low in LIKERT_TEXT_MAP:
        return float(LIKERT_TEXT_MAP[s_low])

    # Check for accounting negative format: "(50.00)" or "($1,200)"
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()

    # Remove currency symbols and word tokens (USD, EUR, GBP, SEK, kr, etc.)
    curr_pattern = r'(?:[$€£¥₹₽₩₪₺₫]|\b(?:SEK|USD|EUR|GBP|NOK|DKK|CAD|AUD|CHF|JPY|CNY|kr|krona|kronor)\b)'
    s_clean = re.sub(curr_pattern, '', s, flags=re.IGNORECASE).strip()
    s_clean = s_clean.replace('%', '').strip()

    # Normalize space thousands separators: e.g. "1 234,56" or "1 200"
    s_clean = re.sub(r'(\d)\s+(\d)', r'\1\2', s_clean)

    # Handle European decimal: e.g. "1.234,56" or "12,5" vs US "1,234.56"
    if ',' in s_clean and '.' in s_clean:
        if s_clean.find('.') < s_clean.find(','):
            # European: 1.234,56
            s_clean = s_clean.replace('.', '').replace(',', '.')
        else:
            # US with comma: 1,234.56
            s_clean = s_clean.replace(',', '')
    elif ',' in s_clean:
        # Check if comma is decimal (e.g. "12,5") or thousands (e.g. "1,200")
        parts = s_clean.split(',')
        if len(parts) == 2 and len(parts[1]) != 3:
            s_clean = s_clean.replace(',', '.')
        else:
            s_clean = s_clean.replace(',', '')

    # Leading dot e.g. ".00" -> "0.00"
    if s_clean.startswith('.'):
        s_clean = '0' + s_clean

    try:
        num = float(s_clean)
        return -num if is_negative else num
    except ValueError:
        return np.nan


def clean_numeric_val(val, min_val=None, max_val=None):
    """Legacy wrapper for KFL scale parsing within bounds."""
    v = parse_numeric_cell(val)
    if pd.isna(v):
        return np.nan
    if min_val is not None and v < min_val:
        return np.nan
    if max_val is not None and v > max_val:
        return np.nan
    return v


def make_columns_unique(cols):
    """
    Ensures all column names in a list, index, or DataFrame are unique, string-based, and non-empty.
    If a DataFrame is passed, returns a copy of the DataFrame with unique columns.
    If an Index or List is passed, returns a list of unique column names.
    Example: ['Q1', 'Q1', '', None] -> ['Q1', 'Q1_2', 'Column_3', 'Column_4']
    """
    is_df = isinstance(cols, pd.DataFrame)
    col_iter = cols.columns if is_df else cols

    used = set()
    unique = []
    for i, c in enumerate(col_iter):
        if pd.isna(c) or c is None:
            base = f"Column_{i+1}"
        else:
            cleaned = str(c).strip()
            base = cleaned if cleaned else f"Column_{i+1}"

        cand = base
        count = 2
        while cand in used:
            cand = f"{base}_{count}"
            count += 1

        used.add(cand)
        unique.append(cand)

    if is_df:
        out = cols.copy()
        out.columns = unique
        return out
    return unique


def get_numeric_columns(df):
    """
    Returns list of columns in df that are numeric or can be reliably coerced to numeric.
    """
    numeric_cols = []
    for c in df.columns:
        col = df[c]
        if isinstance(col, pd.Series):
            if pd.api.types.is_numeric_dtype(col):
                numeric_cols.append(c)
            else:
                s_num = pd.to_numeric(col, errors='coerce')
                val_count = int(col.dropna().shape[0])
                if val_count >= 2 and (int(s_num.notna().sum()) / val_count >= 0.7):
                    numeric_cols.append(c)
    return numeric_cols


# ---------------------------------------------------------------------------
# 3. Structural & Layout Reconstruction (Category A)
# ---------------------------------------------------------------------------

def detect_header_row(df_raw, max_scan=10):
    """
    Scans the first `max_scan` rows of an unparsed sheet to find the most probable
    real header row (highest string ratio, uniqueness, fewest empty cells).
    """
    best_row = 0
    best_score = -1.0
    scan_limit = min(max_scan, len(df_raw))

    for r in range(scan_limit):
        row_vals = df_raw.iloc[r].dropna()
        if len(row_vals) == 0:
            continue
        str_count = sum(1 for v in row_vals if isinstance(v, str) and len(v.strip()) > 1)
        unique_ratio = len(set(row_vals)) / max(len(row_vals), 1)
        fill_ratio = len(row_vals) / df_raw.shape[1]
        score = (str_count * 2.0) + (unique_ratio * 3.0) + (fill_ratio * 2.0)
        if score > best_score:
            best_score = score
            best_row = r

    return best_row


def merge_multi_headers(df_raw, header_indices=[0, 1]):
    """
    Combines stacked header rows (e.g. Row 0 = Category, Row 1 = Subcategory)
    into clean, unified column headers.
    """
    if not header_indices or len(header_indices) == 1:
        return df_raw

    cols = []
    for c in range(df_raw.shape[1]):
        parts = []
        for r in header_indices:
            v = df_raw.iloc[r, c]
            if pd.notna(v) and str(v).strip() and not str(v).startswith("Unnamed:"):
                part = clean_text_hygiene(str(v))
                if part and (not parts or part != parts[-1]):
                    parts.append(part)
        col_name = " - ".join(parts) if parts else f"Column_{c+1}"
        cols.append(col_name)

    data = df_raw.iloc[max(header_indices) + 1:].copy().reset_index(drop=True)
    data.columns = make_columns_unique(cols)
    return data


def detect_and_strip_stacked_tables(df_raw):
    """
    Detects repeated embedded header rows and section banners.
    Strips repeated headers and adds a `source_section` column tagging each row.
    """
    d = df_raw.copy()
    col_names = [str(clean_text_hygiene(c)).lower() for c in d.columns if pd.notna(c)]
    
    sections = []
    current_section = "Main"
    rows_to_drop = []

    for idx in d.index:
        non_null = d.iloc[idx].dropna()
        if len(non_null) == 0:
            continue

        # Check for single-cell banner title
        if len(non_null) == 1 and isinstance(non_null.iloc[0], str) and len(non_null.iloc[0].strip()) > 1:
            current_section = clean_text_hygiene(non_null.iloc[0])
            rows_to_drop.append(idx)
            continue

        # Check if row is a repeated header (matching column names)
        row_strs = [clean_text_hygiene(v).lower() for v in non_null if isinstance(v, str)]
        matches = sum(1 for s in row_strs if s in col_names)
        if len(row_strs) >= 3 and matches >= (len(row_strs) * 0.6):
            rows_to_drop.append(idx)
            continue

        sections.append((idx, current_section))

    has_sections = any(sec != "Main" for _, sec in sections) or len(rows_to_drop) > 0
    if has_sections:
        sec_map = dict(sections)
        d["source_section"] = [sec_map.get(i, "Main") for i in d.index]
    if rows_to_drop:
        d = d.drop(index=rows_to_drop).reset_index(drop=True)
    return d


def strip_summary_rows(df_raw):
    """
    Detects and drops accounting/summary rows like 'Total', 'Subtotal', 'Average', 'Sum', etc.
    """
    d = df_raw.copy()
    rows_to_drop = []

    for idx in d.index:
        first_few = [str(clean_text_hygiene(d.iloc[idx, c])).lower() for c in range(min(5, d.shape[1])) if pd.notna(d.iloc[idx, c])]
        for text in first_few:
            if any(k in text for k in SUMMARY_KEYWORDS):
                rows_to_drop.append(idx)
                break

    if rows_to_drop:
        d = d.drop(index=rows_to_drop).reset_index(drop=True)
    return d, len(rows_to_drop)


def consolidate_multisheet_excel(excel_file_or_bytes, sheet_names=None):
    """
    Reads multiple sheets from an Excel workbook and consolidates them into a single dataframe
    with a `source_sheet` column.
    """
    xl = pd.ExcelFile(excel_file_or_bytes)
    targets = sheet_names if sheet_names else xl.sheet_names
    dfs = []

    for name in targets:
        sub_df = pd.read_excel(excel_file_or_bytes, sheet_name=name)
        sub_df["source_sheet"] = name
        dfs.append(sub_df)

    if not dfs:
        return pd.DataFrame()
    res = pd.concat(dfs, ignore_index=True)
    res.columns = make_columns_unique(res.columns)
    return res


# ---------------------------------------------------------------------------
# 4. Forensic X-Ray Inspector & General Cleaner
# ---------------------------------------------------------------------------

def xray_inspect_spreadsheet(df_raw):
    """
    Deep scan of any spreadsheet for:
    - Blank separator rows
    - Section banner rows
    - Subtotal / summary rows
    - Disguised missing sentinels ('N/A', '-', '999')
    - Excel date range auto-conversions
    - Mixed Likert text columns
    - Repeated embedded header rows
    - Exact duplicate rows
    """
    total_rows = len(df_raw)
    total_cols = df_raw.shape[1]

    # 1. Blank rows
    row_na_counts = df_raw.isna().sum(axis=1)
    blank_rows = list(df_raw.index[row_na_counts == total_cols])

    # 2. Section banners
    banner_rows = []
    for idx in df_raw.index:
        non_null = df_raw.iloc[idx].dropna()
        if len(non_null) == 1 and isinstance(non_null.iloc[0], str) and len(non_null.iloc[0].strip()) > 1:
            banner_rows.append((idx, non_null.iloc[0].strip()))

    # 3. Summary / subtotal rows
    summary_rows = []
    for idx in df_raw.index:
        first_few = [str(df_raw.iloc[idx, c]).strip().lower() for c in range(min(5, total_cols)) if pd.notna(df_raw.iloc[idx, c])]
        for text in first_few:
            if any(k in text for k in SUMMARY_KEYWORDS):
                summary_rows.append((idx, text))
                break

    # 4. Excel date range auto-conversions
    date_corruptions = []
    for c_idx in range(total_cols):
        col_name = str(df_raw.columns[c_idx])
        dt_cells = []
        for r_idx in df_raw.index:
            val = df_raw.iloc[r_idx, c_idx]
            if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
                dt_cells.append((r_idx, val))
        if dt_cells:
            sample_val = dt_cells[0][1]
            repaired = f"{sample_val.month}-{sample_val.day}" if hasattr(sample_val, 'month') else str(sample_val)
            date_corruptions.append({
                "column_index": c_idx,
                "column_name": col_name,
                "corrupted_cells_count": len(dt_cells),
                "example_raw": str(sample_val),
                "example_repaired": repaired,
            })

    # 5. Likert & categorical columns
    likert_cols = []
    for c_idx in range(total_cols):
        col_name = str(df_raw.columns[c_idx])
        non_null_vals = df_raw.iloc[:, c_idx].dropna().astype(str).str.strip().str.lower()
        if len(non_null_vals) == 0:
            continue
        matched_likert = non_null_vals.isin(LIKERT_TEXT_MAP.keys()).sum()
        if matched_likert >= 2:
            likert_cols.append({
                "column_index": c_idx,
                "column_name": col_name,
                "matched_count": int(matched_likert),
                "pct_matched": round(100.0 * matched_likert / len(non_null_vals), 1),
                "sample_labels": list(df_raw.iloc[:, c_idx].dropna().unique()[:4]),
            })

    # 6. Disguised missing sentinels
    sentinel_findings = []
    for c_idx in range(total_cols):
        col_name = str(df_raw.columns[c_idx])
        vals = df_raw.iloc[:, c_idx].dropna().astype(str).str.strip().str.lower()
        s_count = vals.isin(SENTINEL_VALUES).sum()
        if s_count > 0:
            found_words = list(vals[vals.isin(SENTINEL_VALUES)].unique())
            sentinel_findings.append({
                "column_name": col_name,
                "sentinel_count": int(s_count),
                "placeholders_found": found_words[:5]
            })

    # 7. Duplicates
    dup_count = int(df_raw.duplicated().sum())

    return {
        "total_rows": total_rows,
        "total_cols": total_cols,
        "blank_rows": blank_rows,
        "banner_rows": banner_rows,
        "summary_rows": summary_rows,
        "date_corruptions": date_corruptions,
        "likert_cols": likert_cols,
        "sentinel_findings": sentinel_findings,
        "duplicate_rows_count": dup_count,
    }


def clean_general_dataframe(df_raw,
                            drop_blanks=True,
                            drop_banners=True,
                            drop_summaries=True,
                            strip_stacked=True,
                            clean_sentinels=True,
                            repair_dates=True,
                            parse_numbers=True,
                            map_likert=True,
                            trim_strings=True,
                            imputation="none",
                            drop_duplicates=False):
    """
    Full automated pipeline applying chosen upgrades to any dataset.
    """
    d = df_raw.copy()
    d.columns = make_columns_unique(d.columns)

    # 1. Drop completely empty rows
    if drop_blanks:
        na_counts = d.isna().sum(axis=1)
        d = d.drop(index=d.index[na_counts == d.shape[1]]).reset_index(drop=True)

    # 2. Strip single-cell banners or handle stacked tables
    if strip_stacked:
        d = detect_and_strip_stacked_tables(d)
        d.columns = make_columns_unique(d.columns)
    elif drop_banners:
        rows_to_drop = []
        for idx in d.index:
            non_null = d.iloc[idx].dropna()
            if len(non_null) == 1 and isinstance(non_null.iloc[0], str) and len(non_null.iloc[0].strip()) > 1:
                rows_to_drop.append(idx)
        if rows_to_drop:
            d = d.drop(index=rows_to_drop).reset_index(drop=True)

    # 3. Strip summary rows (Totals, Averages, Footnotes)
    if drop_summaries:
        d, _ = strip_summary_rows(d)

    # 4. Clean disguised missing sentinels ('N/A', '-', '999')
    if clean_sentinels:
        for c in d.columns:
            col_series = d[c]
            if isinstance(col_series, pd.Series) and (col_series.dtype == object or pd.api.types.is_string_dtype(col_series)):
                mask = col_series.astype(str).str.strip().str.lower().isin(SENTINEL_VALUES)
                d.loc[mask, c] = np.nan

    # 5. String hygiene
    if trim_strings:
        for c in d.columns:
            col_series = d[c]
            if isinstance(col_series, pd.Series) and (col_series.dtype == object or pd.api.types.is_string_dtype(col_series)):
                d[c] = col_series.apply(clean_text_hygiene)

    # 6. Repair Excel date corruptions ('2025-01-09' -> '1-9')
    if repair_dates:
        for c in d.columns:
            col_series = d[c]
            if isinstance(col_series, pd.Series):
                has_dt = any(isinstance(v, (datetime.datetime, datetime.date, pd.Timestamp)) for v in col_series.dropna())
                if has_dt:
                    d[c] = col_series.apply(fix_excel_date_range)

    # 7. Map Likert text labels to numeric
    if map_likert:
        for c in d.columns:
            col_series = d[c]
            if isinstance(col_series, pd.Series) and not pd.api.types.is_numeric_dtype(col_series):
                s_low = col_series.dropna().astype(str).str.strip().str.lower()
                if len(s_low) > 0 and (s_low.isin(LIKERT_TEXT_MAP.keys()).sum() >= 2):
                    d[c] = pd.to_numeric(col_series.apply(parse_numeric_cell), errors='coerce')

    # 8. Smart currency, percentage & number parsing
    if parse_numbers:
        for c in d.columns:
            col_series = d[c]
            if isinstance(col_series, pd.Series) and not pd.api.types.is_numeric_dtype(col_series):
                val_count = int(col_series.dropna().shape[0])
                if val_count > 0:
                    s_num = pd.to_numeric(col_series, errors='coerce')
                    n_valid_num = int(s_num.notna().sum())
                    if n_valid_num >= 2 and (n_valid_num / val_count >= 0.7):
                        d[c] = s_num
                    else:
                        s_parsed = pd.to_numeric(col_series.apply(parse_numeric_cell), errors='coerce')
                        n_valid_parsed = int(s_parsed.notna().sum())
                        if n_valid_parsed >= 2 and (n_valid_parsed / val_count >= 0.7):
                            d[c] = s_parsed

    # Auto-convert purely numeric object columns to proper numeric dtypes
    for c in d.columns:
        col_series = d[c]
        if isinstance(col_series, pd.Series) and not pd.api.types.is_numeric_dtype(col_series):
            try:
                s_num = pd.to_numeric(col_series, errors='raise')
                d[c] = s_num
            except (ValueError, TypeError):
                pass

    # 9. Deduplication
    if drop_duplicates:
        d = d.drop_duplicates().reset_index(drop=True)

    # 10. Missing value imputation
    if imputation in ("median", "mean"):
        for c in d.columns:
            col_series = d[c]
            if isinstance(col_series, pd.Series) and pd.api.types.is_numeric_dtype(col_series):
                fill_val = col_series.median() if imputation == "median" else col_series.mean()
                if pd.notna(fill_val):
                    d[c] = col_series.fillna(fill_val)

    return d


# ---------------------------------------------------------------------------
# 5. Psychometric Quality Control (Category C)
# ---------------------------------------------------------------------------

def compute_cronbach_alpha(df_items, use_pairwise_if_needed=True):
    """
    Compute Cronbach's alpha on a DataFrame of numeric items.
    Supports complete listwise cases with automatic pairwise covariance fallback
    when missing responses exist.
    """
    clean = df_items.apply(pd.to_numeric, errors='coerce')
    clean_listwise = clean.dropna()
    k = clean.shape[1]
    if k < 2:
        return np.nan

    # Try listwise complete if >= 5 rows
    if len(clean_listwise) >= 5:
        item_vars = clean_listwise.var(axis=0, ddof=1).sum()
        total_var = clean_listwise.sum(axis=1).var(ddof=1)
        if total_var > 0 and pd.notna(total_var):
            alpha = (k / (k - 1)) * (1.0 - (item_vars / total_var))
            return float(alpha)

    # Pairwise covariance fallback if listwise drops too many rows
    if use_pairwise_if_needed and len(clean) >= 5:
        cov_matrix = clean.cov()
        item_vars = np.diag(cov_matrix).sum()
        total_var = cov_matrix.values.sum()
        if total_var > 0 and pd.notna(total_var) and item_vars > 0:
            alpha = (k / (k - 1)) * (1.0 - (item_vars / total_var))
            return float(alpha)

    return np.nan


def compute_alpha_with_item_deleted(df_items):
    """
    Computes overall Cronbach's alpha plus item-rest correlation and
    'Alpha if item deleted' for every item in the scale.
    """
    clean = df_items.apply(pd.to_numeric, errors='coerce').dropna()
    k = clean.shape[1]
    if k < 2 or len(clean) < 3:
        # Try with pairwise if rows exist
        raw_items = df_items.apply(pd.to_numeric, errors='coerce')
        if len(raw_items.dropna(how='all')) >= 3 and k >= 2:
            clean = raw_items
        else:
            return None

    overall_alpha = compute_cronbach_alpha(clean)
    results = []

    total_score = clean.sum(axis=1, skipna=True)

    for col in clean.columns:
        rest = clean.drop(columns=[col])
        alpha_dropped = compute_cronbach_alpha(rest)
        item_rest_corr = clean[col].corr(total_score - clean[col])
        results.append({
            "Item": col,
            "Item_Mean": round(clean[col].mean(), 3),
            "Item_SD": round(clean[col].std(), 3),
            "Item_Rest_Correlation": round(item_rest_corr, 3) if pd.notna(item_rest_corr) else np.nan,
            "Alpha_If_Item_Deleted": round(alpha_dropped, 3) if pd.notna(alpha_dropped) else np.nan,
        })

    return {
        "overall_alpha": overall_alpha,
        "n_respondents": len(clean),
        "n_items": k,
        "item_stats": pd.DataFrame(results),
    }


def detect_survey_quality_issues(df_raw, item_cols, straightline_threshold=0.0):
    """
    Identifies careless responders (Straightliners) who entered zero variance
    across survey questions, plus extreme multi-item outliers.
    """
    sub = df_raw[item_cols].apply(pd.to_numeric, errors='coerce')
    row_stds = sub.std(axis=1, skipna=True)
    row_non_na = sub.notna().sum(axis=1)

    min_items = min(3, len(item_cols))
    # Flag straightliners (standard deviation <= straightline_threshold across sufficient items)
    is_straightline = (row_stds <= straightline_threshold) & (row_non_na >= min_items)

    # Multi-item outlier score (Z-score of row means)
    row_means = sub.mean(axis=1, skipna=True)
    m_mean = row_means.mean()
    m_std = row_means.std()
    z_scores = ((row_means - m_mean) / m_std).abs() if m_std > 0 else pd.Series(0, index=df_raw.index)
    is_outlier = z_scores >= 3.0

    return pd.DataFrame({
        "Row_Index": df_raw.index,
        "Items_Answered": row_non_na,
        "Item_Response_SD": row_stds.round(3),
        "Is_Straightliner": is_straightline,
        "Row_Mean": row_means.round(3),
        "Outlier_Z_Score": z_scores.round(2),
        "Is_Extreme_Outlier": is_outlier,
    })


def reverse_code_items(df, item_cols, scale_min=1, scale_max=5):
    """
    Reverses items using formula: (scale_max + scale_min) - x.
    """
    d = df.copy()
    for col in item_cols:
        if col in d.columns:
            rev_name = f"{col}_Rev"
            d[rev_name] = (scale_max + scale_min) - pd.to_numeric(d[col], errors='coerce')
    return d


# ---------------------------------------------------------------------------
# 6. Statistical Analysis Engine (Correlation, Regression, EFA, Group Tests)
# ---------------------------------------------------------------------------

def compute_correlation_matrix(df, cols, method="pearson"):
    """
    Computes bivariate correlation matrix with p-values, significance stars,
    and pairwise sample sizes (reporting valid responses out of total).
    """
    sub = df[cols].apply(pd.to_numeric, errors='coerce')
    corr_df = pd.DataFrame(index=cols, columns=cols, dtype=float)
    pval_df = pd.DataFrame(index=cols, columns=cols, dtype=float)
    stars_df = pd.DataFrame(index=cols, columns=cols, dtype=object)
    n_matrix = pd.DataFrame(index=cols, columns=cols, dtype=object)
    total_n = len(df)

    for c1 in cols:
        for c2 in cols:
            if c1 == c2:
                r, p = 1.0, 0.0
                n_pair = int(sub[c1].notna().sum())
            else:
                v1 = sub[c1]
                v2 = sub[c2]
                mask = v1.notna() & v2.notna()
                n_pair = int(mask.sum())
                if n_pair < 3 or v1[mask].nunique() <= 1 or v2[mask].nunique() <= 1:
                    r, p = np.nan, np.nan
                else:
                    if method == "spearman":
                        r_val, p_val = stats.spearmanr(v1[mask], v2[mask])
                    else:
                        r_val, p_val = stats.pearsonr(v1[mask], v2[mask])
                    r = float(r_val)
                    p = float(p_val)

            corr_df.loc[c1, c2] = round(r, 4) if pd.notna(r) else np.nan
            pval_df.loc[c1, c2] = round(p, 4) if pd.notna(p) else np.nan
            if pd.isna(p):
                stars = ""
            elif p < 0.001:
                stars = "***"
            elif p < 0.01:
                stars = "**"
            elif p < 0.05:
                stars = "*"
            else:
                stars = ""
            stars_df.loc[c1, c2] = f"{r:.3f}{stars}" if pd.notna(r) else "NaN"
            n_matrix.loc[c1, c2] = f"{n_pair} / {total_n} valid"

    return {"corr": corr_df, "pval": pval_df, "formatted": stars_df, "n_matrix": n_matrix}


def compute_linear_regression(df, y_col, x_cols):
    """
    Computes OLS Multiple Linear Regression model with R^2, standard errors, t-stats, and p-values.
    """
    cols = [y_col] + list(x_cols)
    clean = df[cols].apply(pd.to_numeric, errors='coerce').dropna()
    n = len(clean)
    k = len(x_cols)
    if n <= k + 1:
        return None
    if clean[y_col].std(ddof=1) == 0 or clean[y_col].nunique() <= 1:
        return {"error": f"Dependent variable '{y_col}' has zero variance (all responses are identical). OLS regression requires variation in the outcome."}

    y = clean[y_col].values
    X = np.column_stack([np.ones(n), clean[x_cols].values])

    try:
        beta, residuals, rank, s = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return None

    y_pred = X @ beta
    ss_total = np.sum((y - np.mean(y)) ** 2)
    ss_resid = np.sum((y - y_pred) ** 2)
    r_squared = 1.0 - (ss_resid / ss_total) if ss_total > 0 else 0.0
    adj_r_squared = 1.0 - (1.0 - r_squared) * ((n - 1) / (n - k - 1)) if n > k + 1 else r_squared

    sigma2 = ss_resid / (n - k - 1) if n > k + 1 else 0.0
    try:
        var_beta = sigma2 * np.linalg.inv(X.T @ X)
        se = np.sqrt(np.maximum(0, np.diag(var_beta)))
    except Exception:
        se = np.full(k + 1, np.nan)

    t_stats = beta / np.where(se == 0, np.nan, se)
    p_values = [2.0 * (1.0 - stats.t.cdf(np.abs(t), df=n - k - 1)) if pd.notna(t) else np.nan for t in t_stats]

    f_stat = ((ss_total - ss_resid) / k) / (ss_resid / (n - k - 1)) if (k > 0 and n > k + 1 and ss_resid > 0) else np.nan
    f_pval = 1.0 - stats.f.cdf(f_stat, k, n - k - 1) if pd.notna(f_stat) else np.nan

    var_names = ["(Intercept)"] + list(x_cols)
    results_df = pd.DataFrame({
        "Predictor": var_names,
        "Coefficient (B)": np.round(beta, 4),
        "Std Error": np.round(se, 4),
        "t-statistic": np.round(t_stats, 3),
        "p-value": np.round(p_values, 4),
        "Sig": ["***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "")) for p in p_values]
    })

    total_sample = len(df)
    missing_count = total_sample - n
    return {
        "n_obs": n,
        "n_total": total_sample,
        "n_missing": missing_count,
        "obs_summary": f"{n} valid responses out of {total_sample} ({missing_count} excluded due to missing data)",
        "r_squared": round(float(r_squared), 4),
        "adj_r_squared": round(float(adj_r_squared), 4),
        "f_stat": round(float(f_stat), 3) if pd.notna(f_stat) else np.nan,
        "f_pval": round(float(f_pval), 4) if pd.notna(f_pval) else np.nan,
        "table": results_df,
    }


def compute_pca_factor_analysis(df, cols, n_factors=3):
    """
    Computes Principal Component / Factor loadings and explained variance.
    Uses SVD on standardized data for numerical stability, handles singular/collinear matrices,
    and isolates zero-variance (constant) variables.
    """
    if not cols or len(cols) < 2:
        return None

    clean = df[cols].apply(pd.to_numeric, errors='coerce').dropna()
    if len(clean) < 3:
        return None

    # Identify and isolate constant / zero-variance variables
    valid_cols = [c for c in cols if clean[c].std(ddof=1) > 0 and clean[c].nunique() > 1]
    zero_var_cols = [c for c in cols if c not in valid_cols]

    if len(valid_cols) < 2:
        return {
            "error": f"The selected items {zero_var_cols} have zero variance (all respondents entered identical values). Factor extraction requires at least 2 variables with response variance.",
            "zero_var_cols": zero_var_cols,
        }

    # Standardize valid columns (Z = (X - mean) / std)
    clean_valid = clean[valid_cols]
    std_devs = clean_valid.std(ddof=1)
    std_devs = std_devs.replace(0, 1.0)
    Z = (clean_valid - clean_valid.mean()) / std_devs
    Z = Z.fillna(0.0)

    n_samples = len(Z)
    k_vars = len(valid_cols)

    try:
        # SVD on scaled data matrix: Z / sqrt(n - 1)
        # S^2 corresponds to the eigenvalues of the correlation matrix
        U, S, Vt = np.linalg.svd(Z.values / np.sqrt(max(n_samples - 1, 1)), full_matrices=False)
        eigvals = S ** 2
    except Exception:
        try:
            corr_mat = np.nan_to_num(clean_valid.corr().values, nan=0.0)
            corr_mat = (corr_mat + corr_mat.T) / 2.0
            np.fill_diagonal(corr_mat, 1.0)
            eigvals, eigvecs = np.linalg.eigh(corr_mat)
            idx = np.argsort(eigvals)[::-1]
            eigvals = np.maximum(0, eigvals[idx])
            Vt = eigvecs[:, idx].T
        except Exception:
            return None

    n_comps = min(int(n_factors), k_vars, len(eigvals))
    if n_comps < 1:
        return None

    var_explained = (eigvals[:n_comps] / k_vars) * 100.0
    cum_var = np.cumsum(var_explained)

    # Component loadings: eigenvector * sqrt(eigenvalue)
    loadings = Vt[:n_comps, :].T * np.sqrt(np.maximum(0, eigvals[:n_comps]))

    loadings_df = pd.DataFrame(
        loadings.round(3),
        index=valid_cols,
        columns=[f"Factor {i+1}" for i in range(n_comps)]
    )

    scree_df = pd.DataFrame({
        "Component": [f"Factor {i+1}" for i in range(n_comps)],
        "Eigenvalue": eigvals[:n_comps].round(3),
        "Variance Explained (%)": var_explained.round(1),
        "Cumulative Variance (%)": cum_var.round(1),
    })

    warning_msg = None
    if zero_var_cols:
        warning_msg = (
            f"ℹ️ **Constant Items Excluded**: {len(zero_var_cols)} variable(s) with zero response variance "
            f"({', '.join(zero_var_cols)}) were excluded from factor extraction."
        )

    return {
        "loadings": loadings_df,
        "scree": scree_df,
        "n_obs": n_samples,
        "k_items": k_vars,
        "zero_var_cols": zero_var_cols,
        "warning": warning_msg,
    }


def compute_group_comparison(df, group_col, metric_col):
    """
    Computes descriptive breakdown and Independent samples t-test across 2 groups.
    """
    clean = df[[group_col, metric_col]].dropna()
    groups = clean[group_col].unique()
    if len(groups) < 2:
        return None

    g1_vals = clean[clean[group_col] == groups[0]][metric_col].apply(pd.to_numeric, errors='coerce').dropna()
    g2_vals = clean[clean[group_col] == groups[1]][metric_col].apply(pd.to_numeric, errors='coerce').dropna()

    if len(g1_vals) < 2 or len(g2_vals) < 2:
        return None

    t_stat, p_val = stats.ttest_ind(g1_vals, g2_vals, equal_var=False)

    pooled_sd = np.sqrt(
        (((len(g1_vals) - 1) * g1_vals.var()) + ((len(g2_vals) - 1) * g2_vals.var()))
        / (len(g1_vals) + len(g2_vals) - 2)
    )
    d_val = (g1_vals.mean() - g2_vals.mean()) / pooled_sd if pooled_sd > 0 else 0.0

    summary_df = pd.DataFrame([
        {"Group": str(groups[0]), "N": len(g1_vals), "Mean": round(g1_vals.mean(), 3), "SD": round(g1_vals.std(), 3)},
        {"Group": str(groups[1]), "N": len(g2_vals), "Mean": round(g2_vals.mean(), 3), "SD": round(g2_vals.std(), 3)},
    ])

    return {
        "summary": summary_df,
        "t_stat": round(float(t_stat), 3),
        "p_val": round(float(p_val), 4),
        "cohens_d": round(float(d_val), 3),
        "group_names": (str(groups[0]), str(groups[1])),
    }


# ---------------------------------------------------------------------------
# Advanced Statistical Engines: SEM/CFA, Multi-Level HLM, RM-ANOVA, Logistic, Cox
# ---------------------------------------------------------------------------

def compute_sem_cfa(df, model_desc):
    """
    Computes Confirmatory Factor Analysis (CFA) or Structural Equation Modeling (SEM)
    using semopy. Parses model syntax, estimates factor loadings/paths, standard errors,
    z-statistics, p-values, and global goodness-of-fit indices (Chi2, CFI, TLI, RMSEA, AIC, BIC).
    """
    try:
        import semopy
    except ImportError:
        return {"error": "The 'semopy' package is required for Structural Equation Modeling. Please install it via pip or requirements.txt."}

    try:
        import warnings
        tokens = re.findall(r'[a-zA-Z0-9_]+', model_desc)
        vars_needed = [t for t in tokens if t in df.columns]
        if not vars_needed:
            return {"error": "No matching variables found in the model syntax. Ensure indicator and manifest variable names match dataframe columns."}

        clean = df[vars_needed].apply(pd.to_numeric, errors='coerce').dropna()
        if len(clean) < 5:
            return {"error": f"Insufficient complete cases ({len(clean)} found). Structural equation modeling requires at least 5 complete cases."}

        # Check for zero variance
        zero_vars = [c for c in vars_needed if clean[c].std(ddof=1) == 0 or clean[c].nunique() <= 1]
        if zero_vars:
            return {"error": f"Variable(s) {zero_vars} have zero variance. Indicator variables must exhibit variation across respondents."}

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = semopy.Model(model_desc)
            model.fit(clean)
            estimates = model.inspect()

        estimates = estimates.rename(columns={
            "lval": "Outcome / Indicator",
            "op": "Path",
            "rval": "Predictor / Factor",
            "Estimate": "Estimate (B)",
            "Std. Err": "Std. Error",
            "z-value": "z-statistic",
            "p-value": "p-value",
        })

        # Calculate standard fit indices
        fit_dict = {}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                stats_raw = semopy.calc_stats(model)
                for col in stats_raw.columns:
                    val = stats_raw[col].iloc[0]
                    if pd.notna(val):
                        fit_dict[col] = round(float(val), 4)
        except Exception:
            pass

        return {
            "estimates": estimates,
            "fit_stats": fit_dict,
            "n_obs": len(clean),
            "manifest_vars": vars_needed,
            "is_success": True
        }
    except Exception as e:
        return {"error": f"SEM/CFA estimation error: {str(e)}"}


def compute_multilevel_hlm(df, y_col, fixed_cols, group_col, random_slopes=None):
    """
    Computes Multi-Level Hierarchical Linear Modeling (HLM / Mixed-Effects Linear Model)
    using statsmodels MixedLM. Estimates fixed effect coefficients with 95% CIs,
    random intercept variance (tau_00), residual variance (sigma^2), and Intraclass Correlation (ICC).
    Safeguards against group/predictor overlap, collinearity, and patsy special characters.
    """
    try:
        import statsmodels.api as sm
        from statsmodels.regression.mixed_linear_model import MixedLM
        import warnings
    except ImportError:
        return {"error": "The 'statsmodels' package is required for Multi-Level Hierarchical Linear Modeling."}

    try:
        if y_col not in df.columns:
            return {"error": f"Dependent variable '{y_col}' was not found in the dataset."}
        if group_col not in df.columns:
            return {"error": f"Grouping variable '{group_col}' was not found in the dataset."}
        missing_x = [c for c in fixed_cols if c not in df.columns]
        if missing_x:
            return {"error": f"Predictor column(s) {missing_x} were not found in the dataset."}

        # Guard against predictor and cluster overlap
        if group_col in fixed_cols:
            return {
                "error": (
                    f"Selection conflict: The grouping/cluster variable '{group_col}' cannot also be included in Fixed Predictors (X). "
                    f"In hierarchical linear modeling, the grouping variable defines the Level-2 clusters (random intercepts) and cannot predict itself. "
                    f"Please remove '{group_col}' from Fixed Predictors."
                )
            }

        if y_col in fixed_cols:
            return {"error": f"Dependent variable '{y_col}' cannot also be included as a predictor (X)."}
        if y_col == group_col:
            return {"error": f"Dependent variable '{y_col}' cannot also be the grouping cluster."}

        valid_fixed = [c for c in fixed_cols if c != group_col and c != y_col and c in df.columns]
        if not valid_fixed:
            return {"error": "Please select at least 1 predictor (X) distinct from the outcome and grouping variable."}

        # Safe single-column extraction preventing duplicate column DataFrame slices
        clean = pd.DataFrame(index=df.index)
        clean[y_col] = pd.to_numeric(df[y_col], errors="coerce")
        for c in valid_fixed:
            clean[c] = pd.to_numeric(df[c], errors="coerce")
        clean[group_col] = df[group_col].astype(str).str.strip()
        clean = clean.dropna()

        if len(clean) < 10:
            return {"error": f"Insufficient complete rows ({len(clean)} found) after excluding missing data. At least 10 complete cases required."}

        n_groups = clean[group_col].nunique()
        if n_groups < 2:
            return {"error": f"Grouping variable '{group_col}' has only {n_groups} group/cluster in the valid sample. At least 2 groups required to compute between-group variance."}

        zero_x = [c for c in valid_fixed if clean[c].std(ddof=1) == 0 or clean[c].nunique() <= 1]
        if zero_x:
            return {"error": f"Predictor(s) {zero_x} have zero variance (identical values for all respondents). Predictors must vary."}

        # Use patsy Q("col") to protect against spaces, dots, dashes, parentheses
        formula = f'Q("{y_col}") ~ ' + ' + '.join([f'Q("{c}")' for c in valid_fixed])
        re_formula = None
        if random_slopes:
            valid_slopes = [s for s in random_slopes if s in valid_fixed]
            if valid_slopes:
                re_formula = ' + '.join([f'Q("{s}")' for s in valid_slopes])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = MixedLM.from_formula(formula, clean, groups=clean[group_col], re_formula=re_formula)
            try:
                fit = model.fit(reml=True, method=["lbfgs", "bfgs"])
            except np.linalg.LinAlgError:
                return {
                    "error": (
                        "Multi-level model estimation failed due to a Singular Matrix (extreme collinearity). "
                        "One or more predictors have zero variance within clusters or are redundant with the cluster definition. "
                        "Please remove collinear predictors or select a different Level-2 grouping variable."
                    )
                }
            except Exception as fit_err:
                if "Singular matrix" in str(fit_err) or "singular" in str(fit_err).lower():
                    return {
                        "error": (
                            "Multi-level model estimation failed due to a Singular Matrix (extreme collinearity). "
                            "One or more predictors have zero variance within clusters or are redundant with the cluster definition. "
                            "Please remove collinear predictors or select a different Level-2 grouping variable."
                        )
                    }
                try:
                    fit = model.fit(reml=True)
                except Exception as fit_err2:
                    return {"error": f"Multi-level model optimization failed: {str(fit_err2)}"}

        fe_params = fit.fe_params
        bse = fit.bse_fe
        tvalues = fit.tvalues
        pvalues = fit.pvalues
        conf_int = fit.conf_int()

        rows = []
        for term in fe_params.index:
            p = float(pvalues.get(term, np.nan))
            stars = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))
            clean_term = term.replace('Q("', '').replace('")', '')
            rows.append({
                "Parameter": clean_term,
                "Estimate (B)": round(float(fe_params[term]), 4),
                "Std. Error": round(float(bse.get(term, np.nan)), 4),
                "z-value": round(float(tvalues.get(term, np.nan)), 3),
                "p-value": round(p, 4) if pd.notna(p) else np.nan,
                "Sig": stars,
                "95% CI Lower": round(float(conf_int.loc[term, 0]), 4) if term in conf_int.index else np.nan,
                "95% CI Upper": round(float(conf_int.loc[term, 1]), 4) if term in conf_int.index else np.nan,
            })
        fe_df = pd.DataFrame(rows)

        group_var = float(fit.cov_re.iloc[0, 0]) if hasattr(fit, 'cov_re') and fit.cov_re.shape[0] > 0 else 0.0
        resid_var = float(fit.scale)
        total_var = group_var + resid_var
        icc = round(group_var / total_var, 4) if total_var > 0 else 0.0

        re_df = pd.DataFrame([
            {"Component": f"Between-Group Variance (τ₀₀: {group_col})", "Variance": round(group_var, 4), "Std. Dev": round(np.sqrt(max(0, group_var)), 4)},
            {"Component": "Residual / Within-Group Variance (σ²)", "Variance": round(resid_var, 4), "Std. Dev": round(np.sqrt(max(0, resid_var)), 4)},
            {"Component": "Total Variance (τ₀₀ + σ²)", "Variance": round(total_var, 4), "Std. Dev": round(np.sqrt(max(0, total_var)), 4)},
        ])

        return {
            "fixed_effects": fe_df,
            "random_effects": re_df,
            "icc": icc,
            "n_obs": int(fit.nobs),
            "n_groups": int(n_groups),
            "aic": round(float(fit.aic), 2) if hasattr(fit, 'aic') and pd.notna(fit.aic) else "-",
            "bic": round(float(fit.bic), 2) if hasattr(fit, 'bic') and pd.notna(fit.bic) else "-",
            "converged": bool(fit.converged),
            "is_success": True
        }
    except Exception as e:
        return {"error": f"Multi-level model estimation failed: {str(e)}"}



def compute_repeated_measures_anova(df, time_cols, between_col=None):
    """
    Computes Repeated-Measures ANOVA or Mixed Repeated/Between ANOVA using Pingouin.
    Reports ANOVA F-table, partial eta-squared (np2), Mauchly's test of sphericity,
    Greenhouse-Geisser / Huynh-Feldt corrections, and post-hoc Bonferroni pairwise comparisons.
    """
    try:
        import pingouin as pg
    except ImportError:
        return {"error": "The 'pingouin' package is required for Repeated-Measures ANOVA."}

    try:
        import warnings
        missing_t = [c for c in time_cols if c not in df.columns]
        if missing_t:
            return {"error": f"Repeated measure column(s) {missing_t} were not found in the dataset."}
        if len(time_cols) < 2:
            return {"error": "Repeated-Measures ANOVA requires at least 2 measurement occasions (e.g. Pre-test, Post-test)."}

        if between_col:
            if between_col not in df.columns:
                return {"error": f"Between-subject column '{between_col}' was not found in the dataset."}

        clean_cols = list(time_cols) + ([between_col] if between_col else [])
        clean = df[clean_cols].copy()
        for c in time_cols:
            clean[c] = pd.to_numeric(clean[c], errors='coerce')
        if between_col:
            clean[between_col] = clean[between_col].astype(str).str.strip()
        clean = clean.dropna().reset_index(drop=True)

        if len(clean) < 3:
            return {"error": f"Insufficient complete cases ({len(clean)} found) for Repeated-Measures ANOVA. At least 3 complete cases required."}

        if between_col:
            n_between = clean[between_col].nunique()
            if n_between < 2:
                return {"error": f"Between-subject factor '{between_col}' has only {n_between} group in the clean sample. Mixed ANOVA requires at least 2 distinct groups (e.g. Treatment vs Control). Choose '(None - Pure Within-Subject Design)' for a single cohort."}

        clean["subject_id"] = [f"Subj_{i+1}" for i in range(len(clean))]
        long_df = clean.melt(
            id_vars=["subject_id"] + ([between_col] if between_col else []),
            value_vars=time_cols,
            var_name="Measurement_Time",
            value_name="Score"
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if between_col:
                aov = pg.mixed_anova(data=long_df, dv="Score", within="Measurement_Time", between=between_col, subject="subject_id")
            else:
                aov = pg.rm_anova(data=long_df, dv="Score", within="Measurement_Time", subject="subject_id", detailed=True)

        # Sphericity test
        spher_res = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                spher = pg.sphericity(data=long_df, dv="Score", within="Measurement_Time", subject="subject_id")
                spher_res = {
                    "sphericity_w": round(float(spher[0]), 4),
                    "chi2": round(float(spher[1]), 4),
                    "df": int(spher[2]),
                    "p_value": round(float(spher[3]), 4),
                    "sphericity_met": bool(spher[4])
                }
        except Exception:
            pass

        # Pairwise post-hoc comparisons
        posthoc_df = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                posthoc = pg.pairwise_tests(data=long_df, dv="Score", within="Measurement_Time", subject="subject_id", padjust="bonf")
                if isinstance(posthoc, pd.DataFrame):
                    posthoc_df = posthoc.round(4)
        except Exception:
            pass

        return {
            "aov_table": aov.round(4) if isinstance(aov, pd.DataFrame) else aov,
            "sphericity": spher_res,
            "posthoc": posthoc_df,
            "n_subjects": len(clean),
            "time_levels": list(time_cols),
            "between_col": between_col,
            "is_success": True
        }
    except Exception as e:
        return {"error": f"Repeated-Measures ANOVA failed: {str(e)}"}


def compute_logistic_regression(df, y_col, x_cols):
    """
    Computes Binary Logistic Regression using statsmodels Logit.
    Supports numeric, string, or boolean binary outcomes (e.g. Yes/No, Manager/Employee, 0/1).
    Calculates Odds Ratios (e^B) with 95% CIs, Wald z-statistics, p-values,
    McFadden's Pseudo R-squared, Log-Likelihood, and classification accuracy.
    """
    try:
        import statsmodels.api as sm
        from statsmodels.discrete.discrete_model import Logit
    except ImportError:
        return {"error": "The 'statsmodels' package is required for Binary Logistic Regression."}

    try:
        import warnings
        if y_col not in df.columns:
            return {"error": f"Dependent variable '{y_col}' was not found in the dataset."}
        missing_x = [c for c in x_cols if c not in df.columns]
        if missing_x:
            return {"error": f"Predictor variable(s) {missing_x} were not found in the dataset."}

        y_raw = df[y_col].dropna()
        unique_y = y_raw.unique()
        if len(unique_y) != 2:
            return {
                "error": f"Dependent variable '{y_col}' must be strictly binary (2 unique categories). Found {len(unique_y)} unique values: {list(unique_y[:10])}."
            }

        sorted_vals = sorted(list(unique_y), key=lambda v: str(v))
        ref_val, target_val = sorted_vals[0], sorted_vals[1]

        sub = pd.DataFrame(index=df.index)
        sub["_Y_"] = df[y_col].map({ref_val: 0, target_val: 1})
        for c in x_cols:
            sub[c] = pd.to_numeric(df[c], errors="coerce")

        clean = sub.dropna()
        if len(clean) < 10:
            return {"error": f"Insufficient complete rows ({len(clean)} found) for Logistic Regression. At least 10 complete cases required."}

        y_clean = clean["_Y_"]
        if y_clean.nunique() < 2:
            return {"error": f"After excluding missing values in predictors, outcome '{y_col}' contains only class '{ref_val if y_clean.iloc[0] == 0 else target_val}'. Both categories must have valid predictor data."}

        valid_x = [c for c in x_cols if clean[c].std(ddof=1) > 0 and clean[c].nunique() > 1]
        if not valid_x:
            return {"error": "All selected predictors have zero variance. Predictors must exhibit variation."}

        X = sm.add_constant(clean[valid_x])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logit_model = Logit(y_clean, X)
            fit = logit_model.fit(disp=False, maxiter=100)

        params = fit.params
        bse = fit.bse
        zvalues = fit.tvalues
        pvalues = fit.pvalues
        conf_int = fit.conf_int()

        rows = []
        for term in params.index:
            coef = float(params[term])
            se = float(bse.get(term, np.nan))
            z = float(zvalues.get(term, np.nan))
            p = float(pvalues.get(term, np.nan))
            ci_low = float(conf_int.loc[term, 0]) if term in conf_int.index else np.nan
            ci_high = float(conf_int.loc[term, 1]) if term in conf_int.index else np.nan

            odds_ratio = np.exp(coef) if np.abs(coef) < 700 else np.nan
            or_low = np.exp(ci_low) if np.abs(ci_low) < 700 else np.nan
            or_high = np.exp(ci_high) if np.abs(ci_high) < 700 else np.nan
            stars = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))

            rows.append({
                "Predictor": term,
                "Coefficient (B)": round(coef, 4),
                "Std. Error": round(se, 4),
                "Wald z": round(z, 3),
                "p-value": round(p, 4),
                "Sig": stars,
                "Odds Ratio (e^B)": round(odds_ratio, 4) if pd.notna(odds_ratio) else "-",
                "95% CI Lower (OR)": round(or_low, 4) if pd.notna(or_low) else "-",
                "95% CI Upper (OR)": round(or_high, 4) if pd.notna(or_high) else "-",
            })

        res_df = pd.DataFrame(rows)

        # Classification accuracy
        y_pred = (fit.predict(X) >= 0.5).astype(int)
        accuracy = round(100.0 * (y_pred == y_clean).mean(), 1)

        n_ref = int((y_clean == 0).sum())
        n_target = int((y_clean == 1).sum())

        return {
            "table": res_df,
            "pseudo_r2": round(float(fit.prsquared), 4) if hasattr(fit, 'prsquared') else "-",
            "log_likelihood": round(float(fit.llf), 2),
            "lr_pvalue": round(float(fit.llr_pvalue), 4) if hasattr(fit, 'llr_pvalue') else "-",
            "accuracy": accuracy,
            "n_obs": int(fit.nobs),
            "target_mapping": {
                "reference": str(ref_val),
                "target": str(target_val),
                "n_ref": n_ref,
                "n_target": n_target,
            },
            "is_success": True
        }
    except Exception as e:
        return {"error": f"Logistic Regression failed: {str(e)}"}


def compute_cox_survival(df, duration_col, event_col, covariates):
    """
    Computes Cox Proportional Hazards Survival Analysis using lifelines.
    Supports numeric, string, or boolean event indicators.
    Reports Hazard Ratios (e^B) with 95% CIs, Wald z, p-values, Concordance Index (C-index),
    partial AIC, and log-likelihood.
    """
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return {"error": "The 'lifelines' package is required for Cox Proportional Hazards Survival Analysis."}

    try:
        import warnings
        if duration_col not in df.columns:
            return {"error": f"Duration column '{duration_col}' was not found in the dataset."}
        if event_col not in df.columns:
            return {"error": f"Event column '{event_col}' was not found in the dataset."}
        missing_cov = [c for c in covariates if c not in df.columns]
        if missing_cov:
            return {"error": f"Covariate column(s) {missing_cov} were not found in the dataset."}

        ev_raw = df[event_col].dropna()
        unique_ev = ev_raw.unique()
        if len(unique_ev) < 2:
            return {"error": f"Event column '{event_col}' must contain both events and censored cases. Found only 1 unique value: {list(unique_ev)}."}
        if len(unique_ev) > 2:
            return {"error": f"Event column '{event_col}' must be strictly binary. Found {len(unique_ev)} categories: {list(unique_ev[:10])}."}

        sorted_ev = sorted(list(unique_ev), key=lambda v: str(v))
        censored_val, event_val = sorted_ev[0], sorted_ev[1]

        sub = pd.DataFrame(index=df.index)
        sub["_duration_"] = pd.to_numeric(df[duration_col], errors="coerce")
        sub["_event_"] = df[event_col].map({censored_val: 0, event_val: 1})
        for c in covariates:
            sub[c] = pd.to_numeric(df[c], errors="coerce")

        clean = sub.dropna()
        clean = clean[clean["_duration_"] > 0]

        if len(clean) < 10:
            return {"error": f"Insufficient complete cases ({len(clean)} found) with duration > 0 for Cox Survival Analysis. At least 10 complete cases required."}

        n_events = int(clean["_event_"].sum())
        if n_events == 0:
            return {"error": f"No events observed in the valid sample ({censored_val}=0, {event_val}=1). Survival models require at least 1 observed event."}
        if n_events == len(clean):
            return {"error": f"All {len(clean)} cases experienced the event (0 censored cases). Survival analysis requires censored observations."}

        valid_covs = [c for c in covariates if clean[c].std(ddof=1) > 0 and clean[c].nunique() > 1]
        if not valid_covs:
            return {"error": "All selected covariates have zero variance. Covariates must exhibit variation."}

        fit_df = clean[["_duration_", "_event_"] + valid_covs].copy()
        cph = CoxPHFitter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cph.fit(fit_df, duration_col="_duration_", event_col="_event_")

        summary = cph.summary.reset_index().rename(columns={"covariate": "Covariate"})
        p_vals = summary["p"]
        stars = ["***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "")) for p in p_vals]

        summary_formatted = pd.DataFrame({
            "Covariate": summary["Covariate"],
            "Coefficient (B)": summary["coef"].round(4),
            "Hazard Ratio (e^B)": summary["exp(coef)"].round(4),
            "Std. Error": summary["se(coef)"].round(4),
            "z-value": summary["z"].round(3),
            "p-value": summary["p"].round(4),
            "Sig": stars,
            "95% CI Lower (HR)": summary["exp(coef) lower 95%"].round(4),
            "95% CI Upper (HR)": summary["exp(coef) upper 95%"].round(4),
        })

        n_censored = len(clean) - n_events

        return {
            "table": summary_formatted,
            "concordance_index": round(float(cph.concordance_index_), 4),
            "aic": round(float(cph.AIC_partial_), 2),
            "log_likelihood": round(float(cph.log_likelihood_), 2),
            "n_obs": int(len(clean)),
            "n_events": n_events,
            "n_censored": n_censored,
            "event_mapping": {
                "censored": str(censored_val),
                "event": str(event_val),
            },
            "is_success": True
        }
    except Exception as e:
        return {"error": f"Cox Proportional Hazards estimation failed: {str(e)}"}



def replicate_thesis_table_3(df_thesis):
    """
    Replicates Andersson & Malm (2025) Table 3 Convergent Validity Correlation Analyses (N = 122).
    """
    pairs = [
        ("KFL Total & CPE Change/Employee (CE)", "KFL_Total_18", "CPE_CE_Combined_Mean", 0.269, 0.271),
        ("KFL Total & CPE Production (P)", "KFL_Total_18", "CPE_Production_Mean", 0.301, 0.330),
        ("Factor 1 (Idea-Support) & CPE Employee (E)", "KFL_F1_IdeaSupport", "CPE_Employee_Mean", 0.156, 0.307),
        ("Factor 1 (Idea-Support) & CPE CE Combined", "KFL_F1_IdeaSupport", "CPE_CE_Combined_Mean", 0.095, 0.317),
        ("Factor 1 & Factor 2 (Autonomy)", "KFL_F1_IdeaSupport", "KFL_F2_Autonomy", 0.377, 0.360),
        ("Factor 2 (Autonomy) & CPE Production (P)", "KFL_F2_Autonomy", "CPE_Production_Mean", 0.411, 0.407),
        ("Factor 3 (Conservatism) & CPE Change (C)", "KFL_F3_Conservatism", "CPE_Change_Mean", -0.534, -0.502),
        ("Factor 3 (Conservatism) & CPE CE Combined", "KFL_F3_Conservatism", "CPE_CE_Combined_Mean", -0.488, -0.461),
        ("Factor 3 (Conservatism) & CPE Production (P)", "KFL_F3_Conservatism", "CPE_Production_Mean", -0.302, -0.258),
    ]

    rows = []
    for label, col1, col2, th_r, th_rho in pairs:
        if col1 in df_thesis.columns and col2 in df_thesis.columns:
            sub = df_thesis[[col1, col2]].dropna()
            if len(sub) >= 5:
                r, p_r = stats.pearsonr(sub[col1], sub[col2])
                rho, p_rho = stats.spearmanr(sub[col1], sub[col2])
                star_r = "***" if p_r < 0.001 else ("**" if p_r < 0.01 else ("*" if p_r < 0.05 else ""))
                star_rho = "***" if p_rho < 0.001 else ("**" if p_rho < 0.01 else ("*" if p_rho < 0.05 else ""))
                rows.append({
                    "Scale Dimension Pair": label,
                    "Replicated Pearson r": f"{r:+.3f}{star_r}",
                    "Published Pearson r": f"{th_r:+.3f}",
                    "Replicated Spearman ρ": f"{rho:+.3f}{star_rho}",
                    "Published Spearman ρ": f"{th_rho:+.3f}",
                    "Sample Size N": len(sub),
                })

    return pd.DataFrame(rows)


def generate_r_analysis_script(filename, num_cols, factor_dict=None, y_col=None, x_cols=None):
    """
    Generates a complete, publication-ready R analysis script (`survey_analysis.R`).
    Uses tidyverse, psych (alpha, describe, fa), lavaan (CFA), and corrplot.
    """
    scale_items_str = ', '.join(f'"{c}"' for c in num_cols[:min(18, len(num_cols))])
    r_script = f'''# ==============================================================================
# R Statistical & Psychometric Analysis Script
# Target Dataset: {filename}
# Generated by: Dycson Cleaning Studio
# ==============================================================================

# 1. Package Installation and Loading
required_packages <- c("tidyverse", "psych", "lavaan", "corrplot")
new_packages <- required_packages[!(required_packages %in% installed.packages()[, "Package"])]
if (length(new_packages) > 0) install.packages(new_packages)
invisible(lapply(required_packages, library, character.only = TRUE))

cat("\\n=======================================================\\n")
cat("  Dycson Cleaning Studio: R Statistical Analysis Engine  \\n")
cat("=======================================================\\n\\n")

# 2. Data Loading
data_file <- "{filename}"
cat("Loading cleaned dataset:", data_file, "\\n")
df <- read.csv(data_file, check.names = FALSE, na.strings = c("NA", "NaN", "", "."))
cat("Dataset Dimensions:", nrow(df), "rows by", ncol(df), "columns\\n\\n")

# 3. Scale Items Definition
scale_items <- c({scale_items_str})
cat("Scale items for psychometric evaluation:\\n")
print(scale_items)
cat("\\n")

# Subset numeric items
sub_items <- df[, scale_items, drop = FALSE]
sub_items <- data.frame(lapply(sub_items, as.numeric))

# 4. Comprehensive Descriptive Statistics & Normality (psych::describe)
cat("-------------------------------------------------------\\n")
cat("4. Descriptive Statistics & Normality Assessment\\n")
cat("-------------------------------------------------------\\n")
desc_stats <- describe(sub_items)
print(round(desc_stats[, c("n", "mean", "sd", "median", "skew", "kurtosis", "se")], 3))
cat("\\n")

# 5. Internal Consistency: Cronbach's Alpha (psych::alpha)
cat("-------------------------------------------------------\\n")
cat("5. Reliability Analysis (Cronbach's Alpha & Item-Rest)\\n")
cat("-------------------------------------------------------\\n")
if (ncol(sub_items) >= 2) {{
  alpha_res <- psych::alpha(sub_items, check.keys = TRUE)
  cat("Overall Raw Alpha:", round(alpha_res$total$raw_alpha, 3), "\\n")
  cat("Standardized Alpha:", round(alpha_res$total$std.alpha, 3), "\\n\\n")
  cat("Item-Level Statistics & Alpha if Item Deleted:\\n")
  print(round(alpha_res$alpha.drop[, c("raw_alpha", "std.alpha")], 3))
  print(round(alpha_res$item.stats[, c("r.cor", "r.drop", "mean", "sd")], 3))
}}
cat("\\n")

# 6. Bivariate Correlation Matrix
cat("-------------------------------------------------------\\n")
cat("6. Correlation Matrix (Pearson)\\n")
cat("-------------------------------------------------------\\n")
if (ncol(sub_items) >= 2) {{
  corr_mat <- cor(sub_items, use = "pairwise.complete.obs")
  print(round(corr_mat, 3))
}}
cat("\\n")
'''
    if factor_dict:
        model_lines = []
        for f_name, items in factor_dict.items():
            model_lines.append(f"{f_name} =~ {' + '.join(items)}")
        cfa_model_str = "\n".join(model_lines)
        r_script += f'''
# 7. Confirmatory Factor Analysis (lavaan::cfa)
cat("-------------------------------------------------------\\n")
cat("7. Confirmatory Factor Analysis (CFA via lavaan)\\n")
cat("-------------------------------------------------------\\n")
cfa_model <- '
{cfa_model_str}
'
tryCatch({{
  fit_cfa <- cfa(cfa_model, data = df, missing = "fiml")
  cat("CFA Fit Summary:\\n")
  summary(fit_cfa, fit.measures = TRUE, standardized = TRUE)
}}, error = function(e) {{
  cat("CFA Error:", conditionMessage(e), "\\n")
}})
cat("\\n")
'''

    if y_col and x_cols:
        r_script += f'''
# 8. Multiple Linear Regression Model
cat("-------------------------------------------------------\\n")
cat("8. Multiple Linear Regression Analysis\\n")
cat("-------------------------------------------------------\\n")
formula_str <- "{y_col} ~ {' + '.join(x_cols)}"
cat("Regression Formula:", formula_str, "\\n")
reg_model <- lm(as.formula(formula_str), data = df)
print(summary(reg_model))
cat("\\n")
'''

    r_script += '''
cat("=======================================================\\n")
cat("  Analysis Complete! Generated by Dycson Cleaning Studio \\n")
cat("=======================================================\\n")
'''
    return r_script


def run_r_script_if_available(r_script_content, workdir=None):
    """
    Checks if Rscript is available and executes the script, returning output.
    """
    try:
        check = subprocess.run(["Rscript", "--version"], capture_output=True, text=True, timeout=5, shell=True)
        if check.returncode != 0:
            return {"available": False, "message": "Rscript command returned non-zero code. R may not be installed in system PATH."}
    except Exception as e:
        return {"available": False, "message": f"R runtime (Rscript) is not detected on this machine: {str(e)}"}

    script_path = os.path.join(workdir or ".", "temp_survey_analysis.R")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(r_script_content)

    try:
        res = subprocess.run(["Rscript", script_path], capture_output=True, text=True, timeout=60, shell=True)
        return {"available": True, "stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}
    except Exception as ex:
        return {"available": True, "stdout": "", "stderr": str(ex), "exit_code": -1}



# ---------------------------------------------------------------------------
# 6. Auto-Codebook & Reproducible Python Script Generation
# ---------------------------------------------------------------------------

def generate_non_response_audit_report(df):
    """
    Generates comprehensive item-level and case-level non-response & missing data audit.
    Reports exact valid responses out of total (e.g. '5 valid responses out of 10'),
    percentage response rate, and missing count.
    """
    df_copy = df.copy()
    df_copy.columns = make_columns_unique(df_copy.columns)
    total_rows = len(df_copy)
    total_cols = len(df_copy.columns)

    # 1. Item-Level Audit
    item_rows = []
    for c_idx in range(total_cols):
        col = df_copy.columns[c_idx]
        s = df_copy.iloc[:, c_idx]
        n_valid = int(s.notna().sum())
        n_missing = int(s.isna().sum())
        resp_rate = round(100.0 * n_valid / max(total_rows, 1), 1)
        missing_rate = round(100.0 * n_missing / max(total_rows, 1), 1)

        if n_missing == 0:
            status = "🟢 Complete (100%)"
        elif n_valid == 0:
            status = "🔴 Zero Responses (100% Missing)"
        elif resp_rate >= 80.0:
            status = f"🟢 High Response ({resp_rate}%)"
        elif resp_rate >= 50.0:
            status = f"🟡 Moderate Response ({resp_rate}%)"
        else:
            status = f"🟠 Low Response ({resp_rate}%)"

        item_rows.append({
            "Variable / Question": str(col),
            "Valid Responses": n_valid,
            "Not Reported / Missing": n_missing,
            "Total Surveyed": total_rows,
            "Response Count Summary": f"{n_valid} of {total_rows} responded",
            "Response Rate (%)": resp_rate,
            "Missing Rate (%)": missing_rate,
            "Data Quality Status": status,
        })
    df_items = pd.DataFrame(item_rows)

    # 2. Case-Level (Respondent) Audit
    case_rows = []
    for idx in range(total_rows):
        row = df_copy.iloc[idx]
        n_answered = int(row.notna().sum())
        n_unanswered = int(row.isna().sum())
        case_rate = round(100.0 * n_answered / max(total_cols, 1), 1)

        if n_unanswered == 0:
            pattern = "🟢 Complete (100%)"
        elif n_answered == 0:
            pattern = "🔴 Zero Responses (Dropped Out)"
        elif case_rate >= 80.0:
            pattern = f"🟢 High Completion ({case_rate}%)"
        else:
            pattern = f"🟡 Partial Non-Response ({case_rate}%)"

        resp_label = f"Respondent #{idx + 1}"
        for id_candidate in ["thesis_id", "respondent_id", "Respondent_ID", "ID", "id", "Subject", "subject"]:
            if id_candidate in df_copy.columns:
                val = row[id_candidate]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                if pd.notna(val) and str(val).strip():
                    resp_label = str(val).strip()
                    break

        case_rows.append({
            "Respondent": resp_label,
            "Questions Answered": n_answered,
            "Questions Skipped / Missing": n_unanswered,
            "Total Questions": total_cols,
            "Completion Summary": f"{n_answered} of {total_cols} answered",
            "Completion Rate (%)": case_rate,
            "Respondent Pattern": pattern,
        })
    df_cases = pd.DataFrame(case_rows)

    # 3. Overall Matrix Summary
    total_cells = total_rows * total_cols
    total_valid_cells = int(df_copy.notna().values.sum()) if total_cells > 0 else 0
    total_missing_cells = total_cells - total_valid_cells
    overall_response_rate = round(100.0 * total_valid_cells / max(total_cells, 1), 1)

    complete_respondents = int((df_copy.isna().sum(axis=1) == 0).sum()) if total_rows > 0 else 0
    partial_respondents = int(((df_copy.isna().sum(axis=1) > 0) & (df_copy.notna().sum(axis=1) > 0)).sum()) if total_rows > 0 else 0
    dropout_respondents = int((df_copy.notna().sum(axis=1) == 0).sum()) if total_rows > 0 else 0

    overview = {
        "total_respondents": total_rows,
        "total_questions": total_cols,
        "total_cells": total_cells,
        "total_valid_cells": total_valid_cells,
        "total_missing_cells": total_missing_cells,
        "overall_response_rate": overall_response_rate,
        "complete_respondents": complete_respondents,
        "partial_respondents": partial_respondents,
        "dropout_respondents": dropout_respondents,
    }

    return {
        "item_audit": df_items,
        "case_audit": df_cases,
        "overview": overview,
    }


def generate_data_dictionary(df):
    """Generates comprehensive variable dictionary with summary metrics for every column."""
    df_copy = df.copy()
    df_copy.columns = make_columns_unique(df_copy.columns)
    rows = []
    for c_idx in range(df_copy.shape[1]):
        col = df_copy.columns[c_idx]
        s = df_copy.iloc[:, c_idx]
        n_valid = int(s.notna().sum())
        n_missing = int(s.isna().sum())
        pct_valid = round(100.0 * n_valid / max(len(df_copy), 1), 1)

        is_num = pd.api.types.is_numeric_dtype(s)
        mean_val = f"{round(float(s.mean()), 3):.3f}" if is_num and n_valid > 0 else "-"
        std_val = f"{round(float(s.std()), 3):.3f}" if is_num and n_valid > 1 else "-"

        if is_num and n_valid > 0:
            min_val = f"{round(float(s.min()), 3):.3f}"
            max_val = f"{round(float(s.max()), 3):.3f}"
        elif n_valid > 0:
            s_non_null = s.dropna().astype(str)
            min_val = str(s_non_null.min())[:30] if len(s_non_null) > 0 else "-"
            max_val = str(s_non_null.max())[:30] if len(s_non_null) > 0 else "-"
        else:
            min_val = "-"
            max_val = "-"

        n_unique = int(s.nunique(dropna=True))

        rows.append({
            "Variable_Name": str(col),
            "Data_Type": str(s.dtype),
            "N_Valid": n_valid,
            "N_Missing": n_missing,
            "Pct_Valid": pct_valid,
            "Unique_Values": n_unique,
            "Mean": str(mean_val),
            "Std_Dev": str(std_val),
            "Min": str(min_val),
            "Max": str(max_val),
        })
    df_dict = pd.DataFrame(rows)
    for col_name in ["Variable_Name", "Data_Type", "Mean", "Std_Dev", "Min", "Max"]:
        df_dict[col_name] = df_dict[col_name].astype(str)
    return df_dict


def generate_reproducible_script(filename, options):
    """
    Generates standalone, copy-pasteable Python script reproducing user's cleaning steps.
    """
    script = f'''"""
reproduce_cleaning.py
=====================
Auto-generated cleaning script for: {filename}
Generated by Survey & Excel Data Cleaning Studio.
"""

import sys
import datetime
import re
import numpy as np
import pandas as pd

INPUT_FILE = "{filename}"
OUTPUT_FILE = "Cleaned_{filename}"

# Likert Scale Dictionary
LIKERT_MAP = {LIKERT_TEXT_MAP}
SENTINELS = {SENTINEL_VALUES}
SUMMARY_WORDS = {SUMMARY_KEYWORDS}

def fix_excel_dates(val):
    if pd.isna(val): return np.nan
    if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
        return f"{{val.month}}-{{val.day}}"
    m = re.match(r"^20\\d\\d-(\\d{{1,2}})-(\\d{{1,2}})", str(val).strip())
    if m: return f"{{int(m.group(1))}}-{{int(m.group(2))}}"
    return val

def clean_dataset():
    print(f"Reading {{INPUT_FILE}}...")
    if INPUT_FILE.endswith(".csv"):
        df = pd.read_csv(INPUT_FILE)
    else:
        df = pd.read_excel(INPUT_FILE)

    raw_shape = df.shape
    print(f"Initial shape: {{raw_shape}}")

    # 1. Drop completely empty rows
    {"df = df.dropna(how='all').reset_index(drop=True)" if options.get("drop_blanks") else "# Blank rows kept"}

    # 2. Sentinels -> NaN
    {"for c in df.columns: df.loc[df[c].astype(str).str.strip().str.lower().isin(SENTINELS), c] = np.nan" if options.get("clean_sentinels") else "# Sentinels kept"}

    # 3. String hygiene
    {"for c in df.select_dtypes(include='object').columns: df[c] = df[c].astype(str).str.strip().replace('nan', np.nan)" if options.get("trim_strings") else "# Strings kept"}

    # 4. Repair Excel date bugs
    {"for c in df.columns: df[c] = df[c].apply(fix_excel_dates)" if options.get("repair_dates") else "# Dates untouched"}

    # 5. Map Likert text labels
    {"for c in df.columns: df[c] = df[c].apply(lambda v: LIKERT_MAP.get(str(v).strip().lower(), v))" if options.get("map_likert") else "# Likert untouched"}

    # 6. Parse currency, percentages, European decimals & space thousands
    {"# Smart currency & number parsing\\n    curr_pattern = r'(?:[$€£¥₹₽₩₪₺₫]|\\b(?:SEK|USD|EUR|GBP|NOK|DKK|CAD|AUD|CHF|JPY|CNY|kr)\\b)'\\n    for c in df.select_dtypes(include='object').columns:\\n        try:\\n            cleaned_col = df[c].astype(str).str.replace(curr_pattern, '', regex=True).str.replace('%', '').str.strip()\\n            cleaned_col = cleaned_col.str.replace(r'(\\d)\\s+(\\d)', r'\\1\\2', regex=True)\\n            df[c] = pd.to_numeric(cleaned_col.str.replace(',', '.'), errors='ignore')\\n        except Exception: pass" if options.get("parse_numbers") else "# Numeric formats kept"}

    # 7. Deduplication
    {"df = df.drop_duplicates().reset_index(drop=True)" if options.get("drop_duplicates") else "# Duplicates kept"}

    # 8. Missing value imputation
    {"for c in df.select_dtypes(include='number').columns: df[c] = df[c].fillna(df[c].median())" if options.get("imputation") == "median" else ("for c in df.select_dtypes(include='number').columns: df[c] = df[c].fillna(df[c].mean())" if options.get("imputation") == "mean" else "# Missing values kept as NaN")}

    print(f"Final cleaned shape: {{df.shape}}")
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"Cleaned dataset saved to: {{OUTPUT_FILE}}")

if __name__ == "__main__":
    clean_dataset()
'''
    return script


# ---------------------------------------------------------------------------
# 7. KFL & CPE Thesis Survey Preset Pipeline
# ---------------------------------------------------------------------------

class KFLSchemaMismatchError(Exception):
    """Raised when an input DataFrame does not match the 9-block survey benchmark schema."""
    pass


def build_b3_b4_bijection(df):
    match_pairs = [
        ("bakgrund20", "var0400"), ("bakgrund21", "bakgrund20"), ("var0402", "var0401"),
        ("Tegelsten", "bakgrund21"), ("KFL2", "var0402"), ("KFL4", "Tegelsten"),
        ("KFL5", "tegelsten"), ("KFL6", "KFL1"), ("KFL7", "KFL2"),
        ("KFL8", "KFL3"), ("KFL9", "KFL4"), ("KFL11", "KFL5"),
        ("KFL12", "KFL6"), ("KFL13", "KFL7"), ("KFL14", "KFL8"),
        ("KFL15", "KFL9"), ("KFL17", "KFL10"), ("KFL18", "KFL11"),
        ("KFL19", "KFL12"), ("KFL20", "KFL13"), ("KFL21", "KFL14"),
        ("KFL22", "KFL15"), ("KFL25", "KFL16"), ("KFL26", "KFL17"),
        ("KFL27", "KFL18"), ("KFL28", "KFL19"), ("KFL29", "KFL20"),
    ]
    if df is None or not isinstance(df, pd.DataFrame):
        raise KFLSchemaMismatchError("Uploaded file is not a valid DataFrame.")
    if len(df) < 473:
        raise KFLSchemaMismatchError(
            f"Uploaded spreadsheet has {len(df)} rows. The 9-block benchmark cohort requires at least 473 rows "
            f"to reconstruct the B3 and B4 respondent cohorts."
        )
    missing_cols = [p[0] for p in match_pairs if p[0] not in df.columns] + [p[1] for p in match_pairs if p[1] not in df.columns]
    if missing_cols:
        unique_missing = list(dict.fromkeys(missing_cols))
        raise KFLSchemaMismatchError(
            f"Uploaded workbook is missing required benchmark columns: {unique_missing[:5]}."
        )
    def get_first_loc(c):
        loc = df.columns.get_loc(c)
        if isinstance(loc, (slice, np.ndarray)):
            return int(np.where(df.columns == c)[0][0])
        return int(loc)

    b3_cols = [get_first_loc(p[0]) for p in match_pairs]
    b4_cols = [get_first_loc(p[1]) for p in match_pairs]

    b3_sigs = {}
    for r3 in range(113, 292):
        sig = (
            int(clean_numeric_val(df.iloc[r3, 1])),
            int(clean_numeric_val(df.iloc[r3, 2])),
            int(clean_numeric_val(df.iloc[r3, 3])),
            tuple(str(df.iloc[r3, c]).strip() for c in b3_cols),
        )
        b3_sigs[r3] = sig

    age_map = {"16-25 years": 1, "26-35 years": 2, "36-45 years": 3, "46-55 years": 4, "56-65 years": 5, "Over 65 years": 6}
    edu_map = {
        "Compulsory school": 1, "Upper secondary education": 2,
        "Higher education, shorter than 3 years": 3, "University education, longer than 3 years": 4,
        "Other education": 5,
    }
    mgr_map = {"Top manager": 1, "Higher-level manager": 2, "Mid-level manager": 3, "Lower-level manager": 4, "Other:": 5}

    b4_sigs = {}
    for r4 in range(294, 473):
        sig = (
            age_map.get(str(df.iloc[r4, 1]).strip(), -1),
            edu_map.get(str(df.iloc[r4, 2]).strip(), -1),
            mgr_map.get(str(df.iloc[r4, 3]).strip(), 5),
            tuple(str(df.iloc[r4, c]).strip() for c in b4_cols),
        )
        b4_sigs[r4] = sig

    b3_to_b4 = {}
    used_b4 = set()
    for r3, s3 in b3_sigs.items():
        for r4, s4 in b4_sigs.items():
            if r4 not in used_b4 and s3 == s4:
                b3_to_b4[r3] = r4
                used_b4.add(r4)
                break

    for r3, s3 in b3_sigs.items():
        if r3 in b3_to_b4:
            continue
        best_r4, best_score = None, -1
        for r4, s4 in b4_sigs.items():
            if r4 in used_b4:
                continue
            k_matches = sum(1 for a, b in zip(s3[3], s4[3]) if a == b)
            demo_matches = sum(1 for a, b in zip(s3[:3], s4[:3]) if a == b)
            score = demo_matches * 100 + k_matches
            if score > best_score:
                best_score = score
                best_r4 = r4
        b3_to_b4[r3] = best_r4
        used_b4.add(best_r4)

    return b3_to_b4


def parse_gender(val):
    if pd.isna(val): return np.nan
    s = str(val).strip().lower()
    if s in ("1", "1.0", "1.00", "man", "male", "m"): return 1
    if s in ("2", "2.0", "2.00", "woman", "kvinna", "female", "f"): return 2
    return np.nan


def parse_age(val):
    if pd.isna(val): return np.nan
    v = clean_numeric_val(val, 1, 6)
    if pd.notna(v): return int(v)
    s = str(val).strip().lower()
    for k, code in [("16-25", 1), ("26-35", 2), ("36-45", 3), ("46-55", 4), ("56-65", 5), ("over 65", 6), ("65+", 6)]:
        if k in s: return code
    return np.nan


def parse_edu(val):
    if pd.isna(val): return np.nan
    v = clean_numeric_val(val, 1, 5)
    if pd.notna(v): return int(v)
    s = str(val).strip().lower()
    if "compulsory" in s or "grundskola" in s: return 1
    if "upper secondary" in s or "gymnasi" in s: return 2
    if "shorter than 3" in s or "1-3" in s: return 3
    if "longer than 3" in s or "university" in s or "4+" in s: return 4
    if "other" in s or "annan" in s: return 5
    return np.nan


def parse_tenure(val):
    if pd.isna(val): return np.nan
    v = clean_numeric_val(val, 1, 7)
    if pd.notna(v): return int(v)
    s = str(val).strip().lower()
    for k, code in [("0-1", 1), ("1-2", 1), ("3-5", 2), ("6-8", 3), ("9-10", 4), ("11-15", 5), ("16-20", 6), ("21", 7), ("more than 20", 7)]:
        if k in s: return code
    return np.nan


def extract_demographics(df, r, block, r4_partner=None):
    out = {}
    if block in ("B0", "B5", "B6"):
        g_code = parse_gender(df.iloc[r, 0])
        a_code = parse_age(df.iloc[r, 1])
        e_code = parse_edu(df.iloc[r, 2])
        raw_mgr = clean_numeric_val(df.iloc[r, 3])
        m_code = int(raw_mgr) if pd.notna(raw_mgr) else np.nan
        emp_raw = clean_numeric_val(df.iloc[r, 7])
        emp_code = int(emp_raw) if pd.notna(emp_raw) in (1, 2, 3) else (1 if pd.notna(emp_raw) else np.nan)
        comp = df.iloc[r, 9] if block in ("B5", "B6") else df.iloc[r, 7]
        ind = df.iloc[r, 10] if block in ("B5", "B6") else df.iloc[r, 8]
        org_sz = clean_numeric_val(df.iloc[r, 19] if block in ("B5", "B6") else df.iloc[r, 17])
        unit_sz = fix_excel_date_range(df.iloc[r, 21] if block in ("B5", "B6") else df.iloc[r, 19])
        ten_pos = parse_tenure(df.iloc[r, 26] if block in ("B5", "B6") else df.iloc[r, 24])
        ten_mgr = parse_tenure(df.iloc[r, 27] if block in ("B5", "B6") else df.iloc[r, 25])
        wk_hrs = clean_numeric_val(df.iloc[r, 28] if block in ("B5", "B6") else df.iloc[r, 26])
        sick = clean_numeric_val(df.iloc[r, 30] if block in ("B5", "B6") else df.iloc[r, 28])
        role_txt = df.iloc[r, 23] if block in ("B5", "B6") else df.iloc[r, 21]

    elif block == "B1":
        g_code = parse_gender(df.iloc[r, 0])
        a_code = parse_age(df.iloc[r, 1])
        e_code = parse_edu(df.iloc[r, 2])
        raw_mgr = clean_numeric_val(df.iloc[r, 3])
        b1_mgr_map = {1: 3, 2: 2, 3: 4}
        m_code = b1_mgr_map.get(int(raw_mgr), 4) if pd.notna(raw_mgr) else np.nan
        emp_raw = clean_numeric_val(df.iloc[r, 7])
        emp_code = int(emp_raw) if pd.notna(emp_raw) else np.nan
        comp = df.iloc[r, 5]
        ind = df.iloc[r, 12]
        org_sz = clean_numeric_val(df.iloc[r, 15])
        unit_sz = fix_excel_date_range(df.iloc[r, 16])
        ten_pos = parse_tenure(df.iloc[r, 13])
        ten_mgr = np.nan
        wk_hrs = clean_numeric_val(df.iloc[r, 8])
        sick = clean_numeric_val(df.iloc[r, 19])
        role_txt = df.iloc[r, 9]

    elif block == "B2":
        g_code = parse_gender(df.iloc[r, 0])
        a_code = parse_age(df.iloc[r, 1])
        e_code = parse_edu(df.iloc[r, 2])
        sit = str(df.iloc[r, 3]).strip()
        if "Employees" in sit:
            m_code = 0
        else:
            m_str = str(df.iloc[r, 4]).strip().lower()
            if "ceo" in m_str or "top" in m_str or "higher" in m_str: m_code = 1
            elif "mid" in m_str: m_code = 2
            elif "lower" in m_str or "first" in m_str: m_code = 3
            else: m_code = 4
        emp_str = str(df.iloc[r, 5]).strip().lower()
        emp_code = 1 if "permanent" in emp_str else (2 if "fixed" in emp_str else 3)
        comp = df.iloc[r, 7]
        ind = df.iloc[r, 9]
        org_sz = fix_excel_date_range(df.iloc[r, 12])
        unit_sz = fix_excel_date_range(df.iloc[r, 125])
        ten_pos = parse_tenure(df.iloc[r, 10])
        ten_mgr = parse_tenure(df.iloc[r, 11])
        wk_hrs = df.iloc[r, 8]
        sick = df.iloc[r, 14]
        role_txt = df.iloc[r, 16]

    elif block in ("B3", "B4"):
        r_b3 = r if block == "B3" else r4_partner
        r_b4 = r4_partner if block == "B3" else r
        g_code = parse_gender(df.iloc[r_b4, 0]) if r_b4 is not None else parse_gender(df.iloc[r, 0])
        a_code = parse_age(df.iloc[r_b3, 1])
        e_code = parse_edu(df.iloc[r_b3, 2])
        raw_mgr = clean_numeric_val(df.iloc[r_b3, 3])
        b3_mgr_map = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}
        m_code = b3_mgr_map.get(int(raw_mgr), 4) if pd.notna(raw_mgr) else np.nan
        emp_raw = clean_numeric_val(df.iloc[r_b3, 7])
        emp_code = int(emp_raw) if pd.notna(emp_raw) else np.nan
        comp = df.iloc[r_b3, 9]
        ind = df.iloc[r_b4, 12] if r_b4 is not None else df.iloc[r_b3, 12]
        org_sz = clean_numeric_val(df.iloc[r_b3, 17])
        unit_sz = fix_excel_date_range(df.iloc[r_b4, 16] if r_b4 is not None else df.iloc[r_b3, 16])
        ten_pos = parse_tenure(df.iloc[r_b3, 18])
        ten_mgr = parse_tenure(df.iloc[r_b3, 19])
        wk_hrs = clean_numeric_val(df.iloc[r_b3, 20])
        sick = clean_numeric_val(df.iloc[r_b3, 22])
        role_txt = df.iloc[r_b4, 14] if r_b4 is not None else df.iloc[r_b3, 14]

    elif block in ("B7", "B8"):
        g_code = parse_gender(df.iloc[r, 2])
        a_code = parse_age(df.iloc[r, 3])
        e_code = parse_edu(df.iloc[r, 4])
        raw_mgr = clean_numeric_val(df.iloc[r, 5])
        m_code = int(raw_mgr) if pd.notna(raw_mgr) else np.nan
        emp_raw = clean_numeric_val(df.iloc[r, 9])
        emp_code = int(emp_raw) if pd.notna(emp_raw) else np.nan
        comp = df.iloc[r, 11]
        ind = df.iloc[r, 15]
        org_sz = clean_numeric_val(df.iloc[r, 18])
        unit_sz = fix_excel_date_range(df.iloc[r, 20])
        ten_pos = parse_tenure(df.iloc[r, 22])
        ten_mgr = parse_tenure(df.iloc[r, 23])
        wk_hrs = clean_numeric_val(df.iloc[r, 26])
        sick = clean_numeric_val(df.iloc[r, 28])
        role_txt = df.iloc[r, 17]

    out["gender_code"] = g_code
    out["gender_label"] = GENDER_LABELS.get(g_code, np.nan)
    out["age_code"] = a_code
    out["age_label"] = AGE_LABELS.get(a_code, np.nan)
    out["education_code"] = e_code
    out["education_label"] = EDU_LABELS.get(e_code, np.nan)
    out["manager_level_code"] = m_code
    out["manager_level_label"] = MGR_LABELS.get(m_code, np.nan)
    out["employment_type_code"] = emp_code
    out["employment_type_label"] = EMP_LABELS.get(emp_code, np.nan)
    out["company_name"] = str(comp).strip() if pd.notna(comp) and str(comp).strip() not in ("nan", ".") else np.nan
    out["industry_sector"] = str(ind).strip() if pd.notna(ind) and str(ind).strip() not in ("nan", ".") else np.nan
    out["org_size_code"] = org_sz if isinstance(org_sz, (int, float)) else np.nan
    out["org_size_label"] = ORG_SIZE_LABELS.get(int(org_sz), str(org_sz)) if pd.notna(org_sz) and isinstance(org_sz, (int, float)) else (str(org_sz) if pd.notna(org_sz) else np.nan)
    out["unit_size_raw"] = unit_sz
    out["tenure_current_pos_code"] = ten_pos
    out["tenure_current_pos_label"] = TENURE_LABELS.get(ten_pos, np.nan)
    out["tenure_manager_code"] = ten_mgr
    out["tenure_manager_label"] = TENURE_LABELS.get(ten_mgr, np.nan)
    out["weekly_hours_raw"] = wk_hrs
    out["sick_leave_raw"] = sick
    out["work_tasks_text"] = str(role_txt).strip() if pd.notna(role_txt) and str(role_txt).strip() not in ("nan", ".") else np.nan
    return out


def extract_scales(df, r, block, r3_partner=None):
    out = {}
    for i in range(1, 100): out[f"KFL{i}"] = np.nan
    for i in range(88, 92): out[f"KFL_vA_{i}"] = np.nan
    for i in range(1, 16): out[f"CPE{i}"] = np.nan

    r_kfl = r3_partner if (block == "B4" and r3_partner is not None) else r
    b_kfl = "B3" if (block == "B4" and r3_partner is not None) else block

    if b_kfl == "B0":
        start = 34
        out["kfl_survey_version"] = "Version_A"
        for i in range(1, 61): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
        for i in range(67, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 60 + (i - 67)], 0, 5)
        for idx, i in enumerate(range(88, 92)): out[f"KFL_vA_{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 87 + idx], 0, 5)
        out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 125], 0, 5)
        out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 126], 0, 5)
        out["KFL94"] = clean_numeric_val(df.iloc[r_kfl, 127], 0, 5)
        out["KFL95"] = clean_numeric_val(df.iloc[r_kfl, 128], 0, 5)
        out["KFL96"] = clean_numeric_val(df.iloc[r_kfl, 129], 0, 5)
        out["KFL97"] = clean_numeric_val(df.iloc[r_kfl, 130], 0, 5)
        for i in range(1, 16): out[f"CPE{i}"] = clean_numeric_val(df.iloc[r_kfl, 157 + i - 1], 0, 5)

    elif b_kfl == "B1":
        start = 21
        out["kfl_survey_version"] = "Version_A"
        for i in range(1, 61): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
        for i in range(67, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 60 + (i - 67)], 0, 5)
        for idx, i in enumerate(range(88, 92)): out[f"KFL_vA_{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 87 + idx], 0, 5)
        out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 112], 0, 5)
        out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 113], 0, 5)
        out["KFL94"] = clean_numeric_val(df.iloc[r_kfl, 118], 0, 5)
        out["KFL95"] = clean_numeric_val(df.iloc[r_kfl, 119], 0, 5)
        out["KFL96"] = clean_numeric_val(df.iloc[r_kfl, 121], 0, 5)
        out["KFL97"] = clean_numeric_val(df.iloc[r_kfl, 122], 0, 5)

    elif b_kfl == "B2":
        start = 19
        out["kfl_survey_version"] = "Version_A"
        for i in range(1, 61): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
        for i in range(67, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 60 + (i - 67)], 0, 5)
        for idx, i in enumerate(range(88, 92)): out[f"KFL_vA_{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 87 + idx], 0, 5)
        out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 110], 0, 5)
        out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 111], 0, 5)

    elif b_kfl == "B3":
        start = 27
        if r_kfl <= 239:
            out["kfl_survey_version"] = "Version_B"
            for i in range(1, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
            out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 120], 0, 5)
            out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 121], 0, 5)
        else:
            out["kfl_survey_version"] = "Version_A"
            for i in range(1, 61): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
            for i in range(67, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 60 + (i - 67)], 0, 5)
            for idx, i in enumerate(range(88, 92)): out[f"KFL_vA_{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 87 + idx], 0, 5)
            out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 118], 0, 5)
            out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 119], 0, 5)

    elif b_kfl in ("B5", "B6"):
        start = 36
        out["kfl_survey_version"] = "Version_A"
        for i in range(1, 61): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
        for i in range(67, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 60 + (i - 67)], 0, 5)
        for idx, i in enumerate(range(88, 92)): out[f"KFL_vA_{i}"] = clean_numeric_val(df.iloc[r_kfl, start + 87 + idx], 0, 5)
        out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 127], 0, 5)
        out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 128], 0, 5)
        out["KFL94"] = clean_numeric_val(df.iloc[r_kfl, 129], 0, 5)
        out["KFL95"] = clean_numeric_val(df.iloc[r_kfl, 130], 0, 5)
        out["KFL96"] = clean_numeric_val(df.iloc[r_kfl, 131], 0, 5)
        out["KFL97"] = clean_numeric_val(df.iloc[r_kfl, 132], 0, 5)
        for i in range(1, 16): out[f"CPE{i}"] = clean_numeric_val(df.iloc[r_kfl, 159 + i - 1], 0, 5)

    elif b_kfl in ("B7", "B8"):
        start = 32
        out["kfl_survey_version"] = "Version_B"
        for i in range(1, 94): out[f"KFL{i}"] = clean_numeric_val(df.iloc[r_kfl, start + i - 1], 0, 5)
        out["KFL98"] = clean_numeric_val(df.iloc[r_kfl, 131], 0, 5)
        out["KFL99"] = clean_numeric_val(df.iloc[r_kfl, 132], 0, 5)
        out["KFL94"] = clean_numeric_val(df.iloc[r_kfl, 135], 0, 5)
        out["KFL95"] = clean_numeric_val(df.iloc[r_kfl, 136], 0, 5)
        out["KFL96"] = clean_numeric_val(df.iloc[r_kfl, 137], 0, 5)
        out["KFL97"] = clean_numeric_val(df.iloc[r_kfl, 139], 0, 5)
        if b_kfl == "B8":
            for i in range(1, 16): out[f"CPE{i}"] = clean_numeric_val(df.iloc[r_kfl, 156 + i - 1], 0, 5)

    return out


def compute_composite_scores(df_in):
    d = df_in.copy()
    d["KFL86R"] = 5.0 - d["KFL86"]
    d["KFL84R"] = 5.0 - d["KFL84"]
    for item in KFL_F3_RAW_ITEMS:
        d[f"{item}R"] = 5.0 - d[item]

    f2_rev_items = ["KFL86R", "KFL84R", "KFL90", "KFL89", "KFL78", "KFL74"]
    f3_rev_items = [f"{item}R" for item in KFL_F3_RAW_ITEMS]
    all_18_rev = KFL_F1_ITEMS + f2_rev_items + f3_rev_items

    d["KFL_F1_IdeaSupport"] = d[KFL_F1_ITEMS].mean(axis=1).round(4)
    d["KFL_F2_Autonomy"] = d[f2_rev_items].mean(axis=1).round(4)
    d["KFL_F3_Conservatism"] = d[KFL_F3_RAW_ITEMS].mean(axis=1).round(4)
    d["KFL_Total_18"] = d[all_18_rev].mean(axis=1).round(4)

    d["CPE_Change_Mean"] = d[CPE_CHANGE_ITEMS].mean(axis=1).round(4)
    d["CPE_Production_Mean"] = d[CPE_PRODUCTION_ITEMS].mean(axis=1).round(4)
    d["CPE_Employee_Mean"] = d[CPE_EMPLOYEE_ITEMS].mean(axis=1).round(4)
    d["CPE_CE_Combined_Mean"] = d[CPE_CHANGE_ITEMS + CPE_EMPLOYEE_ITEMS].mean(axis=1).round(4)
    d["CPE_Total_15_Mean"] = d[CPE_CHANGE_ITEMS + CPE_PRODUCTION_ITEMS + CPE_EMPLOYEE_ITEMS].mean(axis=1).round(4)
    return d


def run_kfl_masterfile_pipeline(df_raw, imputation_strategy="median"):
    b3_to_b4 = build_b3_b4_bijection(df_raw)
    b4_to_b3 = {v: k for k, v in b3_to_b4.items()}

    b6_kfl_sigs = set()
    for r6 in range(515, 548):
        sig = tuple(clean_numeric_val(df_raw.iloc[r6, c]) for c in range(36, 96))
        if not all(pd.isna(x) for x in sig):
            b6_kfl_sigs.add((str(df_raw.iloc[r6, 9]).strip(), sig))

    block_specs = [
        ("B0", "B0_External_Managers", "Rasulzada External Managers Cohort 1", range(1, 23), True),
        ("B1", "B1_Joel_Managers", "Wallin & Björklund (2012) - Preschool/Municipal Managers", range(30, 59), True),
        ("B2", "B2_Jennie_Josefin", "Jennie & Josefin Cohort (13 Managers, 37 Employees)", range(61, 111), False),
        ("B3", "B3_B4_Rebecca_Anna", "Kvist & Lundqvist Frogner (2013) - Merged B3 KFL + B4 Demographics", range(113, 292), True),
        ("B4", "B4_AnnaReb_DuplicateCohort", "Kvist & Lundqvist Frogner (2013) - B4 Duplicate Row Order", range(294, 473), False),
        ("B5", "B5_KFL1", "Rasulzada KFL1 Managers Cohort", range(476, 508), True),
        ("B6", "B6_Ledarna", "Rasulzada Ledarna Managers Cohort", range(515, 548), True),
        ("B7", "B7_Unionen_Case1", "Unionen Occasion 1 Managers Cohort", [557] + list(range(560, 607)), False),
        ("B8", "B8_Unionen_Occasion2", "Unionen Occasion 2 Managers Cohort", range(610, 657), True),
    ]

    all_records = []
    for short_b, block_name, citation, r_range, in_thesis in block_specs:
        for r in r_range:
            r4_p = b3_to_b4.get(r) if short_b == "B3" else None
            r3_p = b4_to_b3.get(r) if short_b == "B4" else None
            r_partner = r4_p if short_b == "B3" else r3_p

            demo = extract_demographics(df_raw, r, short_b, r4_partner=r_partner)
            scales = extract_scales(df_raw, r, short_b, r3_partner=r3_p)

            kfl_vals = [scales[f"KFL{i}"] for i in range(1, 94)]
            non_na_kfl = sum(1 for v in kfl_vals if pd.notna(v))

            is_dup_cohort = False
            if short_b == "B4":
                is_dup_cohort = True
            elif short_b == "B5":
                sig = tuple(clean_numeric_val(df_raw.iloc[r, c]) for c in range(36, 96))
                if (str(df_raw.iloc[r, 9]).strip(), sig) in b6_kfl_sigs:
                    is_dup_cohort = True

            if non_na_kfl == 0:
                q_flag = "All_KFL_Missing"
            elif non_na_kfl < 75:
                q_flag = "Partial_Dropoff"
            else:
                q_flag = "Complete"

            is_mgr = demo["manager_level_code"] != 0
            rec = {
                "respondent_id": f"R{len(all_records) + 1:03d}",
                "excel_row_1based": r + 2,
                "paired_b3_b4_excel_row_1based": (r4_p + 2 if r4_p is not None else (r3_p + 2 if r3_p is not None else np.nan)),
                "source_block": block_name,
                "study_citation": citation,
                "kfl_survey_version": scales.pop("kfl_survey_version"),
                "is_manager": bool(is_mgr),
                "rater_role": "Manager (Self-rating)" if is_mgr else "Employee (Rating Manager)",
                "in_thesis_sample_342": bool(in_thesis),
                "is_duplicate_cohort_row": bool(is_dup_cohort),
                "kfl_valid_item_count": non_na_kfl,
                "data_quality_flag": q_flag,
            }
            rec.update(demo)
            rec.update(scales)
            all_records.append(rec)

    df_all_619 = pd.DataFrame(all_records)
    df_all_619 = compute_composite_scores(df_all_619)

    df_thesis_raw = df_all_619[df_all_619["in_thesis_sample_342"]].copy().reset_index(drop=True)
    df_thesis_raw["thesis_id"] = [f"T{i+1:03d}" for i in range(len(df_thesis_raw))]
    cols_t = ["thesis_id"] + [c for c in df_thesis_raw.columns if c != "thesis_id"]
    df_thesis_raw = df_thesis_raw[cols_t]

    df_thesis_imp = df_thesis_raw.copy()
    kfl_all_cols = [f"KFL{i}" for i in range(1, 100)] + [f"KFL_vA_{i}" for i in range(88, 92)]
    for c in kfl_all_cols:
        if imputation_strategy == "median":
            val = df_thesis_imp[c].median()
        elif imputation_strategy == "mean":
            val = df_thesis_imp[c].mean()
        else:
            val = np.nan
        if pd.notna(val):
            df_thesis_imp[c] = df_thesis_imp[c].fillna(val)
    df_thesis_imp = compute_composite_scores(df_thesis_imp)

    df_unique_409 = df_all_619[~df_all_619["is_duplicate_cohort_row"]].copy().reset_index(drop=True)

    row0_q = {df_raw.columns[c]: str(df_raw.iloc[0, c]).strip() for c in range(df_raw.shape[1]) if pd.notna(df_raw.iloc[0, c])}
    row29_q = {str(df_raw.iloc[28, c]).strip(): str(df_raw.iloc[29, c]).strip() for c in range(df_raw.shape[1]) if pd.notna(df_raw.iloc[28, c]) and pd.notna(df_raw.iloc[29, c])}

    dict_rows = []
    for col in df_thesis_raw.columns:
        non_na_342 = int(df_thesis_raw[col].notna().sum())
        non_na_409 = int(df_unique_409[col].notna().sum()) if col in df_unique_409.columns else non_na_342
        if col.startswith("KFL") and re.match(r"^KFL\d+$", col):
            q_txt = row0_q.get(col, "")
            cat = "KFL Scale Item (0-5)"
            if col in KFL_F1_ITEMS: cat += " [Factor 1: Idea-Supportive Relationship]"
            elif col in KFL_F2_RAW_ITEMS: cat += " [Factor 2: Autonomy]"
            elif col in KFL_F3_RAW_ITEMS: cat += " [Factor 3: Conservatism]"
        elif col.startswith("KFL_vA_"):
            idx = int(col.split("_")[-1])
            q_txt = row29_q.get(f"KFL{idx}", "Survey Version A specific item")
            cat = "KFL Version-A Item (0-5)"
        elif col.startswith("CPE") and re.match(r"^CPE\d+$", col):
            q_txt = row0_q.get(col, "")
            cat = "CPE Scale Item (0-5)"
            if col in CPE_CHANGE_ITEMS: cat += " [Change Orientation]"
            elif col in CPE_PRODUCTION_ITEMS: cat += " [Production/Structure Orientation]"
            elif col in CPE_EMPLOYEE_ITEMS: cat += " [Employee/Relationship Orientation]"
        elif col.endswith("R") and col.startswith("KFL"):
            base = col[:-1]
            q_txt = f"Reversed ({base}): 5 - {base} ({row0_q.get(base, '')})"
            cat = "KFL Reversed Item (0-5)"
        elif col.startswith("KFL_F") or col == "KFL_Total_18" or col.startswith("CPE_"):
            q_txt = f"Computed composite mean score for {col}"
            cat = "Computed Composite / Factor Score"
        elif col in ("thesis_id", "respondent_id", "excel_row_1based", "paired_b3_b4_excel_row_1based",
                     "source_block", "study_citation", "kfl_survey_version", "is_manager",
                     "rater_role", "in_thesis_sample_342", "is_duplicate_cohort_row",
                     "kfl_valid_item_count", "data_quality_flag"):
            q_txt = f"Provenance / data quality metadata: {col}"
            cat = "Metadata & Provenance"
        else:
            q_txt = f"Harmonized demographic variable: {col}"
            cat = "Demographics"

        mean_342 = df_thesis_raw[col].mean() if pd.api.types.is_numeric_dtype(df_thesis_raw[col]) and not pd.api.types.is_bool_dtype(df_thesis_raw[col]) else np.nan
        sd_342 = df_thesis_raw[col].std() if pd.api.types.is_numeric_dtype(df_thesis_raw[col]) and not pd.api.types.is_bool_dtype(df_thesis_raw[col]) else np.nan

        dict_rows.append({
            "Variable_Name": col,
            "Category": cat,
            "Description_or_Question_Text": q_txt,
            "N_Valid_Thesis342": non_na_342,
            "Pct_Valid_Thesis342": round(100.0 * non_na_342 / len(df_thesis_raw), 1),
            "Mean_Thesis342": round(float(mean_342), 3) if pd.notna(mean_342) else np.nan,
            "SD_Thesis342": round(float(sd_342), 3) if pd.notna(sd_342) else np.nan,
            "N_Valid_Unique409": non_na_409,
        })
    df_dict = pd.DataFrame(dict_rows)

    f1_items = KFL_F1_ITEMS
    f2_rev_items = ["KFL86R", "KFL84R", "KFL90", "KFL89", "KFL78", "KFL74"]
    f3_raw_items = KFL_F3_RAW_ITEMS
    f3_rev_items = [f"{item}R" for item in KFL_F3_RAW_ITEMS]
    all_18_rev = f1_items + f2_rev_items + f3_rev_items

    stats = {
        "alpha_f1_raw": compute_cronbach_alpha(df_thesis_raw[f1_items]),
        "alpha_f1_imp": compute_cronbach_alpha(df_thesis_imp[f1_items]),
        "alpha_f2_raw": compute_cronbach_alpha(df_thesis_raw[f2_rev_items]),
        "alpha_f2_imp": compute_cronbach_alpha(df_thesis_imp[f2_rev_items]),
        "alpha_f3_raw": compute_cronbach_alpha(df_thesis_raw[f3_raw_items]),
        "alpha_f3_imp": compute_cronbach_alpha(df_thesis_imp[f3_raw_items]),
        "alpha_total18_raw": compute_cronbach_alpha(df_thesis_raw[all_18_rev]),
        "alpha_total18_imp": compute_cronbach_alpha(df_thesis_imp[all_18_rev]),
        "alpha_cpe_total": compute_cronbach_alpha(df_thesis_raw[CPE_CHANGE_ITEMS + CPE_PRODUCTION_ITEMS + CPE_EMPLOYEE_ITEMS]),
        "alpha_cpe_change": compute_cronbach_alpha(df_thesis_raw[CPE_CHANGE_ITEMS]),
        "alpha_cpe_prod": compute_cronbach_alpha(df_thesis_raw[CPE_PRODUCTION_ITEMS]),
        "alpha_cpe_emp": compute_cronbach_alpha(df_thesis_raw[CPE_EMPLOYEE_ITEMS]),
        "gender_counts": df_thesis_raw["gender_code"].value_counts().to_dict(),
        "age_counts": df_thesis_raw["age_code"].value_counts().to_dict(),
        "edu_counts": df_thesis_raw["education_code"].value_counts().to_dict(),
        "tenure_mgr_counts": df_thesis_raw["tenure_manager_code"].value_counts().to_dict(),
    }

    return {
        "df_thesis_raw": df_thesis_raw,
        "df_thesis_imp": df_thesis_imp,
        "df_unique_409": df_unique_409,
        "df_all_619": df_all_619,
        "df_dict": df_dict,
        "stats": stats,
    }


# Backward-compatibility aliases
reverse_code_likert = reverse_code_items
compute_item_total_correlations = compute_alpha_with_item_deleted
