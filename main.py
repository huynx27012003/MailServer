from fastapi import FastAPI
from app.routes import auth, mail
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Cho phép từ http://localhost
origins = [
    "http://localhost",
    "http://localhost:80",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://127.0.0.1",
    "http://127.0.0.1:80",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8081",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # ✅ Cho phép các origin cụ thể
    allow_credentials=True,
    allow_methods=["*"],              # GET, POST, etc.
    allow_headers=["*"],
)



app.include_router(auth.router)
app.include_router(mail.router)