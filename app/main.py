from fastapi import FastAPI
from app.api.tickets import router as tickets_router

app = FastAPI(title="Customer Support Agent Service")

app.include_router(tickets_router)