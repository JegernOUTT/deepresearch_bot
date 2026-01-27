import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional
from dataclasses import asdict

from pymongo import AsyncMongoClient
from duckduckgo_search import DDGS
from newspaper import Article

from flexus_client_kit import ckit_client
from flexus_client_kit import ckit_cloudtool
from flexus_client_kit import ckit_bot_exec
from flexus_client_kit import ckit_shutdown
from flexus_client_kit import ckit_ask_model
from flexus_client_kit import ckit_mongo
from flexus_client_kit import ckit_kanban
from flexus_client_kit import ckit_external_auth
from flexus_client_kit.integrations import fi_mongo_store
from flexus_client_kit.integrations import fi_pdoc
from flexus_client_kit.integrations import fi_slack

logger = logging.getLogger("bot_deep_research")

BOT_NAME = "deep_research"
BOT_VERSION = "0.0.7"

ASK_CLARIFYING_QUESTIONS_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="ask_clarifying_questions",
    description="Ask the user clarifying questions before starting research to ensure the research is focused and meets their needs.",
    parameters={
        "type": "object",
        "properties": {
            "scope_question": {
                "type": "string",
                "description": "Question about research scope and boundaries"
            },
            "focus_question": {
                "type": "string",
                "description": "Question about specific focus areas or priorities"
            },
            "goals_question": {
                "type": "string",
                "description": "Question about desired outcomes and goals"
            },
            "audience_question": {
                "type": ["string", "null"],
                "description": "Optional question about target audience for the research"
            },
        },
        "required": ["scope_question", "focus_question", "goals_question", "audience_question"],
        "additionalProperties": False,
    },
)

WEB_RESEARCH_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="web_research",
    description="Perform parallel web searches to gather information on a topic. Returns search results that can be further analyzed.",
    parameters={
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "description": "List of search queries to execute in parallel (max 10)",
                "items": {"type": "string"},
            },
            "max_results_per_query": {
                "type": "integer",
                "description": "Maximum number of results to return per query (default 5)"
            },
            "date_filter": {
                "type": ["string", "null"],
                "description": "Optional date filter: 'any', 'last_week', 'last_month', 'last_year', or null to use setup default"
            },
        },
        "required": ["queries", "max_results_per_query", "date_filter"],
        "additionalProperties": False,
    },
)

READ_ARTICLE_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="read_article",
    description="Read and analyze content from web URLs in parallel. Extracts key information and insights.",
    parameters={
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "description": "List of URLs to read and analyze (max 15 per call)",
                "items": {"type": "string"},
            },
            "focus": {
                "type": ["string", "null"],
                "description": "Optional specific aspect to focus on while reading"
            },
        },
        "required": ["urls", "focus"],
        "additionalProperties": False,
    },
)

CREATE_RESEARCH_REPORT_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="create_research_report",
    description="Create a comprehensive research report document at the specified path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path where the report should be created (e.g., '/research/topic-name-2024-01-15')"
            },
            "report": {
                "type": "object",
                "description": "The complete research report",
                "properties": {
                    "title": {"type": "string", "description": "Report title"},
                    "executive_summary": {"type": "string", "description": "2-3 paragraph executive summary"},
                    "research_questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of research questions clarified with user"
                    },
                    "key_findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "theme": {"type": "string"},
                                "finding": {"type": "string"},
                                "citations": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "Source numbers (1-indexed) that support this finding"
                                },
                            },
                            "required": ["theme", "finding", "citations"],
                            "additionalProperties": False,
                        },
                        "description": "Key findings organized by themes with citations"
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer", "description": "Source number (1-indexed)"},
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "type": {"type": "string", "description": "Type of source (article, paper, documentation, etc.)"},
                            },
                            "required": ["number", "title", "url", "type"],
                            "additionalProperties": False,
                        },
                        "description": "Numbered list of sources with links"
                    },
                    "conclusions": {"type": "string", "description": "Conclusions and recommendations"},
                    "research_date": {"type": "string", "description": "Date when research was conducted (YYYY-MM-DD)"},
                    "source_count": {"type": "integer", "description": "Total number of sources consulted"},
                    "research_time_minutes": {"type": "integer", "description": "Approximate time spent researching"},
                    "confidence_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence level in the findings"
                    },
                },
                "required": ["title", "executive_summary", "research_questions", "key_findings", "sources", "conclusions", "research_date", "source_count", "research_time_minutes", "confidence_level"],
                "additionalProperties": False,
            },
        },
        "required": ["path", "report"],
        "additionalProperties": False,
    },
)

TOOLS = [
    ASK_CLARIFYING_QUESTIONS_TOOL,
    WEB_RESEARCH_TOOL,
    READ_ARTICLE_TOOL,
    CREATE_RESEARCH_REPORT_TOOL,
    fi_mongo_store.MONGO_STORE_TOOL,
    fi_pdoc.POLICY_DOCUMENT_TOOL,
    fi_slack.SLACK_TOOL,
]

async def deep_research_main_loop(fclient: ckit_client.FlexusClient, rcx: ckit_bot_exec.RobotContext) -> None:
    from deep_research_install import deep_research_setup_schema

    setup = ckit_bot_exec.official_setup_mixing_procedure(deep_research_setup_schema, rcx.persona.persona_setup)

    mongo_conn_str = await ckit_mongo.mongo_fetch_creds(fclient, rcx.persona.persona_id)
    mongo = AsyncMongoClient(mongo_conn_str)
    dbname = rcx.persona.persona_id + "_db"
    mydb = mongo[dbname]
    personal_mongo = mydb["personal_mongo"]

    pdoc_integration = fi_pdoc.IntegrationPdoc(rcx, rcx.persona.ws_root_group_id)

    slack = None
    if setup.get("SLACK_BOT_TOKEN") and setup.get("SLACK_BOT_TOKEN") != "":
        slack = fi_slack.IntegrationSlack(
            fclient,
            rcx,
            SLACK_BOT_TOKEN=setup["SLACK_BOT_TOKEN"],
            SLACK_APP_TOKEN=setup.get("SLACK_APP_TOKEN", ""),
            should_join=setup.get("slack_should_join", False),
        )

    research_start_times = {}

    @rcx.on_updated_message
    async def updated_message_in_db(msg: ckit_ask_model.FThreadMessageOutput):
        if slack:
            await slack.look_assistant_might_have_posted_something(msg)
            if msg.ftm_role == "assistant" and msg.ftm_content:
                content = str(msg.ftm_content)
                if "create_research_report" in str(msg.ftm_tool_calls) or "📊 Research report created" in content:
                    if setup.get("SLACK_NOTIFICATION_CHANNEL"):
                        try:
                            channel = setup["SLACK_NOTIFICATION_CHANNEL"]
                            thread = rcx.latest_threads.get(msg.ftm_ft_id)
                            if thread:
                                task_title = thread.thread_fields.ft_app_searchable or "Research completed"
                                await slack.bot_post_text(
                                    channel_name=channel,
                                    text=f"✅ Research completed: {task_title}\n\nReport has been saved to policy documents.",
                                    thread_ts=None
                                )
                        except Exception as e:
                            logger.error(f"Failed to post completion notification to Slack: {e}")

    @rcx.on_updated_thread
    async def updated_thread_in_db(th: ckit_ask_model.FThreadOutput):
        pass

    @rcx.on_updated_task
    async def updated_task_in_db(t: ckit_kanban.FPersonaKanbanTaskOutput):
        logger.info(f"Deep Research task update: {t.fpt_title}")

    @rcx.on_tool_call(ASK_CLARIFYING_QUESTIONS_TOOL.name)
    async def toolcall_ask_clarifying_questions(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        questions = []
        for key in ["scope_question", "focus_question", "goals_question", "audience_question"]:
            if model_produced_args.get(key):
                questions.append(model_produced_args[key])

        return "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])

    @rcx.on_tool_call(WEB_RESEARCH_TOOL.name)
    async def toolcall_web_research(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        if toolcall.fcall_ft_id not in research_start_times:
            research_start_times[toolcall.fcall_ft_id] = time.time()

        queries = model_produced_args.get("queries", [])
        max_results = model_produced_args.get("max_results_per_query", 5)
        date_filter = model_produced_args.get("date_filter")

        if not queries:
            return "Error: No search queries provided."

        if len(queries) > 10:
            return f"Error: Maximum 10 queries allowed per call. You provided {len(queries)}."

        effective_date_filter = date_filter if date_filter else setup.get("date_range", "any")

        timelimit = None
        if effective_date_filter == "last_week":
            timelimit = "w"
        elif effective_date_filter == "last_month":
            timelimit = "m"
        elif effective_date_filter == "last_year":
            timelimit = "y"

        region = "wt-wt"
        research_language = setup.get("research_language", "en")
        if research_language and research_language != "en":
            region = f"{research_language}-{research_language}"

        all_results = []
        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        results = list(ddgs.text(query, region=region, timelimit=timelimit, max_results=max_results))
                        query_results = {
                            "query": query,
                            "results": [
                                {
                                    "title": r.get("title", ""),
                                    "url": r.get("href", ""),
                                    "snippet": r.get("body", ""),
                                }
                                for r in results
                            ],
                        }
                        all_results.append(query_results)
                    except Exception as e:
                        logger.error(f"Search error for query '{query}': {e}")
                        all_results.append({"query": query, "error": str(e)})
        except Exception as e:
            logger.error(f"DDGS initialization error: {e}")
            return f"Error: Failed to initialize search: {e}"

        return json.dumps(all_results, indent=2)

    @rcx.on_tool_call(READ_ARTICLE_TOOL.name)
    async def toolcall_read_article(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        urls = model_produced_args.get("urls", [])
        focus = model_produced_args.get("focus")

        if not urls:
            return "Error: No URLs provided."

        if len(urls) > 15:
            return f"Error: Maximum 15 URLs allowed per call. You provided {len(urls)}."

        results = []
        for url in urls:
            try:
                article = Article(url)
                article.download()
                article.parse()

                result = {
                    "url": url,
                    "title": article.title,
                    "authors": article.authors,
                    "publish_date": str(article.publish_date) if article.publish_date else None,
                    "text": article.text[:8000],
                    "summary": article.text[:800] + "..." if len(article.text) > 800 else article.text,
                }
                results.append(result)
            except Exception as e:
                logger.error(f"Error reading article {url}: {e}")
                results.append({"url": url, "error": str(e)})

        return json.dumps(results, indent=2)

    @rcx.on_tool_call(CREATE_RESEARCH_REPORT_TOOL.name)
    async def toolcall_create_research_report(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        path = model_produced_args["path"]
        report = model_produced_args["report"]

        research_report_doc = {
            "research_report": {
                "meta": {
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_by": "deep_research",
                    "microfrontend": BOT_NAME,
                },
                **report,
            }
        }

        fuser_id = ckit_external_auth.get_fuser_id_from_rcx(rcx, toolcall.fcall_ft_id)
        await pdoc_integration.pdoc_create(path, json.dumps(research_report_doc, indent=2), fuser_id)

        return f"📊 Research report created at: {path}\n\nTitle: {report['title']}\nConfidence: {report['confidence_level']}\nSources: {report['source_count']}\nTime: ~{report['research_time_minutes']} minutes"

    @rcx.on_tool_call(fi_mongo_store.MONGO_STORE_TOOL.name)
    async def toolcall_mongo_store(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await fi_mongo_store.handle_mongo_store(
            rcx.workdir,
            personal_mongo,
            toolcall,
            model_produced_args,
        )

    @rcx.on_tool_call(fi_pdoc.POLICY_DOCUMENT_TOOL.name)
    async def toolcall_pdoc(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await pdoc_integration.called_by_model(toolcall, model_produced_args)

    @rcx.on_tool_call(fi_slack.SLACK_TOOL.name)
    async def toolcall_slack(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        if not slack:
            return "Error: Slack integration not configured. Please set SLACK_BOT_TOKEN in setup."
        return await slack.called_by_model(toolcall, model_produced_args)

    async def slack_activity_callback(a: fi_slack.ActivitySlack, already_posted_to_captured_thread: bool):
        logger.info(f"{rcx.persona.persona_id} Slack activity: {a.what_happened} in {a.channel_name} by @{a.message_author_name}: {a.message_text}")
        if not already_posted_to_captured_thread:
            channel_name_slash_thread = a.channel_name
            if a.thread_ts:
                channel_name_slash_thread += "/" + a.thread_ts
            title = f"Slack research request from @{a.message_author_name} in {channel_name_slash_thread}\n{a.message_text}"
            details = asdict(a)

            await ckit_kanban.bot_kanban_post_into_inbox(
                fclient,
                rcx.persona.persona_id,
                title=title,
                details_json=json.dumps(details),
                provenance_message="deep_research_slack_activity"
            )

    try:
        if slack:
            slack.set_activity_callback(slack_activity_callback)
            await slack.join_channels()
            await slack.start_reactive()

        while not ckit_shutdown.shutdown_event.is_set():
            await rcx.unpark_collected_events(sleep_if_no_work=10.0)

    finally:
        if slack:
            await slack.close()
        logger.info("%s exit" % (rcx.persona.persona_id,))


def main():
    from deep_research_install import install

    scenario_fn = ckit_bot_exec.parse_bot_args()
    fclient = ckit_client.FlexusClient(ckit_client.bot_service_name(BOT_NAME, BOT_VERSION), endpoint="/v1/jailed-bot")

    asyncio.run(ckit_bot_exec.run_bots_in_this_group(
        fclient,
        marketable_name=BOT_NAME,
        marketable_version_str=BOT_VERSION,
        bot_main_loop=deep_research_main_loop,
        inprocess_tools=TOOLS,
        scenario_fn=scenario_fn,
        install_func=install,
        subscribe_to_erp_tables=[],
    ))


if __name__ == "__main__":
    main()
