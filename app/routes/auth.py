from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.services import jwt_service, user_db_service, laoid_service
from app.services.jwt_service import get_current_user
from app.services.session_store import set as store_password
from app.services.imap_idle import start_idle_for_user
import subprocess
import os
from app.services import user_db_service, imap_service
router = APIRouter(prefix="/auth")

# ---- App credentials (LaoID) ----
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

# ---- API: Đăng nhập thủ công bằng email/password (user ảo trong MySQL) ----
@router.post("/login")
def login(request: LoginRequest):
    username = request.username.strip()

    if '@' not in username:
        username += "@example.com"  # bổ sung domain nếu thiếu

    plain_password = request.password

    # ✅ Xác thực bằng database
    if not user_db_service.verify_user_credentials(username, plain_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ✅ Thử login IMAP với password nhập vào
    if imap_service.login_imap(username, plain_password):
        store_password(username, plain_password)
        print(f"✅ Đăng nhập user ảo: {username}")
    else:
        # ✅ Nếu thất bại, thử với password mặc định
        fallback = "Huyhuhong123@"
        print(f"⚠️ Thử lại với mật khẩu mặc định cho {username}")
        if imap_service.login_imap(username, fallback):
            store_password(username, fallback)
            print(f"✅ Đăng nhập bằng mật khẩu mặc định: {username}")
        else:
            print(f"❌ IMAP login thất bại với cả 2 mật khẩu")
            raise HTTPException(status_code=401, detail="IMAP login failed")

    # ✅ Tạo token trả về
    token = jwt_service.create_token(username)
    return {"token": token}

# ---- API: Đăng nhập bằng LaoID SSO (access_token từ FE) ----
@router.post("/laoid-login")
async def laoid_login(data: LaoIDCodeRequest):
    print(f"📥 Nhận code từ frontend: {data.code}")

    token_res = await laoid_service.get_access_token_from_code(data.code, CLIENT_ID, CLIENT_SECRET)
    if not token_res.get("success"):
        raise HTTPException(status_code=400, detail=token_res.get("message", "Lỗi lấy access_token"))

    access_token = token_res["data"]["accessToken"]

    userinfo = await laoid_service.get_user_info(access_token, CLIENT_ID)
    if not userinfo.get("success") or "data" not in userinfo:
        raise HTTPException(status_code=400, detail="Không lấy được thông tin người dùng")

    email = userinfo["data"]["email"][0]["email"]
    token = jwt_service.create_token(email)
    return {"token": token}

# ---- API: Xác thực IMAP cho user ảo (không tạo user hệ thống) ----
@router.post("/imap-auth")
def imap_auth(data: IMAPAuthRequest, user: str = Depends(get_current_user)):
    email = user.strip()

    if user_db_service.verify_user_credentials(email, data.password):
        store_password(email, data.password)
        print(f"✅ IMAP auth thành công cho user ảo: {email}")
        return {"message": "Xác thực IMAP thành công"}

    raise HTTPException(status_code=401, detail="IMAP login thất bại (user ảo sai thông tin)")
