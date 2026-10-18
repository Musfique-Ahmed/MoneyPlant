# Sample data

The CSVs in this directory are **synthetic demo data**. They do not
represent any real business. The numbers are intentionally small and
internally consistent so the financial engine produces sensible results
when the seed script imports them.

| File | Industry | Workspace seeded |
|---|---|---|
| `clothing_demo.csv`   | Manufacturing | Aurora Garments (demo) |
| `retail_demo.csv`     | Retail        | Main Street Boutique (demo) |
| `service_demo.csv`    | Service       | Helios Consulting (demo) |
| `wholesale_demo.csv`  | Wholesale     | Pioneer Distribution Co. (demo) |
| `food_demo.csv`       | Food          | Maple Street Eatery (demo) |

The `scripts/seed_demo.py` script imports each CSV via the same
ingestion pipeline the API uses (`parse_rows` + `suggest_mapping`), so
the column mapping is the auto-suggested one.
