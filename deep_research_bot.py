import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional

from pymongo import AsyncMongoClient
from duckduckgo_search import DDGS

from flexus_client_kit import ckit_client
from flexus_client_kit import ckit_cloudtool
from flexus_client_kit import ckit_bot_exec
from flexus_client_kit import ckit_shutdown
from flexus_client_kit import ckit_ask_model
from flexus_client_kit import ckit_mongo
from flexus_client_kit import ckit_kanban
from flexus_client_kit import ckit_external_auth
from flexus_client_kit import erp_schema
from flexus_client_kit.integrations import fi_mongo_store
from flexus_client_kit.integrations import fi_pdoc

logger = logging.getLogger("bot_deep_research")


BOT_NAME = "deep_research"
BOT_VERSION = "0.0.5"


# Tool for initiating web research
WEB_RESEARCH_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="web_research",
    description="Perform parallel web searches to gather information on a topic. Returns search results that can be further analyzed.",
    parameters={
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "description": "List of search queries to execute in parallel (max 5)",
                "items": {"type": "string"},
            },
            "max_results_per_query": {
                "type": "integer",
                "description": "Maximum number of results to return per query (default 5)"
            },
            "date_filter": {
                "type": ["string", "null"],
                "description": "Optional date filter override: 'any', 'last_week', 'last_month', 'last_year', or null to use setup default"
            },
        },
        "required": ["queries", "max_results_per_query", "date_filter"],
        "additionalProperties": False,
    },
)

# Tool for reading and summarizing web content
READ_ARTICLE_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="read_article",
    description="Read and analyze content from web URLs in parallel. Extracts key information and insights.",
    parameters={
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "description": "List of URLs to read and analyze (max 10 per call)",
                "items": {"type": "string"},
            },
            "focus": {
                "type": ["string", "null"],
                "description": "Optional specific aspect to focus on while reading (e.g., 'pricing', 'technical details', 'reviews')"
            },
        },
        "required": ["urls", "focus"],
        "additionalProperties": False,
    },
)

# Tool for creating comprehensive research reports
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
                    "topic": {"type": "string", "description": "Main research topic"},
                    "summary": {"type": "string", "description": "Executive summary of findings"},
                    "key_findings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of key findings from the research"
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of source URLs referenced"
                    },
                    "detailed_analysis": {"type": "string", "description": "In-depth analysis and insights"},
                    "confidence_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence level in the findings"
                    },
                },
                "required": ["topic", "summary", "key_findings", "sources", "detailed_analysis", "confidence_level"],
                "additionalProperties": False,
            },
        },
        "required": ["path", "report"],
        "additionalProperties": False,
    },
)

TOOLS = [
    WEB_RESEARCH_TOOL,
    READ_ARTICLE_TOOL,
    CREATE_RESEARCH_REPORT_TOOL,
    fi_mongo_store.MONGO_STORE_TOOL,
    fi_pdoc.POLICY_DOCUMENT_TOOL,
]

# Tools for the researcher subchat (no recursive research tools)
TOOLS_SUBCHAT = [
    fi_mongo_store.MONGO_STORE_TOOL,
    fi_pdoc.POLICY_DOCUMENT_TOOL,
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

    # Track research depth usage per thread
    research_depth_used = {}

    @rcx.on_updated_message
    async def updated_message_in_db(msg: ckit_ask_model.FThreadMessageOutput):
        pass

    @rcx.on_updated_thread
    async def updated_thread_in_db(th: ckit_ask_model.FThreadOutput):
        pass

    @rcx.on_updated_task
    async def updated_task_in_db(t: ckit_kanban.FPersonaKanbanTaskOutput):
        logger.info(f"Deep Research task update: {t}")
        pass

    @rcx.on_tool_call(WEB_RESEARCH_TOOL.name)
    async def toolcall_web_research(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        queries = model_produced_args.get("queries", [])
        max_results = model_produced_args.get("max_results_per_query", 5)
        date_filter = model_produced_args.get("date_filter")

        if not queries:
            return "Error: No search queries provided."

        if len(queries) > 5:
            return f"Error: Maximum 5 queries allowed per call. You provided {len(queries)}."

        used = research_depth_used.get(toolcall.fcall_ft_id, 0)
        remaining = setup["max_research_depth"] - used

        if len(queries) > remaining:
            return f"Error: Research depth limit reached. Only {remaining}/{setup['max_research_depth']} queries remaining for this thread."

        research_depth_used[toolcall.fcall_ft_id] = used + len(queries)

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

        if len(urls) > 10:
            return f"Error: Maximum 10 URLs allowed per call. You provided {len(urls)}."

        focus_instruction = f" Focus specifically on: {focus}." if focus else ""

        # Create subchats for parallel article reading
        subchats = await ckit_ask_model.bot_subchat_create_multiple(
            client=fclient,
            who_is_asking="deep_research_read_article",
            persona_id=rcx.persona.persona_id,
            first_question=[f"Read and analyze the content from this URL: {url}. Extract the main points, key insights, and relevant information.{focus_instruction}" for url in urls],
            first_calls=["null" for _ in urls],
            title=[f"Reading: {url[:50]}..." for url in urls],
            fcall_id=toolcall.fcall_id,
            fexp_name="researcher",
        )
        raise ckit_cloudtool.WaitForSubchats(subchats)

    @rcx.on_tool_call(CREATE_RESEARCH_REPORT_TOOL.name)
    async def toolcall_create_research_report(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        path = model_produced_args["path"]
        report = model_produced_args["report"]

        research_report_doc = {
            "research_report": {
                "meta": {
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_by": "deep_research_bot",
                },
                **report,
            }
        }

        fuser_id = ckit_external_auth.get_fuser_id_from_rcx(rcx, toolcall.fcall_ft_id)
        await pdoc_integration.pdoc_create(path, json.dumps(research_report_doc, indent=2), fuser_id)
        return f"📊 Research report created at: {path}\n\nTopic: {report['topic']}\nConfidence: {report['confidence_level']}\nSources: {len(report['sources'])}"

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

    try:
        while not ckit_shutdown.shutdown_event.is_set():
            await rcx.unpark_collected_events(sleep_if_no_work=10.0)

    finally:
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
