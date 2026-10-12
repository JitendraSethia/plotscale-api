from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import files
from app.db.database import Base, engine
from app.errors import FileError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)
app.include_router(files.router)


@app.exception_handler(FileError)
def handle_file_error(_request: Request, exc: FileError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
