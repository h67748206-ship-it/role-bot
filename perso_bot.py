# Bot ticket + générateur d'embeds (yuu). Lancer : python ticket_bot.py
import asyncio
import datetime as dt
import html as hm
import os
import subprocess
import sys

try:
    import discord
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "discord.py"])
    import discord

from aiohttp import web
from discord import app_commands
from discord.ext import commands

# ===================== CONFIG =====================
TOKEN = (os.getenv("DISCORD_TOKEN") or "COLLE_TON_TOKEN_ICI").strip().strip('"').strip("'")
COULEUR = 0x5865F2
TICKET_COULEUR = 0x1F4FFF

# Emojis personnalisés de yuu
EMOJI_COURONNE = "<:couronne:1561382845035974788>"
EMOJI_STAFF = "<:staff:1561382969938153655>"
EMOJI_ABUS = "<:abus:1561383046232670289>"

CATEGORIES = {
    "couronne": {
        "label": "Couronne",
        "emoji": EMOJI_COURONNE,
        "court": "Demande d'invest, décale, fourni ou hautes demandes",
        "long": "Demande d'invest, décale, fourni ou hautes demandes.",
    },
    "staff": {
        "label": "Gestion Staff",
        "emoji": EMOJI_STAFF,
        "court": "Devenir staff, être rank sur yuu",
        "long": "Ouvre un ticket pour être rank sur yuu !",
    },
    "abus": {
        "label": "Gestion Abus",
        "emoji": EMOJI_ABUS,
        "court": "Abus de perm, abus de plainte, etc.",
        "long": "Abus de perm, abus de plainte, etc.",
    },
}

intents = discord.Intents.default()
intents.members = True


# ===================== OUTILS =====================
def emb(titre: str, desc: str = "", couleur: int = COULEUR) -> discord.Embed:
    return discord.Embed(title=titre, description=desc, color=couleur, timestamp=discord.utils.utcnow())


def ticket_info(ch):
    """(id_proprio, id_claim ou None) si le salon est un ticket, sinon None."""
    t = getattr(ch, "topic", None) or ""
    if not t.startswith("ticket:"):
        return None
    try:
        d = dict(p.split(":", 1) for p in t.split("|") if ":" in p)
        owner = int(d["ticket"])
        claim = int(d["claim"]) if d.get("claim") else None
    except (ValueError, KeyError):
        return None
    return owner, claim


def ticket_cat(ch) -> str:
    t = getattr(ch, "topic", None) or ""
    d = dict(p.split(":", 1) for p in t.split("|") if ":" in p)
    return d.get("cat", "autre")


def est_staff(inter: discord.Interaction) -> bool:
    p = inter.user.guild_permissions
    return p.manage_channels or p.administrator


async def refus(inter: discord.Interaction, texte: str):
    if inter.response.is_done():
        await inter.followup.send(texte, ephemeral=True)
    else:
        await inter.response.send_message(texte, ephemeral=True)


# ===================== MINI SITE WEB =====================
PANEL_PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panneau de tickets - __NOM__</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#1e1f22;color:#dbdee1;font-family:system-ui,sans-serif;padding:20px;box-sizing:border-box}
.embed{background:#2b2d31;border-left:4px solid #1F4FFF;border-radius:6px;padding:16px 18px;
max-width:520px;width:100%;box-sizing:border-box}
h1{margin:0 0 10px;font-size:18px;color:#fff}
.desc{font-size:14px;line-height:1.5;margin-bottom:12px}
.opt{display:flex;gap:10px;padding:10px 0;border-top:1px solid #3f4147;font-size:14px}
.opt b{color:#fff}
.opt p{margin:2px 0 0;color:#b5bac1}
.menu{margin-top:12px;background:#1e1f22;border-radius:4px;padding:10px 12px;color:#949ba4;font-size:14px}
.foot{margin-top:14px;font-size:12px;color:#949ba4}
</style></head><body><div class="embed">
<h1>Besoin d'aide sur __NOM__ ?</h1>
<div class="desc">Choisis le motif de ton ticket ci-dessous — un salon privé sera créé pour discuter avec l'équipe.</div>
__LIGNES__
<div class="opt"><div><b>🔒 Privé</b><p>visible seulement par toi et le staff</p></div></div>
<div class="opt"><div><b>⏱️ Réponse</b><p>sous 24h en moyenne</p></div></div>
<div class="menu">Sélectionne une catégorie... ▾</div>
<div class="foot">Aperçu du panneau de tickets</div>
</div></body></html>"""


async def page_panneau(request: web.Request):
    b = request.app["bot"]
    lignes = "".join(
        f'<div class="opt"><div><b>{hm.escape(v["label"])}</b><p>{hm.escape(v["long"])}</p></div></div>'
        for v in CATEGORIES.values()
    )
    nom = hm.escape(b.user.name if b.user else "yuu")
    page = PANEL_PAGE.replace("__NOM__", nom).replace("__LIGNES__", lignes)
    return web.Response(text=page, content_type="text/html")


async def health(request: web.Request):
    return web.json_response({"status": "ok"})


async def lancer_site(b: commands.Bot):
    app = web.Application()
    app["bot"] = b
    app.router.add_get("/", page_panneau)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"Site web lancé sur le port {port}")


# ===================== TICKETS =====================
class RenameModal(discord.ui.Modal, title="Renommer le ticket"):
    nom = discord.ui.TextInput(label="Nouveau nom", placeholder="ex : problème-paiement", max_length=90)

    async def on_submit(self, inter: discord.Interaction):
        try:
            await inter.channel.edit(name=str(self.nom), reason=f"Renommé par {inter.user}")
        except discord.Forbidden:
            return await refus(inter, "❌ Il me manque la permission « Gérer les salons ».")
        await inter.response.send_message(f"✏️ Ticket renommé en **{self.nom}** par {inter.user.mention}.")


async def supprimer_ticket(ch, user):
    await asyncio.sleep(5)
    try:
        await ch.delete(reason=f"Ticket fermé par {user}")
    except discord.HTTPException:
        pass


class TicketControl(discord.ui.View):
    def __init__(self, claimed: bool = False):
        super().__init__(timeout=None)
        if claimed:
            self.claim.disabled = True
            self.claim.label = "Pris en charge"

    @discord.ui.button(label="Claim", emoji=EMOJI_STAFF, style=discord.ButtonStyle.primary, custom_id="ticket:claim")
    async def claim(self, inter: discord.Interaction, bouton: discord.ui.Button):
        info = ticket_info(inter.channel)
        if not info:
            return await refus(inter, "❌ Ce n'est pas un ticket.")
        if not est_staff(inter):
            return await refus(inter, "❌ Réservé au staff.")
        owner, claim = info
        if claim:
            return await refus(inter, f"❌ Déjà pris en charge par <@{claim}>.")
        await inter.response.edit_message(view=TicketControl(claimed=True))
        try:
            await inter.channel.edit(topic=f"ticket:{owner}|claim:{inter.user.id}|cat:{ticket_cat(inter.channel)}")
        except discord.HTTPException:
            pass
        await inter.channel.send(embed=emb("Ticket pris en charge", f"{inter.user.mention} s'occupe de ce ticket.", 0x57F287))

    @discord.ui.button(label="Fermer", emoji=EMOJI_ABUS, style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def fermer(self, inter: discord.Interaction, bouton: discord.ui.Button):
        ch = inter.channel
        info = ticket_info(ch)
        if not info:
            return await refus(inter, "❌ Ce n'est pas un ticket.")
        if not (info[0] == inter.user.id or est_staff(inter)):
            return await refus(inter, "❌ Tu ne peux pas fermer ce ticket.")
        await inter.response.send_message("🔒 Ticket fermé, suppression dans 5 secondes…")
        asyncio.create_task(supprimer_ticket(ch, inter.user))

    @discord.ui.button(label="Renommer", emoji=EMOJI_COURONNE, style=discord.ButtonStyle.secondary, custom_id="ticket:rename")
    async def renommer(self, inter: discord.Interaction, bouton: discord.ui.Button):
        if not ticket_info(inter.channel):
            return await refus(inter, "❌ Ce n'est pas un ticket.")
        if not est_staff(inter):
            return await refus(inter, "❌ Réservé au staff.")
        await inter.response.send_modal(RenameModal())


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="Sélectionne une catégorie...",
        custom_id="ticket:panel",
        options=[
            discord.SelectOption(label=v["label"], value=k, emoji=v["emoji"], description=v["court"])
            for k, v in CATEGORIES.items()
        ],
    )
    async def choisir(self, inter: discord.Interaction, select: discord.ui.Select):
        key = select.values[0]
        cat = CATEGORIES[key]
        guild, user = inter.guild, inter.user

        for ch in guild.text_channels:
            info = ticket_info(ch)
            if info and info[0] == user.id:
                return await refus(inter, f"Tu as déjà un ticket ouvert : {ch.mention}")

        ow = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        await inter.response.defer(ephemeral=True)
        try:
            ch = await guild.create_text_channel(
                name=f"{key}-{user.name}"[:90],
                category=inter.channel.category,
                overwrites=ow,
                topic=f"ticket:{user.id}|cat:{key}",
                reason=f"Ticket {cat['label']} de {user}",
            )
        except discord.Forbidden:
            return await refus(inter, "❌ Il me manque la permission « Gérer les salons ».")

        e = discord.Embed(
            title=f"{cat['emoji']} {cat['label']} — {user.display_name}",
            description="Merci d'avoir contacté le support.\nDécris ton problème puis attends qu'un membre de l'équipe te réponde.",
            color=TICKET_COULEUR,
        )
        e.set_thumbnail(url=user.display_avatar.url)
        await ch.send(content=user.mention, embed=e, view=TicketControl())
        await inter.followup.send(f"✅ Ticket créé : {ch.mention}", ephemeral=True)


# ===================== BOT =====================
class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

    async def setup_hook(self):
        self.add_view(TicketPanel())
        self.add_view(TicketControl())
        await self.tree.sync()
        await lancer_site(self)


bot = TicketBot()


@bot.tree.error
async def on_app_error(inter: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        return await refus(inter, "❌ Tu n'as pas la permission pour ça.")
    print(f"Erreur commande : {error!r}")
    await refus(inter, "❌ Une erreur est survenue.")


# ===================== COMMANDES =====================
@bot.tree.command(name="ticketpanel", description="Envoyer le panneau de tickets dans ce salon")
@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
async def ticketpanel(inter: discord.Interaction):
    if not inter.user.guild_permissions.manage_guild:
        return await refus(inter, "❌ Tu n'as pas la permission pour ça.")
    lignes = "\n\n".join(f"{v['emoji']} **{v['label']}** — {v['long']}" for v in CATEGORIES.values())
    e = discord.Embed(
        title=f"Besoin d'aide sur {inter.guild.name} ?",
        description=(
            "Choisis le motif de ton ticket ci-dessous — un salon privé sera créé pour discuter avec l'équipe.\n\n"
            + lignes
            + "\n\n🔒 **Privé** — visible seulement par toi et le staff\n⏱️ **Réponse** sous 24h en moyenne"
        ),
        color=TICKET_COULEUR,
    )
    if inter.guild.icon:
        e.set_thumbnail(url=inter.guild.icon.url)
    await inter.channel.send(embed=e, view=TicketPanel())
    await inter.response.send_message("✅ Panneau envoyé.", ephemeral=True)


@bot.tree.command(name="embed", description="Créer un embed personnalisé")
@app_commands.describe(
    titre="Titre de l'embed",
    description="Texte de l'embed (\\n pour un saut de ligne)",
    couleur="Couleur hexadécimale, ex : 5865F2",
    image="Lien d'une image (optionnel)",
    miniature="Lien d'une miniature (optionnel)",
    footer="Texte du bas (optionnel)",
)
@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
async def embed_cmd(
    inter: discord.Interaction,
    titre: str,
    description: str,
    couleur: str = "5865F2",
    image: str = None,
    miniature: str = None,
    footer: str = None,
):
    if not inter.user.guild_permissions.manage_messages:
        return await refus(inter, "❌ Tu n'as pas la permission pour ça.")
    try:
        c = int(couleur.strip().lstrip("#"), 16)
    except ValueError:
        return await refus(inter, "❌ Couleur invalide (ex : 5865F2).")
    e = discord.Embed(title=titre, description=description.replace("\\n", "\n"), color=c)
    if image:
        e.set_image(url=image)
    if miniature:
        e.set_thumbnail(url=miniature)
    if footer:
        e.set_footer(text=footer)
    await inter.channel.send(embed=e)
    await inter.response.send_message("✅ Embed envoyé.", ephemeral=True)


# ===================== LANCEMENT =====================
if __name__ == "__main__":
    if TOKEN == "COLLE_TON_TOKEN_ICI":
        print("ERREUR : mets ton token dans DISCORD_TOKEN ou dans le script.")
        sys.exit(1)
    bot.run(TOKEN)
