import requests
from locust import HttpUser, task, between, events

STRESS_EMAIL = "stress@test.com"
STRESS_PASSWORD = "StressTest123!"
WRONG_PASSWORD = "definitely-not-the-password"


@events.test_start.add_listener
def ensure_stress_user(environment, **kwargs):
    base = (environment.host or "http://localhost:8000").rstrip("/")
    try:
        requests.post(
            f"{base}/api/v1/auth/register",
            json={"email": STRESS_EMAIL, "password": STRESS_PASSWORD},
            timeout=10,
        )
    except requests.RequestException:
        pass


class FinSightLoadUser(HttpUser):
    host = "http://localhost:8000"
    wait_time = between(1, 3)

    @task(1)
    def health_check(self):
        self.client.get("/health", name="GET /health [light]")

    @task(3)
    def login_bcrypt_stress(self):
        with self.client.post(
            "/api/v1/auth/login",
            data={"username": STRESS_EMAIL, "password": WRONG_PASSWORD},
            name="POST /api/v1/auth/login [bcrypt]",
            catch_response=True,
        ) as response:
            if response.status_code == 401:
                response.success()