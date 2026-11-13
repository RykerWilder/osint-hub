async def instagram(phone, country_code, client, out):
    out.append({"name": "instagram", "domain": "instagram.com", "method": "register", "frequent_rate_limit": False, "rateLimit": True, "exists": False})
