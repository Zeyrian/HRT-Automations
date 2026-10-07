import os
import sqlite3
import time
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

db = sqlite3.connect("hrt.db")
db.execute("""CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER
)""")
db.execute("""CREATE TABLE IF NOT EXISTS breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER
)""")
db.commit()


def fmt(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def get_open_shift(uid):
    return db.execute(
        "SELECT id, start_ts FROM shifts WHERE user_id=? AND end_ts IS NULL", (uid,)
    ).fetchone()


def get_open_break(shift_id):
    return db.execute(
        "SELECT id, start_ts FROM breaks WHERE shift_id=? AND end_ts IS NULL", (shift_id,)
    ).fetchone()


def break_total(shift_id, now):
    return db.execute(
        "SELECT COALESCE(SUM(COALESCE(end_ts, ?) - start_ts), 0) FROM breaks WHERE shift_id=?",
        (now, shift_id),
    ).fetchone()[0]


def total_time(uid, now):
    worked = db.execute(
        "SELECT COALESCE(SUM(COALESCE(end_ts, ?) - start_ts), 0) FROM shifts WHERE user_id=?",
        (now, uid),
    ).fetchone()[0]
    brk = db.execute(
        """SELECT COALESCE(SUM(COALESCE(b.end_ts, ?) - b.start_ts), 0)
           FROM breaks b JOIN shifts s ON s.id = b.shift_id WHERE s.user_id=?""",
        (now, uid),
    ).fetchone()[0]
    return worked - brk


def build_embed(user):
    now = int(time.time())
    shift = get_open_shift(user.id)
    if not shift:
        embed = discord.Embed(
            title="HRT Shift Panel",
            description="You are **off duty**.",
            color=discord.Color.light_grey(),
        )
    else:
        shift_id, start = shift
        on_break = get_open_break(shift_id) is not None
        breaks = break_total(shift_id, now)
        embed = discord.Embed(
            title="HRT Shift Panel",
            description="You are **on break**." if on_break else "You are **on duty**.",
            color=discord.Color.orange() if on_break else discord.Color.green(),
        )
        embed.add_field(name="Started", value=f"<t:{start}:R>", inline=True)
        embed.add_field(name="Time on duty", value=fmt(now - start - breaks), inline=True)
        embed.add_field(name="Break time", value=fmt(breaks), inline=True)
    embed.set_footer(text=user.display_name)
    return embed


class ShiftView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.refresh_buttons()

    def refresh_buttons(self):
        shift = get_open_shift(self.user.id)
        on_break = bool(shift and get_open_break(shift[0]))
        self.start_btn.disabled = bool(shift)
        self.break_btn.disabled = not shift
        self.break_btn.label = "End Break" if on_break else "Take Break"
        self.break_btn.style = (
            discord.ButtonStyle.primary if on_break else discord.ButtonStyle.secondary
        )
        self.end_btn.disabled = not shift

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your panel.", ephemeral=True)
            return False
        return True

    async def update(self, interaction: discord.Interaction, embed=None):
        self.refresh_buttons()
        await interaction.response.edit_message(
            embed=embed or build_embed(self.user), view=self
        )

    @discord.ui.button(label="Start Shift", style=discord.ButtonStyle.success)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not get_open_shift(self.user.id):
            db.execute(
                "INSERT INTO shifts (user_id, start_ts) VALUES (?, ?)",
                (self.user.id, int(time.time())),
            )
            db.commit()
        await self.update(interaction)

    @discord.ui.button(label="Take Break", style=discord.ButtonStyle.secondary)
    async def break_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        shift = get_open_shift(self.user.id)
        if shift:
            now = int(time.time())
            open_break = get_open_break(shift[0])
            if open_break:
                db.execute("UPDATE breaks SET end_ts=? WHERE id=?", (now, open_break[0]))
            else:
                db.execute(
                    "INSERT INTO breaks (shift_id, start_ts) VALUES (?, ?)", (shift[0], now)
                )
            db.commit()
        await self.update(interaction)

    @discord.ui.button(label="End Shift", style=discord.ButtonStyle.danger)
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        shift = get_open_shift(self.user.id)
        summary = None
        if shift:
            shift_id, start = shift
            now = int(time.time())
            open_break = get_open_break(shift_id)
            if open_break:
                db.execute("UPDATE breaks SET end_ts=? WHERE id=?", (now, open_break[0]))
            db.execute("UPDATE shifts SET end_ts=? WHERE id=?", (now, shift_id))
            db.commit()
            breaks = break_total(shift_id, now)
            summary = discord.Embed(
                title="Shift ended",
                color=discord.Color.red(),
            )
            summary.add_field(name="Time on duty", value=fmt(now - start - breaks), inline=True)
            summary.add_field(name="Break time", value=fmt(breaks), inline=True)
            summary.set_footer(text=self.user.display_name)
        await self.update(interaction, embed=summary)


class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = Bot()
shift = app_commands.Group(name="shift", description="HRT shift commands")
bot.tree.add_command(shift)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="ping", description="Check if the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency * 1000)}ms")


@shift.command(name="manage", description="Open your shift panel")
async def shift_manage(interaction: discord.Interaction):
    view = ShiftView(interaction.user)
    await interaction.response.send_message(
        embed=build_embed(interaction.user), view=view, ephemeral=True
    )


@shift.command(name="active", description="See who is currently on shift")
async def shift_active(interaction: discord.Interaction):
    rows = db.execute(
        """SELECT s.user_id, s.start_ts,
                  EXISTS(SELECT 1 FROM breaks b WHERE b.shift_id = s.id AND b.end_ts IS NULL)
           FROM shifts s WHERE s.end_ts IS NULL ORDER BY s.start_ts"""
    ).fetchall()
    if not rows:
        await interaction.response.send_message("Nobody is on shift right now.")
        return
    lines = [
        f"<@{uid}> — {'On Break' if on_break else 'On Duty'} (since <t:{start}:R>)"
        for uid, start, on_break in rows
    ]
    await interaction.response.send_message(
        "**On shift:**\n" + "\n".join(lines),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@shift.command(name="time", description="Show total shift time")
@app_commands.describe(member="Member to check (defaults to you)")
async def shift_time(interaction: discord.Interaction, member: discord.Member | None = None):
    target = member or interaction.user
    total = total_time(target.id, int(time.time()))
    await interaction.response.send_message(
        f"{target.display_name}: {fmt(total)} total shift time (breaks excluded)",
        allowed_mentions=discord.AllowedMentions.none(),
    )


bot.run(os.getenv("DISCORD_TOKEN"))