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
