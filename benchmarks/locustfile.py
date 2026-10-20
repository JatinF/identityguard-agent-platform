"""Local load-test entry. No measurement from this file is committed."""

from locust import HttpUser, task


class HealthUser(HttpUser):
    @task
    def health(self):
        self.client.get("/healthz")
