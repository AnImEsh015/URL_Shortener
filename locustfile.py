"""Locust load testing scenario for the URL Shortener service.

Workload Profile:
- Heavy read/redirect workload (95% weight): Simulates high-throughput link clicks.
  Important: allow_redirects=False ensures Locust records the shortener's own response latency
  (the 302 redirect), rather than the destination server's latency.
- Light write workload (5% weight): Authenticated link generation.

Usage:
  # 1. Run with cache enabled (default)
  locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 --run-time 1m

  # 2. Run with cache disabled (set CACHE_ENABLED=false in docker-compose or .env, restart api)
  locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 --run-time 1m
"""

import random
import uuid

from locust import HttpUser, between, task


class ShortenerUser(HttpUser):
    # Wait between 50ms and 200ms between requests to simulate active traffic
    wait_time = between(0.05, 0.2)

    def on_start(self):
        """Initializes user session by registering, logging in, and creating a seed link."""
        self.email = f"loadtest_{uuid.uuid4().hex[:10]}@benchmark.com"
        self.password = "benchmarkSecret123"
        self.headers = {}
        self.short_codes = []

        # 1. Register
        self.client.post(
            "/auth/register",
            json={"email": self.email, "password": self.password},
            name="/auth/register",
        )

        # 2. Login
        login_resp = self.client.post(
            "/auth/login",
            data={"username": self.email, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="/auth/login",
        )
        if login_resp.status_code == 200:
            token = login_resp.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {token}"}

        # 3. Create initial seed link
        create_resp = self.client.post(
            "/api/links",
            json={"url": f"https://example.com/initial/{uuid.uuid4().hex[:8]}"},
            headers=self.headers,
            name="/api/links [seed]",
        )
        if create_resp.status_code == 201:
            code = create_resp.json().get("short_code")
            if code:
                self.short_codes.append(code)

    @task(20)
    def redirect_task(self):
        """Heavy task: Simulates clicking shortened links.

        allow_redirects=False is required to measure shortener redirect latency
        without fetching third-party external web pages.
        """
        if not self.short_codes:
            return

        code = random.choice(self.short_codes)
        with self.client.get(
            f"/{code}",
            allow_redirects=False,
            name="/{short_code} [redirect]",
            catch_response=True,
        ) as response:
            if response.status_code == 302:
                response.success()
            else:
                response.failure(f"Expected 302, got {response.status_code}")

    @task(1)
    def create_link_task(self):
        """Light task: Authenticated link creation."""
        if not self.headers:
            return

        target_url = f"https://example.com/target/{random.randint(1000, 999999)}"
        resp = self.client.post(
            "/api/links",
            json={"url": target_url},
            headers=self.headers,
            name="/api/links [create]",
        )
        if resp.status_code == 201:
            new_code = resp.json().get("short_code")
            if new_code:
                self.short_codes.append(new_code)
