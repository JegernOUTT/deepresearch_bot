import asyncio
import json

from flexus_client_kit import ckit_client, ckit_bot_install
from flexus_client_kit import ckit_cloudtool

from flexus_simple_bots import prompts_common
import deep_research_prompts


BOT_DESCRIPTION = """
## Deep Research - Comprehensive Research Assistant

A powerful AI bot designed to conduct thorough, systematic research on any topic using advanced web search and content analysis capabilities.

**Key Features:**
- **Parallel Web Search**: Execute multiple search queries simultaneously for comprehensive coverage
- **Article Analysis**: Read and extract insights from web content in parallel
- **Source Cross-Referencing**: Verify information across multiple authoritative sources
- **Structured Reports**: Generate well-organized research reports with citations
- **Confidence Tracking**: Explicitly note uncertainty levels and source quality

**Research Capabilities:**
- Broad exploratory research on new topics
- Deep-dive analysis of specific subjects
- Competitive analysis and market research
- Technical documentation review
- News and trend monitoring
- Academic literature surveys

**Perfect for:**
- Market research and competitive intelligence
- Technical due diligence
- Content research for writing projects
- Academic research support
- Product evaluation and comparison
- Industry trend analysis

Deep Research combines systematic methodology with parallel processing to deliver comprehensive, well-sourced findings efficiently.
"""


deep_research_setup_schema = [
    {
        "bs_name": "research_style",
        "bs_type": "string_short",
        "bs_default": "comprehensive",
        "bs_group": "Research Approach",
        "bs_order": 1,
        "bs_importance": 0,
        "bs_description": "Research depth: 'quick' (fast overview), 'comprehensive' (balanced), 'exhaustive' (maximum depth)",
    },
    {
        "bs_name": "source_preference",
        "bs_type": "string_short",
        "bs_default": "authoritative",
        "bs_group": "Research Approach",
        "bs_order": 2,
        "bs_importance": 0,
        "bs_description": "Source priority: 'authoritative' (official/academic), 'diverse' (broad range), 'recent' (latest info)",
    },
    {
        "bs_name": "research_language",
        "bs_type": "string_short",
        "bs_default": "en",
        "bs_group": "Research Approach",
        "bs_order": 3,
        "bs_importance": 0,
        "bs_description": "Language for research (e.g., 'en' for English, 'es' for Spanish, 'fr' for French, 'de' for German)",
    },
    {
        "bs_name": "max_research_depth",
        "bs_type": "int",
        "bs_default": 10,
        "bs_group": "Research Limits",
        "bs_order": 1,
        "bs_importance": 1,
        "bs_description": "Maximum number of parallel search queries allowed per research session. Higher values enable more thorough research but consume more resources.",
    },
    {
        "bs_name": "confidence_threshold",
        "bs_type": "string_short",
        "bs_default": "medium",
        "bs_group": "Quality Control",
        "bs_order": 1,
        "bs_importance": 0,
        "bs_description": "Minimum confidence level before presenting findings: 'low' (permissive), 'medium' (balanced), 'high' (strict)",
    },
]


RESEARCH_SUBCHAT_LARK = f"""
# This subchat is for individual research operations (searches, article reads)
print("Research subchat executing")
subchat_result = "Research completed successfully"
"""

RESEARCH_DEFAULT_LARK = f"""
# Main research bot logic
print("Processing %d messages" % len(messages))
msg = messages[-1]
if msg["role"] == "assistant":
    content = str(msg.get("content", ""))
    tool_calls = str(msg.get("tool_calls", ""))

    # Track research progress
    if "web_research" in tool_calls or "read_article" in tool_calls:
        print("Research operation in progress")

    # Remind to create report if research seems complete
    if len(messages) > 5 and "create_research_report" not in tool_calls:
        content_lower = content.lower()
        keywords = ["conclusion", "findings", "summary", "complete"]
        matches = [k for k in keywords if k in content_lower]
        if len(matches) > 0:
            post_cd_instruction = "Consider creating a research report to document your findings."
"""


async def install(
    client: ckit_client.FlexusClient,
    ws_id: str,
    bot_name: str,
    bot_version: str,
    tools: list[ckit_cloudtool.CloudTool],
):
    import deep_research_bot
    bot_internal_tools = json.dumps([t.openai_style_tool() for t in tools])
    bot_subchat_tools = json.dumps([t.openai_style_tool() for t in deep_research_bot.TOOLS_SUBCHAT])

    await ckit_bot_install.marketplace_upsert_dev_bot(
        client,
        ws_id=ws_id,
        marketable_name=bot_name,
        marketable_version=bot_version,
        marketable_accent_color="#1E90FF",
        marketable_title1="Deep Research",
        marketable_title2="Conduct comprehensive research with web search and analysis",
        marketable_author="Flexus",
        marketable_occupation="Research Analyst",
        marketable_description=BOT_DESCRIPTION,
        marketable_typical_group="Research / Analysis",
        marketable_github_repo="https://github.com/smallcloudai/flexus-client-kit.git",
        marketable_run_this="python -m deep_research_bot",
        marketable_setup_default=deep_research_setup_schema,
        marketable_featured_actions=[
            {"feat_question": "Research the latest developments in AI and machine learning", "feat_run_as_setup": False, "feat_depends_on_setup": []},
            {"feat_question": "Analyze market trends for electric vehicles in 2024", "feat_run_as_setup": False, "feat_depends_on_setup": []},
            {"feat_question": "Compare the top 5 project management tools", "feat_run_as_setup": False, "feat_depends_on_setup": []},
        ],
        marketable_intro_message="Hello! I'm Deep Research, your comprehensive research assistant. I can help you investigate any topic using systematic web research, analyze multiple sources, and create detailed reports with my findings. What would you like me to research today?",
        marketable_preferred_model_default="grok-4-1-fast-non-reasoning",
        marketable_daily_budget_default=150_000,
        marketable_default_inbox_default=20_000,
        marketable_experts=[
            ("default", ckit_bot_install.FMarketplaceExpertInput(
                fexp_system_prompt=deep_research_prompts.deep_research_prompt,
                fexp_python_kernel=RESEARCH_DEFAULT_LARK,
                fexp_block_tools="",
                fexp_allow_tools="",
                fexp_app_capture_tools=bot_internal_tools,
            )),
            ("researcher", ckit_bot_install.FMarketplaceExpertInput(
                fexp_system_prompt=deep_research_prompts.deep_research_prompt,
                fexp_python_kernel=RESEARCH_SUBCHAT_LARK,
                fexp_block_tools="",
                fexp_allow_tools="",
                fexp_app_capture_tools=bot_subchat_tools,
            )),
        ],
        marketable_tags=["Research", "Analysis", "Web Search", "Reports"],
        marketable_picture_big_b64=open("/workspace/big_image_b64.txt").read(),
        marketable_picture_small_b64=open("/workspace/small_image_b64.txt").read(),
        marketable_schedule=[
            prompts_common.SCHED_TASK_SORT_10M | {"sched_when": "EVERY:10m", "sched_first_question": "Check inbox for research tasks and organize them by priority."},
            prompts_common.SCHED_TODO_5M | {"sched_when": "EVERY:5m", "sched_first_question": "Continue working on the assigned research task with systematic methodology."},
        ],
        marketable_forms=ckit_bot_install.load_form_bundles(__file__),
    )


if __name__ == "__main__":
    import deep_research_bot
    args = ckit_bot_install.bot_install_argparse()
    client = ckit_client.FlexusClient("deep_research_install")
    asyncio.run(install(client, ws_id=args.ws, bot_name=deep_research_bot.BOT_NAME, bot_version=deep_research_bot.BOT_VERSION, tools=deep_research_bot.TOOLS))
