"""Adapter registry with lazy loading.

Only imports adapter modules when their platform is actually configured.
This avoids requiring slack-sdk or discord.py when they aren't needed.
"""

import sys
from typing import Callable, Optional

from notify.config import NotifyConfig
from notify.adapters.base import BaseAdapter, AnswerCallback, CommandCallback


def load_adapters(
    config: NotifyConfig,
    answer_callback: AnswerCallback,
    command_callback: Optional[CommandCallback] = None,
) -> list[BaseAdapter]:
    """Instantiate and return adapters for all configured platforms.

    Only imports platform SDKs that are actually needed.
    Silently skips platforms whose SDK is not installed.
    """
    adapters = []

    if config.slack.has_bot:
        try:
            from notify.adapters.slack import SlackAdapter
            adapters.append(SlackAdapter(
                answer_callback=answer_callback,
                bot_token=config.slack.bot_token,
                app_token=config.slack.app_token,
                channel=config.slack.channel,
                authorized_users=config.slack.authorized_users,
                command_callback=command_callback,
            ))
        except ImportError:
            print("Warning: slack-sdk not installed. Slack bot disabled.", file=sys.stderr)
            print("  Install with: pip install slack-sdk", file=sys.stderr)

    if config.discord.has_bot:
        try:
            from notify.adapters.discord import DiscordAdapter
            adapters.append(DiscordAdapter(
                answer_callback=answer_callback,
                bot_token=config.discord.bot_token,
                channel_id=config.discord.channel_id,
                authorized_users=config.discord.authorized_users,
                command_callback=command_callback,
            ))
        except ImportError:
            print("Warning: discord.py not installed. Discord bot disabled.", file=sys.stderr)
            print("  Install with: pip install discord.py", file=sys.stderr)

    return adapters
