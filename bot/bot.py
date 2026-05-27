import discord
from discord.ext import commands
import os
import asyncio
from aiohttp import web
from dotenv import load_dotenv

# Load env vars from root directory (global .env)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID_ENV = os.getenv("DISCORD_CHANNEL_ID")
CHANNEL_ID = int(CHANNEL_ID_ENV) if (CHANNEL_ID_ENV and CHANNEL_ID_ENV.isdigit()) else None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"=== Discord Bot Online ===")
    print(f"Logged in as: {bot.user.name} (ID: {bot.user.id})")
    if CHANNEL_ID:
        print(f"Configured Alerts Channel ID: {CHANNEL_ID}")
    else:
        print("WARNING: DISCORD_CHANNEL_ID not set or invalid. Set it in .env to route alerts.")
    print(f"==========================")
    
    # Start the HTTP listener
    bot.loop.create_task(start_webserver())

async def handle_alert(request):
    """
    HTTP POST handler to broadcast messages from backend API to Discord.
    Expected payload: {"message": "Alert text string"}
    """
    try:
        data = await request.json()
        message = data.get("message")
        if not message:
            return web.json_response({"success": False, "error": "Missing 'message' in request body"}, status=400)
            
        if not CHANNEL_ID:
            return web.json_response({"success": False, "error": "Channel ID not configured on Bot"}, status=500)
            
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            # Try to fetch channel if not cached
            try:
                channel = await bot.fetch_channel(CHANNEL_ID)
            except Exception:
                pass
                
        if channel:
            # Embed format for premium aesthetics
            embed = discord.Embed(
                title="📈 Dark Pool Indicator Alert",
                description=message,
                color=discord.Color.dark_purple()
            )
            embed.set_footer(text="DarkPoolData Platform • Automated Signal")
            await channel.send(embed=embed)
            return web.json_response({"success": True, "message": "Alert broadcasted successfully"})
        else:
            return web.json_response({"success": False, "error": f"Could not resolve channel {CHANNEL_ID}"}, status=404)
            
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def start_webserver():
    """
    Runs a lightweight HTTP server inside the bot loop to accept webhook requests.
    """
    app = web.Application()
    app.router.add_post("/alert", handle_alert)
    runner = web.AppRunner(app)
    await runner.setup()
    # Run locally on port 5000
    site = web.TCPSite(runner, "localhost", 5000)
    await site.start()
    print("Webhook listener activated on http://localhost:5000/alert")

@bot.command(name="ping")
async def ping(ctx):
    """Simple ping-pong health check command."""
    await ctx.send(f"Pong! Latency: {round(bot.latency * 1000)}ms")

@bot.command(name="status")
async def status(ctx):
    """Returns bot status."""
    status_msg = (
        f"**DarkPoolData Bot Status:**\n"
        f"🟢 Online\n"
        f"📢 Alert Channel Configured: `{CHANNEL_ID is not None}`\n"
        f"🔗 API Receiver: `http://localhost:5000/alert`"
    )
    await ctx.send(status_msg)

def main():
    if not TOKEN or TOKEN.startswith("YOUR_"):
        print("DISCORD_BOT_TOKEN not configured in .env. Skipping Discord Bot execution.")
        print("Please set up a bot token in your global .env to run this.")
        return
        
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
