# merge_files.py

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# Set pandas display options for better readability
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)

# Read in data
DATA = Path("data")
pheno = pd.read_excel(DATA / "Calopogon multiflorus Phenology Data COMPREHENSIVE 2026JUN22.xlsx")  # fix to full file name
rain = pd.read_csv(DATA / "rain_data.csv")

print(pheno.shape, rain.shape)
print(pheno.head())
print(rain.head())

# Standardize date formats
pheno["Burn_Date"] = pd.to_datetime(pheno["Burn_Date"])  # use your actual column names
rain["DATE"] = pd.to_datetime(rain["DATE"])
rain["DATE"] = rain["DATE"].dt.tz_localize(None).dt.normalize()
pheno["Burn_Date"] = pheno["Burn_Date"].dt.normalize()

# Select columns from rain df
print(rain.columns.tolist())

# These are the columns we want
rain = rain[["DATE", "cra", "onset", "days_from_onset"]]

# Merge dataframes on date
df = pheno.merge(rain, left_on="Burn_Date", right_on="DATE", how="left")

# Check for columns
print(df.columns.tolist())

# Check for missing values in the new columns
print(df[["cra", "onset", "days_from_onset"]].isna().sum())

# Logic to define season
df['season'] = 'None'
df.loc[df['days_from_onset'] > 7, 'season'] = 'wet'
df.loc[df['days_from_onset'] < -21, 'season'] = 'dry'
df.loc[(df['days_from_onset'] <= 7) & (df['days_from_onset'] >= -21), 'season'] = 'trans'

# Graphing to check this worked

# One point per burn date
plot_df = df.drop_duplicates("Burn_Date").sort_values("Burn_Date")

colors = {"dry": "tab:orange", "trans": "tab:green", "wet": "tab:blue", "None": "lightgray"}

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

for season, color in colors.items():
    sub = plot_df[plot_df["season"] == season]
    ax1.scatter(sub["Burn_Date"], sub["cra"], c=color, label=season, s=20)
    ax2.scatter(sub["Burn_Date"], sub["days_from_onset"], c=color, label=season, s=20)

# Panel A
ax1.set_ylabel("CRA")
ax1.set_title("A", loc="left", fontweight="bold")
ax1.legend(title="Season")

# Panel B
ax2.axhline(-21, color="gray", linestyle="--", linewidth=1)
ax2.axhline(7, color="gray", linestyle="--", linewidth=1)
ax2.set_ylabel("Days from onset")
ax2.set_xlabel("Burn date")
ax2.set_title("B", loc="left", fontweight="bold")

plt.tight_layout()
plt.show()

# Output the merged dataframe
df.to_excel(DATA / "Calopogon multiflorus Phenology Data COMPREHENSIVE 2026JUN22 WITH SEASON.xlsx", index=False)