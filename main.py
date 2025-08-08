import os
import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import psycopg2
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import random

# 환경 변수
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [int(g) for g in os.getenv("GUILD_ID", "").split(",")]
RECORD_CHANNEL_IDS = [int(c) for c in os.getenv("RECORD_CHANNEL_ID", "").split(",")]
DB_URL = os.getenv("DATABASE_URL")
COCO_USER_ID = int(os.getenv("COCO_USER_ID", 0))

SONG_LIST = [
    "실리카겔 - APEX", "넥스트 - 도시인", "윤상 - 달리기", "DAY6 - Healer", "Young K - Let it be summer",
    "김승주 - 케이크가 불쌍해", "원필 - 행운을 빌어줘", "Shibata Jun - 救世主", "H.O.T - 오늘도 짜증나는 날이네",
    "Porter Robinson - Shelter", "King gnu - 白日", "Jazztronik - Samurai", "Do As Infinity - Oasis",
    "東京事変 - 修羅場", "Nirvana - Smells Like Teen Spirit", "Flight Facilities - Stranded"
]

# 디스코드 봇 설정
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

class AnonToCocoModal(discord.ui.Modal, title="코코에게 익명 메세지 보내기"):
    message = discord.ui.TextInput(label="보낼 메세지", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            coco = await bot.fetch_user(COCO_USER_ID)
            embed = discord.Embed(title="📩 새로운 익명 메세지", color=0xADD8E6)
            embed.add_field(name="내용", value=self.message.value, inline=False)
            embed.set_footer(text=f"시간: {datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')}")

            await coco.send(embed=embed)
            await interaction.response.send_message("✅ 메세지가 코코에게 익명으로 전송되었어요!", ephemeral=True)
        except Exception as e:
            print(f"[ERROR] 코코 디엠 전송 실패: {e}")
            await interaction.response.send_message("❌ 디엠 전송에 실패했어요. 관리자에게 문의해주세요.", ephemeral=True)

def get_db_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            category TEXT NOT NULL,
            checklist TEXT,
            image_url TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

async def scheduled_task_runner():
    await send_weekly_summaries()

async def send_weekly_summaries():
    print("[SCHEDULER] 주간 기록 자동 전송 시작")
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    start_date = today - timedelta(days=today.weekday())

    coco = await bot.fetch_user(COCO_USER_ID)
    backup_summary = ""

    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT category, checklist, image_url, date
                FROM records
                WHERE user_id = %s AND date >= %s
                ORDER BY date ASC
            """, (member.id, start_date))
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows:
                continue

            summary = f"📋 @{member.name} 님의 주간 기록 요약:\n"
            for r in rows:
                line = f"[{r[0]}] {r[1]} ({r[3].strftime('%Y-%m-%d')})"
                if r[2]:
                    line += f"\n📷 이미지: {r[2]}"
                line += "\n"
                summary += line

            backup_summary += summary + "\n-----------------------------\n"

            thread = await get_user_thread(member, guild)
            if thread:
                try:
                    await thread.send(f"{member.mention}님의 주간 기록 요약이에요!\n\n{summary}")
                except Exception as e:
                    print(f"[SCHEDULER] 주간기록 전송 실패: {e}")

    if backup_summary:
        try:
            await coco.send("📦 이번 주 전체 유저 주간기록 백업입니다:\n\n" + backup_summary)
        except Exception as e:
            print(f"[SCHEDULER] 코코 디엠 전송 실패: {e}")

async def get_user_thread(user, guild):
    for channel_id in RECORD_CHANNEL_IDS:
        forum_channel = guild.get_channel(channel_id)
        if not forum_channel:
            continue
        try:
            for thread in forum_channel.threads:
                if str(user.id) in thread.name:
                    return thread
        except Exception as e:
            print(f"[DEBUG] 스레드 탐색 실패: {e}")
    return None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    scheduler.add_job(scheduled_task_runner, 'cron', day_of_week='sun', hour=23, minute=59, timezone='Asia/Seoul')
    scheduler.start()
    print("✅ APScheduler로 주간기록 스케줄 등록됨 (일요일 23:59)")

@bot.event
async def setup_hook():
    for guild_id in GUILD_IDS:
        guild = discord.Object(id=guild_id)
        await bot.tree.sync(guild=guild)
    print("명령어 동기화 완료 (길드 전용)")

class RecordModal(discord.ui.Modal, title="기록 입력"):
    checklist = discord.ui.TextInput(label="오늘의 기록", style=discord.TextStyle.paragraph)

    def __init__(self, category):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO records (user_id, date, category, checklist) VALUES (%s, %s, %s, %s)",
            (interaction.user.id, today, self.category, self.checklist.value)
        )
        conn.commit()
        cur.close()
        conn.close()

        try:
            await interaction.response.send_message("기록이 저장되었습니다! 아래에 사진을 한 장만 올려주세요!", ephemeral=True)
        except Exception as e:
            print("[DEBUG] followup 메시지 전송 실패:", e)

        thread = await get_user_thread(interaction.user, interaction.guild)
        if thread:
            try:
                await thread.send(f"{interaction.user.mention}님의 오늘 기록 : [{self.category}] {self.checklist.value}")
            except Exception as e:
                print(f"[DEBUG] 오늘 기록 메시지 전송 실패: {e}")
        else:
            await interaction.followup.send("⚠️ 해당 유저의 포럼 스레드를 찾을 수 없습니다. 운영자에게 문의하세요.", ephemeral=True)

@bot.tree.command(name="기록", description="오늘의 기록을 남깁니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 기록(interaction: discord.Interaction):
    view = discord.ui.View()
    for category in ["운동", "식단", "단식"]:
        button = discord.ui.Button(label=category, style=discord.ButtonStyle.primary)

        async def callback(i, category=category):
            await i.response.send_modal(RecordModal(category))

        button.callback = callback
        view.add_item(button)

    await interaction.response.send_message("오늘의 기록을 선택하세요!", view=view, ephemeral=True)

@bot.tree.command(name="주간기록", description="이번 주 기록 요약", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 주간기록(interaction: discord.Interaction):
    conn = get_db_connection()
    cur = conn.cursor()
    start_date = date.today() - timedelta(days=7)
    cur.execute("""
        SELECT category, checklist, image_url, date
        FROM records
        WHERE user_id = %s AND date >= %s
        ORDER BY date ASC
    """, (interaction.user.id, start_date))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await interaction.response.send_message("이번 주에는 기록이 없습니다!", ephemeral=True)
        return

    chunks = []
    current_chunk = "📋 이번 주 기록 요약:\n"
    for r in rows:
        line = f"[{r[0]}] {r[1]} ({r[3].strftime('%Y-%m-%d')})"
        if r[2]:
            line += f"\n📷 이미지: {r[2]}"
        line += "\n"
        if len(current_chunk) + len(line) > 1900:
            chunks.append(current_chunk)
            current_chunk = ""
        current_chunk += line
    if current_chunk:
        chunks.append(current_chunk)

    for i, chunk in enumerate(chunks):
        await interaction.followup.send(chunk, ephemeral=False) if i > 0 else await interaction.response.send_message(chunk, ephemeral=False)

@bot.tree.command(name="디엠", description="코코에게 익명 메세지를 보냅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 디엠(interaction: discord.Interaction):
    await interaction.response.send_modal(AnonToCocoModal())

@bot.tree.command(name="coco", description="코코를 불러봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def coco(interaction: discord.Interaction):
    if COCO_USER_ID:
        await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)
    else:
        await interaction.response.send_message("COCO_USER_ID가 설정되지 않았습니다.", ephemeral=True)

@bot.tree.command(name="추천음악", description="랜덤 추천 음악을 받아봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 추천음악(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)
    await interaction.response.send_message(f"오늘의 추천 음악은: **{song}**", ephemeral=False)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.type == discord.ChannelType.public_thread:
        if message.attachments:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE records
                    SET image_url = %s
                    WHERE id = (
                        SELECT id FROM records
                        WHERE user_id = %s AND date = %s AND image_url IS NULL
                        ORDER BY id DESC
                        LIMIT 1
                    )
                    """,
                    (message.attachments[0].url, message.author.id, date.today())
                )
                conn.commit()
                if cur.rowcount > 0:
                    await message.channel.send(f"{message.author.mention}님의 사진이 기록에 추가되었습니다!")
            except Exception as e:
                print(f"[DEBUG] 이미지 저장 SQL 실패: {e}")
            finally:
                cur.close()
                conn.close()
    await bot.process_commands(message)

if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
