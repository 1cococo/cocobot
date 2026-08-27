import os
import io
import random
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import psycopg2
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from PIL import Image

# ============================================================
# 환경 변수
# ============================================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [int(g) for g in os.getenv("GUILD_ID", "").split(",") if g.strip()]
RECORD_CHANNEL_IDS = [int(c) for c in os.getenv("RECORD_CHANNEL_ID", "").split(",") if c.strip()]
DB_URL = os.getenv("DATABASE_URL")
COCO_USER_ID = int(os.getenv("COCO_USER_ID", 0))

# ============================================================
# 키워드 자동 반응 설정
# ============================================================
TRIGGER_KEYWORDS = [
    s.strip()
    for s in os.getenv("TRIGGER_KEYWORDS", "coco").split(",")
    if s.strip()
]
TRIGGER_RESPONSE = os.getenv("TRIGGER_RESPONSE", "코코를 부르셨나요?")
TRIGGER_COOLDOWN_SECONDS = int(os.getenv("TRIGGER_COOLDOWN_SECONDS", "5"))
COCO_LOG_CHANNEL_ID = int(os.getenv("COCO_LOG_CHANNEL_ID", 0))
_last_trigger_ts = {}

# ============================================================
# 링크 기능
# ============================================================
LINKS = {
    "정보공유방": "https://open.kakao.com/o/gRCXZYyi",
    "투표방": "https://open.kakao.com/o/ggVsiofi",
    "네이버카페": "https://naver.me/FdoSMZi3",
    "공식디스코드": "https://discord.gg/suitu",
    "과금사이트": "https://suitu-pay-payermax.libii.com/KR/suitu",
}

# ============================================================
# 자동 글 전송 설정
# ============================================================
SOURCE_GUILD_ID = 1088352346322518066
SOURCE_CHANNEL_ID = 1096279871031889930

TARGET_GUILD_ID = 1359504363378184242
TARGET_CHANNEL_ID = 1359524353494093864

# ============================================================
# 추천 음악
# ============================================================
SONG_LIST = [
    "실리카겔 - APEX",
    "넥스트 - 도시인",
    "윤상 - 달리기",
    "DAY6 - Healer",
    "Young K - Let it be summer",
    "김승주 - 케이크가 불쌍해",
    "원필 - 행운을 빌어줘",
    "Shibata Jun - 救世主",
    "H.O.T - 오늘도 짜증나는 날이네",
    "Porter Robinson - Shelter",
    "King gnu - 白日",
    "Jazztronik - Samurai",
    "Do As Infinity - Oasis",
    "東京事変 - 修羅場",
    "Nirvana - Smells Like Teen Spirit",
    "Flight Facilities - Stranded",
]

# ============================================================
# 디스코드 봇 설정
# ============================================================
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

# ============================================================
# DB
# ============================================================
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


# ============================================================
# 익명 DM
# ============================================================
class AnonToCocoModal(discord.ui.Modal, title="코코에게 익명 메세지 보내기"):
    message = discord.ui.TextInput(
        label="보낼 메세지",
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            coco = await bot.fetch_user(COCO_USER_ID)

            embed = discord.Embed(
                title="📩 새로운 익명 메세지",
                color=0xADD8E6
            )
            embed.add_field(
                name="내용",
                value=self.message.value,
                inline=False
            )
            embed.set_footer(
                text=(
                    f"시간: {datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')}"
                )
            )

            await coco.send(embed=embed)
            await interaction.response.send_message(
                "✅ 메세지가 코코에게 익명으로 전송되었어요!",
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] 코코 디엠 전송 실패: {e}")
            await interaction.response.send_message(
                "❌ 디엠 전송에 실패했어요. 관리자에게 문의해주세요.",
                ephemeral=True
            )


# ============================================================
# 유저 스레드 찾기
# ============================================================
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


# ============================================================
# 주간 기록 자동 전송
# ============================================================
async def scheduled_task_runner():
    await send_weekly_summaries()


async def send_weekly_summaries():
    print("[SCHEDULER] 주간 기록 자동 전송 시작")

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    start_of_week = today_kst - timedelta(days=today_kst.weekday())
    end_of_week = start_of_week + timedelta(days=6)

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
                WHERE user_id = %s
                  AND date BETWEEN %s AND %s
                ORDER BY date ASC
            """, (member.id, start_of_week, end_of_week))

            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows:
                continue

            range_text = (
                f"{start_of_week.strftime('%Y-%m-%d')} ~ "
                f"{end_of_week.strftime('%Y-%m-%d')}"
            )

            summary = (
                f"📋 @{member.name} 님의 주간 기록 요약 "
                f"({range_text}):\n"
            )

            for row in rows:
                line = (
                    f"[{row[0]}] {row[1]} "
                    f"({row[3].strftime('%Y-%m-%d')})"
                )

                if row[2]:
                    line += f"\n📷 이미지: {row[2]}"

                line += "\n"
                summary += line

            backup_summary += (
                summary +
                "\n-----------------------------\n"
            )

            thread = await get_user_thread(member, guild)

            if thread:
                try:
                    await thread.send(
                        f"{member.mention}님의 주간 기록 요약이에요!\n\n{summary}"
                    )
                except Exception as e:
                    print(f"[SCHEDULER] 주간기록 전송 실패: {e}")

    if backup_summary:
        try:
            await coco.send(
                "📦 이번 주 전체 유저 주간기록 백업입니다:\n\n"
                + backup_summary
            )
        except Exception as e:
            print(f"[SCHEDULER] 코코 디엠 전송 실패: {e}")


# ============================================================
# 기록 모달
# ============================================================
class RecordModal(discord.ui.Modal, title="기록 입력"):
    checklist = discord.ui.TextInput(
        label="오늘의 기록",
        style=discord.TextStyle.paragraph
    )

    def __init__(self, category):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO records
            (user_id, date, category, checklist)
            VALUES (%s, %s, %s, %s)
            """,
            (
                interaction.user.id,
                today,
                self.category,
                self.checklist.value
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        await interaction.response.send_message(
            "기록이 저장되었습니다! 아래에 사진을 한 장만 올려주세요!",
            ephemeral=True
        )

        thread = await get_user_thread(
            interaction.user,
            interaction.guild
        )

        if thread:
            try:
                await thread.send(
                    f"{interaction.user.mention}님의 오늘 기록 : "
                    f"[{self.category}] {self.checklist.value}"
                )
            except Exception as e:
                print(f"[DEBUG] 오늘 기록 메시지 전송 실패: {e}")

        else:
            await interaction.followup.send(
                "⚠️ 해당 유저의 포럼 스레드를 찾을 수 없습니다. "
                "운영자에게 문의하세요.",
                ephemeral=True
            )


# ============================================================
# /링크
# ============================================================
class LinkButton(discord.ui.Button):
    def __init__(self, label, url):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary
        )
        self.link_url = url

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            self.link_url,
            ephemeral=True
        )


class LinkView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

        for label, url in LINKS.items():
            self.add_item(LinkButton(label, url))


@bot.tree.command(
    name="링크",
    description="SuitU 관련 링크를 확인합니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 링크(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔗 SuitU 관련 링크",
        description="원하는 링크의 버튼을 눌러주세요!",
        color=0x8EA7FF
    )

    await interaction.response.send_message(
        embed=embed,
        view=LinkView(),
        ephemeral=True
    )


# ============================================================
# 주사위 이미지
# ============================================================
DICE_VALUES = [10, 20, 30, 40, 50, 60, 70, 80, 90]
DICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dice")


def get_dice_image_path(value):
    path = os.path.join(DICE_DIR, f"dice_{value}.png")

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"주사위 이미지 파일을 찾을 수 없습니다: {path}"
        )

    return path


# ============================================================
# /주사위
# ============================================================
@bot.tree.command(
    name="주사위",
    description="10부터 90까지 10단위로 주사위를 굴립니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 주사위(interaction: discord.Interaction):
    value = random.choice(DICE_VALUES)

    try:
        image_path = get_dice_image_path(value)

        file = discord.File(
            image_path,
            filename=f"dice_{value}.png"
        )

        await interaction.response.send_message(
            f"**주사위 결과: {value}**",
            file=file
        )

    except FileNotFoundError as e:
        print(f"[ERROR] 주사위 이미지 없음: {e}")

        await interaction.response.send_message(
            "❌ 주사위 이미지 파일을 찾을 수 없습니다. 관리자에게 문의해주세요.",
            ephemeral=True
        )

    except Exception as e:
        print(f"[ERROR] 주사위 실행 실패: {e}")

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ 주사위를 굴리는 중 오류가 발생했습니다.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ 주사위를 굴리는 중 오류가 발생했습니다.",
                ephemeral=True
            )


# ============================================================
# /기록
# ============================================================
@bot.tree.command(
    name="기록",
    description="오늘의 기록을 남깁니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 기록(interaction: discord.Interaction):
    view = discord.ui.View()

    for category in ["운동", "식단", "단식"]:
        button = discord.ui.Button(
            label=category,
            style=discord.ButtonStyle.primary
        )

        async def callback(i, category=category):
            await i.response.send_modal(
                RecordModal(category)
            )

        button.callback = callback
        view.add_item(button)

    await interaction.response.send_message(
        "오늘의 기록을 선택하세요!",
        view=view,
        ephemeral=True
    )


# ============================================================
# /주간기록
# ============================================================
@bot.tree.command(
    name="주간기록",
    description="이번 주 기록 요약",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 주간기록(interaction: discord.Interaction):
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    start_of_week = today_kst - timedelta(days=today_kst.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT category, checklist, image_url, date
        FROM records
        WHERE user_id = %s
          AND date BETWEEN %s AND %s
        ORDER BY date ASC
    """, (
        interaction.user.id,
        start_of_week,
        end_of_week
    ))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await interaction.response.send_message(
            "이번 주에는 기록이 없습니다!",
            ephemeral=True
        )
        return

    chunks = []
    current_chunk = "📋 이번 주 기록 요약:\n"

    for row in rows:
        line = (
            f"[{row[0]}] {row[1]} "
            f"({row[3].strftime('%Y-%m-%d')})"
        )

        if row[2]:
            line += f"\n📷 이미지: {row[2]}"

        line += "\n"

        if len(current_chunk) + len(line) > 1900:
            chunks.append(current_chunk)
            current_chunk = ""

        current_chunk += line

    if current_chunk:
        chunks.append(current_chunk)

    for i, chunk in enumerate(chunks):
        if i == 0:
            await interaction.response.send_message(
                chunk,
                ephemeral=False
            )
        else:
            await interaction.followup.send(
                chunk,
                ephemeral=False
            )


# ============================================================
# /디엠
# ============================================================
@bot.tree.command(
    name="디엠",
    description="코코에게 익명 메세지를 보냅니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 디엠(interaction: discord.Interaction):
    await interaction.response.send_modal(
        AnonToCocoModal()
    )


# ============================================================
# /coco
# ============================================================
@bot.tree.command(
    name="coco",
    description="코코를 불러봅니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def coco(interaction: discord.Interaction):
    if COCO_USER_ID:
        await interaction.response.send_message(
            f"<@{COCO_USER_ID}>",
            ephemeral=False
        )
    else:
        await interaction.response.send_message(
            "COCO_USER_ID가 설정되지 않았습니다.",
            ephemeral=True
        )


# ============================================================
# /추천음악
# ============================================================
@bot.tree.command(
    name="추천음악",
    description="랜덤 추천 음악을 받아봅니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 추천음악(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)

    await interaction.response.send_message(
        f"오늘의 추천 음악은: **{song}**",
        ephemeral=False
    )



   


# ============================================================
# /이미지합치기
# ============================================================
IMAGE_MERGE_COUNT = 10
IMAGE_MERGE_COLUMNS = 5
IMAGE_MERGE_ROWS = 2
IMAGE_MERGE_OUTPUT_WIDTH = 1800
IMAGE_MERGE_OUTPUT_HEIGHT = 1800
IMAGE_MERGE_CELL_WIDTH = IMAGE_MERGE_OUTPUT_WIDTH // IMAGE_MERGE_COLUMNS
IMAGE_MERGE_CELL_HEIGHT = IMAGE_MERGE_OUTPUT_HEIGHT // IMAGE_MERGE_ROWS

# 투명 배경
IMAGE_MERGE_BACKGROUND = (255, 255, 255, 0)

# /이미지합치기 명령어를 실행한 사람의 다음 메시지만 처리
_pending_image_merge_users = {}


def is_image_attachment(attachment):
    content_type = (attachment.content_type or "").lower()

    if content_type.startswith("image/"):
        return True

    return attachment.filename.lower().endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")
    )


async def merge_ten_images(message):
    attachments = [
        attachment
        for attachment in message.attachments
        if is_image_attachment(attachment)
    ]

    if len(attachments) != IMAGE_MERGE_COUNT:
        return False

    images = []

    try:
        # Discord 메시지에 첨부된 순서 그대로 처리
        for attachment in attachments:
            data = await attachment.read()

            image = Image.open(io.BytesIO(data))
            image.seek(0)
            image = image.convert("RGBA")

            # 각 칸 안에 비율을 유지하면서 최대한 크게 배치
            image.thumbnail(
                (IMAGE_MERGE_CELL_WIDTH, IMAGE_MERGE_CELL_HEIGHT),
                Image.Resampling.LANCZOS
            )

            cell = Image.new(
                "RGBA",
                (IMAGE_MERGE_CELL_WIDTH, IMAGE_MERGE_CELL_HEIGHT),
                IMAGE_MERGE_BACKGROUND
            )

            x = (IMAGE_MERGE_CELL_WIDTH - image.width) // 2
            y = (IMAGE_MERGE_CELL_HEIGHT - image.height) // 2

            cell.alpha_composite(image, (x, y))
            images.append(cell)

        merged = Image.new(
            "RGBA",
            (IMAGE_MERGE_OUTPUT_WIDTH, IMAGE_MERGE_OUTPUT_HEIGHT),
            IMAGE_MERGE_BACKGROUND
        )

        for index, image in enumerate(images):
            row = index // IMAGE_MERGE_COLUMNS
            column = index % IMAGE_MERGE_COLUMNS

            merged.alpha_composite(
                image,
                (
                    column * IMAGE_MERGE_CELL_WIDTH,
                    row * IMAGE_MERGE_CELL_HEIGHT
                )
            )

        buffer = io.BytesIO()
        merged.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        # 업로드가 성공한 뒤에만 원본 메시지 삭제
        await message.channel.send(
            file=discord.File(
                buffer,
                filename="merged_10_images.png"
            )
        )

        try:
            await message.delete()
            print("[IMAGE MERGE] 원본 10장 메시지 삭제 완료")
        except discord.Forbidden:
            print("[IMAGE MERGE] 메시지 삭제 권한이 없습니다.")
        except discord.NotFound:
            pass

        return True

    except Exception as e:
        print(f"[IMAGE MERGE] 처리 실패: {e}")
        return False


@bot.tree.command(
    name="이미지합치기",
    description="다음 메시지의 이미지 10장을 5×2로 합칩니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 이미지합치기(interaction: discord.Interaction):
    key = (
        interaction.guild.id if interaction.guild else 0,
        interaction.channel.id,
        interaction.user.id
    )

    _pending_image_merge_users[key] = True

    await interaction.response.send_message(
        "🖼️ 다음 메시지에 **이미지 10장**을 한 번에 첨부해주세요!\n"
        "확인되면 5×2로 합쳐 **1800×1800 PNG**로 업로드합니다.",
        ephemeral=True
    )


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    key = (
        message.guild.id if message.guild else 0,
        message.channel.id,
        message.author.id
    )

    if _pending_image_merge_users.pop(key, False):
        success = await merge_ten_images(message)

        if not success:
            try:
                await message.channel.send(
                    f"{message.author.mention} 이미지가 **정확히 10장**인지 확인해주세요. "
                    "원본 메시지는 삭제하지 않았습니다."
                )
            except Exception as e:
                print(f"[IMAGE MERGE] 안내 메시지 전송 실패: {e}")

    # 기존 명령어 처리 유지
    await bot.process_commands(message)


# ============================================================
# 봇 시작
# ============================================================
@bot.event
async def setup_hook():
    print(f"[SYNC] GUILD_IDS = {GUILD_IDS}")

    for guild_id in GUILD_IDS:
        guild = discord.Object(id=guild_id)
        synced = await bot.tree.sync(guild=guild)

        print(f"[SYNC] guild={guild_id}, commands={len(synced)}")

        for command in synced:
            print(f"[SYNC] /{command.name}")

    print("명령어 동기화 완료 (길드 전용)")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not scheduler.running:
        scheduler.add_job(
            scheduled_task_runner,
            "cron",
            day_of_week="sun",
            hour=23,
            minute=59,
            timezone="Asia/Seoul"
        )
        scheduler.start()

    print(
        "✅ APScheduler로 주간기록 스케줄 등록됨 "
        "(일요일 23:59 KST)"
    )


if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
