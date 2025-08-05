import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import psycopg2
from datetime import datetime, timedelta
import random

# 환경 변수
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [int(g) for g in os.getenv("GUILD_ID", "").split(",")]
RECORD_CHANNEL_IDS = [int(c) for c in os.getenv("RECORD_CHANNEL_ID", "").split(",")]
DB_URL = os.getenv("DATABASE_URL")
COCO_USER_ID = int(os.getenv("COCO_USER_ID", 0))

SONG_LIST = [
    "실리카겔 - APEX",
    "Hoshino Gen - Fushigi",
    "넥스트 - 도시인",
    "윤상 - 달리기",
    "DAY6 - Healer",
    "Young K - Let it be summer",
    "김승주 - 케이크가 불쌍해",
    "원필 - 행운을 빌어줘",
    "Shibata Jun - 救世主(구세주)",
    "H.O.T - 오늘도 짜증나는 날이네",
    "Porter Robinson - Shelter",
    "King gnu - 白日(백일)",
    "Jazztronik - Samurai",
    "The Delfonics - La-La Means I Love You",
    "Do As Infinity - Oasis",
    "東京事変 - 修羅場",
    "Nirvana - Smells Like Teen Spirit",
    "Blood Orange - Time Will Tell",
    "QURULI - 東京",
    "Flight Facilities - Stranded",
]

# DB 연결
def get_db_connection():
    return psycopg2.connect(DB_URL)

# 디스코드 클라이언트
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

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
async def get_user_thread(user, guild):
    for channel_id in RECORD_CHANNEL_IDS:
        try:
            forum_channel = await bot.fetch_channel(channel_id)
        except Exception as e:
            print(f"[DEBUG] 채널 불러오기 실패: {e}")
            continue

        if not isinstance(forum_channel, discord.ForumChannel):
            continue

        # 현재 스레드들
        try:
            for thread in forum_channel.threads:
                if str(user.id) in thread.name:
                    print(f"[DEBUG] 스레드 찾음 (활성): {thread.name}")
                    return thread
        except Exception as e:
            print(f"[DEBUG] 활성 스레드 탐색 실패: {e}")

        # 아카이브 스레드들
        try:
            async for archived in forum_channel.archived_threads(limit=50):
                if str(user.id) in archived.name:
                    print(f"[DEBUG] 스레드 찾음 (아카이브): {archived.name}")
                    return archived
        except Exception as e:
            print(f"[DEBUG] 아카이브 스레드 탐색 실패: {e}")

    print(f"[DEBUG] 스레드 없음: user={user.id}, name={user.display_name}")
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
                await thread.send(f"{interaction.user.mention}님의 오늘 기록 : [{self.category}] {self.checklist.value}")
                print(f"[DEBUG] 오늘 기록 메시지 전송 성공: user={interaction.user.id}")
            except Exception as e:
                print(f"[DEBUG] 오늘 기록 메시지 전송 실패: {e}")

# slash command - 기록
@bot.tree.command(name="기록", description="오늘의 기록을 남깁니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
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
@bot.tree.command(name="주간기록", description="이번 주 기록 요약", guilds=[discord.Object(id=g) for g in GUILD_IDS])
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
    await interaction.response.send_message(f"이번 주 기록 요약:\n{summary}", ephemeral=False)

# slash command - coco 호출
@bot.tree.command(name="coco", description="코코를 불러봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def coco(interaction: discord.Interaction):
    if COCO_USER_ID:
        await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)
    else:
        await interaction.response.send_message("COCO_USER_ID가 설정되지 않았습니다.", ephemeral=True)

# slash command - 추천 음악
@bot.tree.command(name="추천음악", description="랜덤 추천 음악을 받아봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 추천음악(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)
    await interaction.response.send_message(f"오늘의 추천 음악은: **{song}**", ephemeral=False)

# 메시지 이벤트 - 사진 저장
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.Thread):  # 수정됨
        if message.attachments:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE records SET image_url = %s WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                (str(message.attachments[0].url), message.author.id)
            )
            conn.commit()
            rowcount = cur.rowcount
            cur.close()
            conn.close()

            print(f"[DEBUG] 이미지 처리: user={message.author.id}, url={message.attachments[0].url}, rowcount={rowcount}")

            if rowcount > 0:
                try:
                    await message.channel.send(f"{message.author.mention}님의 사진이 기록에 추가되었습니다!")
                    print(f"[DEBUG] 사진 안내 메시지 전송 성공: user={message.author.id}")
                except Exception as e:
                    print(f"[DEBUG] 사진 안내 메시지 전송 실패: {e}")

# setup
@bot.event
async def setup_hook():
    for guild_id in GUILD_IDS:
        guild = discord.Object(id=guild_id)
        await bot.tree.sync(guild=guild)
    print("명령어 동기화 완료 (길드 전용)")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
