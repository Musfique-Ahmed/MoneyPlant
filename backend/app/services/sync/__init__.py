"""Data-source sync connectors and services.

Layout:

- ``connectors.py`` — :class:`Connector` protocol plus the row-dict contract
  used by both connectors and the sync service.
- ``file_connector.py`` — reads CSV/XLSX from a configured allowed
  directory; rejects path traversal and symlink escapes.
- ``sql_connector.py`` — SQLAlchemy Core; parameterised, SELECT-only
  statement with a statement timeout and a row limit.
- ``service.py`` — orchestrates a sync: connect → read → map → validate
  → de-dup → write → record a :class:`SyncRun`. Wraps the writes in
  one transaction so a failed sync leaves existing data intact.
"""