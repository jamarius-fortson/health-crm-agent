from fastapi import FastAPI
from healthcare_agent.api.routes import router

app = FastAPI(
    title="Healthcare CRM Agent",
    description="HIPAA-compliant autonomous front-office and care-coordination platform",
    version="0.1.0",
)

app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Healthcare CRM Agent API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}