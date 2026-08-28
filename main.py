import os
import io
import random
import re
import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import psycopg2
from datetime import datetime, timedelta, date, time
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
# 자체 활동 레벨 시스템 / 레벨업 축하 설정
# ============================================================
LEVELUP_CHANNEL_ID = 1359520343177302047
CELEBRATION_CHANNEL_ID = 1359513583641432194
BIRTHDAY_CHANNEL_ID = 1359513583641432194
WELCOME_CHANNEL_ID = 1359513583641432194
RULES_CHANNEL_URL = "https://discord.com/channels/1359504363378184242/1359511715074801904"

LEVEL_ROLES = {
    1362875669633040575: "저렙",
    1362875716521164913: "중렙",
    1362875731234787469: "고렙",
}
LEVEL_ROLE_IDS = {
    "저렙": 1362875669633040575,
    "중렙": 1362875716521164913,
    "고렙": 1362875731234787469,
}
LEVEL_ACTIVITY_REQUIRED = {"신입": 3, "저렙": 10, "중렙": 20}
FRAME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "celebration_frame.png")
PROFILE_SIZE = 1000
PROFILE_X = 0
PROFILE_Y = 0

# ============================================================
# 자체 활동 레벨 / 축하 설정
# ============================================================
CELEBRATION_CHANNEL_ID = 1359513583641432194
BIRTHDAY_CHANNEL_ID = 1359513583641432194

LEVEL_ROLE_IDS = {
    "저렙": 1362875669633040575,
    "중렙": 1362875716521164913,
    "고렙": 1362875731234787469,
}

LEVEL_ROLE_NAMES = {
    1362875669633040575: "저렙",
    1362875716521164913: "중렙",
    1362875731234787469: "고렙",
}

# 현재 레벨에서 다음 레벨까지 필요한 '추가 활동' 수
LEVEL_ACTIVITY_REQUIRED = {
    "신입": 3,
    "저렙": 10,
    "중렙": 20,
}

FRAME_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "celebration_frame.png"
)

# 프로필 이미지는 1000x1000 전체를 꽉 채움
PROFILE_SIZE = 1000
PROFILE_X = 0
PROFILE_Y = 0

WELCOME_CHANNEL_ID = 1359513583641432194
RULES_CHANNEL_URL = (
    "https://discord.com/channels/"
    "1359504363378184242/1359511715074801904"
)

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
        CREATE TABLE IF NOT EXISTS activity_counts (
            user_id BIGINT PRIMARY KEY,
            activity_count INTEGER NOT NULL DEFAULT 0,
            level TEXT NOT NULL DEFAULT '신입'
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
# 자체 활동 레벨 / 축하 이미지
# ============================================================

def crop_square(image):
    image = image.convert("RGBA")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


async def make_celebration_image(user):
    """프로필을 1000x1000 전체에 채우고 프레임을 최상단에 합성."""
    if not os.path.isfile(FRAME_PATH):
        raise FileNotFoundError(f"축하 프레임 파일을 찾을 수 없습니다: {FRAME_PATH}")

    avatar_data = await user.display_avatar.read()
    avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
    avatar = crop_square(avatar)
    avatar = avatar.resize((1000, 1000), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (1000, 1000), (255, 255, 255, 0))
    canvas.alpha_composite(avatar, (0, 0))

    frame = Image.open(FRAME_PATH).convert("RGBA")
    if frame.size != (1000, 1000):
        frame = frame.resize((1000, 1000), Image.Resampling.LANCZOS)
    canvas.alpha_composite(frame, (0, 0))

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer


def get_member_level(member):
    for role in member.roles:
        if role.id in LEVEL_ROLE_NAMES:
            return LEVEL_ROLE_NAMES[role.id]
    return "신입"


def level_start_count(level):
    return {
        "신입": 0,
        "저렙": 3,
        "중렙": 13,
        "고렙": 33,
    }.get(level, 0)


def required_total_for_next(level):
    return {
        "신입": 3,
        "저렙": 13,
        "중렙": 33,
    }.get(level)


def next_level(level):
    return {
        "신입": "저렙",
        "저렙": "중렙",
        "중렙": "고렙",
    }.get(level)


async def initialize_member_activity(member):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT activity_count, level FROM activity_counts WHERE user_id = %s",
        (member.id,)
    )
    row = cur.fetchone()

    actual_level = get_member_level(member)

    if row is None:
        count = level_start_count(actual_level)
        cur.execute(
            """
            INSERT INTO activity_counts (user_id, activity_count, level)
            VALUES (%s, %s, %s)
            """,
            (member.id, count, actual_level)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(
            f"[LEVEL] 기존/신규 유저 초기화: {member} / "
            f"{actual_level} / 누적기준 {count}"
        )
        return count, actual_level

    count, db_level = row

    # Discord에 이미 더 높은 레벨 역할이 있으면 그 역할을 기준으로 시작.
    rank = {"신입": 0, "저렙": 1, "중렙": 2, "고렙": 3}
    if rank.get(actual_level, 0) > rank.get(db_level, 0):
        count = max(count, level_start_count(actual_level))
        db_level = actual_level
        cur.execute(
            """
            UPDATE activity_counts
            SET activity_count = %s, level = %s
            WHERE user_id = %s
            """,
            (count, db_level, member.id)
        )
        conn.commit()

    cur.close()
    conn.close()
    return count, db_level


async def add_activity(member, reason):
    if member.bot or member.guild is None:
        return

    count, level = await initialize_member_activity(member)

    if level == "고렙":
        print(f"[ACTIVITY] {member} / {reason} / 고렙 / 승급 없음")
        return

    count += 1

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE activity_counts SET activity_count = %s WHERE user_id = %s",
        (count, member.id)
    )
    conn.commit()
    cur.close()
    conn.close()

    target = required_total_for_next(level)
    print(
        f"[ACTIVITY] {member} / {reason} / "
        f"{level} → {next_level(level)} / {count}/{target}"
    )

    if count >= target:
        await promote_member(member, level, next_level(level))


async def promote_member(member, old_level, new_level):
    new_role = member.guild.get_role(LEVEL_ROLE_IDS[new_level])
    if new_role is None:
        print(
            f"[LEVEL UP ERROR] 역할을 찾을 수 없습니다: "
            f"{new_level} ({LEVEL_ROLE_IDS[new_level]})"
        )
        return

    old_roles = [
        role for role in member.roles
        if role.id in LEVEL_ROLE_NAMES
        and role.id != new_role.id
    ]

    try:
        if old_roles:
            await member.remove_roles(
                *old_roles,
                reason=f"코코봇 자동 레벨업 {old_level} → {new_level}"
            )

        await member.add_roles(
            new_role,
            reason=f"코코봇 자동 레벨업 {old_level} → {new_level}"
        )

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE activity_counts
            SET activity_count = %s, level = %s
            WHERE user_id = %s
            """,
            (level_start_count(new_level), new_level, member.id)
        )
        conn.commit()
        cur.close()
        conn.close()

        print(
            f"[LEVEL UP] {member} : {old_level} → {new_level}"
        )
        await send_levelup_greeting(member, new_level)

    except discord.Forbidden as e:
        print(f"[LEVEL UP ERROR] 역할 변경 권한 부족: {member} / {e}")
    except Exception as e:
        print(f"[LEVEL UP ERROR] 승급 처리 실패: {member} / {e}")


async def send_levelup_greeting(member, level_name):
    try:
        channel = bot.get_channel(CELEBRATION_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(CELEBRATION_CHANNEL_ID)

        buffer = await make_celebration_image(member)
        await channel.send(
            f"{member.mention}님, {level_name}이 된 것을 축하합니다!!!",
            file=discord.File(
                buffer,
                filename=f"levelup_{member.id}_{level_name}.png"
            ),
            allowed_mentions=discord.AllowedMentions(users=True)
        )

        print(
            f"[LEVEL UP] 축하 메시지 전송 완료: "
            f"{member} -> {CELEBRATION_CHANNEL_ID}"
        )

    except discord.Forbidden as e:
        print(f"[LEVEL UP ERROR] 축하 채널 권한 부족: {e}")
    except Exception as e:
        print(f"[LEVEL UP ERROR] 축하 메시지 실패: {e}")


@tasks.loop(time=time(0, 0, tzinfo=ZoneInfo("Asia/Seoul")))
async def birthday_loop():
    """매일 한국시간 자정에 생일을 확인합니다."""
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    year = now.year
    month = now.month
    day = now.day

    print(f"[BIRTHDAY] {year}-{month:02d}-{day:02d} 확인")

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
        print("[BIRTHDAY] 오늘 생일 유저 없음")
        return

    channel = bot.get_channel(BIRTHDAY_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(BIRTHDAY_CHANNEL_ID)
        except Exception as e:
            print(f"[BIRTHDAY ERROR] 채널 조회 실패: {e}")
            return

    for user_id in user_ids:
        try:
            member = channel.guild.get_member(user_id)
            if member is None:
                member = await channel.guild.fetch_member(user_id)

            buffer = await make_celebration_image(member)
            await channel.send(
                f"{member.mention}님, 생일 축하합니다!!!",
                file=discord.File(
                    buffer,
                    filename=f"birthday_{user_id}_{year}.png"
                ),
                allowed_mentions=discord.AllowedMentions(users=True)
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

            print(f"[BIRTHDAY] 축하 완료: {member}")

        except discord.NotFound:
            print(f"[BIRTHDAY] 유저를 찾을 수 없습니다: {user_id}")
        except Exception as e:
            print(f"[BIRTHDAY ERROR] {user_id} 처리 실패: {e}")

# ============================================================
# 레벨업 / 생일 축하 이미지 + 자체 활동 레벨 시스템
# ============================================================

def crop_square(image):
    image = image.convert("RGBA")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


async def make_celebration_image(user):
    if not os.path.isfile(FRAME_PATH):
        raise FileNotFoundError(f"축하 프레임 파일을 찾을 수 없습니다: {FRAME_PATH}")
    avatar_data = await user.display_avatar.read()
    avatar = crop_square(Image.open(io.BytesIO(avatar_data)))
    avatar = avatar.resize((1000, 1000), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (1000, 1000), (255, 255, 255, 0))
    canvas.alpha_composite(avatar, (0, 0))
    frame = Image.open(FRAME_PATH).convert("RGBA")
    if frame.size != (1000, 1000):
        frame = frame.resize((1000, 1000), Image.Resampling.LANCZOS)
    canvas.alpha_composite(frame, (0, 0))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer


def get_member_level(member):
    for role in member.roles:
        if role.id in LEVEL_ROLES:
            return LEVEL_ROLES[role.id]
    return "신입"


def level_base_count(level):
    return {"신입": 0, "저렙": 3, "중렙": 13, "고렙": 33}.get(level, 0)


def next_level(level):
    return {"신입": "저렙", "저렙": "중렙", "중렙": "고렙"}.get(level)


def total_required(level):
    return {"신입": 0, "저렙": 3, "중렙": 13, "고렙": 33}.get(level, 0)


async def initialize_member_activity(member):
    current_level = get_member_level(member)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT activity_count, level FROM activity_counts WHERE user_id=%s", (member.id,))
    row = cur.fetchone()
    if row is None:
        count = level_base_count(current_level)
        cur.execute("INSERT INTO activity_counts (user_id,activity_count,level) VALUES (%s,%s,%s)", (member.id,count,current_level))
        conn.commit(); cur.close(); conn.close()
        print(f"[LEVEL] 초기 등록: {member} / {current_level} / {count}")
        return count, current_level
    count, db_level = row
    # Discord의 실제 역할이 DB보다 높은 경우 기존 역할을 기준으로 시작점을 맞춤
    if total_required(current_level) > total_required(db_level):
        count = max(count, level_base_count(current_level)); db_level = current_level
        cur.execute("UPDATE activity_counts SET activity_count=%s,level=%s WHERE user_id=%s", (count,db_level,member.id)); conn.commit()
    cur.close(); conn.close()
    return count, db_level


async def add_activity(member, reason):
    if member.bot or member.guild is None:
        return
    count, level = await initialize_member_activity(member)
    if level == "고렙":
        print(f"[ACTIVITY] {member} / 고렙 / {reason} / 승급 없음")
        return
    count += 1
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE activity_counts SET activity_count=%s WHERE user_id=%s", (count,member.id)); conn.commit(); cur.close(); conn.close()
    nxt = next_level(level); required = total_required(nxt)
    print(f"[ACTIVITY] {member} / {reason} / {count}/{required} / 현재={level}")
    if count >= required:
        await promote_member(member, level, nxt, count)


async def promote_member(member, old_level, new_level, activity_count):
    new_role = member.guild.get_role(LEVEL_ROLE_IDS[new_level])
    if new_role is None:
        print(f"[LEVEL] 새 역할을 찾을 수 없습니다: {new_level}")
        return
    old_roles = [r for r in member.roles if r.id in LEVEL_ROLE_IDS.values() and r.id != new_role.id]
    try:
        if old_roles:
            await member.remove_roles(*old_roles, reason=f"코코봇 자동 레벨업: {old_level} → {new_level}")
        await member.add_roles(new_role, reason=f"코코봇 자동 레벨업: {old_level} → {new_level}")
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE activity_counts SET activity_count=%s,level=%s WHERE user_id=%s", (total_required(new_level),new_level,member.id)); conn.commit(); cur.close(); conn.close()
        print(f"[LEVEL UP] {member} : {old_level} → {new_level} / 활동={activity_count}")
        await send_levelup_greeting(member, new_level)
    except discord.Forbidden as e:
        print(f"[LEVEL] 역할 변경 권한 오류: {member} / {e}")
    except Exception as e:
        print(f"[LEVEL] 승급 처리 실패: {member} / {e}")


async def get_channel_by_id(channel_id):
    for guild in bot.guilds:
        try:
            channel = await bot.fetch_channel(channel_id)
            if channel:
                return channel
        except (discord.NotFound, discord.Forbidden):
            continue
        except Exception as e:
            print(f"[CHANNEL] 채널 조회 실패: {channel_id} / {e}")
            continue
    return None


async def send_levelup_greeting(member, level_name):
    try:
        channel = await get_channel_by_id(CELEBRATION_CHANNEL_ID)
        if channel is None:
            print(f"[LEVEL UP] 축하 채널을 찾을 수 없습니다: {CELEBRATION_CHANNEL_ID}")
            return
        buffer = await make_celebration_image(member)
        await channel.send(f"{member.mention}님, {level_name}이 된 것을 축하합니다!!!", file=discord.File(buffer, filename=f"levelup_{member.id}_{level_name}.png"), allowed_mentions=discord.AllowedMentions(users=True))
    except Exception as e:
        print(f"[LEVEL UP] 축하 메시지 전송 실패: {e}")



@bot.event
async def on_member_join(member):
    """신규 멤버 환영 + 신입 활동 DB 등록."""
    if member.bot:
        return

    # 신규 가입자는 신입 0회에서 시작.
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO activity_counts (user_id, activity_count, level)
            VALUES (%s, 0, '신입')
            ON CONFLICT (user_id) DO NOTHING
            """,
            (member.id,)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"[WELCOME] 신규 멤버 등록: {member} ({member.id})")
    except Exception as e:
        print(f"[WELCOME ERROR] 활동 DB 등록 실패: {member} / {e}")

    try:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(WELCOME_CHANNEL_ID)

        embed = discord.Embed(
            title="Welcome to SuitU Korea Discord Server!!",
            description=(
                "안녕하세요!!! 수트유 한국 디스코드에 오신 것을 환영합니다!!!\n\n"
                f"{RULES_CHANNEL_URL} 채널에서 규칙을 잘 읽어주시고, "
                "하단에 `/링크`를 쳐서 카카오톡 정보공유방에도 놀러오세요!!!"
            ),
            color=discord.Color.blurple()
        )

        await channel.send(
            content=member.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True)
        )

        print(f"[WELCOME] 환영 메시지 전송 완료: {member} -> {WELCOME_CHANNEL_ID}")

    except discord.Forbidden as e:
        print(f"[WELCOME ERROR] 환영 채널 권한 부족: {e}")
    except discord.NotFound as e:
        print(f"[WELCOME ERROR] 환영 채널을 찾을 수 없음: {WELCOME_CHANNEL_ID} / {e}")
    except Exception as e:
        print(f"[WELCOME ERROR] 환영 메시지 전송 실패: {member} / {e}")

@bot.event
async def on_message(message):
    """일반 유저의 글쓰기 활동을 1회 기록합니다."""
    if message.author.bot:
        return

    if message.guild is not None:
        try:
            await add_activity(message.author, "글쓰기")
        except Exception as e:
            print(f"[ACTIVITY ERROR] 글쓰기 처리 실패: {message.author} / {e}")

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
                    f"{message.author.mention} 이미지가 **정확히 10장**인지 "
                    "확인해주세요. 원본 메시지는 삭제하지 않았습니다."
                )
            except Exception as e:
                print(f"[IMAGE MERGE] 안내 메시지 전송 실패: {e}")

    await bot.process_commands(message)


@bot.event
async def on_raw_reaction_add(payload):
    """유저의 이모지/커스텀 이모지 반응 추가를 활동 1회로 기록합니다."""
    if payload.guild_id is None:
        return

    if bot.user is not None and payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        print(f"[ACTIVITY] 길드를 찾지 못했습니다: {payload.guild_id}")
        return

    member = guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception as e:
            print(f"[ACTIVITY ERROR] 반응 유저 조회 실패: {payload.user_id} / {e}")
            return

    if member.bot:
        return

    try:
        await add_activity(member, f"이모지 반응 {payload.emoji}")
    except Exception as e:
        print(f"[ACTIVITY ERROR] 이모지 반응 처리 실패: {member} / {e}")

# ============================================================
# 봇 시작
# ============================================================

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
    print("[LEVEL] 자체 활동 레벨 시스템 활성화")
    print("[LEVEL] 글쓰기 +1 / 이모지 반응 +1")
    print("[LEVEL] 신입→저렙 3회 / 저렙→중렙 10회 추가 / 중렙→고렙 20회 추가")
    print(f"[LEVEL] 레벨 역할 ID = {LEVEL_ROLE_IDS}")
    print(f"[LEVEL] 축하 채널 ID = {CELEBRATION_CHANNEL_ID}")
    print("[LEVEL] 자체 활동 레벨 시스템 활성화: 글쓰기 +1 / 이모지 반응 +1")
    print("[LEVEL] 승급 기준: 신입→저렙 3회 / 저렙→중렙 10회 추가 / 중렙→고렙 20회 추가")
    print("[CONFIG] 활동 레벨: 신입→저렙 3회 / 저렙→중렙 10회 추가 / 중렙→고렙 20회 추가")
    print(f"[CONFIG] 축하 전송 채널 = {CELEBRATION_CHANNEL_ID}")
    if not birthday_loop.is_running():
        birthday_loop.start()
        print("[BIRTHDAY] 한국시간 자정 자동 생일 확인 시작")

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
        "✅ APScheduler 등록 완료 "
        "(주간기록: 일요일 23:59 / 생일: 매일 00:00 KST)"
    )


if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)
