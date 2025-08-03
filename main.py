import os
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import psycopg2
import datetime
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_ID = int(os.getenv("GUILD_ID"))
COCO_USER_ID = 710614752963067985
RECORD_CHANNEL_ID = int(os.getenv("RECORD_CHANNEL_ID")) 

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

# DB 연결
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# 테이블 생성 (최초 1번만 필요)
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
bot = commands.Bot(command_prefix="!", intents=intents)

# === Modal ===
class RecordModal(Modal, title="기록 입력"):
    checklist = TextInput(label="오늘 기록 (운동/식단/단식)", style=discord.TextStyle.paragraph)

    def __init__(self, category: str, user_id: int):
        super().__init__()
        self.category = category
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        today = datetime.date.today()
        # 첨부파일 URL (사진 업로드)
        image_url = interaction.message.attachments[0].url if interaction.message and interaction.message.attachments else None

        cur.execute(
            "INSERT INTO records (user_id, date, category, checklist, image_url) VALUES (%s, %s, %s, %s, %s)",
            (self.user_id, today, self.category, self.checklist.value, image_url)
        )
        conn.commit()

        # 1) 사용자에게만 안내
        await interaction.response.send_message("기록이 저장되었습니다!", ephemeral=True)

        # 2) 채널에도 기록 남기기
        channel = bot.get_channel(운동팟채널ID)  # 이건 변수로 따로 저장해둬야 함
        await channel.send(
    f"{interaction.user.mention}님의 오늘 기록 : {self.checklist.value}"
)

# === 버튼 뷰 ===
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


# === 스케줄러: 주간 요약 ===
async def weekly_report():
    today = datetime.date.today()
    start = today - datetime.timedelta(days=today.weekday())  # 이번 주 월요일
    end = start + datetime.timedelta(days=6)  # 이번 주 일요일

    cur.execute("""
        SELECT user_id, date, category, checklist, image_url
        FROM records
        WHERE date BETWEEN %s AND %s
        ORDER BY user_id, date
    """, (start, end))
    rows = cur.fetchall()

    # 데이터 정리
    user_records = {}
    for row in rows:
        user_id, date, category, checklist, image_url = row
        if user_id not in user_records:
            user_records[user_id] = {}
        user_records[user_id][date] = (category, checklist, image_url)

    # 리포트 메시지 생성
    report = "**📋 이번 주 운동팟 기록 요약**\n"
    for user_id, records in user_records.items():
        report += f"\n<@{user_id}>의 주간 기록\n"
        for i in range(7):  # 월~일 반복
            day = start + datetime.timedelta(days=i)
            if day in records:
                cat, chk, img = records[day]
                if img:
                    report += f"{day.strftime('%a')} : [{cat}] {chk}\n📷 {img}\n"
                else:
                    report += f"{day.strftime('%a')} : [{cat}] {chk}\n"
            else:
                report += f"{day.strftime('%a')} : 기록없음\n"

    # 주간 기록 채널에 보내기
    channel = bot.get_channel(RECORD_CHANNEL_ID)
    if channel:
        await channel.send(report)


    # 요약 메시지 만들기
    report = "**주간 운동팟 기록**\n"
    user_records = {}
    for row in rows:
        user_id, date, category, checklist, image_url = row
        if user_id not in user_records:
            user_records[user_id] = {}
        user_records[user_id][date] = (category, checklist, image_url)

    for user_id, records in user_records.items():
        report += f"\n<@{user_id}>의 기록\n"
        for i in range(7):
            day = start + datetime.timedelta(days=i)
            if day in records:
                cat, chk, img = records[day]
                report += f"{day.strftime('%a')} : [{cat}] {chk} {img or ''}\n"
            else:
                report += f"{day.strftime('%a')} : 기록없음\n"

    channel = bot.get_channel(RECORD_CHANNEL_ID)
    if channel:
        await channel.send(report)

# 스케줄러 등록
scheduler = AsyncIOScheduler()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("명령어 동기화 완료")
    except Exception as e:
        print(e)

    # 스케줄러를 여기서 시작
    if not scheduler.running:
        scheduler.start()
        print("스케줄러 시작됨")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    if message.attachments:
        image_url = message.attachments[0].url
        # DB에서 오늘 날짜 + user_id 기록 찾기
        cur.execute(
            "UPDATE records SET image_url = %s WHERE user_id = %s AND date = %s",
            (image_url, message.author.id, datetime.date.today())
        )
        conn.commit()
        await message.channel.send(f"{message.author.mention}님의 사진이 기록에 추가되었습니다!")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))  # 특정 서버
        await bot.tree.sync()  # 전역 싱크도 추가
        print("명령어 동기화 완료")
    except Exception as e:
        print(e)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("명령어 동기화 완료")
    except Exception as e:
        print(e)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(e)

# === Slash Command ===
@bot.tree.command(name="기록", description="오늘의 운동/식단/단식을 기록합니다", guild=discord.Object(id=GUILD_ID))
async def 기록(interaction: discord.Interaction):
    view = RecordView(interaction.user.id)
    await interaction.response.send_message(
        f"{interaction.user.mention} 오늘의 기록을 선택하세요!", view=view, ephemeral=True
    )

@bot.tree.command(name="coco", description="coco..을 소환해요!", guild=discord.Object(id=GUILD_ID))
async def coco_command(interaction: discord.Interaction):
    await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)

@bot.tree.command(name="추천음악", description="랜덤으로 음악을 추천해드려요!", guild=discord.Object(id=GUILD_ID))
async def recommend_song(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)
    await interaction.response.send_message(f"♬ 오늘의 추천 음악은...\n**{song}**..", ephemeral=False)

bot.run(TOKEN)
