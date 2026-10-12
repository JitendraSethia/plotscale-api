from fastapi import FastAPI

app = FastAPI(title="Geospatial File Measurement API")


@app.get("/")
def root():
    return {"status": "ok"}
