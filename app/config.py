import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./plotscale.db")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
# Zip bomb guard: limit on the uncompressed size of the extracted shapefile parts.
MAX_UNZIPPED_MB = int(os.getenv("MAX_UNZIPPED_MB", "200"))
