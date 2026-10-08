import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="commands", description="List all bot commands")
    async def commands_list(self, interaction: discord.Interaction):
        sections = {}
        for cmd in self.bot.tree.walk_commands():
            if not isinstance(cmd, app_commands.Command):
                continue
            section = cmd.binding.qualified_name if cmd.binding else "Other"
            sections.setdefault(section, []).append(cmd)

        embed = discord.Embed(title="HRT Bot Commands", color=discord.Color.blurple())
        for section, cmds in sorted(sections.items()):
            lines = [
                f"`/{c.qualified_name}` — {c.description}"
                for c in sorted(cmds, key=lambda c: c.qualified_name)
            ]
            embed.add_field(name=section, value="\n".join(lines), inline=False)
        embed.set_footer(text=f"{sum(len(c) for c in sections.values())} commands")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))