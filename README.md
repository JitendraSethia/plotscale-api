# Geospatial File Measurement API

A FastAPI service that accepts a KML file or a zipped Shapefile, extracts every feature, and returns accurate measurements: area for polygons, length for lines, and nothing for points. Geometries are always projected to a metric UTM zone before measuring, never measured in degrees.

## Setup

### Get the code

```bash
git clone https://github.com/JitendraSethia/Untouched.git
cd Untouched
```

### Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000 and interactive docs are at http://127.0.0.1:8000/docs.

### Run with Docker

```bash
docker build -t plotscale-api .
docker run -p 8000:8000 plotscale-api
```

No system GDAL is needed: the `pyogrio`, `shapely` and `pyproj` wheels bundle GDAL, GEOS and PROJ.

### Run the tests

```bash
pytest
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./plotscale.db` | SQLAlchemy database URL |
| `MAX_UPLOAD_MB` | `20` | Maximum upload size |
| `MAX_UNZIPPED_MB` | `200` | Maximum uncompressed size of the shapefile parts (zip bomb guard) |

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/files/` | Upload and process a `.kml` or `.zip` (shapefile) |
| `GET` | `/api/files/{id}/` | File information and processing status |
| `GET` | `/api/files/{id}/measurements/` | Per-feature measurements, geometry, CRS and properties |

### Upload a file

```bash
curl -F "file=@tests/fixtures/sample.kml" http://localhost:8000/api/files/
```

`201 Created`

```json
{
  "id": "94f2874d862f4db398e70b684dea952b",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error": null
}
```

A zipped shapefile is uploaded the same way:

```bash
curl -F "file=@tests/fixtures/sample_shapefile.zip" http://localhost:8000/api/files/
```

### Get file information

```bash
curl http://localhost:8000/api/files/94f2874d862f4db398e70b684dea952b/
```

`200 OK` returns the same body as the upload. For a failed file, `status` is `FAILED` and `error` explains why:

```json
{
  "id": "57aa306076904bbebcdaf043db8d97dd",
  "filename": "bad.kml",
  "feature_count": 0,
  "crs": null,
  "status": "FAILED",
  "error": "File is not a valid KML document."
}
```

### Get measurements

```bash
curl http://localhost:8000/api/files/94f2874d862f4db398e70b684dea952b/measurements/
```

`200 OK` (properties and coordinates shortened here)

```json
{
  "file_id": "94f2874d862f4db398e70b684dea952b",
  "status": "COMPLETED",
  "feature_count": 3,
  "features": [
    {
      "index": 0,
      "geometry_type": "Polygon",
      "measurement_status": "MEASURED",
      "area_m2": 999662.33,
      "length_m": null,
      "projected_crs": "EPSG:32645",
      "note": null,
      "crs": "EPSG:4326",
      "properties": { "Name": "Plot A", "description": "1 km x 1 km square", "...": "..." },
      "geometry": { "type": "Polygon", "coordinates": [[[88.3639, 22.5726, 0.0], "..."]] }
    },
    {
      "index": 1,
      "geometry_type": "LineString",
      "measurement_status": "MEASURED",
      "area_m2": null,
      "length_m": 1999.7,
      "projected_crs": "EPSG:32645",
      "note": null,
      "crs": "EPSG:4326",
      "properties": { "Name": "Access road", "...": "..." },
      "geometry": { "type": "LineString", "coordinates": [[88.3639, 22.5726], "..."] }
    },
    {
      "index": 2,
      "geometry_type": "Point",
      "measurement_status": "NOT_APPLICABLE",
      "area_m2": null,
      "length_m": null,
      "projected_crs": null,
      "note": "Points have no area or length.",
      "crs": "EPSG:4326",
      "properties": { "Name": "Site gate", "...": "..." },
      "geometry": { "type": "Point", "coordinates": [88.3639, 22.5726] }
    }
  ]
}
```

`measurement_status` is one of:

| Status | Meaning |
|---|---|
| `MEASURED` | `area_m2` (Polygon, MultiPolygon) or `length_m` (LineString, MultiLineString) is set. Multi-geometries are the sum of their parts. |
| `NOT_APPLICABLE` | Point or MultiPoint, which has no measurement. |
| `UNSUPPORTED` | GeometryCollection, or a feature outside UTM coverage (beyond 80°S or 84°N). |
| `EMPTY` | The feature has no geometry. |
| `INVALID` | Invalid geometry (e.g. a self-intersecting polygon) or coordinates outside the range of the declared CRS. `note` gives the reason. |

### Errors

Errors return `{"detail": "..."}`. If a file was saved before it failed, the response also includes its `id` so the `FAILED` record can be fetched.

| Code | When |
|---|---|
| `400` | Uploaded file is empty |
| `404` | Unknown file id |
| `413` | Upload larger than `MAX_UPLOAD_MB`, or shapefile larger than `MAX_UNZIPPED_MB` uncompressed |
| `415` | Extension is not `.kml` or `.zip` |
| `422` | Invalid content: not KML, not a zip, missing `.shp`/`.shx`/`.dbf`, missing or unreadable `.prj`, unsafe paths in the zip, unreadable data, no features. Also returned when the `file` form field is missing. |

## Architecture

### Application structure

```
app/
├── main.py              # App setup, table creation, FileError → JSON handler
├── config.py            # Settings from environment variables
├── errors.py            # FileError: a client-fixable problem with its HTTP status
├── api/files.py         # The three endpoints and the upload flow
├── db/
│   ├── database.py      # Engine, session, get_db dependency
│   └── models.py        # File and Feature tables
├── schemas/files.py     # Pydantic response models
└── services/
    ├── storage.py       # Size-limited save, KML check, safe shapefile extraction
    ├── file_loader.py   # Reads features with pyogrio (GDAL)
    ├── crs.py           # UTM zone selection and reprojection
    └── measurements.py  # Area/length and measurement status per feature
tests/                   # Unit tests per service, API tests, small fixtures
```

Services know nothing about HTTP or the database. They take paths and geometries and raise `FileError` for client problems, which keeps each one testable on its own.

### File-processing flow

1. **Validate the extension.** Only `.kml` and `.zip` are accepted (415 otherwise).
2. **Save the upload** to a temporary directory in 1 MB chunks, stopping once it passes the size limit (413). The client's filename is never used as a path.
3. **Create a `File` record** with status `PROCESSING`.
4. **Check the content.**
   - KML: the file must contain a `<kml` element.
   - ZIP: it must be a real zip archive with no absolute or `..` paths (zip-slip), exactly one `.shp`, and a matching `.shx` and `.dbf`, all within the uncompressed size limit.
   - Only the shapefile parts (`.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`) are extracted, under fixed names.
5. **Read every layer** with pyogrio and number features across the whole file. For each feature, keep the geometry, the layer CRS and the attributes. A missing CRS is rejected.
6. **Measure each feature** (see below) and store it with its GeoJSON geometry, CRS, properties and result.
7. **Set status** to `COMPLETED`, or to `FAILED` with an `error` message. The temporary directory is always deleted.

### Measurement calculation flow

For each feature, in order:

1. No geometry, or an empty one → `EMPTY`.
2. Point or MultiPoint → `NOT_APPLICABLE`. Anything other than (Multi)Polygon or (Multi)LineString → `UNSUPPORTED`.
3. Drop Z values, since measurements are on the ground plane.
4. Invalid geometry → `INVALID`, with Shapely's reason (e.g. `Self-intersection[88.365 22.575]`). It is reported, not repaired.
5. Reproject to WGS84. If the coordinates fall outside valid longitude/latitude, the file's CRS is wrong → `INVALID`.
6. Pick the UTM zone of the feature's centroid. Outside 80°S–84°N → `UNSUPPORTED`.
7. Reproject to that UTM zone and take Shapely's `area` or `length` in metres, rounded to 2 decimals.

### CRS handling

- **Source CRS:** KML is always EPSG:4326. For shapefiles the CRS comes from the `.prj` file, which GDAL resolves to an EPSG code when it can (for example, an ESRI `WGS_1984_UTM_Zone_45N` `.prj` becomes `EPSG:32645`). Projected source data works too, because every geometry is reprojected from its own CRS.
- **Projected CRS:** each feature is measured in the WGS84 UTM zone containing its centroid: zone `floor((lon + 180) / 6) + 1`, EPSG `326xx` in the north and `327xx` in the south. The zone used is returned as `projected_crs`.
- **Axis order:** transformers use `always_xy=True`, so coordinates are always (lon, lat), even though EPSG:4326 officially lists latitude first.
- **Accuracy:** the tests compare UTM results with geodesic (ellipsoidal) results from `pyproj.Geod`. The 1 km × 1 km square near Kolkata gives 999,662 m² against 999,973 m² geodesic (−0.03%). A square near Sydney (EPSG:32756) differs by −0.01%.

## Design decisions

| Decision | Alternatives considered | Why |
|---|---|---|
| **FastAPI + SQLAlchemy 2 + SQLite** | Django + DRF | Three endpoints don't need Django's admin, auth or templating. FastAPI gives typed request/response models and OpenAPI docs for free. SQLite needs no server, and SQLAlchemy keeps a switch to PostgreSQL to a change of URL. |
| **pyogrio + shapely, without geopandas** | geopandas; fiona; a pure-Python KML parser (fastkml) | pyogrio reads both formats through GDAL (LIBKML for KML) and returns raw WKB, which Shapely converts directly. geopandas would add pandas just to iterate rows. One reader for both formats is less code than a separate KML parser. |
| **One UTM zone per feature** | One zone per file; a single equal-area CRS; geodesic area with `pyproj.Geod` | Per-feature zones stay accurate when a file spans several zones, and cost nothing extra. Geodesic calculation is slightly more accurate, but the brief asks for projection to a projected CRS, so Geod is used in tests as an independent check. |
| **422 for a shapefile without a `.prj`** | Assume EPSG:4326 | If the data were actually in metres, a guessed CRS would silently give wrong numbers. Asking for the `.prj` is safer than a confident wrong answer. |
| **Flag invalid geometry, don't repair it** | `shapely.make_valid` and measure the result | Repairing changes the user's data without asking (a bow-tie becomes two triangles). Reporting `INVALID` with the reason surfaces a data-quality problem instead of hiding it. |
| **Measure once at upload and store results** | Compute on every GET | Files don't change after upload, so GETs are simple reads, and `status` reflects what really happened. |
| **Synchronous processing with a status field** | Background worker (Celery/RQ) or FastAPI `BackgroundTasks` | Processing typical survey files takes milliseconds. The `PROCESSING/COMPLETED/FAILED` status is kept so moving to async later doesn't change the API contract. |
| **Plain `def` endpoints** | `async def` | GDAL, GEOS and SQLite calls are blocking, so FastAPI runs sync endpoints in its thread pool and the event loop isn't blocked. |
| **Return geometry in the source CRS** | Convert all geometry to EPSG:4326 | The response shows exactly what was uploaded, with `crs` beside it. Reprojection is only used for measuring. |
| **Failed uploads are saved as `FAILED`** | Reject without saving | Content problems are recorded with an `error`, so `GET /api/files/{id}/` can explain them later. Requests that are clearly wrong (bad extension, too large, empty) are rejected before anything is saved. |
| **Fixed names for extracted files plus an explicit zip-slip check** | Trust archive paths; read in place with GDAL `/vsizip/` | Rejecting unsafe paths gives a clear error. Writing to fixed names means nothing in the archive decides where data lands. |

Known limits: features crossing the antimeridian are not split before measuring; tables are created with `create_all` instead of migrations; Starlette buffers the whole multipart body before the endpoint runs, so a production deployment should also cap request size at the reverse proxy (e.g. nginx `client_max_body_size`).

## Learnings

- Latitude and longitude are angles, not distances, and one degree of longitude shrinks from about 111 km at the equator to zero at the poles. That is why I project every feature to a UTM zone, which uses meters, before measuring it.
- A CRS (coordinate reference system) tells you what the numbers in a file mean, and for a shapefile it is stored in the .prj file. Without it the numbers could be degrees or meters, so I return a 422 instead of guessing and giving an area that looks right but is not.
- I pick the UTM zone from each feature's own centroid, so a file that spans two zones is still measured in the right one. To check accuracy, my tests compare against pyproj's geodesic results: a 1 km square near Kolkata is within 0.03%, and one near Sydney is within 0.01%.
- A self-intersecting polygon has no clear area. Shapely can repair it, but that changes the user's shape without telling them, so I mark it INVALID with the reason and keep measuring the other features in the file.
- An uploaded file cannot be trusted, so I reject zip entries with paths like `../../x` that would write outside the target folder (zip-slip) and save the extracted parts under fixed names. I also limit the upload and unzipped sizes, and do all the work in a temporary folder that is deleted even when processing fails.
- Small details in geo libraries matter. EPSG:4326 officially lists latitude first, so I set `always_xy=True` in pyproj to keep coordinates in (longitude, latitude) order.
- pyogrio reads both KML and shapefiles through GDAL, and its wheels bundle GDAL, so the Docker image needed no extra system packages. I checked that the KML driver worked inside the Docker image before building the rest of the code on it.

## Future scope

- Add pagination to the measurements endpoint. Right now a large file returns every feature in one response.
- Move processing to a background worker for big uploads. The PROCESSING, COMPLETED and FAILED statuses already exist, so the API would not need to change.
- Use Alembic migrations instead of creating tables at startup, and move from SQLite to Postgres with PostGIS.
- Add authentication, and cap the request size at the proxy or gateway. The current 20 MB limit is only checked after the framework has already buffered the upload.
- Support more input formats such as GeoJSON, KMZ and GeoPackage. GDAL can already read them, so most of the work is validation and tests.
- Replace the simple KML content check, which only looks for a `<kml` tag in the first 4 KB of the file, with proper XML validation.
- Handle features that cross the 180th meridian, which are not split before measuring today, and features near the poles, which are outside UTM and currently marked UNSUPPORTED.
