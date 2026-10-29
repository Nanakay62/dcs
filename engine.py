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
    data.columns = cols
    return data


def detect_and_strip_stacked_tables(df_raw):
    """
    Detects repeated embedded header rows and section banners.
    Strips repeated headers and adds a `source_section` column tagging each row.
    """
    d = df_raw.copy()
    col_names = [clean_text_hygiene(c).lower() for c in d.columns if pd.notna(c)]
    
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
        first_few = [clean_text_hygiene(d.iloc[idx, c]).lower() for c in range(min(5, d.shape[1])) if pd.notna(d.iloc[idx, c])]
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
        sub_df = xl.parse(name)
        sub_df["source_sheet"] = name
        dfs.append(sub_df)

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


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

    # 1. Drop completely empty rows
    if drop_blanks:
        na_counts = d.isna().sum(axis=1)
        d = d.drop(index=d.index[na_counts == d.shape[1]]).reset_index(drop=True)

    # 2. Strip single-cell banners or handle stacked tables
    if strip_stacked:
        d = detect_and_strip_stacked_tables(d)
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
            if d[c].dtype == object or pd.api.types.is_string_dtype(d[c]):
                mask = d[c].astype(str).str.strip().str.lower().isin(SENTINEL_VALUES)
                d.loc[mask, c] = np.nan

    # 5. String hygiene
    if trim_strings:
        for c in d.columns:
            if d[c].dtype == object or pd.api.types.is_string_dtype(d[c]):
                d[c] = d[c].apply(clean_text_hygiene)

    # 6. Repair Excel date corruptions ('2025-01-09' -> '1-9')
    if repair_dates:
        for c in d.columns:
            has_dt = any(isinstance(v, (datetime.datetime, datetime.date, pd.Timestamp)) for v in d[c].dropna())
            if has_dt:
                d[c] = d[c].apply(fix_excel_date_range)

    # 7. Map Likert text labels to numeric
    if map_likert:
        for c in d.columns:
            s_low = d[c].dropna().astype(str).str.strip().str.lower()
            if len(s_low) > 0 and (s_low.isin(LIKERT_TEXT_MAP.keys()).sum() >= 2):
                d[c] = d[c].apply(parse_numeric_cell)

    # 8. Smart currency, percentage & number parsing
    if parse_numbers:
        for c in d.columns:
            if d[c].dtype == object and not pd.api.types.is_numeric_dtype(d[c]):
                # Test numeric conversion on sample
                s_non_null = d[c].dropna()
                if len(s_non_null) >= 3:
                    parsed = s_non_null.apply(parse_numeric_cell)
                    if parsed.notna().sum() >= (len(s_non_null) * 0.7):
                        d[c] = d[c].apply(parse_numeric_cell)

    # 9. Deduplication
    if drop_duplicates:
        d = d.drop_duplicates().reset_index(drop=True)

    # 10. Missing value imputation
    if imputation in ("median", "mean"):
        for c in d.columns:
            if pd.api.types.is_numeric_dtype(d[c]):
                fill_val = d[c].median() if imputation == "median" else d[c].mean()
                if pd.notna(fill_val):
                    d[c] = d[c].fillna(fill_val)

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
    Computes bivariate correlation matrix with p-values and significance stars.
    """
    sub = df[cols].apply(pd.to_numeric, errors='coerce')
    corr_df = pd.DataFrame(index=cols, columns=cols, dtype=float)
    pval_df = pd.DataFrame(index=cols, columns=cols, dtype=float)
    stars_df = pd.DataFrame(index=cols, columns=cols, dtype=object)

    for c1 in cols:
        for c2 in cols:
            if c1 == c2:
                r, p = 1.0, 0.0
            else:
                v1 = sub[c1]
                v2 = sub[c2]
                mask = v1.notna() & v2.notna()
                if mask.sum() < 3:
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

    return {"corr": corr_df, "pval": pval_df, "formatted": stars_df}


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

    return {
        "n_obs": n,
        "r_squared": round(float(r_squared), 4),
        "adj_r_squared": round(float(adj_r_squared), 4),
        "f_stat": round(float(f_stat), 3) if pd.notna(f_stat) else np.nan,
        "f_pval": round(float(f_pval), 4) if pd.notna(f_pval) else np.nan,
        "table": results_df,
    }


def compute_pca_factor_analysis(df, cols, n_factors=3):
    """
    Computes Principal Component / Factor loadings and explained variance.
    """
    clean = df[cols].apply(pd.to_numeric, errors='coerce').dropna()
    if len(clean) < 5 or len(cols) < 2:
        return None

    corr_mat = clean.corr().values
    eigvals, eigvecs = np.linalg.eigh(corr_mat)

    idx = np.argsort(eigvals)[::-1]
    eigvals = eigvals[idx]
    eigvecs = eigvecs[:, idx]

    n_comps = min(n_factors, len(cols))
    var_explained = (eigvals[:n_comps] / len(cols)) * 100.0
    cum_var = np.cumsum(var_explained)

    loadings = eigvecs[:, :n_comps] * np.sqrt(np.maximum(0, eigvals[:n_comps]))

    loadings_df = pd.DataFrame(
        loadings.round(3),
        index=cols,
        columns=[f"Factor {i+1}" for i in range(n_comps)]
    )

    scree_df = pd.DataFrame({
        "Component": [f"Factor {i+1}" for i in range(n_comps)],
        "Eigenvalue": eigvals[:n_comps].round(3),
        "Variance Explained (%)": var_explained.round(1),
        "Cumulative Variance (%)": cum_var.round(1),
    })

    return {
        "loadings": loadings_df,
        "scree": scree_df,
        "n_obs": len(clean),
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

def generate_data_dictionary(df):
    """Generates comprehensive variable dictionary with summary metrics for every column."""
    rows = []
    for col in df.columns:
        s = df[col]
        n_valid = int(s.notna().sum())
        n_missing = int(s.isna().sum())
        pct_valid = round(100.0 * n_valid / max(len(df), 1), 1)

        is_num = pd.api.types.is_numeric_dtype(s)
        mean_val = round(float(s.mean()), 3) if is_num and n_valid > 0 else np.nan
        std_val = round(float(s.std()), 3) if is_num and n_valid > 1 else np.nan
        min_val = round(float(s.min()), 3) if is_num and n_valid > 0 else (str(s.dropna().min())[:20] if n_valid > 0 else np.nan)
        max_val = round(float(s.max()), 3) if is_num and n_valid > 0 else (str(s.dropna().max())[:20] if n_valid > 0 else np.nan)
        n_unique = int(s.nunique(dropna=True))

        rows.append({
            "Variable_Name": col,
            "Data_Type": str(s.dtype),
            "N_Valid": n_valid,
            "N_Missing": n_missing,
            "Pct_Valid": pct_valid,
            "Unique_Values": n_unique,
            "Mean": mean_val,
            "Std_Dev": std_val,
            "Min": min_val,
            "Max": max_val,
        })
    return pd.DataFrame(rows)


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
    b3_cols = [df.columns.get_loc(p[0]) for p in match_pairs]
    b4_cols = [df.columns.get_loc(p[1]) for p in match_pairs]

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
