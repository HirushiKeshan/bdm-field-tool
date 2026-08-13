"""
Phase 0 exploration script. Reads all four CSVs as raw strings (dtype=str,
keep_default_na=False) so nothing is silently coerced or imputed by pandas
before we've looked at it. Prints schema, dtypes-as-observed, row counts,
null counts, and sample rows.
"""
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

FILES = {
    "outlets": "outlets.csv",
    "bdms": "bdms.csv",
    "billing_monthly": "billing-monthly.csv",
    "visit_log": "visit-log.csv",
}

dfs = {}
for name, path in FILES.items():
    # Read everything as raw string, do NOT let pandas interpret "NA", "N/A" etc.
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    dfs[name] = df
    print(f"\n{'='*80}\n{name}  ({path})\n{'='*80}")
    print(f"rows: {len(df)}   cols: {len(df.columns)}")
    print(f"columns: {list(df.columns)}")
    print("\n--- raw dtypes (all object since read as str) / blank-string counts ---")
    for col in df.columns:
        blank = (df[col].str.strip() == "").sum()
        pct = blank / len(df) * 100
        n_unique = df[col].nunique()
        print(f"  {col:22s} blanks={blank:5d} ({pct:5.1f}%)  unique={n_unique}")
    print("\n--- sample rows ---")
    print(df.head(5).to_string())

import pickle
with open("scripts/_raw_dfs.pkl", "wb") as f:
    pickle.dump(dfs, f)
print("\nSaved raw string dataframes to scripts/_raw_dfs.pkl for further analysis.")
