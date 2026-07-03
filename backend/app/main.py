import uvicorn
from fastapi import FastAPI
from app.core.config import settings

# Create FastAPI app instance
app = FastAPI(title="Job Automation")

@app.get("/")
def health_check():
    return {"environment": settings.env, "port": settings.port}

if __name__ == "__main__":
    # Run FastAPI app running in uvicorn webserver
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)