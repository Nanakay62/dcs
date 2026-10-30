import os
import sys
import tempfile
import pytest
import numpy as np
import pandas as pd
import openpyxl
import pyreadstat

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import engine


def test_qualtrics_import_profile():
    """Verifies Qualtrics 3-row header parsing, question label extraction, and preview filtering."""
    raw_qualtrics = [
        ["StartDate", "Status", "IPAddress", "Q1", "Q2_1"],
        ["Start Date", "Response Type", "IP Address", "Overall Satisfaction with Management", "Tools Used - Python"],
        ['{"ImportId":"startDate"}', '{"ImportId":"status"}', '{"ImportId":"ipAddress"}', '{"ImportId":"QID1"}', '{"ImportId":"QID2_1"}'],
        ["2025-01-01 10:00:00", "IP Address", "192.168.1.1", "5", "1"],
        ["2025-01-01 11:00:00", "Survey Preview", "192.168.1.2", "4", "0"],
        ["2025-01-01 12:00:00", "IP Address", "192.168.1.3", "3", "1"],
    ]
    df_raw = pd.DataFrame(raw_qualtrics)
    
    # 1. Detection
    p_info = engine.detect_survey_platform_profile(df_raw)
    assert p_info["profile"] == "qualtrics"
    assert p_info["header_rows"] == 3

    # 2. Parsing & Preview Filtering
    parsed = engine.apply_import_profile(df_raw, profile="auto", filter_preview=True)
    df_clean = parsed["df"]
    labels = parsed["variable_labels"]

    assert len(df_clean) == 2  # Preview row removed
    assert list(df_clean.columns) == ["StartDate", "Status", "IPAddress", "Q1", "Q2_1"]
    assert labels["Q1"] == "Overall Satisfaction with Management"
    assert labels["Q2_1"] == "Tools Used - Python"


def test_limesurvey_and_google_forms_profiles():
    """Verifies LimeSurvey bracketed subquestions and Google Forms timestamp headers."""
    # LimeSurvey
    ls_data = [
        ["id", "submitdate", "Q01[SQ001]", "Q01[SQ002]", "Q02[other]"],
        [1, "2025-01-01", "5", "4", "Other feedback"],
        [2, "2025-01-02", "3", "2", "N/A"],
    ]
    df_ls = pd.DataFrame(ls_data)
    p_ls = engine.detect_survey_platform_profile(df_ls)
    assert p_ls["profile"] == "limesurvey"

    parsed_ls = engine.apply_import_profile(df_ls, profile="limesurvey")
    assert "Q01_SQ001" in parsed_ls["df"].columns
    assert parsed_ls["variable_labels"]["Q01_SQ001"] == "Q01[SQ001]"

    # Google Forms
    gf_data = [
        ["Timestamp", "How old are you?", "What department do you work in?"],
        ["2025-01-01 12:00:00", "28", "Engineering"],
        ["2025-01-01 12:05:00", "34", "Marketing"],
    ]
    df_gf = pd.DataFrame(gf_data)
    p_gf = engine.detect_survey_platform_profile(df_gf)
    assert p_gf["profile"] == "google_forms"

    parsed_gf = engine.apply_import_profile(df_gf, profile="google_forms")
    assert parsed_gf["variable_labels"]["how_old_are_you"] == "How old are you?"


def test_mojibake_encoding_repair():
    """Verifies automated repair of UTF-8 decoded as Latin-1/CP1252 corrupted text."""
    corrupted_cases = [
        ("StÃ¤mmer inte alls", "Stämmer inte alls"),
        ("GÃ¶teborg", "Göteborg"),
        ("BorÃ¥s", "Borås"),
        ("KvalitÃ©", "Kvalité"),
        ("Employeeâ€™s Feedback", "Employee’s Feedback"),
        ("Non-breaking\u00a0space", "Non-breaking space"),
    ]
    for bad, expected in corrupted_cases:
        repaired = engine.repair_mojibake_encoding(bad)
        assert repaired == expected, f"Failed to repair '{bad}', got '{repaired}'"


def test_openrefine_category_clustering():
    """Verifies near-duplicate category unification across casing and spelling variants."""
    series = pd.Series([
        "Full-time", "full time", "Fulltime", "Full-time",
        "Part-time", "part time", "Part-time",
        "Contractor", "Contractor "
    ])
    mapping = engine.cluster_near_duplicate_categories(series, threshold=0.82)
    assert len(mapping) >= 2
    # Verify variants map to the canonical most frequent spelling
    assert mapping.get("full time") == "Full-time" or mapping.get("Fulltime") == "Full-time"
    assert mapping.get("part time") == "Part-time"


def test_impossible_values_and_sentinels_audit():
    """Verifies detection of out-of-bounds values (e.g. Age = 250), sentinels, and change log generation."""
    df_test = pd.DataFrame({
        "Respondent_ID": [1, 2, 3, 4],
        "Age": [25, 250, 42, -5],
        "Score": ["4", "N/A", "5", "999"],
        "Tenure_Date": ["2025-01-09", "3-5", "2025-06-08", "1-2"]
    })

    prop_res = engine.propose_cleaning_repairs(df_test)
    assert prop_res["is_success"] is True
    assert prop_res["total_proposals"] >= 3

    all_p_ids = [p["proposal_id"] for p in prop_res["proposals"]]
    res = engine.apply_accepted_repairs(df_test, all_p_ids, prop_res["proposals"])
    assert res["is_success"] is True

    df_cleaned = res["df_cleaned"]
    df_rules = res["df_rule_changelog"]
    df_cells = res["df_cell_audit"]

    # 1. Impossible ages converted to NaN and flagged
    assert pd.isna(df_cleaned.loc[1, "Age"])
    assert pd.isna(df_cleaned.loc[3, "Age"])
    assert df_cleaned.loc[1, "Age_out_of_range_flag"] == 1
    assert df_cleaned.loc[3, "Age_out_of_range_flag"] == 1
    assert df_cleaned.loc[0, "Age"] == 25.0

    # 2. Sentinels converted to NaN
    assert pd.isna(df_cleaned.loc[1, "Score"])
    assert pd.isna(df_cleaned.loc[3, "Score"])

    # 3. Excel dates repaired
    assert df_cleaned.loc[0, "Tenure_Date"] == "1-9"
    assert df_cleaned.loc[2, "Tenure_Date"] == "6-8"

    # 4. Audit trail populated
    assert len(df_rules) >= 3
    assert len(df_cells) >= 6
    assert "Excel_Row" in df_cells.columns
    assert "Rule_ID" in df_cells.columns


def test_formatted_excel_and_spss_stata_exports():
    """Verifies multi-sheet formatted Excel (.xlsx) and SPSS (.sav) / Stata (.dta) label preservation."""
    df_clean = pd.DataFrame({
        "gender": [1, 2, 1],
        "sat": [4, 5, 2]
    })
    codebook = pd.DataFrame({
        "Variable_Name": ["gender", "sat"],
        "Original_Header": ["What is your gender?", "Satisfaction with leadership (1-5)"],
        "Data_Type": ["int64", "int64"]
    })
    changelog = pd.DataFrame({
        "Step": [1],
        "Rule_Name": ["Sentinels Cleaned"],
        "Column": ["sat"],
        "Cells_Changed": [2]
    })
    cell_audit = pd.DataFrame({
        "Excel_Row": [2],
        "Column": ["sat"],
        "Rule_ID": ["clean_sentinels"],
        "Value_Before": ["N/A"],
        "Value_After": ["NaN"]
    })

    # 1. Excel 4-sheet formatted export
    xlsx_bytes = engine.export_formatted_excel_workbook(df_clean, codebook, changelog, cell_audit)
    assert len(xlsx_bytes) > 2000

    import io
    # Read back with openpyxl to verify sheets & frozen panes
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert set(wb.sheetnames) == {"Cleaned_Data", "Codebook", "Change_Log", "Cell_Audit_Trail"}
    assert wb["Cleaned_Data"].freeze_panes == "A2"

    # 2. SPSS (.sav) export with labels
    var_labels = {"gender": "Gender Identity", "sat": "Overall Satisfaction (1-5)"}
    val_labels = {"gender": {1: "Male", 2: "Female"}, "sat": {1: "Very Low", 5: "Very High"}}

    sav_bytes = engine.export_spss_stata_bytes(df_clean, var_labels, val_labels, fmt="sav")
    assert len(sav_bytes) > 200

    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as f:
        f.write(sav_bytes)
        f_path = f.name
    try:
        df_read, meta = pyreadstat.read_sav(f_path)
        assert meta.column_names_to_labels["gender"] == "Gender Identity"
        assert meta.variable_value_labels["gender"][1.0] == "Male"
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)

    # 3. Stata (.dta) export with labels
    dta_bytes = engine.export_spss_stata_bytes(df_clean, var_labels, val_labels, fmt="dta")
    assert len(dta_bytes) > 500
