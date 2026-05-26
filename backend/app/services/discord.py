import httpx
from typing import Optional

class DiscordNotifier:
    def __init__(self, endpoint: str = "http://localhost:5000/alert"):
        """
        Sends signals and trade alerts to the Discord bot web service.
        """
        self.endpoint = endpoint

    async def send_alert(self, message: str) -> bool:
        """
        Sends an alert message to the Discord Bot endpoint.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.endpoint,
                    json={"message": message},
                    timeout=3.0
                )
                if response.status_code == 200:
                    return True
                else:
                    print(f"Discord Bot returned status code {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            # Silence bot connection errors to prevent backend requests from breaking if bot is offline
            print(f"Could not connect to Discord Bot on {self.endpoint}: {e}")
            return False

discord_notifier = DiscordNotifier()
