from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.services import jwt_service, imap_service, laoid_service
from app.services.jwt_service import get_current_user
from app.services.session_store import set as store_password
import subprocess
import os

router = APIRouter(prefix="/auth")

# ---- App credentials ----
CLIENT_ID = "660dfa27-5a95-4c88-8a55-abe1310bf579"
CLIENT_SECRET = "df1699140bcb456eaa6d85d54c5fbd79"

# ---- DTO models ----
class LoginRequest(BaseModel):
    username: str
    password: str

class LaoIDLoginRequest(BaseModel):
    access_token: str

class IMAPAuthRequest(BaseModel):
    password: str

class LaoIDCodeRequest(BaseModel):
    code: str

# ---- API: Lấy thông tin user từ JWT ----
@router.get("/me")
async def me(request: Request, user: str = Depends(get_current_user)):
    return {"user": user}

# ---- API: Đăng nhập thủ công bằng username/password ----
@router.post("/login")
def login(request: LoginRequest):
    username = request.username.strip()
    if '@' in username:
        username = username.split("@")[0]

    if imap_service.login_imap(username, request.password):
        store_password(username, request.password)
        token = jwt_service.create_token(request.username)
        print(f"✅ Đăng nhập thủ công: {request.username}")
        return {"token": token}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# ---- API: Đăng nhập bằng LaoID SSO (access_token từ FE) ----
@router.post("/laoid-login")
async def laoid_login(data: LaoIDCodeRequest):
    print(f"📥 Nhận code từ frontend: {data.code}")

    # Step 1: Gửi code để lấy access_token
    token_res = await laoid_service.get_access_token_from_code(data.code, CLIENT_ID, CLIENT_SECRET)
    if not token_res.get("success"):
        raise HTTPException(status_code=400, detail=token_res.get("message", "Lỗi lấy access_token"))

    access_token = token_res["data"]["accessToken"]

    # Step 3: Gọi /me để lấy thông tin người dùng
    userinfo = await laoid_service.get_user_info(access_token, CLIENT_ID)
    if not userinfo.get("success") or "data" not in userinfo:
        raise HTTPException(status_code=400, detail="Không lấy được thông tin người dùng")

    email = userinfo["data"]["email"][0]["email"]
    token = jwt_service.create_token(email)
    return {"token": token}

# ---- API: Xác thực IMAP hoặc tạo user IMAP mới ----
@router.post("/imap-auth")
def imap_auth(data: IMAPAuthRequest, user: str = Depends(get_current_user)):
    username = user.split("@")[0]  # Nếu không có @ thì vẫn lấy đúng

    if imap_service.login_imap(username, data.password):
        store_password(username, data.password)
        print(f"✅ IMAP password stored for {username}")
        return {"message": "Đăng nhập IMAP thành công"}

    print(f"⚠️ IMAP login failed. Thử tạo mới user: {username}")

    # Tạo user mới trên WSL
    if imap_service.create_imap_user(username, data.password):
        if imap_service.login_imap(username, data.password):
            store_password(username, data.password)
            print(f"✅ Đã tạo và login IMAP thành công cho {username}")
            return {"message": "Tạo mới và đăng nhập IMAP thành công"}

    raise HTTPException(status_code=401, detail="IMAP login thất bại, không thể tạo user mới")
