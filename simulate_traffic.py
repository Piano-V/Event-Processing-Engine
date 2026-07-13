import asyncio
import random
import sys
import httpx

API_URL = "https://event-processing-engine.onrender.com/api/v1"

async def simulate_traffic(num_requests: int = 150):
    """
    Simulates high-concurrency traffic:
    1. Registers a new simulator user.
    2. Obtains a JWT token.
    3. Concurrently posts diverse event streams (user.signup, page.view, payment.processed).
    4. Deliberately sends payment.processed values >10k to trigger background worker anomaly detection.
    """
    async with httpx.AsyncClient() as client:
        # 1. Register a test simulator account
        username = f"simulator_{random.randint(1000, 9999)}"
        password = "enterprise-password-456"
        print(f"[Sim] Registering user {username}...")
        
        try:
            reg_resp = await client.post(
                f"{API_URL}/auth/register",
                json={"username": username, "password": password}
            )
            if reg_resp.status_code == 201:
                print("[Sim] Registration successful.")
            else:
                print(f"[Sim] User might already exist or signup failed: {reg_resp.text}")
        except Exception as e:
            print(f"[Sim] Connection error checking FastAPI server: {e}")
            print("[Sim] Make sure the FastAPI application is running at http://localhost:8000/")
            return

        # 2. Authenticate and retrieve OAuth2 JWT token
        print("[Sim] Requesting JWT access token...")
        token_resp = await client.post(
            f"{API_URL}/auth/token",
            data={"username": username, "password": password}
        )
        if token_resp.status_code != 200:
            print(f"[Sim] Token retrieval failed: {token_resp.text}")
            return

        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[Sim] Authentication successful. Initiating high-concurrency ingestion...")

        event_types = ["user.signup", "page.view", "payment.processed"]

        async def send_single_event(index: int):
            etype = random.choice(event_types)
            payload = {}

            if etype == "payment.processed":
                value = random.choice([15.50, 99.00, 450.00, 15000.00])
                payload["value"] = value
                payload["amount"] = value
                payload["transaction_id"] = f"tx_{random.randint(100000, 999999)}"
            elif etype == "page.view":
                payload["route"] = random.choice(["/dashboard", "/settings", "/billing", "/api/keys", "/analytics"])
                payload["user_agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            else:  # user.signup
                payload["email"] = f"user_{random.randint(1000, 9999)}@gmail.com"
                payload["plan"] = random.choice(["free", "pro", "enterprise"])

            try:
                resp = await client.post(
                    f"{API_URL}/events/ingest",
                    json={"event_type": etype, "payload": payload},
                    headers=headers
                )
                
                if resp.status_code == 201:
                    res_json = resp.json()
                    is_anomaly_val = etype == "payment.processed" and value > 10000.0
                    anomaly_flag = "⚠️ [POTENTIAL ANOMALY]" if is_anomaly_val else ""
                    print(f"[Sim] [{index+1}/{num_requests}] Ingested type='{etype}' | Event ID: {res_json['id']} {anomaly_flag}")
                else:
                    print(f"[Sim] [{index+1}/{num_requests}] Ingest failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"[Sim] [{index+1}/{num_requests}] Error during HTTP post: {e}")

        # Distribute event requests concurrently with random jittering
        tasks = []
        for i in range(num_requests):
            tasks.append(send_single_event(i))
            await asyncio.sleep(random.uniform(0.01, 0.08))

        await asyncio.gather(*tasks)
        print("[Sim] Traffic simulation complete. Check live dashboard or Celery worker terminal.")

if __name__ == "__main__":
    total_reqs = 150
    if len(sys.argv) > 1:
        try:
            total_reqs = int(sys.argv[1])
        except ValueError:
            pass
    asyncio.run(simulate_traffic(total_reqs))
