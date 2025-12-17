import asyncio
import base64
import json
from pathlib import Path

from flexus_client_kit import ckit_client, ckit_bot_install
from flexus_client_kit import ckit_cloudtool

from flexus_simple_bots import prompts_common
from flexus_simple_bots.deepresearch import deepresearch_prompts


BOT_DESCRIPTION = """
## DeepResearch - Autonomous Web Research Bot

An AI research assistant that conducts thorough web research and produces comprehensive, cited Markdown reports.

**Key Features:**
- **Autonomous Research**: Conducts multi-step web searches and browses pages automatically
- **Cited Reports**: Generates ~500-word Markdown reports with proper [text](url) citations
- **Policy Document Storage**: Saves research findings to /reports/deepresearch/ for future reference
- **Kanban Integration**: Accepts research tasks like "Research: [topic]" from your board
- **Zero Configuration**: No API keys or setup required - works out of the box

**Workflow:**
1. Search phase: Performs up to 10 web searches to find relevant sources
2. Browse phase: Extracts detailed information from up to 10 key pages
3. Synthesis: Combines findings into a well-structured narrative
4. Save: Stores report in /reports/deepresearch/YYYY-MM-DD--topic-slug/report.md

**Perfect for:**
- Market research and competitive analysis
- Background research on technical topics
- Gathering information for decision-making
- Creating research briefs for teams

**Limits:**
- Maximum 20 tool calls per research task
- 30-minute timeout per session
- Maximum 2 concurrent research tasks
"""


# Zero configuration - no setup fields required
deepresearch_setup_schema = []


DEEPRESEARCH_DEFAULT_LARK = """
print("Processing %d messages in research session" % len(messages))
# Track research progress, no special kernel logic needed for deepresearch
"""


async def install(
    client: ckit_client.FlexusClient,
    ws_id: str,
    bot_name: str,
    bot_version: str,
    tools: list[ckit_cloudtool.CloudTool],
):
    """Install the deepresearch bot to the marketplace."""
    bot_internal_tools = json.dumps([t.openai_style_tool() for t in tools])
    pic_big = base64.b64encode(open(Path(__file__).with_name("deepresearch-1024x1536.webp"), "rb").read()).decode("ascii")
    pic_small = base64.b64encode(open(Path(__file__).with_name("deepresearch-256x256.webp"), "rb").read()).decode("ascii")

    await ckit_bot_install.marketplace_upsert_dev_bot(
        client,
        ws_id=ws_id,
        marketable_name=bot_name,
        marketable_version=bot_version,
        marketable_accent_color="#2E86AB",
        marketable_title1="DeepResearch",
        marketable_title2="Autonomous web research that produces comprehensive cited reports",
        marketable_author="Flexus",
        marketable_occupation="Research Assistant",
        marketable_description=BOT_DESCRIPTION,
        marketable_typical_group="Research / Productivity",
        marketable_github_repo="https://github.com/JegernOUTT/deepresearch_bot",
        marketable_run_this="python -m flexus_simple_bots.deepresearch.deepresearch_bot",
        marketable_setup_default=deepresearch_setup_schema,
        marketable_featured_actions=[
            {
                "feat_question": "Generate research report",
                "feat_run_as_setup": False,
                "feat_depends_on_setup": []
            },
            {
                "feat_question": "Research the latest developments in quantum computing",
                "feat_run_as_setup": False,
                "feat_depends_on_setup": []
            },
        ],
        marketable_intro_message="Hi! I'm DeepResearch. I conduct autonomous web research and create comprehensive 500-word Markdown reports with citations. Give me a topic and I'll gather information, synthesize findings, and save a detailed report for you.",
        marketable_preferred_model_default="grok-4-1-fast-non-reasoning",
        marketable_daily_budget_default=100_000,
        marketable_default_inbox_default=10_000,
        marketable_experts=[
            ("default", ckit_bot_install.FMarketplaceExpertInput(
                fexp_system_prompt=deepresearch_prompts.DEEPRESEARCH_PROMPT,
                fexp_python_kernel=DEEPRESEARCH_DEFAULT_LARK,
                fexp_block_tools="*setup*",
                fexp_allow_tools="",
                fexp_app_capture_tools=bot_internal_tools,
            )),
        ],
        marketable_tags=["Research", "Productivity", "Reports"],
        marketable_picture_big_b64=pic_big,
        marketable_picture_small_b64=pic_small,
        marketable_schedule=[
            prompts_common.SCHED_TASK_SORT_10M | {
                "sched_when": "EVERY:5m",
                "sched_first_question": "Check inbox for research tasks. Tasks starting with 'Research:' should be sorted to todo. Respond with: N tasks sorted.",
            },
            prompts_common.SCHED_TODO_5M | {
                "sched_when": "EVERY:2m",
                "sched_first_question": "Work on assigned research task. Search, browse, synthesize, and save report.",
            },
        ],
        marketable_forms=ckit_bot_install.load_form_bundles(__file__),
    )


if __name__ == "__main__":
    from flexus_simple_bots.deepresearch import deepresearch_bot
    args = ckit_bot_install.bot_install_argparse()
    client = ckit_client.FlexusClient("deepresearch_install")
    asyncio.run(install(client, ws_id=args.ws, bot_name=deepresearch_bot.BOT_NAME, bot_version=deepresearch_bot.BOT_VERSION, tools=deepresearch_bot.TOOLS))
