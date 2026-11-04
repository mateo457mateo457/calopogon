import geopandas as gpd

FIRE = DATA / "fire"

shp_files = sorted(FIRE.rglob("*.shp"))

for f in shp_files:
    g = gpd.read_file(f)
    print(f.name)
    print(g.crs)
    print(g.columns.tolist())
    print(g.head(), "\n")