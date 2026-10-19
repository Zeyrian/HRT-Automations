import discord

NO_PINGS = discord.AllowedMentions.none()
TEXT_LIMIT = 3800  # Discord allows ~4000 characters of text per message


def build_container(title=None, description=None, fields=None, footer=None, accent=None, rows=()):
    """Builds a card like the shift panel.

    fields: list of (label, value) pairs, shown as '**label:** value' lines.
    rows:   ActionRows (buttons or a select) placed at the bottom of the card.
    Give at least a description or fields.
    """
    children = []

    head = []
    if title:
        head.append(f"# {title}")
    if description:
        head.append(description)
    if head:
        children.append(discord.ui.TextDisplay("\n".join(head)))

    if fields:
        if children:
            children.append(discord.ui.Separator())
        children.append(
            discord.ui.TextDisplay("\n".join(f"**{label}:** {value}" for label, value in fields))
        )

    if footer:
        if children:
            children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# {footer}"))

    if rows:
        if children:
            children.append(discord.ui.Separator())
        children.extend(rows)

    return discord.ui.Container(*children, accent_colour=accent)


class CardView(discord.ui.LayoutView):
    """A static card with no buttons."""

    def __init__(self, **kwargs):
        super().__init__(timeout=None)
        self.add_item(build_container(**kwargs))


async def send_card(interaction, ephemeral=False, **kwargs):
    await interaction.response.send_message(
        view=CardView(**kwargs), ephemeral=ephemeral, allowed_mentions=NO_PINGS
    )


async def followup_card(interaction, ephemeral=False, **kwargs):
    await interaction.followup.send(
        view=CardView(**kwargs), ephemeral=ephemeral, allowed_mentions=NO_PINGS
    )


async def post_card(channel, **kwargs):
    await channel.send(view=CardView(**kwargs), allowed_mentions=NO_PINGS)


def chunk_lines(lines, limit=TEXT_LIMIT):
    """Splits a long list of lines into groups that each fit in one card."""
    chunks, current, size = [], [], 0
    for line in lines:
        if current and size + len(line) + 1 > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append(current)
    return chunks or [[]]