# 콩물이 약속했던 최신 에러 수정 반영된 전체 main.py 코드야!
# 이제 date 관련 오류 없이 정상 작동할 거다냐!

import os
import random
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import psycopg2
import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_IDS = [int(gid.strip()) for gid in os.getenv("GUILD_IDS", "").split(",") if gid.strip()]
RECORD_CHANNEL_IDS = [int(cid.strip()) for cid in os.getenv("RECORD_CHANNEL_IDS", "").split(",") if cid.strip()]
COCO_USER_ID = int(os.getenv("COCO_USER_ID", 0))

SONG_LIST = [
    "실리카겔 - APEX", "Hoshino Gen - Fushigi", "넥스트 - 도시인", "윤상 - 달리기",
    "DAY6 - Healer", "Young K - Let it be summer", "김승주 - 케이크가 불쌍해", "원필 - 행운을 빌어줘",
    "Shibata Jun - 救世主(구세주)", "H.O.T - 오늘도 짜증나는 날이네", "Porter Robinson - Shelter",
    "King gnu - 白日(백일)", "Jazztronik - Samurai", "The Delfonics - La-La Means I Love You",
    "Do As Infinity - Oasis", "東京事変 - 修羅場", "Nirvana - Smells Like Teen Spirit",
    "Blood Orange - Time Will Tell", "QURULI - 東京", "Flight Facilities - Stranded"
]

conn = psycopg2.connect(DATABASE_URL)
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

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class CocoBot(commands.Bot):
    async def setup_hook(self):
        try:
            for gid in GUILD_IDS:
                guild_obj = discord.Object(id=gid)
                self.tree.clear_commands(guild=guild_obj)
                await setup_commands(self.tree, gid)
                synced = await self.tree.sync(guild=guild_obj)
                print(f"명령어 동기화 완료 (길드 전용 {gid})")
                print("등록된 커맨드 목록:", [c.name for c in synced])
        except Exception as e:
            print("[ERROR] setup_hook:", e)

        if not scheduler.running:
            scheduler.start()
            print("스케줄러 시작됨")

bot = CocoBot(command_prefix="!", intents=intents)

async def get_user_thread(user: discord.User | discord.Member):
    for cid in RECORD_CHANNEL_IDS:
        forum_channel = bot.get_channel(cid)
        if not isinstance(forum_channel, discord.ForumChannel):
            continue

        try:
            threads = forum_channel.threads
        except Exception as e:
            print(f"[DEBUG] threads 불러오기 실패: {e}")
            threads = []

        target = str(user.id)
        for thread in threads:
            if target in thread.name:
                print(f"[DEBUG] 스레드 찾음 (규칙 매칭): {thread.name}")
                return thread

        try:
            async for archived in forum_channel.archived_threads(limit=50):
                if target in archived.name:
                    print(f"[DEBUG] 아카이브 스레드 찾음 (규칙 매칭): {archived.name}")
                    return archived
        except Exception as e:
            print(f"[DEBUG] 아카이브 스레드 불러오기 실패: {e}")

        thread_names = [t.name for t in threads] if threads else []
        print(f"[DEBUG] 스레드 없음: user={user.id}, name={user.display_name}, threads={thread_names}, forum_channel={forum_channel.name}")
    return None

class RecordModal(Modal, title="기록 입력"):
    checklist = TextInput(label="오늘 기록 (운동/식단/단식)", style=discord.TextStyle.paragraph)
    def __init__(self, category: str, user_id: int):
        super().__init__()
        self.category = category
        self.user_id = user_id
    async def on_submit(self, interaction: discord.Interaction):
        today = datetime.date.today()
        cur.execute(
            "INSERT INTO records (user_id, date, category, checklist, image_url) VALUES (%s, %s, %s, %s, %s)",
            (self.user_id, today, self.category, self.checklist.value, None)
        )
        conn.commit()
        print(f"[DEBUG] 기록 저장됨: user={self.user_id}, category={self.category}, checklist={self.checklist.value}")

        await ensure_response(interaction, "기록이 저장되었습니다!")

        thread = await get_user_thread(interaction.user)
        if thread:
            await thread.send(f"{interaction.user.mention}님의 오늘 기록 : [{self.category}] {self.checklist.value}")
        else:
            await ensure_response(interaction, "⚠️ 해당 유저의 포럼 스레드를 찾을 수 없습니다. 운영자에게 문의하세요.")

async def ensure_response(interaction: discord.Interaction, content: str):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True)
            print("[DEBUG] response 메시지 전송 성공")
        else:
            await interaction.followup.send(content, ephemeral=True)
            print("[DEBUG] followup 메시지 전송 성공")
    except Exception as e:
        print("[DEBUG] ensure_response 실패:", e)

class RecordView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
    @discord.ui.button(label="운동", style=discord.ButtonStyle.green)
    async def exercise_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RecordModal("운동", self.user_id))
    @discord.ui.button(label="식단", style=discord.ButtonStyle.blurple)
    async def diet_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RecordModal("식단", self.user_id))
    @discord.ui.button(label="단식", style=discord.ButtonStyle.red)
    async def fast_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RecordModal("단식", self.user_id))

async def setup_commands(tree, gid):
    guild_obj = discord.Object(id=gid)

    @tree.command(name="기록", description="오늘의 운동/식단/단식을 기록합니다", guild=guild_obj)
    async def record_cmd(interaction: discord.Interaction):
        view = RecordView(interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} 오늘의 기록을 선택하세요!", view=view, ephemeral=True)

    @tree.command(name="coco", description="coco..을 소환해요!", guild=guild_obj)
    async def coco_command(interaction: discord.Interaction):
        if COCO_USER_ID:
            await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)
        else:
            await interaction.response.send_message("COCO_USER_ID가 설정되지 않았습니다.", ephemeral=True)

    @tree.command(name="추천음악", description="랜덤으로 음악을 추천해드려요!", guild=guild_obj)
    async def recommend_song(interaction: discord.Interaction):
        song = random.choice(SONG_LIST)
        await interaction.response.send_message(f"♬ 오늘의 추천 음악은...\n{song}", ephemeral=False)

    @tree.command(name="주간기록", description="이번 주 기록 요약을 강제로 보여줍니다", guild=guild_obj)
    async def manual_weekly(interaction: discord.Interaction):
        await interaction.response.send_message("📋 주간 요약 테스트 시작!", ephemeral=True)
        await weekly_report()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.attachments:
        if isinstance(message.channel, discord.Thread) and message.channel.parent_id in RECORD_CHANNEL_IDS:
            try:
                await message.channel.join()
            except Exception as e:
                print(f"[DEBUG] 스레드 참여 실패: {e}")
            saved = False
            for attachment in message.attachments:
                image_url = attachment.url
                cur.execute("""
                    UPDATE records
                    SET image_url = %s
                    WHERE id = (
                        SELECT id FROM records
                        WHERE user_id = %s AND date = %s AND image_url IS NULL
                        ORDER BY id DESC LIMIT 1
                    )
                """, (image_url, message.author.id, datetime.date.today()))
                print(f"[DEBUG] 이미지 처리: user={message.author.id}, url={image_url}, rowcount={cur.rowcount}")
                if cur.rowcount > 0:
                    saved = True
                conn.commit()
            if saved:
                try:
                    await message.channel.send(f"{message.author.mention}님의 사진이 기록에 추가되었습니다!")
                    print(f"[DEBUG] 사진 안내 메시지 전송 성공: user={message.author.id}")
                except Exception as e:
                    print("[DEBUG] 사진 안내 메시지 전송 실패:", e)
            else:
                print(f"[DEBUG] DB 업데이트 실패: user={message.author.id}")
    await bot.process_commands(message)

async def weekly_report():
    today = datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())
    end = start + datetime.timedelta(days=6)
    cur.execute("""
        SELECT user_id, date, category, checklist, image_url
        FROM records
        WHERE date BETWEEN %s AND %s
        ORDER BY user_id, date, id
    """, (start, end))
    rows = cur.fetchall()
    user_records = {}
    for row in rows:
        user_id, date, category, checklist, image_url = row
        if user_id not in user_records:
            user_records[user_id] = {}
        if date not in user_records[user_id]:
            user_records[user_id][date] = []
        user_records[user_id][date].append((category, checklist, image_url))
    for user_id, records in user_records.items():
        thread = await get_user_thread(await bot.fetch_user(user_id))
        if not thread:
            continue
        report = f"**📋 이번 주 기록 요약**\n<@{user_id}>의 주간 기록\n"
        for i in range(7):
            day = start + datetime.timedelta(days=i)
            if day in records:
                for cat, chk, img in records[day]:
                    if img:
                        report += f"{day.strftime('%a')} : [{cat}] {chk}\n📷 {img}\n"
                    else:
                        report += f"{day.strftime('%a')} : [{cat}] {chk}\n"
            else:
                report += f"{day.strftime('%a')} : 기록없음\n"
        await thread.send(report)

scheduler = AsyncIOScheduler()
scheduler.add_job(weekly_report, "cron", day_of_week="sun", hour=23, minute=59)

bot.run(TOKEN)
