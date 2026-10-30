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




# ---------------------------------------------------------------------------
# 4B. Flagship Cleaning Suite: Profiles, Diffs, OpenRefine Clustering, & Audit
# ---------------------------------------------------------------------------

def repair_mojibake_encoding(val):
    """
    Detects and repairs Latin-1 / CP1252 / UTF-8 mojibake corruptions in survey responses.
    Handles double-encoded Nordic/Germanic characters (ä, ö, å, é) and typographer quotes.
    """
    if not isinstance(val, str) or not val:
        return val
    s = val
    # Try Latin-1 to UTF-8 reconstruction if signature double-byte sequences exist
    if any(seq in s for seq in ["Ã¤", "Ã¶", "Ã¥", "Ã„", "Ã–", "Ã…", "Ã©", "Ã¨", "â€™", "â€œ", "â€“"]):
        try:
            s_reconstructed = s.encode("latin-1").decode("utf-8")
            # Only adopt if it reduced length and did not add replacement characters
            if len(s_reconstructed) < len(s) and "�" not in s_reconstructed:
                s = s_reconstructed
        except Exception:
            pass

    # Direct substitution for persistent character artifacts
    replacements = {
        "Ã¤": "ä", "Ã¶": "ö", "Ã¥": "å", "Ã„": "Ä", "Ã–": "Ö", "Ã…": "Å",
        "Ã©": "é", "Ã¨": "è", "Ã¼": "ü", "ÃŸ": "ß",
        "â€™": "’", "â€˜": "‘", "â€œ": "“", "â€ ": "”", "â€": "”",
        "â€“": "–", "â€”": "—", " ": " ", "﻿": "", "​": ""
    }
    for bad, good in replacements.items():
        if bad in s:
            s = s.replace(bad, good)
    return s.strip()


def cluster_near_duplicate_categories(series, threshold=0.82):
    """
    OpenRefine-style category clustering using fingerprinting and Levenshtein similarity.
    Clusters casing variants, minor typos, and whitespace differences (e.g. 'Full-time' vs 'full time').
    Returns a dictionary mapping variant strings to the canonical (most frequent) category.
    """
    import difflib
    s_clean = series.dropna().astype(str).str.strip()
    counts = s_clean.value_counts()
    unique_vals = list(counts.index)
    if len(unique_vals) <= 1:
        return {}

    def get_fingerprint(text):
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        tokens = sorted(list(set(cleaned.split())))
        return " ".join(tokens)

    # Pass 1: Key-collision fingerprint clustering
    fp_map = {}
    for v in unique_vals:
        fp = get_fingerprint(v)
        if fp not in fp_map:
            fp_map[fp] = []
        fp_map[fp].append(v)

    mapping = {}
    visited = set()
    for fp, group in fp_map.items():
        if len(group) > 1:
            canonical = sorted(group, key=lambda x: counts.get(x, 0), reverse=True)[0]
            for m in group:
                if m != canonical:
                    mapping[m] = canonical
                    visited.add(m)
            visited.add(canonical)

    # Pass 2: Levenshtein / SequenceMatcher clustering for remaining unclustered
    remaining = [v for v in unique_vals if v not in visited and len(v) >= 3]
    for i, v1 in enumerate(remaining):
        if v1 in visited:
            continue
        group = [v1]
        for v2 in remaining[i+1:]:
            if v2 in visited:
                continue
            ratio = difflib.SequenceMatcher(None, v1.lower(), v2.lower()).ratio()
            if ratio >= threshold:
                group.append(v2)
        if len(group) > 1:
            canonical = sorted(group, key=lambda x: counts.get(x, 0), reverse=True)[0]
            for m in group:
                if m != canonical:
                    mapping[m] = canonical
                    visited.add(m)
            visited.add(canonical)

    return mapping


def detect_impossible_domain_values(df, custom_bounds=None):
    """
    Identifies impossible or out-of-range domain values across numeric/demographic survey columns.
    Checks Age [10..115], Percentages [0..100], and user-specified custom bounds.
    """
    default_bounds = {
        "age": (10, 115),
        "alder": (10, 115),
        "ålder": (10, 115),
        "pct": (0, 100),
        "percent": (0, 100),
        "percentage": (0, 100),
        "tenure": (0, 65),
    }
    bounds = {**default_bounds, **(custom_bounds or {})}
    findings = []

    for col in df.columns:
        c_low = str(col).lower()
        matched_rule = None
        for k_term, b_vals in bounds.items():
            if k_term in c_low:
                matched_rule = (k_term, b_vals)
                break

        if matched_rule:
            rule_name, (min_b, max_b) = matched_rule
            s_num = pd.to_numeric(df[col], errors="coerce")
            out_mask = s_num.notna() & ((s_num < min_b) | (s_num > max_b))
            count = int(out_mask.sum())
            if count > 0:
                for idx in df.index[out_mask]:
                    findings.append({
                        "excel_row": int(idx) + 2,
                        "column": str(col),
                        "value": float(s_num.loc[idx]),
                        "expected_range": f"[{min_b} to {max_b}]",
                        "rule": f"{rule_name.title()} domain boundary"
                    })

    return pd.DataFrame(findings) if findings else pd.DataFrame(columns=["excel_row", "column", "value", "expected_range", "rule"])


def split_multiselect_columns(df, cols=None, delimiter=";"):
    """
    Expands multi-select 'Check all that apply' answer columns into binary 0/1 indicator features.
    """
    d = df.copy()
    if cols is None:
        cols = []
        for c in d.columns:
            s = d[c]
            if (s.dtype == object or pd.api.types.is_string_dtype(s)) and s.nunique() > 2:
                has_delim = s.dropna().astype(str).str.contains(r"[;,]", regex=True).sum()
                if has_delim >= 2:
                    cols.append(c)

    expanded_metadata = {}
    for c in cols:
        s = d[c].dropna().astype(str)
        options = set()
        for val in s:
            parts = re.split(r"[;,]\s*", val.strip())
            for p in parts:
                if p:
                    options.add(p.strip())
        if 2 <= len(options) <= 25:
            created_cols = []
            for opt in sorted(options):
                clean_opt = re.sub(r"[^\w]", "_", opt).strip("_")
                new_col = f"{c}__{clean_opt}"
                d[new_col] = d[c].apply(lambda v: 1 if pd.notna(v) and opt in re.split(r"[;,]\s*", str(v).strip()) else 0)
                created_cols.append((new_col, opt))
            expanded_metadata[c] = created_cols

    return d, expanded_metadata


def detect_duplicate_respondents(df, id_cols=None):
    """
    Identifies exact full-row duplicates and duplicate participant IDs.
    """
    exact_dups = int(df.duplicated().sum())
    id_dups = 0
    dup_indices = []

    if id_cols:
        valid_id_cols = [c for c in id_cols if c in df.columns]
        if valid_id_cols:
            id_dup_mask = df.duplicated(subset=valid_id_cols, keep=False)
            id_dups = int(id_dup_mask.sum())
            dup_indices = list(df.index[id_dup_mask])
    else:
        # Auto-detect potential ID columns
        for c in df.columns:
            c_low = str(c).lower()
            if any(term in c_low for term in ["respondent_id", "participant_id", "email", "ipaddress", "responseid"]):
                id_dup_mask = df.duplicated(subset=[c], keep=False)
                if id_dup_mask.sum() > 0:
                    id_dups = int(id_dup_mask.sum())
                    dup_indices = list(df.index[id_dup_mask])
                    break

    return {
        "exact_duplicates": exact_dups,
        "id_duplicates": id_dups,
        "duplicate_indices": dup_indices
    }


def generate_tidy_variable_names(columns):
    """
    Standardizes messy/verbose question text into tidy snake_case variable names.
    Returns (tidy_columns_list, mapping_dict_original_to_tidy).
    """
    tidy_cols = []
    seen = {}
    mapping = {}

    for i, raw_col in enumerate(columns):
        s = str(raw_col).strip()
        # Remove leading question numbers e.g. '1. ', 'Q1: '
        s_clean = re.sub(r"^(?:Q\d+[:.]?\s*|\d+[:.]\s*)", "", s, flags=re.IGNORECASE)
        # Convert non-alphanumeric to underscores
        s_clean = re.sub(r"[^\w\s]", "", s_clean).strip().lower()
        s_clean = re.sub(r"\s+", "_", s_clean)
        # Truncate overly long sentences to first 5 words
        tokens = s_clean.split("_")
        tidy_base = "_".join(tokens[:5]) if len(tokens) > 5 else s_clean
        if not tidy_base:
            tidy_base = f"var_{i+1}"

        if tidy_base in seen:
            seen[tidy_base] += 1
            final_name = f"{tidy_base}_{seen[tidy_base]}"
        else:
            seen[tidy_base] = 0
            final_name = tidy_base

        tidy_cols.append(final_name)
        mapping[raw_col] = final_name

    return tidy_cols, mapping


def detect_survey_platform_profile(df_raw):
    """
    Forensically detects Qualtrics, LimeSurvey, Google Forms, or Generic spreadsheet imports.
    """
    if df_raw is None or df_raw.empty:
        return {"profile": "generic", "confidence": "Low", "header_rows": 1, "description": "Generic Tabular Data"}

    # 1. Qualtrics 3-Row Header Check
    if df_raw.shape[0] >= 3:
        row0_str = " ".join([str(v).lower() for v in df_raw.iloc[0].dropna()[:10]])
        row2_str = " ".join([str(v) for v in df_raw.iloc[2].dropna()[:10]])
        if '{"importid":' in row2_str.lower() or "importid" in row2_str.lower():
            return {
                "profile": "qualtrics",
                "confidence": "High",
                "header_rows": 3,
                "description": "Qualtrics 3-Row Export (Codes, Question Text, ImportId JSON)"
            }
        if any(term in row0_str for term in ["startdate", "enddate", "ipaddress", "progress", "finished", "responseid"]):
            return {
                "profile": "qualtrics",
                "confidence": "High",
                "header_rows": 3 if 'import' in row2_str.lower() else 2,
                "description": "Qualtrics Metadata Export"
            }

    # 2. LimeSurvey Bracketed Subquestions Check
    header_cand = [str(v) for v in df_raw.iloc[0].dropna()]
    bracket_count = sum(1 for h in header_cand if re.search(r"\[.+\]", h))
    if bracket_count >= 3:
        return {
            "profile": "limesurvey",
            "confidence": "High",
            "header_rows": 1,
            "description": "LimeSurvey Export with Bracketed Subquestion Codes [SQ...]"
        }

    # 3. Google Forms Check
    if len(header_cand) >= 2:
        h0_low = header_cand[0].lower().strip()
        if any(term in h0_low for term in ["timestamp", "tidsstämpel", "horodateur", "zeitstempel"]):
            return {
                "profile": "google_forms",
                "confidence": "High",
                "header_rows": 1,
                "description": "Google Forms Export (Timestamp column + Full-Sentence Questions)"
            }

    return {"profile": "generic", "confidence": "Normal", "header_rows": 1, "description": "Standard Survey / Flat Spreadsheet"}


def apply_import_profile(df_raw, profile="auto", filter_preview=True):
    """
    Applies the platform-specific import profile, extracting tidy variable names,
    preserving full question text in variable labels, and dropping metadata artifacts.
    """
    if profile == "auto":
        p_info = detect_survey_platform_profile(df_raw)
        chosen_profile = p_info["profile"]
    else:
        chosen_profile = profile

    d = df_raw.copy()
    var_labels = {}

    if chosen_profile == "qualtrics" and d.shape[0] >= 3:
        # Row 0: Variable codes, Row 1: Full Question Text, Row 2: ImportId JSON
        codes = [clean_text_hygiene(str(v)) if pd.notna(v) else f"Q_{i+1}" for i, v in enumerate(d.iloc[0])]
        questions = [str(v).strip() if pd.notna(v) else "" for v in d.iloc[1]]
        codes = make_columns_unique(codes)
        for c, q in zip(codes, questions):
            var_labels[c] = q

        # Data starts from row 3 (0-indexed 3)
        d_data = d.iloc[3:].copy().reset_index(drop=True)
        d_data.columns = codes

        # Filter preview rows if requested
        if filter_preview:
            preview_masks = []
            for c in ["Status", "DistributionChannel"]:
                if c in d_data.columns:
                    preview_masks.append(d_data[c].astype(str).str.lower().isin(["survey preview", "preview"]))
            if preview_masks:
                combined_mask = pd.concat(preview_masks, axis=1).any(axis=1)
                d_data = d_data.loc[~combined_mask].reset_index(drop=True)

        return {
            "df": d_data,
            "variable_labels": var_labels,
            "profile": "qualtrics",
            "headers_stripped": 3
        }

    elif chosen_profile == "limesurvey":
        # Row 0: Bracketed headers
        raw_headers = [str(v).strip() for v in d.iloc[0]]
        tidy_headers = []
        for h in raw_headers:
            var_labels[h] = h
            m = re.match(r"^(.+?)\[(.+?)\]$", h)
            if m:
                tidy_name = f"{m.group(1).strip()}_{m.group(2).strip()}"
                tidy_name = re.sub(r"[^\w]", "_", tidy_name).strip("_")
            else:
                tidy_name = re.sub(r"[^\w]", "_", h).strip("_")
            tidy_headers.append(tidy_name if tidy_name else "var")

        tidy_headers = make_columns_unique(tidy_headers)
        d_data = d.iloc[1:].copy().reset_index(drop=True)
        d_data.columns = tidy_headers
        for tidy_c, raw_h in zip(tidy_headers, raw_headers):
            var_labels[tidy_c] = raw_h

        return {
            "df": d_data,
            "variable_labels": var_labels,
            "profile": "limesurvey",
            "headers_stripped": 1
        }

    elif chosen_profile == "google_forms":
        raw_headers = [str(v).strip() for v in d.iloc[0]]
        tidy_headers, _ = generate_tidy_variable_names(raw_headers)
        d_data = d.iloc[1:].copy().reset_index(drop=True)
        d_data.columns = tidy_headers
        for tidy_c, raw_h in zip(tidy_headers, raw_headers):
            var_labels[tidy_c] = raw_h

        return {
            "df": d_data,
            "variable_labels": var_labels,
            "profile": "google_forms",
            "headers_stripped": 1
        }

    else:
        # Generic flat table
        h_idx = detect_header_row(d)
        raw_headers = [clean_text_hygiene(str(v)) if pd.notna(v) and clean_text_hygiene(str(v)) else f"Column_{i+1}" for i, v in enumerate(d.iloc[h_idx])]
        unique_headers = make_columns_unique(raw_headers)
        d_data = d.iloc[h_idx + 1:].copy().reset_index(drop=True)
        d_data.columns = unique_headers
        for col in unique_headers:
            var_labels[col] = str(col)

        return {
            "df": d_data,
            "variable_labels": var_labels,
            "profile": "generic",
            "headers_stripped": h_idx + 1
        }


def propose_cleaning_repairs(df_raw, rules_config=None, bounds_dict=None, profile_info=None):
    """
    Non-destructive forensic scanner generating a catalog of proposed repairs
    for interactive before-and-after review and per-column acceptance.
    """
    proposals = []
    n_rows = len(df_raw)
    n_cols = df_raw.shape[1]
    total_cells = n_rows * max(n_cols, 1)
    defect_cells = 0

    # 1. Blank separator rows
    na_counts = df_raw.isna().sum(axis=1)
    blank_rows = list(df_raw.index[na_counts == n_cols])
    if blank_rows:
        defect_cells += len(blank_rows) * n_cols
        proposals.append({
            "proposal_id": "structure::blank_rows",
            "rule_id": "drop_blanks",
            "rule_name": "Blank Separator Rows",
            "category": "Structure",
            "column": "All Columns (Table-wide)",
            "cells_affected": len(blank_rows),
            "pct_affected": round(100.0 * len(blank_rows) / max(n_rows, 1), 1),
            "examples": [{"row": int(r) + 1, "before": "Empty Row", "after": "Drop Row"} for r in blank_rows[:3]],
            "default_accepted": True
        })

    # 2. Subtotal & Summary Rows
    summary_indices = []
    for idx in df_raw.index:
        first_few = [str(df_raw.iloc[idx, c]).strip().lower() for c in range(min(5, n_cols)) if pd.notna(df_raw.iloc[idx, c])]
        for text in first_few:
            if any(k in text for k in SUMMARY_KEYWORDS):
                summary_indices.append((idx, text))
                break
    if summary_indices:
        defect_cells += len(summary_indices) * n_cols
        proposals.append({
            "proposal_id": "structure::summary_rows",
            "rule_id": "drop_summaries",
            "rule_name": "Summary & Subtotal Rows",
            "category": "Structure",
            "column": "All Columns (Table-wide)",
            "cells_affected": len(summary_indices),
            "pct_affected": round(100.0 * len(summary_indices) / max(n_rows, 1), 1),
            "examples": [{"row": int(idx) + 1, "before": text[:35], "after": "Drop Summary"} for idx, text in summary_indices[:3]],
            "default_accepted": True
        })

    # 3. Disguised Missing Sentinels
    for col in df_raw.columns:
        s = df_raw[col]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            mask = s.astype(str).str.strip().str.lower().isin(SENTINEL_VALUES)
            count = int(mask.sum())
            if count > 0:
                defect_cells += count
                ex = [{"row": int(idx) + 1, "before": str(s.loc[idx]), "after": "NaN"} for idx in df_raw.index[mask][:3]]
                proposals.append({
                    "proposal_id": f"sentinels::{col}",
                    "rule_id": "clean_sentinels",
                    "rule_name": "Disguised Sentinels -> NaN",
                    "category": "Missing Data",
                    "column": str(col),
                    "cells_affected": count,
                    "pct_affected": round(100.0 * count / max(n_rows, 1), 1),
                    "examples": ex,
                    "default_accepted": True
                })

    # 4. Excel Date Corruptions
    for col in df_raw.columns:
        s = df_raw[col]
        dt_mask = s.apply(lambda v: isinstance(v, (datetime.datetime, datetime.date, pd.Timestamp)) or bool(re.match(r"^20\d\d-\d{1,2}-\d{1,2}", str(v).strip())))
        count = int(dt_mask.sum())
        if count > 0:
            defect_cells += count
            ex = [{"row": int(idx) + 1, "before": str(s.loc[idx]), "after": fix_excel_date_range(s.loc[idx])} for idx in df_raw.index[dt_mask][:3]]
            proposals.append({
                "proposal_id": f"repair_dates::{col}",
                "rule_id": "repair_dates",
                "rule_name": "Repair Excel Date Auto-Conversions",
                "category": "Data Integrity",
                "column": str(col),
                "cells_affected": count,
                "pct_affected": round(100.0 * count / max(n_rows, 1), 1),
                "examples": ex,
                "default_accepted": True
            })

    # 5. Mojibake Text Encoding Repair
    for col in df_raw.columns:
        s = df_raw[col]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            moji_mask = s.apply(lambda v: isinstance(v, str) and (repair_mojibake_encoding(v) != v))
            count = int(moji_mask.sum())
            if count > 0:
                defect_cells += count
                ex = [{"row": int(idx) + 1, "before": str(s.loc[idx]), "after": repair_mojibake_encoding(s.loc[idx])} for idx in df_raw.index[moji_mask][:3]]
                proposals.append({
                    "proposal_id": f"mojibake::{col}",
                    "rule_id": "repair_mojibake",
                    "rule_name": "Mojibake & Text Encoding Repair",
                    "category": "Text Hygiene",
                    "column": str(col),
                    "cells_affected": count,
                    "pct_affected": round(100.0 * count / max(n_rows, 1), 1),
                    "examples": ex,
                    "default_accepted": True
                })

    # 6. Near-Duplicate Category Clustering
    for col in df_raw.columns:
        s = df_raw[col]
        if (s.dtype == object or pd.api.types.is_string_dtype(s)) and 2 <= s.nunique() <= 35:
            clusters = cluster_near_duplicate_categories(s)
            if clusters:
                affected = int(s.isin(clusters.keys()).sum())
                defect_cells += affected
                ex = [{"row": 0, "before": k, "after": v} for k, v in list(clusters.items())[:3]]
                proposals.append({
                    "proposal_id": f"cluster::{col}",
                    "rule_id": "cluster_categories",
                    "rule_name": "OpenRefine-Style Category Clustering",
                    "category": "Categorical Harmonization",
                    "column": str(col),
                    "cells_affected": affected,
                    "pct_affected": round(100.0 * affected / max(n_rows, 1), 1),
                    "examples": ex,
                    "mapping": clusters,
                    "default_accepted": True
                })

    # 7. Likert Verbal-to-Numeric Recoding
    for col in df_raw.columns:
        s = df_raw[col]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            s_clean = s.apply(repair_mojibake_encoding).astype(str).str.strip().str.lower()
            likert_mask = s_clean.isin(LIKERT_TEXT_MAP.keys())
            count = int(likert_mask.sum())
            if count >= 2 and (count / max(len(s.dropna()), 1)) >= 0.4:
                defect_cells += count
                ex = []
                for idx in df_raw.index[likert_mask][:3]:
                    val_str = repair_mojibake_encoding(s.loc[idx]).strip().lower()
                    ex.append({"row": int(idx) + 1, "before": str(s.loc[idx]), "after": LIKERT_TEXT_MAP.get(val_str, np.nan)})
                proposals.append({
                    "proposal_id": f"map_likert::{col}",
                    "rule_id": "map_likert",
                    "rule_name": "Likert Recoding (Text -> 0..5/7 Numeric)",
                    "category": "Psychometrics",
                    "column": str(col),
                    "cells_affected": count,
                    "pct_affected": round(100.0 * count / max(n_rows, 1), 1),
                    "examples": ex,
                    "default_accepted": True
                })

    # 8. Impossible / Out-of-Range Domain Values
    default_bounds = {"age": (10, 115), "percentage": (0, 100), "pct": (0, 100), "tenure": (0, 65)}
    bounds = {**default_bounds, **(bounds_dict or {})}
    for col in df_raw.columns:
        c_low = str(col).lower()
        matched_bound = None
        for k_term, b_vals in bounds.items():
            if k_term in c_low:
                matched_bound = b_vals
                break
        if matched_bound:
            min_b, max_b = matched_bound
            s_num = pd.to_numeric(df_raw[col], errors='coerce')
            out_mask = s_num.notna() & ((s_num < min_b) | (s_num > max_b))
            count = int(out_mask.sum())
            if count > 0:
                defect_cells += count
                ex = [{"row": int(idx) + 1, "before": f"{s_num.loc[idx]} [Outside {min_b}-{max_b}]", "after": "NaN (Flagged)"} for idx in df_raw.index[out_mask][:3]]
                proposals.append({
                    "proposal_id": f"impossible::{col}",
                    "rule_id": "impossible_values",
                    "rule_name": f"Out-of-Bounds Values [{min_b}..{max_b}]",
                    "category": "Validation & Bounds",
                    "column": str(col),
                    "cells_affected": count,
                    "pct_affected": round(100.0 * count / max(n_rows, 1), 1),
                    "examples": ex,
                    "bounds": matched_bound,
                    "default_accepted": True
                })

    # 9. Multi-Select 'Check all that apply' Splitting
    for col in df_raw.columns:
        s = df_raw[col]
        if (s.dtype == object or pd.api.types.is_string_dtype(s)) and s.nunique() > 2:
            has_delim = s.dropna().astype(str).str.contains(r"[;,]", regex=True).sum()
            if has_delim >= 2:
                opts = set()
                for v in s.dropna():
                    parts = re.split(r"[;,]\s*", str(v).strip())
                    for p in parts:
                        if p: opts.add(p.strip())
                if 2 <= len(opts) <= 25:
                    proposals.append({
                        "proposal_id": f"multiselect::{col}",
                        "rule_id": "split_multiselect",
                        "rule_name": f"Split Multi-Select ({len(opts)} Choices)",
                        "category": "Structure & Expansion",
                        "column": str(col),
                        "cells_affected": int(len(s.dropna())),
                        "pct_affected": round(100.0 * len(s.dropna()) / max(n_rows, 1), 1),
                        "examples": [{"row": 1, "before": str(s.dropna().iloc[0])[:40], "after": f"Expand {len(opts)} binary columns"}],
                        "options": sorted(list(opts)),
                        "default_accepted": False
                    })

    # 10. Duplicate Respondents
    dup_info = detect_duplicate_respondents(df_raw)
    if dup_info["exact_duplicates"] > 0 or dup_info["id_duplicates"] > 0:
        n_dups = dup_info["exact_duplicates"] + dup_info["id_duplicates"]
        defect_cells += n_dups * n_cols
        proposals.append({
            "proposal_id": "duplicates::all",
            "rule_id": "flag_duplicates",
            "rule_name": "Flag / Deduplicate Duplicate Respondents",
            "category": "Respondent Integrity",
            "column": "All Columns (Table-wide)",
            "cells_affected": n_dups,
            "pct_affected": round(100.0 * n_dups / max(n_rows, 1), 1),
            "examples": [{"row": 0, "before": f"{n_dups} duplicate records", "after": "Flag / Keep first record"}],
            "default_accepted": False
        })

    health_score = max(0, min(100, round(100.0 - (defect_cells * 2.5 / max(total_cells, 1)) * 100.0, 1)))

    return {
        "proposals": proposals,
        "total_proposals": len(proposals),
        "total_cells": total_cells,
        "defect_cells": defect_cells,
        "health_score": health_score,
        "is_success": True
    }


def apply_accepted_repairs(df_raw, accepted_ids, proposals=None, tidy_names=False, base_variable_labels=None):
    """
    Executes user-accepted repairs non-destructively, returning the cleaned dataset,
    a rule-by-column Change Log, a granular cell-by-cell Audit Trail, and Codebook metadata.
    """
    if proposals is None:
        prop_res = propose_cleaning_repairs(df_raw)
        proposals = prop_res["proposals"]

    accepted_prop_map = {p["proposal_id"]: p for p in proposals if p["proposal_id"] in accepted_ids}
    d = df_raw.copy()
    rule_changelog = []
    cell_audit = []
    step_num = 1
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    var_labels = dict(base_variable_labels or {})
    val_labels = {}

    # Step 1: Drop blank rows if accepted
    if "structure::blank_rows" in accepted_prop_map:
        p = accepted_prop_map["structure::blank_rows"]
        na_counts = d.isna().sum(axis=1)
        blank_idx = d.index[na_counts == d.shape[1]]
        if len(blank_idx) > 0:
            for b_idx in blank_idx:
                cell_audit.append({"Excel_Row": int(b_idx) + 2, "Column": "(All Columns)", "Rule_ID": "drop_blanks", "Value_Before": "Empty Row", "Value_After": "Row Removed"})
            d = d.drop(index=blank_idx).reset_index(drop=True)
            rule_changelog.append({"Step": step_num, "Rule_ID": "drop_blanks", "Rule_Name": p["rule_name"], "Column": "(All Columns)", "Cells_Changed": len(blank_idx), "Example_Before": "Empty Row", "Example_After": "Row Removed", "Timestamp": now_str})
            step_num += 1

    # Step 2: Drop summaries if accepted
    if "structure::summary_rows" in accepted_prop_map:
        p = accepted_prop_map["structure::summary_rows"]
        d, dropped_cnt = strip_summary_rows(d)
        if dropped_cnt > 0:
            rule_changelog.append({"Step": step_num, "Rule_ID": "drop_summaries", "Rule_Name": p["rule_name"], "Column": "(All Columns)", "Cells_Changed": dropped_cnt, "Example_Before": "Summary / Total Row", "Example_After": "Row Removed", "Timestamp": now_str})
            step_num += 1

    # Step 3: Mojibake repair
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "repair_mojibake":
            col = p["column"]
            if col in d.columns:
                cells_changed = 0
                ex_b, ex_a = None, None
                for idx in d.index:
                    val = d.loc[idx, col]
                    if isinstance(val, str):
                        repaired = repair_mojibake_encoding(val)
                        if repaired != val:
                            d.loc[idx, col] = repaired
                            cells_changed += 1
                            cell_audit.append({"Excel_Row": int(idx) + 2, "Column": col, "Rule_ID": p["rule_id"], "Value_Before": str(val), "Value_After": str(repaired)})
                            if ex_b is None: ex_b, ex_a = str(val), str(repaired)
                if cells_changed > 0:
                    rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": cells_changed, "Example_Before": ex_b, "Example_After": ex_a, "Timestamp": now_str})
                    step_num += 1

    # Step 4: Disguised Sentinels -> NaN
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "clean_sentinels":
            col = p["column"]
            if col in d.columns:
                cells_changed = 0
                ex_b, ex_a = None, None
                for idx in d.index:
                    val = d.loc[idx, col]
                    if isinstance(val, str) and val.strip().lower() in SENTINEL_VALUES:
                        d.loc[idx, col] = np.nan
                        cells_changed += 1
                        cell_audit.append({"Excel_Row": int(idx) + 2, "Column": col, "Rule_ID": p["rule_id"], "Value_Before": str(val), "Value_After": "NaN"})
                        if ex_b is None: ex_b, ex_a = str(val), "NaN"
                if cells_changed > 0:
                    rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": cells_changed, "Example_Before": ex_b, "Example_After": ex_a, "Timestamp": now_str})
                    step_num += 1

    # Step 5: Excel Date Bugs
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "repair_dates":
            col = p["column"]
            if col in d.columns:
                cells_changed = 0
                ex_b, ex_a = None, None
                for idx in d.index:
                    val = d.loc[idx, col]
                    repaired = fix_excel_date_range(val)
                    if str(val) != str(repaired):
                        d.loc[idx, col] = repaired
                        cells_changed += 1
                        cell_audit.append({"Excel_Row": int(idx) + 2, "Column": col, "Rule_ID": p["rule_id"], "Value_Before": str(val), "Value_After": str(repaired)})
                        if ex_b is None: ex_b, ex_a = str(val), str(repaired)
                if cells_changed > 0:
                    rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": cells_changed, "Example_Before": ex_b, "Example_After": ex_a, "Timestamp": now_str})
                    step_num += 1

    # Step 6: Category Clustering
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "cluster_categories":
            col = p["column"]
            if col in d.columns:
                mapping = p.get("mapping", {})
                cells_changed = 0
                ex_b, ex_a = None, None
                for idx in d.index:
                    val = str(d.loc[idx, col]).strip()
                    if val in mapping:
                        target = mapping[val]
                        d.loc[idx, col] = target
                        cells_changed += 1
                        cell_audit.append({"Excel_Row": int(idx) + 2, "Column": col, "Rule_ID": p["rule_id"], "Value_Before": str(val), "Value_After": str(target)})
                        if ex_b is None: ex_b, ex_a = str(val), str(target)
                if cells_changed > 0:
                    rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": cells_changed, "Example_Before": ex_b, "Example_After": ex_a, "Timestamp": now_str})
                    step_num += 1

    # Step 7: Impossible Values
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "impossible_values":
            col = p["column"]
            if col in d.columns:
                min_b, max_b = p.get("bounds", (10, 115))
                cells_changed = 0
                ex_b, ex_a = None, None
                flag_col = f"{col}_out_of_range_flag"
                d[flag_col] = 0
                for idx in d.index:
                    val = pd.to_numeric(d.loc[idx, col], errors="coerce")
                    if pd.notna(val) and (val < min_b or val > max_b):
                        d.loc[idx, col] = np.nan
                        d.loc[idx, flag_col] = 1
                        cells_changed += 1
                        cell_audit.append({"Excel_Row": int(idx) + 2, "Column": col, "Rule_ID": p["rule_id"], "Value_Before": str(val), "Value_After": f"NaN (Flagged in {flag_col})"})
                        if ex_b is None: ex_b, ex_a = str(val), "NaN"
                if cells_changed > 0:
                    rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": cells_changed, "Example_Before": ex_b, "Example_After": ex_a, "Timestamp": now_str})
                    step_num += 1

    # Step 8: Likert Scale Recoding
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "map_likert":
            col = p["column"]
            if col in d.columns:
                cells_changed = 0
                ex_b, ex_a = None, None
                col_val_labels = {}
                for idx in d.index:
                    val = d.loc[idx, col]
                    if isinstance(val, str):
                        v_low = repair_mojibake_encoding(val).strip().lower()
                        if v_low in LIKERT_TEXT_MAP:
                            num_code = LIKERT_TEXT_MAP[v_low]
                            d.loc[idx, col] = num_code
                            col_val_labels[num_code] = val.strip().title()
                            cells_changed += 1
                            cell_audit.append({"Excel_Row": int(idx) + 2, "Column": col, "Rule_ID": p["rule_id"], "Value_Before": str(val), "Value_After": str(num_code)})
                            if ex_b is None: ex_b, ex_a = str(val), str(num_code)
                if cells_changed > 0:
                    d[col] = pd.to_numeric(d[col], errors="coerce")
                    val_labels[col] = col_val_labels
                    rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": cells_changed, "Example_Before": ex_b, "Example_After": ex_a, "Timestamp": now_str})
                    step_num += 1

    # Step 9: Multi-Select Splitting
    for p_id, p in accepted_prop_map.items():
        if p["rule_id"] == "split_multiselect":
            col = p["column"]
            if col in d.columns:
                options = p.get("options", [])
                for opt in options:
                    clean_opt = re.sub(r"[^\w]", "_", opt.strip()).strip("_")
                    opt_col = f"{col}__{clean_opt}"
                    d[opt_col] = d[col].apply(lambda v: 1 if pd.notna(v) and opt in re.split(r"[;,]\s*", str(v).strip()) else 0)
                    var_labels[opt_col] = f"{var_labels.get(col, col)} [{opt}]"
                    val_labels[opt_col] = {0: "Not selected", 1: "Selected"}
                rule_changelog.append({"Step": step_num, "Rule_ID": p["rule_id"], "Rule_Name": p["rule_name"], "Column": col, "Cells_Changed": len(d), "Example_Before": "Multi-select string", "Example_After": f"Expanded {len(options)} binary columns", "Timestamp": now_str})
                step_num += 1

    # Step 10: Deduplication if accepted
    if "duplicates::all" in accepted_prop_map:
        p = accepted_prop_map["duplicates::all"]
        before_cnt = len(d)
        d = d.drop_duplicates().reset_index(drop=True)
        dropped_dups = before_cnt - len(d)
        if dropped_dups > 0:
            rule_changelog.append({"Step": step_num, "Rule_ID": "drop_duplicates", "Rule_Name": p["rule_name"], "Column": "(All Columns)", "Cells_Changed": dropped_dups, "Example_Before": "Duplicate Row", "Example_After": "Deduplicated", "Timestamp": now_str})
            step_num += 1

    # Step 11: Tidy variable names if requested
    if tidy_names:
        tidy_cols, name_map = generate_tidy_variable_names(d.columns)
        new_var_labels = {}
        for old_c, new_c in zip(d.columns, tidy_cols):
            new_var_labels[new_c] = var_labels.get(old_c, str(old_c))
        var_labels = new_var_labels
        d.columns = tidy_cols
        rule_changelog.append({"Step": step_num, "Rule_ID": "tidy_names", "Rule_Name": "Standardize Tidy Variable Names", "Column": "(All Columns)", "Cells_Changed": len(d.columns), "Example_Before": "Verbose Question String", "Example_After": "tidy_snake_case", "Timestamp": now_str})
        step_num += 1

    # Auto-convert purely numeric object columns to proper numeric types
    for c in d.columns:
        s = d[c]
        if isinstance(s, pd.Series) and s.dtype == object:
            try:
                s_num = pd.to_numeric(s, errors="raise")
                d[c] = s_num
            except (ValueError, TypeError):
                pass

    df_rules = pd.DataFrame(rule_changelog)
    df_cells = pd.DataFrame(cell_audit)
    codebook_meta = {
        "variable_labels": var_labels,
        "value_labels": val_labels
    }

    return {
        "df_cleaned": d,
        "df_rule_changelog": df_rules,
        "df_cell_audit": df_cells,
        "codebook_metadata": codebook_meta,
        "is_success": True
    }


def export_formatted_excel_workbook(df_cleaned, codebook_df=None, rule_changelog_df=None, cell_audit_df=None):
    """
    Exports a publication-grade, multi-sheet formatted Excel workbook (.xlsx):
    - Cleaned_Data, Codebook, Change_Log, Cell_Audit_Trail
    - Frozen row 1 panes, styled navy headers, auto-adjusted column widths,
      explicit number formats, and formula injection sanitization.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    output = io.BytesIO()
    wb = openpyxl.Workbook()
    ws_data = wb.active
    ws_data.title = "Cleaned_Data"

    sheets = [("Cleaned_Data", df_cleaned, ws_data)]
    if codebook_df is not None and not codebook_df.empty:
        ws_code = wb.create_sheet("Codebook")
        sheets.append(("Codebook", codebook_df, ws_code))
    if rule_changelog_df is not None and not rule_changelog_df.empty:
        ws_log = wb.create_sheet("Change_Log")
        sheets.append(("Change_Log", rule_changelog_df, ws_log))
    if cell_audit_df is not None and not cell_audit_df.empty:
        ws_audit = wb.create_sheet("Cell_Audit_Trail")
        sheets.append(("Cell_Audit_Trail", cell_audit_df, ws_audit))

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    data_font = Font(name="Segoe UI", size=10)
    thin_border = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB')
    )

    for s_name, df_s, ws in sheets:
        ws.freeze_panes = "A2"
        # Header Row
        for col_idx, col_name in enumerate(df_s.columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=str(col_name))
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Data Rows
        for row_idx, row in enumerate(df_s.itertuples(index=False), start=2):
            for col_idx, val in enumerate(row, start=1):
                # Sanitize formula injection
                if isinstance(val, str) and len(val) > 0 and val[0] in ('=', '+', '-', '@', '\t', '\r', '\n'):
                    safe_val = "'" + val
                elif pd.isna(val):
                    safe_val = None
                else:
                    safe_val = val

                c = ws.cell(row=row_idx, column=col_idx, value=safe_val)
                c.font = data_font
                c.border = thin_border
                if isinstance(safe_val, float):
                    c.number_format = "0.000" if abs(safe_val - round(safe_val, 2)) > 1e-4 else "0.00"
                elif isinstance(safe_val, int):
                    c.number_format = "#,##0"

        # Auto column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col[:120]:
                v_str = str(cell.value or "")
                if len(v_str) > max_len:
                    max_len = len(v_str)
            ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 48))

    wb.save(output)
    return output.getvalue()


def export_spss_stata_bytes(df_cleaned, variable_labels=None, value_labels=None, fmt="sav"):
    """
    Exports binary SPSS (.sav) or Stata (.dta) files with preserved variable and value labels.
    """
    import tempfile
    import pyreadstat

    # Ensure clean variable names for SPSS/Stata compatibility (no spaces or special chars)
    df_export = df_cleaned.copy()
    clean_cols = []
    col_mapping = {}
    for col in df_export.columns:
        c_clean = re.sub(r"[^\w]", "_", str(col).strip()).strip("_")
        if not c_clean or c_clean[0].isdigit():
            c_clean = f"v_{c_clean}"
        clean_cols.append(c_clean)
        col_mapping[str(col)] = c_clean
    clean_cols = make_columns_unique(clean_cols)
    df_export.columns = clean_cols

    # Map variable labels
    var_labels_mapped = {}
    if variable_labels:
        for old_c, lbl in variable_labels.items():
            new_c = col_mapping.get(str(old_c), str(old_c))
            var_labels_mapped[new_c] = str(lbl)[:250]

    # Map value labels
    val_labels_mapped = {}
    if value_labels:
        for old_c, lbl_dict in value_labels.items():
            new_c = col_mapping.get(str(old_c), str(old_c))
            clean_dict = {}
            for k, v in lbl_dict.items():
                try:
                    clean_dict[float(k)] = str(v)
                except (ValueError, TypeError):
                    clean_dict[str(k)] = str(v)
            val_labels_mapped[new_c] = clean_dict

    suffix = ".sav" if fmt == "sav" else ".dta"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        tmp_path = f.name

    try:
        if fmt == "sav":
            pyreadstat.write_sav(
                df_export,
                tmp_path,
                column_labels=var_labels_mapped if var_labels_mapped else None,
                variable_value_labels=val_labels_mapped if val_labels_mapped else None
            )
        else:
            pyreadstat.write_dta(
                df_export,
                tmp_path,
                column_labels=var_labels_mapped if var_labels_mapped else None,
                variable_value_labels=val_labels_mapped if val_labels_mapped else None
            )
        with open(tmp_path, "rb") as f_read:
            data_bytes = f_read.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return data_bytes


def format_apa7_table_html(df, table_num="Table 1", title="Descriptive Statistics and Model Properties", note=None):
    """
    Renders publication-ready APA 7th Edition formatted tables in HTML with standard horizontal rules.
    """
    stat_patterns = {
        r"\bM\b": "<i>M</i>",
        r"\bSD\b": "<i>SD</i>",
        r"\bSE\b": "<i>SE</i>",
        r"\bt\b": "<i>t</i>",
        r"\bF\b": "<i>F</i>",
        r"\bp\b": "<i>p</i>",
        r"\br\b": "<i>r</i>",
        r"\bz\b": "<i>z</i>",
        r"\bB\b": "<i>B</i>",
        r"\bN\b": "<i>N</i>",
        r"\bdf\b": "<i>df</i>",
        r"\bCI\b": "<i>CI</i>",
        r"α": "<i>α</i>",
        r"ω": "<i>ω</i>",
        r"χ²": "<i>χ</i>²",
    }
    headers_html = []
    for c in df.columns:
        c_str = str(c)
        for pat, repl in stat_patterns.items():
            c_str = re.sub(pat, repl, c_str)
        headers_html.append(f"<th style='padding: 6px 12px; border-bottom: 1px solid #111; font-weight: 600;'>{c_str}</th>")

    rows_html = []
    for _, row in df.iterrows():
        cells = []
        for i, val in enumerate(row):
            align = "left" if i == 0 else "right"
            val_str = f"{val:.3f}" if isinstance(val, float) else str(val if pd.notna(val) else "-")
            cells.append(f"<td style='padding: 5px 12px; text-align: {align}; border: none;'>{val_str}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    note_html = f"<div style='font-size: 0.85rem; margin-top: 6px; color: #4B5563;'><i>Note.</i> {note}</div>" if note else ""

    html = f"""
    <div style="font-family: 'Times New Roman', Times, serif; color: #111; margin: 16px 0;">
        <div style="font-weight: bold; font-size: 1rem;">{table_num}</div>
        <div style="font-style: italic; font-size: 0.95rem; margin-bottom: 8px;">{title}</div>
        <table style="border-collapse: collapse; width: 100%; border-top: 2px solid #111; border-bottom: 2px solid #111; font-size: 0.9rem;">
            <thead><tr>{"".join(headers_html)}</tr></thead>
            <tbody>{"".join(rows_html)}</tbody>
        </table>
        {note_html}
    </div>
    """
    return html


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


def compute_longstring(row):
    """Calculates the maximum consecutive identical non-null responses in a row."""
    vals = row.dropna().values
    if len(vals) == 0:
        return 0
    max_len = 1
    curr_len = 1
    for i in range(1, len(vals)):
        if vals[i] == vals[i - 1]:
            curr_len += 1
            if curr_len > max_len:
                max_len = curr_len
        else:
            curr_len = 1
    return max_len


def sanitize_spreadsheet_formulas(df):
    """
    Prevents CSV / Spreadsheet Formula Injection (CWE-1236).
    Prefixes any text cell beginning with '=', '+', '-', '@' with a single quote (').
    Preserves negative numbers and standard numeric values.
    """
    cleaned = df.copy()
    for col in cleaned.select_dtypes(include=['object', 'string']).columns:
        cleaned[col] = cleaned[col].apply(
            lambda val: f"'{val}" if isinstance(val, str) and val.startswith(('=', '+', '-', '@')) and not (val.startswith('-') and val[1:].replace('.', '', 1).isdigit()) else val
        )
    return cleaned


def compute_careless_response_suite(df, item_cols, longstring_thresh=6, irv_percentile=5, mahalanobis_p=0.001, completion_time_col=None, min_time_seconds=None):
    """
    Comprehensive Careless Response & Inattentive Survey Quality Suite (aligned with R package 'careless').
    Computes:
    1. Longstring: Maximum run length of identical consecutive answers.
    2. IRV (Intra-individual Response Variability): Standard deviation across scale items per respondent.
       Low IRV flags straightlining; high IRV flags random alternating responding.
    3. Mahalanobis Distance (D^2): Multivariate outlier detection with chi-square p-values.
    4. Even-Odd Consistency: Split-half difference across scale items.
    5. Speeding Flag: Flags respondents completing survey faster than min_time_seconds.
    6. Careless_Flag: Composite flag for sensitivity analysis (Flag, Never Delete principle).
    """
    if not item_cols or len(item_cols) < 2:
        return None

    valid_cols = [c for c in item_cols if c in df.columns]
    sub = df[valid_cols].apply(pd.to_numeric, errors='coerce')
    n_resp, k_items = sub.shape

    # 1. Longstring
    longstrings = sub.apply(compute_longstring, axis=1)

    # 2. IRV
    irvs = sub.std(axis=1, ddof=1, skipna=True)
    valid_irvs = irvs.dropna()
    irv_low_cutoff = float(np.nanpercentile(valid_irvs, irv_percentile)) if len(valid_irvs) > 0 else 0.0
    irv_high_cutoff = float(np.nanpercentile(valid_irvs, 100 - irv_percentile)) if len(valid_irvs) > 0 else 999.0

    # 3. Mahalanobis D2
    clean_cases = sub.dropna()
    d2_series = pd.Series(np.nan, index=df.index)
    d2_p_series = pd.Series(np.nan, index=df.index)

    if len(clean_cases) > k_items:
        try:
            cov_mat = np.cov(clean_cases.values, rowvar=False)
            inv_cov = np.linalg.pinv(cov_mat)
            diff = clean_cases.values - clean_cases.mean().values
            d2 = np.sum((diff @ inv_cov) * diff, axis=1)
            p_vals = 1.0 - stats.chi2.cdf(d2, df=k_items)
            d2_series.loc[clean_cases.index] = np.round(d2, 2)
            d2_p_series.loc[clean_cases.index] = np.round(p_vals, 4)
        except Exception:
            pass

    # 4. Even-Odd Consistency
    even_odd_diff = pd.Series(np.nan, index=df.index)
    if k_items >= 4:
        even_cols = sub.columns[::2]
        odd_cols = sub.columns[1::2]
        even_means = sub[even_cols].mean(axis=1)
        odd_means = sub[odd_cols].mean(axis=1)
        even_odd_diff = np.abs(even_means - odd_means).round(3)

    # Flags
    flag_ls = (longstrings >= int(longstring_thresh))
    flag_irv_low = (irvs <= irv_low_cutoff)
    flag_irv_high = (irvs >= irv_high_cutoff)
    flag_irv = flag_irv_low | flag_irv_high
    flag_d2 = (d2_p_series < float(mahalanobis_p))

    flag_speed = pd.Series(False, index=df.index)
    if completion_time_col and completion_time_col in df.columns and min_time_seconds:
        time_vals = pd.to_numeric(df[completion_time_col], errors='coerce')
        flag_speed = (time_vals < float(min_time_seconds)) & time_vals.notna()

    combined_flag = flag_ls | flag_irv | flag_d2 | flag_speed

    reasons = []
    for idx in df.index:
        r_list = []
        if flag_ls.loc[idx]: r_list.append(f"Longstring (≥{longstring_thresh})")
        if flag_irv_low.loc[idx]: r_list.append(f"Low IRV (≤{irv_low_cutoff:.2f})")
        if flag_irv_high.loc[idx]: r_list.append(f"High IRV (≥{irv_high_cutoff:.2f})")
        if flag_d2.loc[idx]: r_list.append(f"Multivariate Outlier (p<{mahalanobis_p})")
        if flag_speed.loc[idx]: r_list.append(f"Speeding (<{min_time_seconds}s)")
        reasons.append(", ".join(r_list) if r_list else "Clean")

    audit_df = pd.DataFrame({
        "Respondent_Index": df.index,
        "Items_Answered": sub.notna().sum(axis=1),
        "Longstring": longstrings,
        "IRV_SD": irvs.round(3),
        "Mahalanobis_D2": d2_series,
        "Mahalanobis_p": d2_p_series,
        "Even_Odd_Diff": even_odd_diff,
        "Careless_Flag": combined_flag.astype(int),
        "Flag_Reasons": reasons,
    })

    return {
        "audit_df": audit_df,
        "n_total": n_resp,
        "n_flagged": int(combined_flag.sum()),
        "pct_flagged": round(100.0 * combined_flag.sum() / max(n_resp, 1), 1),
        "clean_indices": list(df.index[~combined_flag]),
        "flagged_indices": list(df.index[combined_flag]),
        "breakdown": {
            "longstring": int(flag_ls.sum()),
            "irv_low": int(flag_irv_low.sum()),
            "irv_high": int(flag_irv_high.sum()),
            "mahalanobis": int(flag_d2.sum()),
            "speeding": int(flag_speed.sum()),
        },
        "cutoffs": {
            "longstring": int(longstring_thresh),
            "irv_low": round(irv_low_cutoff, 3),
            "irv_high": round(irv_high_cutoff, 3),
            "mahalanobis_p": mahalanobis_p,
        },
        "is_success": True
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






# ===========================================================================
# Milestone B: Principled Missing Data, Advanced Psychometrics & Causal Modeling
# ===========================================================================

def _patch_factor_analyzer_compat():
    """Ensures compatibility between factor_analyzer and modern scikit-learn (>= 1.6)."""
    try:
        import sklearn.utils.validation
        import factor_analyzer.factor_analyzer as fa_mod
        _orig_check = sklearn.utils.validation.check_array
        def _safe_check(*args, **kwargs):
            if 'force_all_finite' in kwargs:
                kwargs['ensure_all_finite'] = kwargs.pop('force_all_finite')
            return _orig_check(*args, **kwargs)
        fa_mod.check_array = _safe_check
        sklearn.utils.validation.check_array = _safe_check
    except Exception:
        pass


def compute_missingness_patterns(df, cols=None):
    """
    Diagnoses missingness patterns across survey variables.
    Identifies unique missing-data masks, case counts, per-variable rates,
    and returns plain-language guidance on MCAR, MAR, and MNAR (Little & Rubin, 2019).
    """
    if df is None or df.empty:
        return {"error": "Input dataframe is empty or invalid."}

    if cols is None:
        cols = [c for c in df.columns if df[c].isna().any()]
    else:
        cols = [c for c in cols if c in df.columns]

    if not cols:
        return {
            "is_empty": True,
            "message": "No missing data detected across the analyzed variables. Complete-case analysis is fully valid."
        }

    sub_df = df[cols].copy()
    n_total = len(sub_df)

    # 1. Per-variable missingness
    var_records = []
    for c in cols:
        n_miss = int(sub_df[c].isna().sum())
        n_valid = n_total - n_miss
        pct_miss = round(100.0 * n_miss / n_total, 2)
        var_records.append({
            "Variable": c,
            "Missing Cases (N)": n_miss,
            "Missing Rate (%)": pct_miss,
            "Valid Cases (N)": n_valid
        })
    df_var_missing = pd.DataFrame(var_records).sort_values("Missing Cases (N)", ascending=False).reset_index(drop=True)

    # 2. Pattern analysis
    # Mask: 0 = Observed, 1 = Missing
    mask_matrix = sub_df.isna().astype(int)
    pattern_series = mask_matrix.apply(lambda row: "".join(row.astype(str)), axis=1)
    pattern_counts = pattern_series.value_counts()

    pattern_records = []
    cum_pct = 0.0
    for idx, (pat_str, count) in enumerate(pattern_counts.items(), start=1):
        pct = round(100.0 * count / n_total, 2)
        cum_pct = round(cum_pct + pct, 2)
        readable_desc = ", ".join([cols[i] for i, char in enumerate(pat_str) if char == "1"])
        if not readable_desc:
            readable_desc = "Complete Case (No Missing Values)"
        else:
            readable_desc = f"Missing in: {readable_desc}"

        pattern_records.append({
            "Pattern #": f"Pattern {idx}",
            "Missing Variables": readable_desc,
            "Pattern Binary Mask": pat_str,
            "Cases (N)": count,
            "Percentage (%)": pct,
            "Cumulative (%)": min(cum_pct, 100.0)
        })
    df_patterns = pd.DataFrame(pattern_records)

    # Guidance text
    guidance = (
        "**Methodological Diagnostic (Little & Rubin, 2019):**\n"
        "- **MCAR (Missing Completely at Random):** Missingness is purely random and independent of observed and unobserved data. "
        "Complete-case analysis is unbiased but discards valuable statistical power.\n"
        "- **MAR (Missing at Random):** Missingness is systematically related to observed survey variables (e.g., tenure, age, branch). "
        "Complete-case deletion introduces systematic sample-selection bias. Multiple Imputation (MICE) or Full Information Maximum Likelihood (FIML) "
        "is required to yield unbiased estimates and valid standard errors.\n"
        "- **MNAR (Missing Not at Random):** Missingness is related to the unobserved values themselves (e.g., sensitive performance or income non-response). "
        "Requires sensitivity analyses comparing Complete-Case vs. MICE-imputed estimates."
    )

    return {
        "df_var_missing": df_var_missing,
        "df_patterns": df_patterns,
        "total_patterns": len(pattern_counts),
        "total_cases": n_total,
        "complete_cases": int((sub_df.isna().sum(axis=1) == 0).sum()),
        "guidance": guidance,
        "is_success": True
    }


def compute_multiple_imputation_m2(df, model_type='linear', y_col=None, x_cols=None, m=20, random_state=42):
    """
    Multiple Imputation by Chained Equations (MICE) with Rubin's (1987) Rules Pooling.
    Supports Linear (OLS) and Binary Logistic Regression models.
    Produces side-by-side Complete-Case vs. MICE-Pooled sensitivity tables with Fraction of
    Missing Information (FMI) and Relative Efficiency (RE).
    """
    if df is None or df.empty:
        return {"error": "Input dataframe is empty or invalid."}
    if not y_col or y_col not in df.columns:
        return {"error": f"Dependent variable '{y_col}' not found in dataframe."}
    if not x_cols or not isinstance(x_cols, list):
        return {"error": "Predictor variables (x_cols) must be a non-empty list."}

    valid_x = [c for c in x_cols if c in df.columns and c != y_col]
    if not valid_x:
        return {"error": "No valid predictor variables selected."}

    # Ensure experimental iterative imputer is imported
    try:
        from sklearn.experimental import enable_iterative_imputer
        from sklearn.impute import IterativeImputer
    except Exception as e:
        return {"error": f"Failed to load sklearn IterativeImputer: {str(e)}"}

    import statsmodels.api as sm

    # Prepare numeric subset
    all_vars = [y_col] + valid_x
    sub_df = df[all_vars].apply(pd.to_numeric, errors="coerce")

    # MID rule (von Hippel, 2007): filter to cases where Y is observed
    sub_df = sub_df.dropna(subset=[y_col]).copy()
    n_sub = len(sub_df)
    if n_sub < len(valid_x) + 5:
        return {"error": f"Insufficient sample size ({n_sub} cases with observed outcome). Need at least {len(valid_x) + 5}."}

    # Complete Case Model (Listwise Deletion)
    df_cc = sub_df.dropna().copy()
    n_cc = len(df_cc)
    if n_cc < len(valid_x) + 2:
        return {"error": f"Too few complete cases ({n_cc}) to estimate baseline listwise deletion model."}

    X_cc = sm.add_constant(df_cc[valid_x])
    y_cc = df_cc[y_col]

    try:
        if model_type == "logistic":
            cc_model = sm.Logit(y_cc, X_cc).fit(disp=False)
        else:
            cc_model = sm.OLS(y_cc, X_cc).fit()
    except Exception as e:
        return {"error": f"Complete-case baseline model failed to converge: {str(e)}"}

    cc_params = cc_model.params
    cc_bse = cc_model.bse
    cc_pvalues = cc_model.pvalues

    # MICE Multiple Imputations & Rubin's Rules
    m = max(5, int(m))
    q_list = []
    u_list = []

    for k in range(m):
        imputer = IterativeImputer(
            max_iter=10,
            sample_posterior=True,
            random_state=random_state + k
        )
        try:
            imputed_arr = imputer.fit_transform(sub_df)
            df_k = pd.DataFrame(imputed_arr, columns=all_vars)
            X_k = sm.add_constant(df_k[valid_x])
            y_k = df_k[y_col]

            if model_type == "logistic":
                fit_k = sm.Logit(y_k, X_k).fit(disp=False)
            else:
                fit_k = sm.OLS(y_k, X_k).fit()

            q_list.append(fit_k.params)
            u_list.append(fit_k.bse ** 2)
        except Exception:
            continue

    actual_m = len(q_list)
    if actual_m < 3:
        return {"error": f"MICE imputation failed to converge on sufficient datasets ({actual_m}/{m} completed)."}

    # Rubin's (1987) Pooling
    Q_matrix = np.array(q_list)  # (m, p)
    U_matrix = np.array(u_list)  # (m, p)

    Q_bar = np.mean(Q_matrix, axis=0)
    U_bar = np.mean(U_matrix, axis=0)
    B = np.var(Q_matrix, axis=0, ddof=1)
    T = U_bar + (1.0 + 1.0 / actual_m) * B
    se_pool = np.sqrt(np.maximum(T, 1e-12))
    t_pool = Q_bar / se_pool

    # FMI & Relative Efficiency
    r = (1.0 + 1.0 / actual_m) * B / np.maximum(U_bar, 1e-12)
    nu_old = (actual_m - 1.0) * (1.0 + 1.0 / np.maximum(r, 1e-12)) ** 2
    fmi = np.clip((r + 2.0 / (nu_old + 3.0)) / (1.0 + r), 0.0, 1.0)
    re_eff = 1.0 / (1.0 + fmi / actual_m)

    # Barnard & Rubin (1999) Degrees of Freedom adjustment
    nu_com = max(1, n_sub - (len(valid_x) + 1))
    nu_obs = ((nu_com + 1.0) / (nu_com + 3.0)) * nu_com * (1.0 - fmi)
    nu_adj = np.where(nu_old + nu_obs > 0, (nu_old * nu_obs) / np.maximum(nu_old + nu_obs, 1e-12), nu_com)
    nu_adj = np.maximum(nu_adj, 1.0)

    p_pool = 2.0 * (1.0 - stats.t.cdf(np.abs(t_pool), df=nu_adj))
    t_crit = stats.t.ppf(0.975, df=nu_adj)
    ci_lower = Q_bar - t_crit * se_pool
    ci_upper = Q_bar + t_crit * se_pool

    # Format side-by-side comparison table
    param_names = list(cc_params.index)
    comparison_rows = []
    for idx, p_name in enumerate(param_names):
        b_cc = cc_params.get(p_name, np.nan)
        se_c = cc_bse.get(p_name, np.nan)
        p_c = cc_pvalues.get(p_name, np.nan)

        b_mice = Q_bar[idx]
        se_m = se_pool[idx]
        p_m = p_pool[idx]
        delta_b = b_mice - b_cc if pd.notna(b_cc) else np.nan

        star_cc = "***" if p_c < 0.001 else ("**" if p_c < 0.01 else ("*" if p_c < 0.05 else ""))
        star_mice = "***" if p_m < 0.001 else ("**" if p_m < 0.01 else ("*" if p_m < 0.05 else ""))

        comparison_rows.append({
            "Predictor": "Intercept" if p_name == "const" else p_name,
            "Complete-Case Coef (B)": round(b_cc, 4) if pd.notna(b_cc) else np.nan,
            "Complete-Case SE": round(se_c, 4) if pd.notna(se_c) else np.nan,
            "Complete-Case p": f"{p_c:.4f} {star_cc}".strip() if pd.notna(p_c) else "",
            "MICE Pooled Coef (B)": round(b_mice, 4),
            "MICE Pooled SE": round(se_m, 4),
            "MICE Pooled p": f"{p_m:.4f} {star_mice}".strip(),
            "Coef Shift (ΔB)": round(delta_b, 4),
            "FMI": round(float(fmi[idx]), 3),
            "Relative Efficiency": round(float(re_eff[idx]), 4),
            "95% CI Lower": round(float(ci_lower[idx]), 4),
            "95% CI Upper": round(float(ci_upper[idx]), 4)
        })

    df_comp = pd.DataFrame(comparison_rows)

    return {
        "comparison_table": df_comp,
        "n_total": len(df),
        "n_observed_y": n_sub,
        "n_complete_cases": n_cc,
        "m_imputations_requested": m,
        "m_imputations_completed": actual_m,
        "model_type": model_type,
        "is_success": True
    }


def compute_efa(df, items, n_factors=2, method='principal', rotation='varimax'):
    """
    Exploratory Factor Analysis (EFA) via factor_analyzer.
    Computes KMO sampling adequacy, Bartlett's test of sphericity,
    Horn's Parallel Analysis, factor loadings, and factor correlations.
    """
    _patch_factor_analyzer_compat()

    if df is None or df.empty:
        return {"error": "Dataframe is empty or invalid."}
    if not items or len(items) < 2:
        return {"error": "At least 2 items are required for factor analysis."}

    valid_items = [c for c in items if c in df.columns]
    if len(valid_items) < 2:
        return {"error": "Fewer than 2 valid item columns present in dataframe."}

    clean = df[valid_items].apply(pd.to_numeric, errors="coerce").dropna().copy()
    n_obs = len(clean)
    p_vars = len(valid_items)

    if n_obs < p_vars:
        return {"error": f"Insufficient complete cases ({n_obs}) for {p_vars} items. N must exceed number of variables."}

    try:
        from factor_analyzer import FactorAnalyzer, calculate_kmo, calculate_bartlett_sphericity
    except ImportError:
        return {"error": "factor-analyzer package is required. Run 'pip install factor-analyzer'."}

    # 1. KMO Sampling Adequacy
    try:
        kmo_per_var, kmo_total = calculate_kmo(clean)
        kmo_eval = (
            "Marvelous" if kmo_total >= 0.90 else
            "Meritorious" if kmo_total >= 0.80 else
            "Middling" if kmo_total >= 0.70 else
            "Mediocre" if kmo_total >= 0.60 else
            "Miserable" if kmo_total >= 0.50 else "Unacceptable"
        )
        kmo_table = pd.DataFrame({
            "Item": valid_items,
            "MSA": np.round(kmo_per_var, 3),
            "Assessment": [
                "Marvelous" if v >= 0.90 else "Meritorious" if v >= 0.80 else
                "Middling" if v >= 0.70 else "Mediocre" if v >= 0.60 else
                "Miserable" if v >= 0.50 else "Unacceptable (<0.50)" for v in kmo_per_var
            ]
        })
    except Exception as e:
        kmo_total = np.nan
        kmo_eval = f"Calculation failed: {str(e)}"
        kmo_table = pd.DataFrame()

    # 2. Bartlett's Test of Sphericity
    try:
        chi_sq, p_val = calculate_bartlett_sphericity(clean)
        df_bartlett = int(p_vars * (p_vars - 1) / 2)
        bartlett_res = {
            "chi2": round(float(chi_sq), 2),
            "df": df_bartlett,
            "p_value": float(p_val),
            "is_significant": bool(p_val < 0.05)
        }
    except Exception as e:
        bartlett_res = {"chi2": np.nan, "df": 0, "p_value": np.nan, "is_significant": False, "error": str(e)}

    # 3. Horn's Parallel Analysis
    try:
        corr_mat = clean.corr().values
        emp_eigvals, _ = np.linalg.eigh(corr_mat)
        emp_eigvals = np.sort(emp_eigvals)[::-1]

        # Simulate 50 random matrices
        n_sim = 50
        sim_eigvals = np.zeros((n_sim, p_vars))
        np.random.seed(42)
        for s in range(n_sim):
            rand_mat = np.random.normal(size=(n_obs, p_vars))
            r_corr = np.corrcoef(rand_mat, rowvar=False)
            r_eig, _ = np.linalg.eigh(r_corr)
            sim_eigvals[s, :] = np.sort(r_eig)[::-1]

        random_p95 = np.percentile(sim_eigvals, 95, axis=0)
        retain_flags = emp_eigvals > random_p95
        parallel_rec = int(np.sum(retain_flags))

        parallel_df = pd.DataFrame({
            "Factor": [f"Factor {i+1}" for i in range(p_vars)],
            "Empirical Eigenvalue": np.round(emp_eigvals, 3),
            "95th Pct Random Eigenvalue": np.round(random_p95, 3),
            "Retain Factor?": ["Retain" if f else "Drop" for f in retain_flags]
        })
    except Exception:
        parallel_df = pd.DataFrame()
        parallel_rec = n_factors

    # 4. Fit FactorAnalyzer
    method_norm = str(method).lower().strip()
    if method_norm in ["pa", "paf", "principal"]:
        fa_method = "principal"
    elif method_norm in ["ml", "mle"]:
        fa_method = "ml"
    elif method_norm in ["minres"]:
        fa_method = "minres"
    elif method_norm in ["uls"]:
        fa_method = "uls"
    else:
        fa_method = "principal"

    rot_norm = None if rotation in [None, "none", "None"] else str(rotation).lower().strip()

    n_factors = max(1, min(int(n_factors), p_vars))
    fa = FactorAnalyzer(n_factors=n_factors, method=fa_method, rotation=rot_norm)
    try:
        fa.fit(clean)
    except Exception as e:
        return {"error": f"FactorAnalyzer estimation failed: {str(e)}"}

    loadings = np.round(fa.loadings_, 3)
    communalities = np.round(fa.get_communalities(), 3)
    uniquenesses = np.round(fa.get_uniquenesses(), 3)

    loadings_cols = [f"Factor {i+1}" for i in range(n_factors)]
    df_loadings = pd.DataFrame(loadings, index=valid_items, columns=loadings_cols)
    df_loadings["Communality (h²)"] = communalities
    df_loadings["Uniqueness (u²)"] = uniquenesses
    df_loadings = df_loadings.reset_index().rename(columns={"index": "Item"})

    # Factor Variance
    var_tuple = fa.get_factor_variance()
    ss_loadings = np.round(var_tuple[0], 3)
    prop_var = np.round(var_tuple[1] * 100.0, 2)
    cum_var = np.round(var_tuple[2] * 100.0, 2)

    df_var = pd.DataFrame({
        "Metric": ["SS Loadings (Eigenvalues)", "Proportion of Variance (%)", "Cumulative Variance (%)"],
        **{f"Factor {i+1}": [ss_loadings[i], prop_var[i], cum_var[i]] for i in range(n_factors)}
    })

    # Factor correlation matrix (for oblique rotations)
    df_factor_corr = None
    if rot_norm in ["promax", "oblimin"] and n_factors > 1:
        try:
            df_factor_corr = pd.DataFrame(
                np.round(fa.phi_, 3),
                index=loadings_cols,
                columns=loadings_cols
            )
        except Exception:
            df_factor_corr = None

    return {
        "loadings_table": df_loadings,
        "variance_table": df_var,
        "kmo_total": round(float(kmo_total), 3) if pd.notna(kmo_total) else np.nan,
        "kmo_eval": kmo_eval,
        "kmo_table": kmo_table,
        "bartlett": bartlett_res,
        "parallel_analysis_table": parallel_df,
        "recommended_factors_parallel": parallel_rec,
        "factor_correlations": df_factor_corr,
        "n_obs": n_obs,
        "n_factors": n_factors,
        "method": fa_method,
        "rotation": rot_norm or "None (Unrotated)",
        "is_success": True
    }


def compute_advanced_psychometrics(df, construct_dict):
    """
    Construct Validity and Advanced Psychometric Evaluation.
    Computes:
    - Composite Reliability (CR / Raykov's rho)
    - Average Variance Extracted (AVE)
    - McDonald's Omega (ω)
    - Cronbach's Alpha (α)
    - Discriminant Validity via Fornell-Larcker Criterion
    - Discriminant Validity via Heterotrait-Monotrait Ratio (HTMT < 0.85/0.90)
    """
    if df is None or df.empty or not construct_dict or not isinstance(construct_dict, dict):
        return {"error": "Invalid dataframe or construct dictionary."}

    valid_constructs = {}
    for c_name, items in construct_dict.items():
        existing = [item for item in items if item in df.columns]
        if len(existing) >= 2:
            valid_constructs[c_name] = existing

    if len(valid_constructs) < 1:
        return {"error": "At least one construct with 2 or more valid items is required."}

    validity_rows = []
    construct_scores = {}
    construct_lambdas = {}

    for c_name, items in valid_constructs.items():
        sub = df[items].apply(pd.to_numeric, errors="coerce").dropna().copy()
        if len(sub) < len(items):
            continue

        k = len(items)
        alpha_val = compute_cronbach_alpha(sub)

        # Standardized factor loadings via correlation principal eigenvector
        corr = sub.corr().values
        eigvals, eigvecs = np.linalg.eigh(corr)
        max_idx = np.argmax(eigvals)
        lambda_raw = eigvecs[:, max_idx] * np.sqrt(max(eigvals[max_idx], 0.0))

        # Orient loadings positively (domain items load positively on scale construct)
        if np.mean(lambda_raw) < 0:
            lambda_raw = -lambda_raw
        lambdas = np.clip(lambda_raw, 0.001, 0.999)
        construct_lambdas[c_name] = lambdas

        sum_lambda = float(np.sum(lambdas))
        sum_lambda_sq = float(np.sum(lambdas ** 2))
        sum_theta = float(np.sum(1.0 - (lambdas ** 2)))

        # Composite Reliability (CR)
        cr = (sum_lambda ** 2) / ((sum_lambda ** 2) + sum_theta)

        # Average Variance Extracted (AVE)
        ave = sum_lambda_sq / k

        # McDonald's Omega (ω)
        omega = (sum_lambda ** 2) / ((sum_lambda ** 2) + sum_theta)

        # Save composite mean for discriminant correlations
        construct_scores[c_name] = sub.mean(axis=1)

        validity_rows.append({
            "Construct": c_name,
            "Items (k)": k,
            "Cronbach α": round(float(alpha_val), 3) if pd.notna(alpha_val) else np.nan,
            "Composite Reliability (CR)": round(float(cr), 3),
            "Average Variance Extracted (AVE)": round(float(ave), 3),
            "McDonald's Omega (ω)": round(float(omega), 3),
            "CR Adequate (>= 0.70)": "Yes" if cr >= 0.70 else "No",
            "Convergent Validity (AVE >= 0.50)": "Yes" if ave >= 0.50 else "No"
        })

    df_validity = pd.DataFrame(validity_rows)

    # Discriminant Validity: Fornell-Larcker Criterion
    construct_names = list(construct_scores.keys())
    m_cons = len(construct_names)

    # Calculate construct correlations
    df_scores = pd.DataFrame(construct_scores)
    corr_scores = df_scores.corr().values

    fl_rows = []
    for i, c1 in enumerate(construct_names):
        row = {}
        row["Construct"] = c1
        c1_ave = [r["Average Variance Extracted (AVE)"] for r in validity_rows if r["Construct"] == c1][0]
        sqrt_ave = np.sqrt(c1_ave)
        for j, c2 in enumerate(construct_names):
            if i == j:
                row[c2] = f"{sqrt_ave:.3f}*"
            else:
                row[c2] = f"{corr_scores[i, j]:.3f}"
        fl_rows.append(row)
    df_fornell = pd.DataFrame(fl_rows)

    # Discriminant Validity: HTMT (Heterotrait-Monotrait Ratio)
    htmt_rows = []
    for i in range(m_cons):
        c1 = construct_names[i]
        c1_items = valid_constructs[c1]
        for j in range(i + 1, m_cons):
            c2 = construct_names[j]
            c2_items = valid_constructs[c2]

            sub_pair = df[c1_items + c2_items].apply(pd.to_numeric, errors="coerce").dropna()
            corr_pair = sub_pair.corr().abs()

            # Heterotrait correlations
            r_hetero = float(corr_pair.loc[c1_items, c2_items].values.mean())

            # Monotrait correlations c1
            mono1_vals = []
            for a in range(len(c1_items)):
                for b in range(a + 1, len(c1_items)):
                    mono1_vals.append(corr_pair.loc[c1_items[a], c1_items[b]])
            r_mono1 = float(np.mean(mono1_vals)) if mono1_vals else 1.0

            # Monotrait correlations c2
            mono2_vals = []
            for a in range(len(c2_items)):
                for b in range(a + 1, len(c2_items)):
                    mono2_vals.append(corr_pair.loc[c2_items[a], c2_items[b]])
            r_mono2 = float(np.mean(mono2_vals)) if mono2_vals else 1.0

            denom = np.sqrt(max(r_mono1 * r_mono2, 1e-12))
            htmt_val = r_hetero / denom

            assessment = (
                "Supported (< 0.85)" if htmt_val < 0.85 else
                "Marginal (0.85 - 0.90)" if htmt_val <= 0.90 else
                "Discriminant Validity Concern (> 0.90)"
            )

            htmt_rows.append({
                "Construct Pair": f"{c1} <-> {c2}",
                "HTMT Ratio": round(htmt_val, 3),
                "Threshold (< 0.85)": "Met" if htmt_val < 0.85 else "Violated",
                "Assessment": assessment
            })
    df_htmt = pd.DataFrame(htmt_rows)

    return {
        "validity_table": df_validity,
        "fornell_larcker_table": df_fornell,
        "htmt_table": df_htmt,
        "is_success": True
    }


def recommend_cfa_estimator(df, items):
    """
    Estimator Advisor for Confirmatory Factor Analysis and Structural Equation Modeling.
    Checks categorical levels, univariate skewness, and excess kurtosis.
    Outputs evidence-based recommendation (ML, Robust ML / MLR, or Ordinal DWLS/WLSMV)
    with academic reviewer citations (Rhemtulla et al., 2012; Finney & DiStefano, 2013).
    """
    if df is None or df.empty or not items:
        return {"error": "Invalid dataframe or items list."}

    valid_items = [c for c in items if c in df.columns]
    if not valid_items:
        return {"error": "None of the specified items exist in dataframe."}

    sub = df[valid_items].apply(pd.to_numeric, errors="coerce")
    records = []
    has_ordinal_under_5 = False
    has_severe_nonnormality = False

    for col in valid_items:
        s = sub[col].dropna()
        n_unique = int(s.nunique())
        skew_val = float(stats.skew(s)) if len(s) > 2 else 0.0
        kurt_val = float(stats.kurtosis(s)) if len(s) > 3 else 0.0

        if n_unique <= 5:
            has_ordinal_under_5 = True
        if abs(skew_val) > 2.0 or abs(kurt_val) > 7.0:
            has_severe_nonnormality = True

        records.append({
            "Item": col,
            "Valid N": int(len(s)),
            "Unique Values": n_unique,
            "Scale Type": "Ordinal Likert (<= 5 cats)" if n_unique <= 5 else "Continuous / Multi-point",
            "Skewness": round(skew_val, 3),
            "Excess Kurtosis": round(kurt_val, 3)
        })

    df_diag = pd.DataFrame(records)

    if has_ordinal_under_5:
        rec = "Ordinal Estimator: DWLS / WLSMV (Diagonally Weighted Least Squares)"
        justification = (
            "One or more scale items exhibit 5 or fewer ordered categories. "
            "Under categorical Likert response formats, normal-theory ML produces severely attenuated factor loadings "
            "and artificially deflated standard errors. Methodological consensus mandates polychoric-based DWLS/WLSMV."
        )
        citation = "Rhemtulla, M., Brosseau-Liard, P. É., & Savalei, V. (2012). When can categorical variables be treated as continuous? Psychological Methods, 17(3), 354–373."
    elif has_severe_nonnormality:
        rec = "Robust Maximum Likelihood: MLR (Satorra-Bentler Scaled Chi-Square)"
        justification = (
            "Items possess continuous scaling (> 5 categories) but violate multivariate normality (|skewness| > 2.0 "
            "or |kurtosis| > 7.0). Standard ML inflates the model chi-square, leading to excessive type I error rates. "
            "MLR applies Huber-White sandwich standard errors and mean-adjusted fit indices."
        )
        citation = "Finney, S. J., & DiStefano, C. (2013). Non-normal and categorical data in structural equation modeling. In G. R. Hancock & R. O. Mueller (Eds.), Structural Equation Modeling: A Second Course (2nd ed., pp. 439–492)."
    else:
        rec = "Standard Maximum Likelihood: ML"
        justification = (
            "Items have continuous scaling (> 5 categories) and satisfy univariate and multivariate normality assumptions "
            "(|skewness| <= 2.0, |kurtosis| <= 7.0). Standard ML is the most statistically efficient and unbiased estimator."
        )
        citation = "Bollen, K. A. (1989). Structural Equations with Latent Variables. John Wiley & Sons."

    return {
        "recommended_estimator": rec,
        "justification": justification,
        "citation": citation,
        "item_diagnostics": df_diag,
        "has_ordinal_under_5": has_ordinal_under_5,
        "has_severe_nonnormality": has_severe_nonnormality,
        "is_success": True
    }


def compute_mediation_analysis(df, x_col, m_col, y_col, covariates=None, n_boot=1000, seed=42):
    """
    PROCESS-style Simple & Covariate-Adjusted Mediation Analysis (Hayes, 2018; Baron & Kenny, 1986).
    Decomposes total effect (c) into direct effect (c') and indirect effect (ab = a * b).
    Computes Sobel test, 95% Percentile Bootstrap CI, and Bias-Corrected (BC) Bootstrap CI (B=1000).
    """
    if df is None or df.empty:
        return {"error": "Input dataframe is empty or invalid."}
    for col, name in [(x_col, "Independent (X)"), (m_col, "Mediator (M)"), (y_col, "Outcome (Y)")]:
        if not col or col not in df.columns:
            return {"error": f"{name} variable '{col}' not found in dataframe."}

    covs = [c for c in (covariates or []) if c in df.columns and c not in [x_col, m_col, y_col]]
    analysis_vars = [x_col, m_col, y_col] + covs

    clean = df[analysis_vars].apply(pd.to_numeric, errors="coerce").dropna().copy()
    n_obs = len(clean)
    if n_obs < len(covs) + 15:
        return {"error": f"Insufficient complete cases ({n_obs}) for mediation analysis."}

    import statsmodels.api as sm

    # 1. Path a: M ~ X + Covariates
    X_a = sm.add_constant(clean[[x_col] + covs])
    mod_a = sm.OLS(clean[m_col], X_a).fit()
    a_coef = float(mod_a.params[x_col])
    a_se = float(mod_a.bse[x_col])
    a_t = float(mod_a.tvalues[x_col])
    a_p = float(mod_a.pvalues[x_col])

    # 2. Path b & Direct Effect c': Y ~ X + M + Covariates
    X_b = sm.add_constant(clean[[x_col, m_col] + covs])
    mod_b = sm.OLS(clean[y_col], X_b).fit()
    b_coef = float(mod_b.params[m_col])
    b_se = float(mod_b.bse[m_col])
    b_t = float(mod_b.tvalues[m_col])
    b_p = float(mod_b.pvalues[m_col])

    c_prime_coef = float(mod_b.params[x_col])
    c_prime_se = float(mod_b.bse[x_col])
    c_prime_t = float(mod_b.tvalues[x_col])
    c_prime_p = float(mod_b.pvalues[x_col])

    # 3. Path c (Total Effect): Y ~ X + Covariates
    X_c = sm.add_constant(clean[[x_col] + covs])
    mod_c = sm.OLS(clean[y_col], X_c).fit()
    c_coef = float(mod_c.params[x_col])
    c_se = float(mod_c.bse[x_col])
    c_t = float(mod_c.tvalues[x_col])
    c_p = float(mod_c.pvalues[x_col])

    # Indirect effect
    ab_coef = a_coef * b_coef

    # Sobel Test
    se_sobel = np.sqrt((a_coef ** 2) * (b_se ** 2) + (b_coef ** 2) * (a_se ** 2))
    z_sobel = ab_coef / np.maximum(se_sobel, 1e-12)
    p_sobel = 2.0 * (1.0 - stats.norm.cdf(abs(z_sobel)))

    # Non-parametric Bootstrap (B iterations)
    n_boot = max(200, int(n_boot))
    np.random.seed(seed)
    boot_ab = []

    arr_clean = clean[[x_col, m_col, y_col] + covs].values
    n_rows = len(arr_clean)

    for _ in range(n_boot):
        idx = np.random.choice(n_rows, size=n_rows, replace=True)
        sample = arr_clean[idx, :]
        sx = sample[:, 0]
        sm_v = sample[:, 1]
        sy = sample[:, 2]
        scovs = sample[:, 3:]

        if scovs.shape[1] > 0:
            X_a_s = np.column_stack([np.ones(n_rows), sx, scovs])
            X_b_s = np.column_stack([np.ones(n_rows), sx, sm_v, scovs])
        else:
            X_a_s = np.column_stack([np.ones(n_rows), sx])
            X_b_s = np.column_stack([np.ones(n_rows), sx, sm_v])

        try:
            beta_a = np.linalg.lstsq(X_a_s, sm_v, rcond=None)[0]
            beta_b = np.linalg.lstsq(X_b_s, sy, rcond=None)[0]
            boot_ab.append(beta_a[1] * beta_b[2])
        except Exception:
            continue

    boot_ab = np.array(boot_ab)
    actual_boot = len(boot_ab)

    # Percentile Bootstrap 95% CI
    ci_perc_low = float(np.percentile(boot_ab, 2.5))
    ci_perc_high = float(np.percentile(boot_ab, 97.5))

    # Bias-Corrected (BC) Bootstrap CI
    prop_less = np.mean(boot_ab < ab_coef)
    prop_less = np.clip(prop_less, 1e-5, 1.0 - 1e-5)
    z0 = stats.norm.ppf(prop_less)
    z_alpha_low = z0 + (z0 + stats.norm.ppf(0.025))
    z_alpha_high = z0 + (z0 + stats.norm.ppf(0.975))
    pct_low = stats.norm.cdf(z_alpha_low) * 100.0
    pct_high = stats.norm.cdf(z_alpha_high) * 100.0
    ci_bc_low = float(np.percentile(boot_ab, max(0.0, min(100.0, pct_low))))
    ci_bc_high = float(np.percentile(boot_ab, max(0.0, min(100.0, pct_high))))

    is_indirect_sig = (ci_bc_low > 0 and ci_bc_high > 0) or (ci_bc_low < 0 and ci_bc_high < 0)
    is_direct_sig = (c_prime_p < 0.05)

    if is_indirect_sig and not is_direct_sig:
        mediation_type = "Full (Indirect-Only) Mediation"
        summary_text = (
            f"The indirect effect of {x_col} on {y_col} via {m_col} is statistically significant "
            f"(b = {ab_coef:.4f}, 95% BC CI [{ci_bc_low:.4f}, {ci_bc_high:.4f}]), "
            f"while the direct effect is non-significant (p = {c_prime_p:.4f}). This establishes Full Mediation."
        )
    elif is_indirect_sig and is_direct_sig:
        if (ab_coef * c_prime_coef) > 0:
            mediation_type = "Complementary Partial Mediation"
        else:
            mediation_type = "Competitive Partial Mediation (Inconsistent Mediation)"
        summary_text = (
            f"Both the indirect effect (b = {ab_coef:.4f}, 95% BC CI [{ci_bc_low:.4f}, {ci_bc_high:.4f}]) "
            f"and direct effect (b = {c_prime_coef:.4f}, p = {c_prime_p:.4f}) are statistically significant. "
            f"This establishes {mediation_type}."
        )
    else:
        mediation_type = "No Mediation"
        summary_text = (
            f"The indirect effect bootstrap confidence interval spans zero "
            f"(b = {ab_coef:.4f}, 95% BC CI [{ci_bc_low:.4f}, {ci_bc_high:.4f}]). "
            f"There is no statistically significant mediation."
        )

    if c_coef != 0 and (ab_coef / c_coef) > 0:
        pct_mediated = round(float(ab_coef / c_coef) * 100.0, 1)
    else:
        pct_mediated = None

    paths_table = pd.DataFrame([
        {
            "Path / Component": f"Path a: {x_col} -> {m_col}",
            "Estimate (B)": round(a_coef, 4),
            "Std. Error": round(a_se, 4),
            "t-value": round(a_t, 3),
            "p-value": round(a_p, 4),
            "Sig": "***" if a_p < 0.001 else ("**" if a_p < 0.01 else ("*" if a_p < 0.05 else ""))
        },
        {
            "Path / Component": f"Path b: {m_col} -> {y_col}",
            "Estimate (B)": round(b_coef, 4),
            "Std. Error": round(b_se, 4),
            "t-value": round(b_t, 3),
            "p-value": round(b_p, 4),
            "Sig": "***" if b_p < 0.001 else ("**" if b_p < 0.01 else ("*" if b_p < 0.05 else ""))
        },
        {
            "Path / Component": f"Direct Effect c': {x_col} -> {y_col}",
            "Estimate (B)": round(c_prime_coef, 4),
            "Std. Error": round(c_prime_se, 4),
            "t-value": round(c_prime_t, 3),
            "p-value": round(c_prime_p, 4),
            "Sig": "***" if c_prime_p < 0.001 else ("**" if c_prime_p < 0.01 else ("*" if c_prime_p < 0.05 else ""))
        },
        {
            "Path / Component": f"Total Effect c: {x_col} -> {y_col}",
            "Estimate (B)": round(c_coef, 4),
            "Std. Error": round(c_se, 4),
            "t-value": round(c_t, 3),
            "p-value": round(c_p, 4),
            "Sig": "***" if c_p < 0.001 else ("**" if c_p < 0.01 else ("*" if c_p < 0.05 else ""))
        }
    ])

    effects_table = pd.DataFrame([
        {
            "Effect": "Indirect Effect (ab)",
            "Estimate": round(ab_coef, 4),
            "Sobel SE": round(se_sobel, 4),
            "Sobel z": round(z_sobel, 3),
            "Sobel p": round(p_sobel, 4),
            "95% Percentile Boot CI": f"[{ci_perc_low:.4f}, {ci_perc_high:.4f}]",
            "95% Bias-Corrected Boot CI": f"[{ci_bc_low:.4f}, {ci_bc_high:.4f}]",
            "Conclusion": "Significant" if is_indirect_sig else "Not Significant"
        }
    ])

    return {
        "paths_table": paths_table,
        "effects_table": effects_table,
        "indirect_ab": round(ab_coef, 4),
        "direct_c_prime": round(c_prime_coef, 4),
        "total_c": round(c_coef, 4),
        "ci_perc": (ci_perc_low, ci_perc_high),
        "ci_bc": (ci_bc_low, ci_bc_high),
        "sobel_p": p_sobel,
        "mediation_type": mediation_type,
        "summary_text": summary_text,
        "pct_mediated": pct_mediated,
        "n_obs": n_obs,
        "n_boot": actual_boot,
        "is_success": True
    }


def compute_moderation_analysis(df, x_col, w_col, y_col, covariates=None):
    """
    Hierarchical Moderation Analysis with Mean-Centering and Simple Slopes (Aiken & West, 1991).
    Tests interaction term (X * W), reports incremental delta R^2 and F-change,
    and estimates conditional simple slopes at -1 SD (Low), Mean (Average), and +1 SD (High).
    """
    if df is None or df.empty:
        return {"error": "Input dataframe is empty or invalid."}
    for col, name in [(x_col, "Focal Predictor (X)"), (w_col, "Moderator (W)"), (y_col, "Outcome (Y)")]:
        if not col or col not in df.columns:
            return {"error": f"{name} variable '{col}' not found in dataframe."}

    covs = [c for c in (covariates or []) if c in df.columns and c not in [x_col, w_col, y_col]]
    all_vars = [x_col, w_col, y_col] + covs

    clean = df[all_vars].apply(pd.to_numeric, errors="coerce").dropna().copy()
    n_obs = len(clean)
    if n_obs < len(covs) + 10:
        return {"error": f"Insufficient complete cases ({n_obs}) for moderation analysis."}

    import statsmodels.api as sm

    # 1. Mean-center X and W
    x_mean = float(clean[x_col].mean())
    w_mean = float(clean[w_col].mean())
    w_sd = float(clean[w_col].std(ddof=1))
    x_sd = float(clean[x_col].std(ddof=1))

    clean["_x_cent_"] = clean[x_col] - x_mean
    clean["_w_cent_"] = clean[w_col] - w_mean
    clean["_xw_interact_"] = clean["_x_cent_"] * clean["_w_cent_"]

    # 2. Model 1: Main Effects (Y ~ X_c + W_c + Covariates)
    X_m1 = sm.add_constant(clean[["_x_cent_", "_w_cent_"] + covs])
    mod_1 = sm.OLS(clean[y_col], X_m1).fit()

    # 3. Model 2: Interaction Model (Y ~ X_c + W_c + XW + Covariates)
    X_m2 = sm.add_constant(clean[["_x_cent_", "_w_cent_", "_xw_interact_"] + covs])
    mod_2 = sm.OLS(clean[y_col], X_m2).fit()

    # 4. Incremental F-test (Delta R^2)
    r2_1 = float(mod_1.rsquared)
    r2_2 = float(mod_2.rsquared)
    delta_r2 = max(0.0, r2_2 - r2_1)
    df_resid_2 = int(mod_2.df_resid)

    f_change = (delta_r2 / 1.0) / ((1.0 - r2_2) / max(1, df_resid_2))
    p_change = float(1.0 - stats.f.cdf(f_change, 1, df_resid_2))

    param_map = {
        "const": "Intercept (Constant)",
        "_x_cent_": f"{x_col} (Mean-Centered)",
        "_w_cent_": f"{w_col} (Mean-Centered)",
        "_xw_interact_": f"Interaction: {x_col} × {w_col}"
    }
    for c in covs:
        param_map[c] = f"Covariate: {c}"

    mod2_rows = []
    for p_name in mod_2.params.index:
        b = float(mod_2.params[p_name])
        se = float(mod_2.bse[p_name])
        t = float(mod_2.tvalues[p_name])
        p = float(mod_2.pvalues[p_name])
        ci_l = float(mod_2.conf_int().loc[p_name, 0])
        ci_u = float(mod_2.conf_int().loc[p_name, 1])
        star = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))

        mod2_rows.append({
            "Predictor": param_map.get(p_name, p_name),
            "Coefficient (B)": round(b, 4),
            "Std. Error": round(se, 4),
            "t-value": round(t, 3),
            "p-value": round(p, 4),
            "Sig": star,
            "95% CI Lower": round(ci_l, 4),
            "95% CI Upper": round(ci_u, 4)
        })
    df_mod2 = pd.DataFrame(mod2_rows)

    # 5. Simple Slopes Analysis (Aiken & West, 1991)
    b1 = float(mod_2.params["_x_cent_"])
    b3 = float(mod_2.params["_xw_interact_"])
    cov_mat = mod_2.cov_params()
    var_b1 = float(cov_mat.loc["_x_cent_", "_x_cent_"])
    var_b3 = float(cov_mat.loc["_xw_interact_", "_xw_interact_"])
    cov_b1_b3 = float(cov_mat.loc["_x_cent_", "_xw_interact_"])

    levels = [
        ("Low Moderator (-1 SD)", -w_sd, round(w_mean - w_sd, 3)),
        ("Average Moderator (Mean)", 0.0, round(w_mean, 3)),
        ("High Moderator (+1 SD)", +w_sd, round(w_mean + w_sd, 3))
    ]

    slopes_records = []
    plot_data = {"x_vals": [-x_sd, x_sd], "lines": {}}

    for label, w_val_cent, w_actual in levels:
        slope = b1 + b3 * w_val_cent
        var_slope = var_b1 + (w_val_cent ** 2) * var_b3 + 2.0 * w_val_cent * cov_b1_b3
        se_slope = np.sqrt(max(var_slope, 1e-12))
        t_slope = slope / se_slope
        p_slope = float(2.0 * (1.0 - stats.t.cdf(abs(t_slope), df=df_resid_2)))
        t_crit = stats.t.ppf(0.975, df=df_resid_2)
        ci_l = slope - t_crit * se_slope
        ci_u = slope + t_crit * se_slope
        star = "***" if p_slope < 0.001 else ("**" if p_slope < 0.01 else ("*" if p_slope < 0.05 else ""))

        slopes_records.append({
            "Moderator Level": label,
            f"{w_col} Value": w_actual,
            "Simple Slope (B)": round(slope, 4),
            "Std. Error": round(se_slope, 4),
            "t-value": round(t_slope, 3),
            "p-value": round(p_slope, 4),
            "Sig": star,
            "95% CI Lower": round(ci_l, 4),
            "95% CI Upper": round(ci_u, 4)
        })

        b0 = float(mod_2.params["const"])
        b2 = float(mod_2.params["_w_cent_"])
        y_low_x = b0 + b2 * w_val_cent + slope * (-x_sd)
        y_high_x = b0 + b2 * w_val_cent + slope * (+x_sd)
        plot_data["lines"][label] = [round(float(y_low_x), 3), round(float(y_high_x), 3)]

    df_slopes = pd.DataFrame(slopes_records)

    is_moderation_sig = (p_change < 0.05)
    conclusion = (
        f"The interaction term between {x_col} and {w_col} is statistically significant "
        f"(ΔR² = {delta_r2:.4f}, F(1, {df_resid_2}) = {f_change:.2f}, p = {p_change:.4f}). "
        f"This confirms that {w_col} significantly moderates the effect of {x_col} on {y_col}."
        if is_moderation_sig else
        f"The interaction term is not statistically significant "
        f"(ΔR² = {delta_r2:.4f}, F(1, {df_resid_2}) = {f_change:.2f}, p = {p_change:.4f}). "
        f"There is no evidence that {w_col} moderates the relationship."
    )

    return {
        "model_table": df_mod2,
        "simple_slopes_table": df_slopes,
        "r2_model1": round(r2_1, 4),
        "r2_model2": round(r2_2, 4),
        "delta_r2": round(delta_r2, 4),
        "f_change": round(f_change, 3),
        "p_change": round(p_change, 4),
        "df_resid": df_resid_2,
        "is_moderation_sig": is_moderation_sig,
        "conclusion": conclusion,
        "plot_data": plot_data,
        "n_obs": n_obs,
        "is_success": True
    }



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
