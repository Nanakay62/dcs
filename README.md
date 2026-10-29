# Universal Survey & Excel Data Cleaning & Statistical Analysis Studio

A web application for forensic spreadsheet reconstruction, Likert scale harmonization, psychometric reliability analysis, survey quality control, and statistical analysis in Python and R.

## Features

### 1. 🎯 KFL & CPE Survey Forensic Preset (2025 Study Benchmark)
- Forensic reconstruction of survey cohorts accompanying Andersson & Malm (2025) *"Ideas Sound Like Music Only When the Leader Can Conduct: on creativity-enhancing leadership as theory and instrument"*.
- **1-to-1 Mathematical Bijection** between `B3_Rebecca` and `B4_AnnaReb` ($N = 179$), recovering true gender ($107$ male, $72$ female) and un-deleted KFL responses.
- **Survey Version A vs. Version B Harmonization** (aligning non-overlapping items $61..66$ and $67..93$).
- **100% Demographic Verification** against published study benchmarks ($N = 342$).
- **Live Psychometric Factor Scoring**: Cronbach's $\alpha$ for Factor 1 ($0.852$), Factor 2 ($0.708$), Factor 3 ($0.785$), and total scale ($0.870$).
- **Table 3 Replicated Convergent Validity**: Replicates all 9 published correlation pairs between KFL factors and CPE dimensions.

### 2. 🔍 Universal Messy Excel & Survey Cleaner (Any File)
- **Smart Header Detection & Multi-Row Header Merger**: Promotes buried table headers and combines stacked headers.
- **Multi-Sheet Workbook Consolidation**: Merge multiple tabs or clean individual sheets with a single click.
- **Stacked Table & Section Banner Splitter**: Strips embedded section headers and tags data with a `source_section` column when present.
- **Summary & Subtotal Stripper**: Drops "Total", "Subtotal", "Average", and footnote rows.
- **Disguised Missing Sentinels Cleaner**: Converts `'N/A'`, `'-'`, `'999'`, `'None'` to `NaN`.
- **Currency, Percentage & European Number Parser**: Strips `$`, `€`, `kr`, `£`, `%`, parses European comma decimals (`1.200,50`), space-separated thousands (`1 234,56`), and accounting negative parentheses `($50.00)`.
- **Universal Likert Scale Normalizer**: Recodes Agreement, Frequency, Satisfaction, Quality, and Boolean scales.
- **Dual Date Engine**: Repairs Excel date range corruptions (`2025-01-09` $\rightarrow$ `"1-9"`).
- **Survey Quality Control**: Detects straightliners (zero-variance careless responders) and statistical outliers ($|z| > 3$), with 1-click removal.
- **Item-Rest Reliability Analysis**: Calculates Cronbach's $\alpha$ alongside **"Alpha if item deleted"** with pairwise covariance fallback.
- **Persistent Reverse-Coding Assistant**: Reverse codes negatively keyed items with session state persistence.
- **Auto Data Dictionary & Codebook**: Comprehensive statistics table.

### 3. 📊 Statistical Data Analysis & Dual-Engine Reproducibility (Python & R)
- **Bivariate Correlation Analysis**: Pearson $r$ and Spearman $\rho$ correlation matrices with p-values and significance stars (`*`, `**`, `***`).
- **Principal Component & Factor Loadings Analysis**: Eigenvalues, variance explained, cumulative variance, and scree plot.
- **Multiple Linear Regression Modeling**: OLS regression with coefficients, standard errors, $t$-statistics, $p$-values, $R^2$, and $F$-tests.
- **Demographic Group Comparisons**: Independent samples Welch's $t$-test with Cohen's $d$ effect sizes.
- **Reproducible Python Script (.py)**: Complete, standalone executable script reproducing all cleaning transformations.
- **Reproducible R Statistical Script (`survey_analysis.R`)**: Ready-to-run R script using `psych`, `lavaan` (Confirmatory Factor Analysis), `corrplot`, and `ggplot2`.

---

## Quick Start (Local)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the studio:
   ```bash
   streamlit run app.py
   ```
3. Open `http://localhost:8501` in your browser.

---

## 1-Click Free Cloud Deployment (Streamlit Community Cloud)

1. Push this repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and log in with GitHub.
3. Click **"New app"**, select your repository, set the main file path to `app.py`, and click **Deploy**!
