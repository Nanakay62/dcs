# Universal Survey & Excel Data Cleaning Studio

A web application for forensic spreadsheet reconstruction, Likert scale harmonization, psychometric reliability analysis, and survey quality control.

## Features

### 1. 🎯 KFL & CPE Thesis Survey Preset (Lund University 2025)
- Forensic reconstruction of `Masterfile_2_English.xlsx` accompanying Andersson & Malm (2025) *"Ideas Sound Like Music Only When the Leader Can Conduct: on creativity-enhancing leadership as theory and instrument"*.
- **1-to-1 Mathematical Bijection** between `B3_Rebecca` and `B4_AnnaReb` ($N = 179$), recovering true gender ($107$ male, $72$ female) and un-deleted KFL responses.
- **Survey Version A vs. Version B Harmonization** (aligning non-overlapping items $61..66$ and $67..93$).
- **100% Demographic Verification** against Thesis Table 5 ($N = 342$).
- **Live Psychometric Factor Scoring**: Cronbach's $\alpha$ for Factor 1 ($0.852$), Factor 2 ($0.894$), Factor 3 ($0.790$), and total scale ($0.866$).

### 2. 🔍 Universal Messy Excel & Survey Cleaner (Any File)
- **Smart Header Detection & Multi-Row Header Merger**: Promotes buried table headers and combines stacked headers.
- **Multi-Sheet Workbook Consolidation**: Merge multiple tabs or clean individual sheets with a single click.
- **Stacked Table & Section Banner Splitter**: Strips embedded section headers and tags data with a `source_section` column.
- **Summary & Subtotal Stripper**: Drops "Total", "Subtotal", "Average", and footnote rows.
- **Disguised Missing Sentinels Cleaner**: Converts `'N/A'`, `'-'`, `'999'`, `'None'` to `NaN`.
- **Currency, Percentage & European Number Parser**: Strips `$`, `€`, `kr`, `%`, and parses European comma decimals (`1.200,50`).
- **Universal Likert Scale Normalizer**: Recodes Agreement, Frequency, Satisfaction, Quality, and Boolean scales.
- **Dual Date Engine**: Repairs Excel date range corruptions (`2025-01-09` $\rightarrow$ `"1-9"`).
- **Survey Quality Control**: Detects straightliners (zero-variance careless responders) and statistical outliers ($|z| > 3$).
- **Item-Rest Reliability Analysis**: Calculates Cronbach's $\alpha$ alongside **"Alpha if item deleted"** to pinpoint weak items.
- **Reverse-Coding Assistant**: Reverse codes negatively keyed items with one click.
- **Auto Data Dictionary & Codebook**: Comprehensive statistics table.
- **Reproducible Python Script**: Generates a standalone `.py` script reproducing all cleaning steps.

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
