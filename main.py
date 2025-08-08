import os
import discord
from discord import app_commands
from discord.ext import commands, tasks  # ✅ tasks를 여기로!
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


# 코코 디엠 모달
class AnonToCocoModal(discord.ui.Modal, title="코코에게 익명 메세지 보내기"):
    message = discord.ui.TextInput(label="보낼 메세지", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            coco = await bot.fetch_user(COCO_USER_ID)
            embed = discord.Embed(title="\ud83d\udce9 새로운 익명 메세지", color=0xADD8E6)
            embed.add_field(name="내용", value=self.message.value, inline=False)
            embed.set_footer(text=f"시간: {datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')}")

            await coco.send(embed=embed)
            await interaction.response.send_message("\u2705 메세지가 코코에게 익명으로 전송되었어요!", ephemeral=True)
            print(f"[DEBUG] 익명 메세지 전송 완료: to COCO_USER_ID={COCO_USER_ID}")

        except Exception as e:
            print(f"[ERROR] 코코 디엠 전송 실패: {e}")
            await interaction.response.send_message("\u274c 디엠 전송에 실패했어요. 관리자에게 문의해주세요.", ephemeral=True)


# DB 연결 함수
def get_db_connection():
    return psycopg2.connect(DB_URL)


# DB 초기화
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

# 디스코드 봇 설정
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)



# 주간기록 자동 전송 + 코코양 디엠 백업
@tasks.loop(minutes=1)
async def scheduled_task():
    await send_weekly_summaries()

async def send_weekly_summaries():
    print("[SCHEDULER] 주간 기록 자동 전송 시작")
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    start_date = today - timedelta(days=today.weekday())  # 이번 주 월요일부터

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
                    print(f"[SCHEDULER] 주간기록 전송 완료: {member.id}")
                except Exception as e:
                    print(f"[SCHEDULER] 주간기록 전송 실패: {e}")

    if backup_summary:
        try:
            await coco.send("📦 이번 주 전체 유저 주간기록 백업입니다:\n\n" + backup_summary)
            print("[SCHEDULER] 코코 디엠 백업 전송 완료")
        except Exception as e:
            print(f"[SCHEDULER] 코코 디엠 전송 실패: {e}")

# 스레드 찾기
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

# 봇 시작 시 봇 정보 출력 및 루프 시작
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not scheduled_task.is_running():
        scheduled_task.start()
        print("✅ 디스코드 tasks.loop로 주간기록 스케줄 시작됨")

# 명령어 동기화
@bot.event
async def setup_hook():
    print("[DEBUG] setup_hook 실행됨")
    print("명령어 동기화 완료 (길드 전용)")





# 스레드 찾기
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

# 기록 모달
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
        print(f"[DEBUG] 기록 저장됨: user={interaction.user.id}, category={self.category}, checklist={self.checklist.value}")

        try:
            await interaction.response.send_message("기록이 저장되었습니다! 아래에 사진을 한 장만 올려주세요!", ephemeral=True)
            print("[DEBUG] response 메시지 전송 성공")
        except Exception as e:
            print("[DEBUG] followup 메시지 전송 실패:", e)

        thread = await get_user_thread(interaction.user, interaction.guild)
        if thread:
            try:
                await thread.send(f"{interaction.user.mention}님의 오늘 기록 : [{self.category}] {self.checklist.value}")
                print(f"[DEBUG] 오늘 기록 메시지 전송 성공: user={interaction.user.id}")
            except Exception as e:
                print(f"[DEBUG] 오늘 기록 메시지 전송 실패: {e}")
        else:
            await interaction.followup.send("\u26a0\ufe0f 해당 유저의 포럼 스레드를 찾을 수 없습니다. 운영자에게 문의하세요.", ephemeral=True)


# 커맨드: 기록
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

# 커맨드: 주간 기록
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

        # 메시지 나눠 보내기
    chunks = []
    current_chunk = "📋 이번 주 기록 요약:\n"
    for r in rows:
        line = f"[{r[0]}] {r[1]} ({r[3].strftime('%Y-%m-%d')})"
        if r[2]:  # image_url
            line += f"\n📷 이미지: {r[2]}"
        line += "\n"

        if len(current_chunk) + len(line) > 1900:
            chunks.append(current_chunk)
            current_chunk = ""
        current_chunk += line
    if current_chunk:
        chunks.append(current_chunk)


    # 차례대로 전송
    for i, chunk in enumerate(chunks):
        await interaction.followup.send(chunk, ephemeral=False) if i > 0 else await interaction.response.send_message(chunk, ephemeral=False)

# 커맨드 ; 코코 디엠
@bot.tree.command(name="디엠", description="코코에게 익명 메세지를 보냅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 디엠(interaction: discord.Interaction):
    await interaction.response.send_modal(AnonToCocoModal())


# 커맨드: 코코 호출
@bot.tree.command(name="coco", description="코코를 불러봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def coco(interaction: discord.Interaction):
    if COCO_USER_ID:
        await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)
    else:
        await interaction.response.send_message("COCO_USER_ID가 설정되지 않았습니다.", ephemeral=True)

# 커맨드: 추천 음악
@bot.tree.command(name="추천음악", description="랜덤 추천 음악을 받아봅니다", guilds=[discord.Object(id=g) for g in GUILD_IDS])
async def 추천음악(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)
    await interaction.response.send_message(f"오늘의 추천 음악은: **{song}**", ephemeral=False)

# 사진 저장 감지
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
                rowcount = cur.rowcount
                if rowcount > 0:
                    await message.channel.send(f"{message.author.mention}님의 사진이 기록에 추가되었습니다!")
                    print(f"[DEBUG] 사진 안내 메시지 전송 성공: user={message.author.id}")
                else:
                    print(f"[DEBUG] DB 업데이트 실패: rowcount=0")
            except Exception as e:
                print(f"[DEBUG] 이미지 저장 SQL 실패: {e}")
            finally:
                cur.close()
                conn.close()
    await bot.process_commands(message)

# 명령어 동기화
@bot.event
async def setup_hook():
    for guild_id in GUILD_IDS:
        guild = discord.Object(id=guild_id)
        await bot.tree.sync(guild=guild)
    print("명령어 동기화 완료 (길드 전용)")

# 봇 준비 완료
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# 실행
if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
