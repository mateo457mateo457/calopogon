# calculate_return_interval.py

# Load libraries
from pathlib import Path
import geopandas as gpd
import pandas as pd

# Display options
pd.set_option("display.max_columns", None)   # show all columns
pd.set_option("display.width", None)         # use full console width
pd.set_option("display.max_colwidth", None)  # don't truncate cell contents
pd.set_option("display.max_rows", 100)       # show up to 100 rows before truncating

# Paths
DATA = Path("Data")
FIRE = DATA / "fire"

###--- Load Fire History Data ---###

# Read fire history shapefiles into GeoDataFrames
old = gpd.read_file(FIRE / "1977_2005" / "APAFR_Burn_History_1977_2005.shp")
new = gpd.read_file(FIRE / "2006_2026" / "APAFR_Burn_Histroy_2006_2026.shp")

# Derive dates for "old" from available columns and fill missing dates with the month and the 15th if available
parts = old[["Year_", "Month_", "day_"]].rename(columns={"Year_": "year", "Month_": "month", "day_": "day"})
full_date = pd.to_datetime(parts, errors="coerce")
mid_month = pd.to_datetime(parts.assign(day=15), errors="coerce")

old["burn_date"] = full_date.fillna(mid_month)
old["day_filled"] = full_date.isna() & mid_month.notna()
old["fire_type"] = old["Type"].str.lower()
old["source"] = "1977_2005"

# Derive dates for "new"; date is stored in fireStartD, which is already a datetime column,
# but we normalize it to remove the time component
new["burn_date"] = pd.to_datetime(new["fireStartD"]).dt.normalize()
new["day_filled"] = False
new["fire_type"] = new["wildland_1"].str.lower()
new["source"] = "2006_2026"
new = new.to_crs(26917)
new["geometry"] = new.geometry.force_2d()

# Combine old and new
cols = ["burn_date", "day_filled", "fire_type", "source", "geometry"]
fires = gpd.GeoDataFrame(pd.concat([old[cols], new[cols]], ignore_index=True),
                         geometry="geometry", crs=26917)

# Report and drop fires with no usable date
print("Day set to 15:", fires["day_filled"].sum())
print("Dropped (no year/month):", fires["burn_date"].isna().sum())
fires = fires.dropna(subset=["burn_date"]).reset_index(drop=True)
print(fires.shape)

###--- Load Calopogon  Data ---###

# Read Calopogon data
_f = "Calopogon multiflorus Phenology Data COMPREHENSIVE 2026JUN22 WITH SEASON.xlsx"
pheno = pd.read_excel(DATA / _f, parse_dates=["Burn_Date", "Survey_Date"])


# ---------------------------------------------------------------
# Goal: For each row in pheno, calculate the fire return interval
# (FRI) at that row's location, using all burns on or before its
# survey date.
#
# Strategy:
#   Step 1: Build a table of unique locations from Lat/Long.
#           Many rows share a location, so the spatial work is
#           done once per location instead of once per row.
#
#   Step 2: Spatial join locations to burn polygons. The result
#           is each location's full fire history (1977-2026):
#           one row per location-burn pair.
#
#   Step 3: Join each pheno row to its location's fire history,
#           and keep only burns on or before that row's survey
#           date.
#
#   Step 4: For each row, count the burns and find the first and
#           last burn dates. FRI = (last - first) / (n - 1), which
#           equals the mean interval between consecutive burns.
#           Rows with fewer than 2 burns get no FRI.
#
#   Step 5: Attach the FRI results to pheno and save.
# ---------------------------------------------------------------

# Step 1: Build a table of unique locations
# - Take Lat/Long from pheno and drop duplicates, so each location appears once
# - Give each location an ID (loc_id) so rows can be linked back to it later
# - Add that loc_id to pheno, so every row knows which location it belongs to
# - Turn each location into a point (Long = x, Lat = y) in lat/long (EPSG:4326)
# - Convert the points to UTM 17N (EPSG:26917) to match the fire polygons

locs = (pheno[["Lat", "Long"]]
        .dropna()
        .drop_duplicates()
        .reset_index(drop=True))
locs["loc_id"] = locs.index

pheno = pheno.merge(locs, on=["Lat", "Long"], how="left")

locs = gpd.GeoDataFrame(locs,
                        geometry=gpd.points_from_xy(locs["Long"], locs["Lat"]),
                        crs=4326).to_crs(26917)

# Check
print("Rows:", len(pheno))
print("Unique locations:", len(locs))
print("Rows with no coordinates:", pheno["loc_id"].isna().sum())

# Step 2: Spatial join locations to burn polygons
# - Match each location point to every burn polygon that contains it
# - Result: a location's fire history is described by a set of rows with each row
#   having the location and a burn date
# - A location burns at most once per date; drop duplicate location-date rows

fire_hist = gpd.sjoin(locs, fires, how="inner", predicate="within")

fire_hist = (fire_hist[["loc_id", "burn_date", "fire_type", "day_filled", "source"]]
             .drop_duplicates(subset=["loc_id", "burn_date"])
             .sort_values(["loc_id", "burn_date"])
             .reset_index(drop=True))

# Check
print("Location-burn pairs:", len(fire_hist))
print("Locations with at least one burn:", fire_hist["loc_id"].nunique(), "of", len(locs))
print(fire_hist.groupby("loc_id").size().describe())
print(fire_hist[fire_hist["loc_id"] == 0])

# Step 3: Join each pheno row to its location's fire history
# - Give each pheno row an ID (row_id) so results can be attached back in Step 5
# - Join rows to fire_hist by loc_id (each row picks up all burns at its location)
# - Keep only burns on or before that row's survey date

pheno["row_id"] = range(len(pheno))

row_hist = pheno[["row_id", "loc_id", "Survey_Date"]].merge(fire_hist, on="loc_id", how="inner")
row_hist = row_hist[row_hist["burn_date"] <= row_hist["Survey_Date"]]

# Check
print("Row-burn pairs:", len(row_hist))
print("Rows with at least one prior burn:", row_hist["row_id"].nunique(), "of", len(pheno))
print(row_hist[row_hist["row_id"] == 0])

# Step 4: Summarize each row's fire history
# - Group by row_id and count burns, first burn date, last burn date
# - FRI (years) = (last - first) / (n - 1)
# - Rows with fewer than 2 burns get no FRI (can't have an interval with one burn)

fri = (row_hist.groupby("row_id")
       .agg(n_burns=("burn_date", "size"),
            first_burn=("burn_date", "min"),
            last_burn=("burn_date", "max"))
       .reset_index())

fri["FRI_years"] = ((fri["last_burn"] - fri["first_burn"]).dt.days
                    / (fri["n_burns"] - 1)
                    / 365.25)
fri.loc[fri["n_burns"] < 2, "FRI_years"] = pd.NA

# Check
print("Rows summarized:", len(fri))
print(fri[fri["row_id"] == 0])
print(fri["FRI_years"].describe())

# Step 5: Attach FRI results to pheno and save
# - Left join keeps every pheno row; rows with no coordinates get blank FRI
# - Drop the helper row_id (keep loc_id in case it's useful later)

pheno = (pheno.merge(fri, on="row_id", how="left")
              .drop(columns="row_id"))

# Check
print("Rows:", len(pheno)) # should still be 12439
print("Rows with no FRI:", pheno["FRI_years"].isna().sum())
# 100 have no FRI because they have no coordinates; work was done on this 11/10/2026 and the locations could not be found
print(pheno[["Survey_Date", "Lat", "Long", "n_burns", "first_burn", "last_burn", "FRI_years"]].head())

# Save
out_file = DATA / "Calopogon multiflorus Phenology Data COMPREHENSIVE 2026JUN22 WITH SEASON AND FRI.xlsx"
pheno.to_excel(out_file, index=False)
print("Saved to:", out_file.resolve())