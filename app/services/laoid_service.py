import httpx

async def get_access_token_from_code(code: str, client_id: str, client_secret: str):
    url = "https://demo-sso.tinasoft.io/api/v1/third-party/verify"
    headers = {
        "Content-Type": "application/json",
        "X-Accept-Language": "vi"
    }
    payload = {
        "code": code,
        "clientId": client_id,
        "clientSecret": client_secret
    }

    print("📤 Gửi request tới:", url)
    print("📦 Headers:", headers)
    print("📦 Payload:", payload)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            print("📥 Trạng thái response:", resp.status_code)
            print("📥 Nội dung response:", resp.text)
            return resp.json()
        except Exception as e:
            print("❌ Lỗi khi gọi verify:", str(e))
            return {"success": False, "message": str(e)}


async def get_user_info(access_token: str, client_id: str):
    url = "https://demo-sso.tinasoft.io/api/v1/third-party/me"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "x-api-key": client_id,
        "X-Accept-Language": "vi"
    }

    print("📤 Gửi request tới:", url)
    print("📦 Headers:", headers)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers)
            print("📥 Trạng thái response:", resp.status_code)
            print("📥 Nội dung response:", resp.text)
            return resp.json()
        except Exception as e:
            print("❌ Lỗi khi gọi /me:", str(e))
            return {"success": False, "message": str(e)}
