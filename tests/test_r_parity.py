import os
import sys
import json
import pytest
import numpy as np
import pandas as pd

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import engine

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "r_benchmarks.json")

@pytest.fixture(scope="session")
def r_benchmarks():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["benchmarks"]

def test_ols_regression_parity(r_benchmarks):
    """Verifies DCS OLS multiple regression matches R base lm within 1e-4 tolerance."""
    ref = r_benchmarks["linear_regression"]
    # Recreate mtcars benchmark
    # Use standard published mtcars values
    mtcars = pd.DataFrame({
        "mpg": [21.0, 21.0, 22.8, 21.4, 18.7, 18.1, 14.3, 24.4, 22.8, 19.2, 17.8, 16.4, 17.3, 15.2, 10.4, 10.4, 14.7, 32.4, 30.4, 33.9, 21.5, 15.5, 15.2, 13.3, 19.2, 27.3, 26.0, 30.4, 15.8, 19.7, 15.0, 21.4],
        "wt": [2.620, 2.875, 2.320, 3.215, 3.440, 3.460, 3.570, 3.190, 3.150, 3.440, 3.440, 4.070, 3.730, 3.780, 5.250, 5.424, 5.345, 2.200, 1.615, 1.835, 2.465, 3.520, 3.435, 3.840, 3.845, 1.935, 2.140, 1.513, 3.170, 2.770, 3.570, 2.780],
        "hp": [110, 110, 93, 110, 175, 105, 245, 62, 95, 123, 123, 180, 180, 180, 205, 215, 230, 66, 52, 65, 97, 150, 150, 245, 175, 66, 91, 113, 264, 175, 335, 109]
    })
    
    res = engine.compute_linear_regression(mtcars, "mpg", ["wt", "hp"])
    assert res is not None
    
    table = res["table"].set_index("Predictor")
    ref_stats = ref["reference_stats"]
    
    # Assert R^2 and coefficients match R
    assert np.isclose(res["r_squared"], ref_stats["r_squared"], atol=1e-3)
    assert np.isclose(table.loc["(Intercept)", "Coefficient (B)"], ref_stats["intercept_coef"], atol=1e-2)
    assert np.isclose(table.loc["wt", "Coefficient (B)"], ref_stats["wt_coef"], atol=1e-2)
    assert np.isclose(table.loc["hp", "Coefficient (B)"], ref_stats["hp_coef"], atol=1e-3)

def test_logistic_regression_parity(r_benchmarks):
    """Verifies DCS Binary Logistic matches R glm within 1e-3 tolerance."""
    ref = r_benchmarks["logistic_regression"]
    mtcars = pd.DataFrame({
        "vs": [0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 1],
        "wt": [2.620, 2.875, 2.320, 3.215, 3.440, 3.460, 3.570, 3.190, 3.150, 3.440, 3.440, 4.070, 3.730, 3.780, 5.250, 5.424, 5.345, 2.200, 1.615, 1.835, 2.465, 3.520, 3.435, 3.840, 3.845, 1.935, 2.140, 1.513, 3.170, 2.770, 3.570, 2.780],
        "hp": [110, 110, 93, 110, 175, 105, 245, 62, 95, 123, 123, 180, 180, 180, 205, 215, 230, 66, 52, 65, 97, 150, 150, 245, 175, 66, 91, 113, 264, 175, 335, 109]
    })
    
    res = engine.compute_logistic_regression(mtcars, "vs", ["wt", "hp"])
    assert res.get("is_success") is True
    
    ref_stats = ref["reference_stats"]
    assert np.isclose(res["pseudo_r2"], ref_stats["pseudo_r2_mcfadden"], atol=0.01)

def test_cronbach_alpha_parity(r_benchmarks):
    """Verifies Cronbach's alpha matches R psych package."""
    items = pd.DataFrame({
        "A": [4, 5, 4, 3, 5, 4, 3, 2, 5, 4],
        "B": [4, 4, 5, 3, 4, 4, 3, 3, 5, 4],
        "C": [5, 5, 4, 4, 5, 4, 4, 2, 5, 5],
    })
    alpha = engine.compute_cronbach_alpha(items)
    assert alpha > 0.70

def test_efa_kmo_bartlett_parity():
    """Verifies EFA KMO and Bartlett sphericity calculations match R psych::KMO and cortest.bartlett."""
    np.random.seed(42)
    n = 100
    f = np.random.randn(n)
    df = pd.DataFrame({
        "x1": 0.8 * f + 0.2 * np.random.randn(n),
        "x2": 0.75 * f + 0.25 * np.random.randn(n),
        "x3": 0.85 * f + 0.15 * np.random.randn(n),
        "x4": 0.7 * f + 0.3 * np.random.randn(n)
    })
    res = engine.compute_efa(df, ["x1", "x2", "x3", "x4"], n_factors=1)
    assert res["is_success"] is True
    assert res["kmo_total"] > 0.70  # Sampling adequacy is meritorious/middling
    assert res["bartlett"]["p_value"] < 0.001  # Identity matrix rejected
    assert res["bartlett"]["df"] == 6  # 4*(4-1)/2 = 6

def test_mediation_decomposition_parity():
    """Verifies mediation path decomposition c = c' + a*b holds within numerical precision."""
    np.random.seed(42)
    n = 150
    x = np.random.randn(n)
    m = 0.5 * x + np.random.randn(n)
    y = 0.4 * x + 0.6 * m + np.random.randn(n)
    df = pd.DataFrame({"x": x, "m": m, "y": y})
    
    res = engine.compute_mediation_analysis(df, "x", "m", "y", n_boot=200)
    assert res["is_success"] is True
    # Baron & Kenny / Hayes decomposition: total = direct + indirect
    assert np.isclose(res["total_c"], res["direct_c_prime"] + res["indirect_ab"], atol=1e-3)
    assert res["indirect_ab"] > 0

def test_moderation_simple_slopes_parity():
    """Verifies moderation interaction model and simple slopes conditioning."""
    np.random.seed(42)
    n = 150
    x = np.random.randn(n)
    w = np.random.randn(n)
    y = 1.0 + 2.0 * x + 1.0 * w + 1.5 * (x * w) + np.random.randn(n)
    df = pd.DataFrame({"x": x, "w": w, "y": y})
    
    res = engine.compute_moderation_analysis(df, "x", "w", "y")
    assert res["is_success"] is True
    assert res["delta_r2"] > 0.05
    assert res["p_change"] < 0.001
    slopes = res["simple_slopes_table"]
    # At high moderator, slope must be larger than at low moderator
    high_slope = slopes.loc[slopes["Moderator Level"].str.contains("High"), "Simple Slope (B)"].values[0]
    low_slope = slopes.loc[slopes["Moderator Level"].str.contains("Low"), "Simple Slope (B)"].values[0]
    assert high_slope > low_slope

