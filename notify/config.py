"""Load and validate notification configuration."""

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SlackConfig:
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    app_token: Optional[str] = None
    channel: Optional[str] = None
    authorized_users: list[str] = field(default_factory=list)

    @property
    def has_webhook(self) -> bool:
        return self.webhook_url is not None

    @property
    def has_bot(self) -> bool:
        return self.bot_token is not None and self.app_token is not None


@dataclass
class DiscordConfig:
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    channel_id: Optional[str] = None
    authorized_users: list[str] = field(default_factory=list)

    @property
    def has_webhook(self) -> bool:
        return self.webhook_url is not None

    @property
    def has_bot(self) -> bool:
        return self.bot_token is not None


@dataclass
class NotifyConfig:
    slack: SlackConfig = field(default_factory=SlackConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    enabled: bool = True
    events: set[str] = field(default_factory=lambda: {"all"})
    timeout: int = 5

    @property
    def has_any_webhook(self) -> bool:
        return self.slack.has_webhook or self.discord.has_webhook

    @property
    def has_any_bot(self) -> bool:
        return self.slack.has_bot or self.discord.has_bot

    def should_notify(self, event_type: str) -> bool:
        if not self.enabled:
            return False
        if not (self.has_any_webhook or self.has_any_bot):
            return False
        return "all" in self.events or event_type in self.events


def load_config(dobby_dir: Path | None = None) -> NotifyConfig:
    """Load config from env vars and .dobby/notify.conf. Env vars win."""
    config = NotifyConfig()

    # Load from file first (lower priority)
    if dobby_dir is None:
        dobby_dir = Path.cwd() / ".dobby"
    conf_path = dobby_dir / "notify.conf"

    if conf_path.exists():
        parser = configparser.ConfigParser()
        parser.read(conf_path)

        if parser.has_section("slack"):
            config.slack.webhook_url = parser.get("slack", "webhook", fallback=None)
            config.slack.bot_token = parser.get("slack", "bot_token", fallback=None)
            config.slack.app_token = parser.get("slack", "app_token", fallback=None)
            config.slack.channel = parser.get("slack", "channel", fallback=None)
            if au := parser.get("slack", "authorized_users", fallback=None):
                config.slack.authorized_users = [u.strip() for u in au.split(",") if u.strip()]

        if parser.has_section("discord"):
            config.discord.webhook_url = parser.get("discord", "webhook", fallback=None)
            config.discord.bot_token = parser.get("discord", "bot_token", fallback=None)
            config.discord.channel_id = parser.get("discord", "channel_id", fallback=None)
            if au := parser.get("discord", "authorized_users", fallback=None):
                config.discord.authorized_users = [u.strip() for u in au.split(",") if u.strip()]

        if parser.has_section("notify"):
            config.enabled = parser.getboolean("notify", "enabled", fallback=True)
            events_str = parser.get("notify", "events", fallback="all")
            config.events = {e.strip() for e in events_str.split(",")}
            config.timeout = parser.getint("notify", "timeout", fallback=5)

    # Override with env vars (higher priority)
    if v := os.environ.get("DOBBY_SLACK_WEBHOOK"):
        config.slack.webhook_url = v
    if v := os.environ.get("DOBBY_SLACK_BOT_TOKEN"):
        config.slack.bot_token = v
    if v := os.environ.get("DOBBY_SLACK_APP_TOKEN"):
        config.slack.app_token = v
    if v := os.environ.get("DOBBY_SLACK_CHANNEL"):
        config.slack.channel = v
    if v := os.environ.get("DOBBY_DISCORD_WEBHOOK"):
        config.discord.webhook_url = v
    if v := os.environ.get("DOBBY_DISCORD_BOT_TOKEN"):
        config.discord.bot_token = v
    if v := os.environ.get("DOBBY_DISCORD_CHANNEL_ID"):
        config.discord.channel_id = v
    if v := os.environ.get("DOBBY_SLACK_AUTHORIZED_USERS"):
        config.slack.authorized_users = [u.strip() for u in v.split(",")]
    if v := os.environ.get("DOBBY_DISCORD_AUTHORIZED_USERS"):
        config.discord.authorized_users = [u.strip() for u in v.split(",")]
    if v := os.environ.get("DOBBY_NOTIFY_EVENTS"):
        config.events = {e.strip() for e in v.split(",")}
    if v := os.environ.get("DOBBY_NOTIFY_TIMEOUT"):
        config.timeout = int(v)

    return config
