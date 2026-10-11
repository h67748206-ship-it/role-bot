# Fichier unique : bot + mini site web. Lancer : python perso_bot.py
import os
import subprocess
import sys

try:
    import discord
except ImportError:  # installe discord.py tout seul (pas besoin de requirements.txt)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "discord.py"])
    import discord

from aiohttp import web
from discord import app_commands
from discord.ext import commands

# ================== CONFIG ==================
TOKEN = os.getenv("DISCORD_TOKEN") or "COLLE_TON_TOKEN_ICI"

# Les rôles sont retrouvés par leur NOM (créés automatiquement s'ils n'existent pas)
ROLES_AFFICHAGE = ["Meow", "Bad boy", "Kiss", "PS"]
ROLES_NOTIFS = ["Annonce", "Smash or pass", "Giveaway"]
# ============================================


async def get_or_create_role(guild: discord.Guild, name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=name)
    if role is None:
        role = await guild.create_role(name=name, reason="Panneau personnalisation")
    return role


async def appliquer_selection(interaction: discord.Interaction, groupe: list[str], choisis: list[str]):
    await interaction.response.defer(ephemeral=True)
    guild, member = interaction.guild, interaction.user
    try:
        a_ajouter, a_retirer = [], []
        for nom in groupe:
            role = await get_or_create_role(guild, nom)
            if nom in choisis and role not in member.roles:
                a_ajouter.append(role)
            elif nom not in choisis and role in member.roles:
                a_retirer.append(role)
        if a_ajouter:
            await member.add_roles(*a_ajouter, reason="Panneau personnalisation")
        if a_retirer:
            await member.remove_roles(*a_retirer, reason="Panneau personnalisation")
    except discord.Forbidden:
        return await interaction.followup.send(
            "❌ Je n'ai pas la permission. Mets mon rôle **au-dessus** des rôles du panneau "
            "et donne-moi « Gérer les rôles ».",
            ephemeral=True,
        )
    if choisis:
        txt = "✅ Mis à jour : " + ", ".join(f"**{n}**" for n in choisis)
    else:
        txt = "🗑️ Tout a été retiré."
    await interaction.followup.send(txt, ephemeral=True)


class SelectGroupe(discord.ui.Select):
    def __init__(self, groupe, placeholder, custom_id, row):
        options = [discord.SelectOption(label=n, value=n) for n in groupe]
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id=custom_id,
            row=row,
        )
        self.groupe = groupe

    async def callback(self, interaction: discord.Interaction):
        await appliquer_selection(interaction, self.groupe, self.values)


class BoutonToutRetirer(discord.ui.Button):
    def __init__(self, groupe, custom_id, row):
        super().__init__(label="Tout retirer", style=discord.ButtonStyle.secondary, custom_id=custom_id, row=row)
        self.groupe = groupe

    async def callback(self, interaction: discord.Interaction):
        await appliquer_selection(interaction, self.groupe, [])


class PanneauPerso(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persistante
        self.add_item(SelectGroupe(ROLES_AFFICHAGE, "Choisis tes rôles", "perso:roles:select", 0))
        self.add_item(BoutonToutRetirer(ROLES_AFFICHAGE, "perso:roles:clear", 1))
        self.add_item(SelectGroupe(ROLES_NOTIFS, "Choisis tes notifications", "perso:notifs:select", 2))
        self.add_item(BoutonToutRetirer(ROLES_NOTIFS, "perso:notifs:clear", 3))


# ============ MINI SITE WEB (pour Render / cron-job.org) ============
PAGE = """<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{nom}</title>
<style>
  body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#1e1f22;color:#dbdee1;font-family:system-ui,sans-serif}}
  .card{{background:#2b2d31;border-radius:14px;padding:28px;max-width:360px;width:90%;text-align:center}}
  h1{{margin:0 0 6px;font-size:22px;color:#fff}}
  p{{margin:0 0 18px;color:#b5bac1;font-size:14px}}
  .row{{display:flex;gap:10px;margin-bottom:18px}}
  .stat{{flex:1;background:#1e1f22;border-radius:10px;padding:12px}}
  .stat b{{display:block;font-size:20px;color:#fff}}
  .stat span{{font-size:12px;color:#949ba4}}
  .ok{{display:inline-block;padding:4px 12px;border-radius:99px;background:#23a55a33;color:#3ba55d;font-size:13px}}
</style></head><body>
<div class="card">
  <h1>{nom}</h1>
  <p>Bot de personnalisation : rôles d'affichage et notifications.</p>
  <div class="row">
    <div class="stat"><b>{serveurs}</b><span>serveurs</span></div>
    <div class="stat"><b>{ping} ms</b><span>ping</span></div>
  </div>
  <span class="ok">● En ligne</span>
</div></body></html>"""


async def page_accueil(request: web.Request):
    bot = request.app["bot"]
    html = PAGE.format(
        nom=bot.user.name if bot.user else "PersoBot",
        serveurs=len(bot.guilds),
        ping=round(bot.latency * 1000) if bot.latency == bot.latency else 0,
    )
    return web.Response(text=html, content_type="text/html")


async def health(request: web.Request):
    return web.json_response({"status": "ok"})


async def lancer_site(bot: commands.Bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", page_accueil)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))  # Render fournit PORT automatiquement
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"Site web lancé sur le port {port}")


intents = discord.Intents.default()
intents.members = True  # à activer dans le portail développeur (Server Members Intent)


class PersoBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(PanneauPerso())  # les anciens panneaux restent fonctionnels
        await self.tree.sync()
        await lancer_site(self)  # mini site web pour Render


bot = PersoBot()


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} ({bot.user.id})")


@bot.tree.command(name="panneau-perso", description="Envoie le panneau de personnalisation")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def panneau_perso(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Personnalisation",
        description="Configure ton profil et tes notifications ci-dessous.",
        color=discord.Color.from_rgb(54, 57, 63),
    )
    embed.add_field(name="Rôles d'affichage", value="Choisis un ou plusieurs rôles pour ton profil.", inline=False)
    embed.add_field(name="Notifications", value="Choisis les alertes que tu veux recevoir.", inline=False)
    await interaction.channel.send(embed=embed, view=PanneauPerso())
    await interaction.response.send_message("✅ Panneau envoyé.", ephemeral=True)


@panneau_perso.error
async def panneau_perso_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
    else:
        raise error


bot.run(TOKEN)
