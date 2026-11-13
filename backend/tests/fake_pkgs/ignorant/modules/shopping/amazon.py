async def amazon(phone, country_code, client, out):
    out.append({"name": "amazon", "domain": "amazon.com", "method": "login", "frequent_rate_limit": False, "rateLimit": False, "exists": phone.endswith("7")})
