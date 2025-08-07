import os
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import psycopg2
import datetime
import random

# 환경 변수 로딩
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_IDS = [int(gid) for gid in os.getenv("GUILD_IDS", "").split(",") if gid]
RECORD_CHANNEL_IDS = [int(cid) for cid in os.getenv("RECORD_CHANNEL_IDS", "").split(",") if cid]
COCO_USER_ID = int(os.getenv("COCO_USER_ID", 0))

# DB 연결 함수
def get_db():
    return psycopg2.connect(DATABASE_URL)

# 추천 음악 리스트
SONG_LIST = [
    "실리카겔 - APEX", "넥스트 - 도시인", "DAY6 - Healer", "윤상 - 달리기", "김승주 - 케이크가 불쌍해",
    "Shibata Jun - 救世主(구세주)", "Porter Robinson - Shelter", "Do As Infinity - Oasis",
    "Jazztronik - Samurai", "King gnu - 白日", "LUCKY TAPES - Gravity"
]

# 디스코드 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 스레드 찾기 함수
async def get_user_thread(user: discord.User | discord.Member):
    for cid in RECORD_CHANNEL_IDS:
        forum_channel = bot.get_channel(cid)
        if not isinstance(forum_channel, discord.ForumChannel):
            continue

        # 기존 스레드 탐색
        for thread in forum_channel.threads:
            if str(user.id) in thread.name:
                return thread

        # 아카이브된 스레드 탐색
        try:
            async for archived in forum_channel.archived_threads(limit=50):
                if str(user.id) in archived.name:
                    return archived
        except Exception as e:
            print(f"[DEBUG] 아카이브 탐색 실패: {e}")
    return None

# 기록 입력 모달
class RecordModal(Modal, title="기록 입력"):
    checklist = TextInput(label="오늘 기록을 입력해주세요!", style=discord.TextStyle.paragraph)

    def __init__(self, category: str, user_id: int):
        super().__init__()
        self.category = category
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        today = datetime.date.today()
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO records (user_id, date, category, checklist, image_url)
                VALUES (%s, %s, %s, %s, %s)
            """, (self.user_id, today, self.category, self.checklist.value, None))
            conn.commit()
            print(f"[DEBUG] 기록 저장됨: user={self.user_id}, category={self.category}, checklist={self.checklist.value}")
        except Exception as e:
            print("[DEBUG] 기록 저장 실패:", e)
        finally:
            cur.close()
            conn.close()

        try:
            await interaction.response.send_message("기록이 저장되었습니다! 하단에 사진 한 장만 올려주세요!", ephemeral=True)
            print("[DEBUG] response 메시지 전송 성공")
        except:
            await interaction.followup.send("기록이 저장되었습니다!", ephemeral=True)
            print("[DEBUG] followup 메시지 전송 성공")

        thread = await get_user_thread(interaction.user)
        if thread:
            try:
                await thread.send(f"{interaction.user.mention}님의 오늘 기록 : [{self.category}] {self.checklist.value}")
            except Exception as e:
                print("[DEBUG] 스레드 메시지 전송 실패:", e)
        else:
            await interaction.followup.send("⚠️ 해당 유저의 포럼 스레드를 찾을 수 없습니다. 운영자에게 문의하세요.", ephemeral=True)

# 기록 선택 버튼 뷰
class RecordView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="운동", style=discord.ButtonStyle.green)
    async def exercise(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RecordModal("운동", self.user_id))

    @discord.ui.button(label="식단", style=discord.ButtonStyle.blurple)
    async def diet(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RecordModal("식단", self.user_id))

    @discord.ui.button(label="단식", style=discord.ButtonStyle.red)
    async def fast(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RecordModal("단식", self.user_id))

# 사진 저장 처리
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.Thread) and message.channel.parent_id in RECORD_CHANNEL_IDS:
        if message.attachments:
            conn = get_db()
            cur = conn.cursor()
            saved = False
            try:
                cur.execute("""
                    UPDATE records
                    SET image_url = %s
                    WHERE user_id = %s AND date = %s AND image_url IS NULL
                    ORDER BY id DESC
                    LIMIT 1
                """, (message.attachments[0].url, message.author.id, datetime.date.today()))
                conn.commit()
                if cur.rowcount > 0:
                    saved = True
                    print(f"[DEBUG] 이미지 저장 성공: user={message.author.id}")
                else:
                    print(f"[DEBUG] 업데이트할 기록 없음: user={message.author.id}")
            except Exception as e:
                print(f"[DEBUG] 이미지 저장 SQL 실패: {e}")
            finally:
                cur.close()
                conn.close()

            if saved:
                try:
                    await message.channel.send(f"{message.author.mention}님의 사진이 기록에 추가되었습니다!")
                except:
                    print("[DEBUG] 사진 안내 메시지 전송 실패")

# 슬래시 커맨드 등록
@bot.tree.command(name="기록", description="오늘의 기록을 입력합니다", guilds=[discord.Object(id=gid) for gid in GUILD_IDS])
async def 기록(interaction: discord.Interaction):
    await interaction.response.send_message("카테고리를 선택해주세요!", view=RecordView(interaction.user.id), ephemeral=True)

@bot.tree.command(name="추천음악", description="랜덤 음악을 추천합니다", guilds=[discord.Object(id=gid) for gid in GUILD_IDS])
async def 추천음악(interaction: discord.Interaction):
    song = random.choice(SONG_LIST)
    await interaction.response.send_message(f"🎵 오늘의 추천 음악:\n{song}")

@bot.tree.command(name="coco", description="코코를 불러요!", guilds=[discord.Object(id=gid) for gid in GUILD_IDS])
async def coco(interaction: discord.Interaction):
    if COCO_USER_ID:
        await interaction.response.send_message(f"<@{COCO_USER_ID}>", ephemeral=False)
    else:
        await interaction.response.send_message("COCO_USER_ID가 설정되지 않았습니다.", ephemeral=True)

# on_ready 이벤트
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

# 명령어 동기화
@bot.event
async def setup_hook():
    for gid in GUILD_IDS:
        guild = discord.Object(id=gid)
        await bot.tree.sync(guild=guild)
        print(f"명령어 동기화 완료 (길드 전용 {gid})")

# 실행
if __name__ == "__main__":
    bot.run(TOKEN)
