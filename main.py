import discord
from discord import app_commands
from discord.ext import commands
import random  # ← 위로 올려줘야 돼!

import os
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1359504363378184242
COCO_USER_ID = 710614752963067985

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 음악 리스트
SONG_LIST = [
    "실리카겔 - APEX",
    "Hoshino Gen - Fushigi",
    "넥스트 - 도시인",
    "Daryl Hall & John Oates - Rich Girl",
    "윤상 - 달리기",
    "DAY6 - Healer",
    "Young K - Let it be summer",
    "DAY6 - 행복했던 날들이었다",
    "PE'Z - Akatsuki",
    "고고학 - 파도",
    "김승주 - 케이크가 불쌍해",
    "솔루션스 - DNCM",
    "원필 - 행운을 빌어줘",
    "Shibata Jun - 救世主(구세주)",
    "H.O.T - 오늘도 짜증나는 날이네",
    "Aiko - 相思相愛(상사상애)",
    "Porter Robinson - Flicker",
    "WEDNESDAY CAMPANELLA - Ghost and Writer",
    "Porter Robinson - Shelter",
    "King gnu - 白日(백일)",
    "Jazztronik - Samurai",
    "The Internet - Under Control",
    "The Delfonics - La-La Means I Love You",
    "OFFICIAL HIGE DANDISM - Universe",
    "Fuji Faze - きらり(반짝)",
    "Do As Infinity - Oasis",
    "LUCKY TAPES - Gravity",
    "東京事変 - 修羅場",
    "Nirvana - Smells Like Teen Spirit",
    "Blood Orange - Time Will Tell",
    "Chatmonchy - 恋愛スピリッツ(연애스피릿츠)",
    "QURULI - 東京",
    "Flight Facilities - Stranded",
    "Avicii - Waiting For Love",
    "Anymore - Life Is Party",
    "Weezer - The world has turned and left me here",
    "YUKI - Cosmic Box",
    "Base Ball Bear - Stand By Me",
    "Fujifabric - Sugar!!",
    "GRAPEVIEN - Tori",
    "ELLEGARDEN - My Favorite Song",
    "Lily Chou Chou - Glider",
    "Scott Wilkie - Water Balloons",
    "Even of Day(DAY6) - 뚫고 지나가요",
    "DAY6 - Love me or leave me",
]

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)

@bot.tree.command(name="coco", description="coco..을 소환해요!", guild=discord.Object(id=GUILD_ID))
async def coco_command(interaction: discord.Interaction):
    await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)

@bot.tree.command(name="추천음악", description="랜덤으로 음악을 추천해드려요!", guild=discord.Object(id=GUILD_ID))
async def recommend_song(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)
    await interaction.response.send_message(f"♬ 오늘의 추천 음악은...\n**{song}**..", ephemeral=False)

bot.run(TOKEN)
