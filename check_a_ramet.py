# check_a_ramet.py
#
# Check the FRI for one row of the output file, independently of
# calculate_return_interval.py:
#   - find every burn polygon that contains the row's location
#   - map those polygons with the location
#   - recalculate n, first burn, last burn, and FRI from the
#     individual intervals (not the (last - first) / (n - 1) shortcut)
#   - compare with the values saved in the output file
#   - save the row's burn history to Excel for checking by hand

# Load libraries
from pathlib import Path
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

# Display options
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)
pd.set_option("display.max_rows", 100)

# Settings
ROW = 55  # row of the output file to check (Excel row number = ROW + 2)

# Paths
DATA = Path("Data")
FIRE = DATA / "fire"
OUT_DIR = DATA / "checks"
OUT_DIR.mkdir(exist_ok=True)

###--- Load Fire History Data (same steps as calculate_return_interval.py) ---###

old = gpd.read_file(FIRE / "1977_2005" / "APAFR_Burn_History_1977_2005.shp")
new = gpd.read_file(FIRE / "2006_2026" / "APAFR_Burn_Histroy_2006_2026.shp")

parts = old[["Year_", "Month_", "day_"]].rename(columns={"Year_": "year", "Month_": "month", "day_": "day"})
full_date = pd.to_datetime(parts, errors="coerce")
mid_month = pd.to_datetime(parts.assign(day=15), errors="coerce")

old["burn_date"] = full_date.fillna(mid_month)
old["day_filled"] = full_date.isna() & mid_month.notna()
old["fire_type"] = old["Type"].str.lower()
old["source"] = "1977_2005"

new["burn_date"] = pd.to_datetime(new["fireStartD"]).dt.normalize()
new["day_filled"] = False
new["fire_type"] = new["wildland_1"].str.lower()
new["source"] = "2006_2026"
new = new.to_crs(26917)
new["geometry"] = new.geometry.force_2d()

cols = ["burn_date", "day_filled", "fire_type", "source", "geometry"]
fires = gpd.GeoDataFrame(pd.concat([old[cols], new[cols]], ignore_index=True),
                         geometry="geometry", crs=26917)
fires = fires.dropna(subset=["burn_date"]).reset_index(drop=True)

###--- Load the row to check ---###

_f = "Calopogon multiflorus Phenology Data COMPREHENSIVE 2026JUN22 WITH SEASON AND FRI.xlsx"
pheno = pd.read_excel(DATA / _f)
row = pheno.iloc[ROW]

if pd.isna(row["Lat"]) or pd.isna(row["Long"]):
    raise SystemExit(f"Row {ROW} has no coordinates; pick another row.")

print(row[["Survey_Date", "Lat", "Long", "PNA", "n_burns", "first_burn", "last_burn", "FRI_years"]])

# Location as a point, in the same coordinates as the fire polygons (UTM 17N)
pt = gpd.GeoSeries(gpd.points_from_xy([row["Long"]], [row["Lat"]]), crs=4326).to_crs(26917)

###--- Find burns at this location ---###

# Every polygon containing the point; mark which ones are on or before the survey date
hits = fires[fires.contains(pt.iloc[0])].copy()
hits["used"] = hits["burn_date"] <= row["Survey_Date"]
hits = hits.sort_values("burn_date")

# Burns that go into the FRI: one row per date, on or before the survey date
used = (hits.loc[hits["used"], ["burn_date", "fire_type", "day_filled", "source"]]
        .drop_duplicates(subset="burn_date")
        .reset_index(drop=True))
used["interval_days"] = used["burn_date"].diff().dt.days
used["interval_years"] = used["interval_days"] / 365.25

###--- Recalculate and compare ---###

n = len(used)
first = used["burn_date"].min()
last = used["burn_date"].max()
fri_hand = used["interval_years"].mean()  # mean of the individual intervals

print("\nAll burns at this location (used = on or before survey date):")
print(hits[["burn_date", "fire_type", "day_filled", "source", "used"]].to_string(index=False))

print("\nBurns used in the FRI:")
print(used.to_string(index=False))

check = pd.DataFrame({"recalculated": [n, first, last, fri_hand],
                      "output_file": [row["n_burns"], row["first_burn"], row["last_burn"], row["FRI_years"]]},
                     index=["n_burns", "first_burn", "last_burn", "FRI_years"])
print("\nComparison:")
print(check)

###--- Map ---###

b = hits[hits["used"]].copy()
b["year"] = b["burn_date"].dt.year
b["geometry"] = b.boundary  # outlines only, so overlapping burns stay visible

fig, ax = plt.subplots(figsize=(8, 8))
b.plot(ax=ax, column="year", cmap="viridis", linewidth=1, legend=True,
       legend_kwds={"label": "Burn year"})
pt.plot(ax=ax, color="red", marker="*", markersize=250, zorder=5)
ax.set_title(f"Row {ROW}: {row['PNA']}, surveyed {pd.Timestamp(row['Survey_Date']):%Y-%m-%d}\n"
             f"{n} burns, FRI = {fri_hand:.2f} years")
ax.set_axis_off()
plt.tight_layout()
plt.show()

###--- Save for checking in Excel ---###

out_file = OUT_DIR / f"check_row_{ROW}.xlsx"
with pd.ExcelWriter(out_file) as xw:
    used.to_excel(xw, sheet_name="burns", index=False)
    check.to_excel(xw, sheet_name="comparison")
print("Saved to:", out_file.resolve())