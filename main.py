```python
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import psycopg2
from datetime import datetime, timedelta

# 환경 변수
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [int(g) for g in os.getenv("GUILD_ID", "").split(",")]
RECORD_CHANNEL_IDS = [int(c) for c in os.getenv("RECORD_CHANNEL_ID", "").split(",")]

DB_URL = os.getenv("DATABASE_URL")

# DB 연결
def get_db_connection():
    return psycopg2.connect(DB_URL)

# 디스코드 클라이언트
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)

tree = app_commands.CommandTree(client)

# DB 초기화
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            category TEXT NOT NULL,
            checklist TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# 스레드 찾기
def match_user_thread(threads, user):
    for t in threads:
        if str(user.id) in t.name:
            return t
    return None

async def get_user_thread(user, guild):
    for channel_id in RECORD_CHANNEL_IDS:
        forum_channel = guild.get_channel(channel_id)
        if not forum_channel:
            continue
        try:
            threads = forum_channel.threads
            thread = match_user_thread(threads, user)
            if thread:
                return thread
        except Exception as e:
            print(f"[DEBUG] 스레드 탐색 실패: {e}")
    return None

# 기록 저장 모달
class RecordModal(discord.ui.Modal, title="기록 작성"):
    checklist = discord.ui.TextInput(label="오늘의 기록", style=discord.TextStyle.paragraph)

    def __init__(self, category):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO records (user_id, category, checklist) VALUES (%s, %s, %s)",
            (interaction.user.id, self.category, self.checklist.value)
        )
        conn.commit()
        cur.close()
        conn.close()

        print(f"[DEBUG] 기록 저장됨: user={interaction.user.id}, category={self.category}, checklist={self.checklist.value}")

        try:
            await interaction.response.send_message("기록이 저장되었습니다!", ephemeral=True)
            print("[DEBUG] response 메시지 전송 성공")
        except Exception as e:
            print(f"[DEBUG] response 메시지 전송 실패: {e}")

        thread = await get_user_thread(interaction.user, interaction.guild)
        if thread:
            try:
                await thread.send("📷 사진이 있다면 여기에 올려주세요!")
                print(f"[DEBUG] 사진 안내 메시지 전송 성공: user={interaction.user.id}")
            except Exception as e:
                print(f"[DEBUG] 사진 안내 메시지 전송 실패: {e}")
        else:
            print(f"[DEBUG] 스레드 없음: user={interaction.user.id}, name={interaction.user.display_name}")

# slash command - 기록
@tree.command(name="기록", description="오늘의 기록을 남깁니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 기록(interaction: discord.Interaction):
    view = discord.ui.View()
    for category in ["운동", "식단", "단식"]:
        button = discord.ui.Button(label=category, style=discord.ButtonStyle.primary)

        async def callback(interaction, category=category):
            await interaction.response.send_modal(RecordModal(category))

        button.callback = callback
        view.add_item(button)

    await interaction.response.send_message("오늘의 기록을 선택하세요!", view=view, ephemeral=True)

# slash command - 주간 기록
@tree.command(name="주간기록", description="이번 주 기록 요약", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 주간기록(interaction: discord.Interaction):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT category, checklist, image_url, created_at
        FROM records
        WHERE user_id = %s AND created_at >= %s
        ORDER BY created_at ASC
    """, (interaction.user.id, datetime.now() - timedelta(days=7)))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await interaction.response.send_message("이번 주에는 기록이 없습니다!", ephemeral=True)
        return

    summary = "\n".join([f"[{r[0]}] {r[1]} ({r[3].strftime('%Y-%m-%d')})" for r in rows])
    await interaction.response.send_message(f"이번 주 기록 요약:\n{summary}", ephemeral=True)

# slash command - coco 호출
@tree.command(name="coco", description="코코를 불러봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def coco(interaction: discord.Interaction):
    await interaction.response.send_message("네! 코코입니다~!", ephemeral=True)

# slash command - 추천 음악
@tree.command(name="추천음악", description="랜덤 추천 음악을 받아봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 추천음악(interaction: discord.Interaction):
    import random
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

    song = random.choice(songs)
    await interaction.response.send_message(f"오늘의 추천 음악은: **{song}**", ephemeral=True)

# 메시지 이벤트 - 사진 저장
@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.type == discord.ChannelType.public_thread:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE records SET image_url = %s WHERE user_id = %s ORDER BY id DESC LIMIT 1",
            (str(message.attachments[0].url) if message.attachments else None, message.author.id)
        )
        conn.commit()
        rowcount = cur.rowcount
        cur.close()
        conn.close()

        print(f"[DEBUG] 이미지 처리: user={message.author.id}, url={message.attachments[0].url if message.attachments else None}, rowcount={rowcount}")

        if rowcount > 0:
            await message.channel.send("✅ 사진이 기록에 추가되었습니다!")

# setup
@client.event
async def setup_hook():
    for guild_id in GUILD_IDS:
        guild = discord.Object(id=guild_id)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    print("명령어 동기화 완료 (길드 전용)")

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

if __name__ == "__main__":
    init_db()
    client.run(TOKEN)
```
