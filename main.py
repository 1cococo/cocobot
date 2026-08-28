import os
import io
import random
import re
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
# 레벨업 축하 설정
# ============================================================
CELEBRATION_CHANNEL_ID = 1359513583641432194
LEVELUP_CHANNEL_ID = 1359520343177302047

LEVEL_ROLES = {
    1362875669633040575: "저렙",
    1362875716521164913: "중렙",
    1362875731234787469: "고렙",
}

# Carl-bot User ID를 알고 있다면 환경변수 CARL_BOT_USER_ID에 넣을 수 있습니다.
# 비워두면 봇 이름에 carl/carl-bot이 포함되는지도 함께 확인합니다.
CARL_BOT_USER_ID = int(os.getenv("CARL_BOT_USER_ID", 0))

# 프레임은 main.py와 같은 폴더에 둡니다.
FRAME_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "celebration_frame.png"
)

BIRTHDAY_CHANNEL_ID = CELEBRATION_CHANNEL_ID

# 프레임 중앙에 들어갈 프로필 이미지 설정
PROFILE_SIZE = 500
PROFILE_X = 250
PROFILE_Y = 250

# ============================================================
# 링크 기능
# ============================================================
LINKS = {
    "정보공유방": "https://open.kakao.com/o/gJdyGZng",
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
        CREATE TABLE IF NOT EXISTS birthdays (
            user_id BIGINT PRIMARY KEY,
            month INTEGER NOT NULL,
            day INTEGER NOT NULL,
            last_greeted_year INTEGER
        )
    """)

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
        title="SuitU 관련 링크",
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
# 레벨업 / 생일 축하 이미지
# ============================================================

def crop_square(image):
    """이미지를 중앙 기준 정사각형으로 자릅니다."""
    image = image.convert("RGBA")
    width, height = image.size
    side = min(width, height)

    left = (width - side) // 2
    top = (height - side) // 2

    return image.crop((left, top, left + side, top + side))


async def make_celebration_image(user):
    """
    Discord 프로필 이미지를 celebration_frame.png 아래에 깔고
    1000x1000 PNG로 반환합니다.
    """
    if not os.path.isfile(FRAME_PATH):
        raise FileNotFoundError(
            f"축하 프레임 파일을 찾을 수 없습니다: {FRAME_PATH}"
        )

    avatar_data = await user.display_avatar.read()
    avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
    avatar = crop_square(avatar)

    avatar = avatar.resize(
        (PROFILE_SIZE, PROFILE_SIZE),
        Image.Resampling.LANCZOS
    )

    canvas = Image.new("RGBA", (1000, 1000), (255, 255, 255, 0))
    canvas.alpha_composite(avatar, (PROFILE_X, PROFILE_Y))

    frame = Image.open(FRAME_PATH).convert("RGBA")

    if frame.size != (1000, 1000):
        frame = frame.resize((1000, 1000), Image.Resampling.LANCZOS)

    # 프레임을 최상단에 얹습니다.
    canvas.alpha_composite(frame, (0, 0))

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    return buffer


def get_carlbot_embed_text(message):
    """Carl-bot Embed 안의 텍스트를 하나의 문자열로 합칩니다."""
    parts = []

    if message.content:
        parts.append(message.content)

    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title)

        if embed.description:
            parts.append(embed.description)

        if embed.author and embed.author.name:
            parts.append(embed.author.name)

        for field in embed.fields:
            if field.name:
                parts.append(field.name)
            if field.value:
                parts.append(field.value)

        if embed.footer and embed.footer.text:
            parts.append(embed.footer.text)

    return "\n".join(parts)


def is_carlbot_message(message):
    """메시지가 Carl-bot Logging 메시지인지 최대한 안전하게 판별합니다."""
    if CARL_BOT_USER_ID and message.author.id == CARL_BOT_USER_ID:
        return True

    author_name = str(message.author).lower()

    if "carl-bot" in author_name or "carl bot" in author_name:
        return True

    # 스크린샷처럼 Carl-bot Logging이라는 Embed가 있는 경우
    for embed in message.embeds:
        texts = [
            embed.title or "",
            embed.description or "",
            (embed.author.name if embed.author else "") or "",
        ]
        joined = " ".join(texts).lower()

        if "carl-bot" in joined or "carl bot" in joined:
            return True

    return False


def extract_levelup_info(message):
    """
    Carl-bot의 Role added 로그에서
    (유저 ID, 역할 ID, 역할 이름)을 추출합니다.
    """
    text = get_carlbot_embed_text(message)

    if not re.search(r"\bRole\s+added\b", text, re.IGNORECASE):
        return None

    # 가장 정확한 방법: Discord Role Mention의 실제 Role ID
    role_ids = re.findall(r"<@&(\d+)>", text)

    role_id = None

    for candidate in role_ids:
        candidate = int(candidate)
        if candidate in LEVEL_ROLES:
            role_id = candidate
            break

    # Embed가 실제 mention 대신 @중렙 같은 텍스트만 갖는 경우의 보조 처리
    if role_id is None:
        for candidate_id, role_name in LEVEL_ROLES.items():
            if re.search(
                rf"@?\s*{re.escape(role_name)}\b",
                text,
                re.IGNORECASE
            ):
                role_id = candidate_id
                break

    if role_id is None:
        return None

    # 스크린샷의 "ID: 640551684719771648" 부분
    user_match = re.search(r"\bID\s*:\s*(\d{15,25})\b", text)

    if not user_match:
        return None

    user_id = int(user_match.group(1))
    return user_id, role_id, LEVEL_ROLES[role_id]


async def handle_carlbot_levelup(message):
    """Carl-bot 레벨업 로그를 감지하고 축하 메시지를 보냅니다."""
    if message.guild is None:
        return

    if message.channel.id != LEVELUP_CHANNEL_ID:
        return

    if not is_carlbot_message(message):
        return

    info = extract_levelup_info(message)

    if not info:
        return

    user_id, role_id, level_name = info

    try:
        member = message.guild.get_member(user_id)

        if member is None:
            member = await message.guild.fetch_member(user_id)

        buffer = await make_celebration_image(member)

        # 축하 채널은 레벨업 로그가 올라오는 채널과 분리되어 있으므로
        # 현재 메시지의 guild 캐시에만 의존하지 않고 봇 전체에서 찾습니다.
        channel = bot.get_channel(CELEBRATION_CHANNEL_ID)

        if channel is None:
            try:
                channel = await bot.fetch_channel(CELEBRATION_CHANNEL_ID)
            except Exception as e:
                print(
                    f"[LEVELUP] 축하 채널을 찾을 수 없습니다: "
                    f"{CELEBRATION_CHANNEL_ID} / {e}"
                )
                return

        filename = f"levelup_{user_id}_{level_name}.png"

        await channel.send(
            f"**{member.display_name}님, {level_name}이 된 것을 축하합니다!!!**",
            file=discord.File(buffer, filename=filename)
        )

        print(
            f"[LEVELUP] {member} -> {level_name} "
            f"(role_id={role_id}, user_id={user_id})"
        )

    except discord.NotFound:
        print(f"[LEVELUP] 유저를 찾을 수 없습니다: {user_id}")

    except discord.Forbidden as e:
        print(f"[LEVELUP] Discord 권한 오류: {e}")

    except Exception as e:
        print(f"[LEVELUP] 처리 실패: {e}")


@bot.tree.command(
    name="생일",
    description="생일을 등록합니다. 예: /생일 12 18",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 생일(interaction: discord.Interaction, month: int, day: int):
    """유저의 생일을 DB에 저장합니다."""
    try:
        # 윤년 여부와 관계없이 월/일 자체가 유효한지 검사합니다.
        # 2000년은 윤년이므로 2월 29일도 정상적으로 저장할 수 있습니다.
        date(2000, month, day)

    except ValueError:
        await interaction.response.send_message(
            "❌ 올바른 생일을 입력해주세요! 예: `/생일 12 18`",
            ephemeral=True
        )
        return

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO birthdays (user_id, month, day, last_greeted_year)
        VALUES (%s, %s, %s, NULL)
        ON CONFLICT (user_id)
        DO UPDATE SET
            month = EXCLUDED.month,
            day = EXCLUDED.day,
            last_greeted_year = NULL
        """,
        (interaction.user.id, month, day)
    )

    conn.commit()
    cur.close()
    conn.close()

    await interaction.response.send_message(
        f"🎂 {month}월 {day}일로 생일이 저장되었습니다!",
        ephemeral=True
    )


@bot.tree.command(
    name="생일삭제",
    description="등록된 생일을 삭제합니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 생일삭제(interaction: discord.Interaction):
    """등록된 생일을 삭제합니다."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM birthdays WHERE user_id = %s",
        (interaction.user.id,)
    )

    deleted = cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    if deleted:
        message = "등록된 생일을 삭제했습니다!"
    else:
        message = "등록된 생일이 없습니다."

    await interaction.response.send_message(
        message,
        ephemeral=True
    )


async def send_birthday_greetings():
    """한국시간 자정에 생일 유저를 찾아 축하합니다."""
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    month = now.month
    day = now.day
    year = now.year

    print(f"[BIRTHDAY] {year}-{month:02d}-{day:02d} 생일 확인 시작")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id
        FROM birthdays
        WHERE month = %s
          AND day = %s
          AND (last_greeted_year IS NULL OR last_greeted_year <> %s)
        """,
        (month, day, year)
    )

    user_ids = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    if not user_ids:
        print("[BIRTHDAY] 오늘 생일인 유저가 없습니다.")
        return

    channel = None

    for guild in bot.guilds:
        candidate = guild.get_channel(BIRTHDAY_CHANNEL_ID)
        if candidate is not None:
            channel = candidate
            break

    if channel is None:
        print(
            f"[BIRTHDAY] 생일 채널을 찾을 수 없습니다: "
            f"{BIRTHDAY_CHANNEL_ID}"
        )
        return

    for user_id in user_ids:
        try:
            member = channel.guild.get_member(user_id)

            if member is None:
                member = await channel.guild.fetch_member(user_id)

            buffer = await make_celebration_image(member)

            filename = f"birthday_{user_id}_{year}.png"

            await channel.send(
                f"**{member.display_name}님, 생일 축하합니다!!!**",
                file=discord.File(buffer, filename=filename)
            )

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(
                """
                UPDATE birthdays
                SET last_greeted_year = %s
                WHERE user_id = %s
                """,
                (year, user_id)
            )

            conn.commit()
            cur.close()
            conn.close()

            print(
                f"[BIRTHDAY] {member} 생일 축하 완료 "
                f"(user_id={user_id})"
            )

        except discord.NotFound:
            print(f"[BIRTHDAY] 서버에서 유저를 찾을 수 없습니다: {user_id}")

        except discord.Forbidden as e:
            print(f"[BIRTHDAY] Discord 권한 오류: {e}")

        except Exception as e:
            print(f"[BIRTHDAY] {user_id} 처리 실패: {e}")


# ============================================================
# 이미지 합치기
# ============================================================
IMAGE_MERGE_COUNT = 10
IMAGE_MERGE_COLUMNS = 5
IMAGE_MERGE_ROWS = 2

# 드레스업: 2635 × 2280
DRESSUP_OUTPUT_WIDTH = 2635
DRESSUP_OUTPUT_HEIGHT = 2280

# 포스트: 2500 × 1000
POST_OUTPUT_WIDTH = 2500
POST_OUTPUT_HEIGHT = 1000

_pending_image_merge_users = {}


def is_image_attachment(attachment):
    content_type = (attachment.content_type or "").lower()

    if content_type.startswith("image/"):
        return True

    return attachment.filename.lower().endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")
    )


async def merge_ten_images(message, mode):
    attachments = [
        attachment
        for attachment in message.attachments
        if is_image_attachment(attachment)
    ]

    if len(attachments) != IMAGE_MERGE_COUNT:
        return False

    if mode == "dressup":
        output_width = DRESSUP_OUTPUT_WIDTH
        output_height = DRESSUP_OUTPUT_HEIGHT
    elif mode == "post":
        output_width = POST_OUTPUT_WIDTH
        output_height = POST_OUTPUT_HEIGHT
    else:
        return False

    cell_width = output_width // IMAGE_MERGE_COLUMNS
    cell_height = output_height // IMAGE_MERGE_ROWS
    images = []

    try:
        for attachment in attachments:
            data = await attachment.read()
            image = Image.open(io.BytesIO(data))
            image.seek(0)
            image = image.convert("RGBA")

            image.thumbnail(
                (cell_width, cell_height),
                Image.Resampling.LANCZOS
            )

            cell = Image.new(
                "RGBA",
                (cell_width, cell_height),
                (255, 255, 255, 0)
            )

            x = (cell_width - image.width) // 2
            y = (cell_height - image.height) // 2
            cell.alpha_composite(image, (x, y))
            images.append(cell)

        merged = Image.new(
            "RGBA",
            (output_width, output_height),
            (255, 255, 255, 0)
        )

        for index, image in enumerate(images):
            row = index // IMAGE_MERGE_COLUMNS
            column = index % IMAGE_MERGE_COLUMNS

            merged.alpha_composite(
                image,
                (
                    column * cell_width,
                    row * cell_height
                )
            )

        buffer = io.BytesIO()
        merged.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        filename = (
            "merged_dressup.png"
            if mode == "dressup"
            else "merged_post.png"
        )

        await message.channel.send(
            file=discord.File(buffer, filename=filename)
        )

        try:
            await message.delete()
            print(f"[IMAGE MERGE] {mode} 원본 메시지 삭제 완료")
        except discord.Forbidden:
            print("[IMAGE MERGE] 메시지 삭제 권한이 없습니다.")
        except discord.NotFound:
            pass

        return True

    except Exception as e:
        print(f"[IMAGE MERGE] {mode} 처리 실패: {e}")
        return False


@bot.tree.command(
    name="이미지합치기_드레스업",
    description="이미지 10장을 5×2로 합쳐 2635x2280으로 만듭니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 이미지합치기_드레스업(interaction: discord.Interaction):
    key = (
        interaction.guild.id if interaction.guild else 0,
        interaction.channel.id,
        interaction.user.id
    )

    _pending_image_merge_users[key] = "dressup"

    await interaction.response.send_message(
        "다음 메시지에 **이미지 10장**을 한 번에 첨부해주세요!!!\n"
        "5×2로 합쳐 **2635×2280 PNG**로 업로드합니다!!",
        ephemeral=True
    )


@bot.tree.command(
    name="이미지합치기_포스트",
    description="이미지 10장을 5×2로 합쳐 2500×1000으로 만듭니다",
    guilds=[discord.Object(id=g) for g in GUILD_IDS]
)
async def 이미지합치기_포스트(interaction: discord.Interaction):
    key = (
        interaction.guild.id if interaction.guild else 0,
        interaction.channel.id,
        interaction.user.id
    )

    _pending_image_merge_users[key] = "post"

    await interaction.response.send_message(
        "다음 메시지에 **이미지 10장**을 한 번에 첨부해주세요!!!\n"
        "5×2로 합쳐 **2500×1000 PNG**로 업로드합니다!!",
        ephemeral=True
    )


@bot.event
async def on_message(message):
    # Carl-bot의 레벨업 로그는 봇 메시지이므로 먼저 검사합니다.
    await handle_carlbot_levelup(message)

    # 나머지 봇 메시지는 기존 기능에서 무시합니다.
    if message.author.bot:
        return

    key = (
        message.guild.id if message.guild else 0,
        message.channel.id,
        message.author.id
    )

    mode = _pending_image_merge_users.pop(key, None)

    if mode:
        success = await merge_ten_images(message, mode)

        if not success:
            try:
                await message.channel.send(
                    f"{message.author.mention} 이미지가 **정확히 10장**인지 확인해주세요. "
                    "원본 메시지는 삭제하지 않았습니다."
                )
            except Exception as e:
                print(f"[IMAGE MERGE] 안내 메시지 전송 실패: {e}")

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
    print(f"[CONFIG] 레벨업 감지 채널 = {LEVELUP_CHANNEL_ID}")
    print(f"[CONFIG] 축하 전송 채널 = {CELEBRATION_CHANNEL_ID}")

    if not scheduler.running:
        scheduler.add_job(
            scheduled_task_runner,
            "cron",
            day_of_week="sun",
            hour=23,
            minute=59,
            timezone="Asia/Seoul"
        )

        scheduler.add_job(
            send_birthday_greetings,
            "cron",
            hour=0,
            minute=0,
            timezone="Asia/Seoul"
        )

        scheduler.start()

    print(
        "✅ APScheduler 등록 완료 "
        "(주간기록: 일요일 23:59 / 생일: 매일 00:00 KST)"
    )


if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
