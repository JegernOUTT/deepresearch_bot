import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional

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
from flexus_client_kit import erp_schema
from flexus_client_kit.integrations import fi_mongo_store
from flexus_client_kit.integrations import fi_pdoc

logger = logging.getLogger("bot_deep_research")


BOT_NAME = "deep_research"
BOT_VERSION = "0.0.9"


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

    logger.info(f"Starting deep_research_main_loop for persona {rcx.persona.persona_id}")

    setup = ckit_bot_exec.official_setup_mixing_procedure(deep_research_setup_schema, rcx.persona.persona_setup)
    logger.info(f"Bot setup: max_research_depth={setup.get('max_research_depth')}, research_language={setup.get('research_language')}, date_range={setup.get('date_range')}")

    mongo_conn_str = await ckit_mongo.mongo_fetch_creds(fclient, rcx.persona.persona_id)
    mongo = AsyncMongoClient(mongo_conn_str)
    dbname = rcx.persona.persona_id + "_db"
    mydb = mongo[dbname]
    personal_mongo = mydb["personal_mongo"]

    pdoc_integration = fi_pdoc.IntegrationPdoc(rcx, rcx.persona.ws_root_group_id)

    # Track research depth usage per thread
    research_depth_used = {}
    logger.debug("Research depth tracking initialized")

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

        logger.info(f"web_research called with {len(queries)} queries, max_results={max_results}, date_filter={date_filter}")

        if not queries:
            logger.warning("web_research called with no queries")
            return "Error: No search queries provided."

        if not isinstance(queries, list):
            logger.error(f"web_research called with invalid queries type: {type(queries)}")
            return "Error: queries parameter must be a list."

        if len(queries) > 5:
            logger.warning(f"web_research called with {len(queries)} queries, exceeding max of 5")
            return f"Error: Maximum 5 queries allowed per call. You provided {len(queries)}. Please reduce the number of queries."

        used = research_depth_used.get(toolcall.fcall_ft_id, 0)
        remaining = setup["max_research_depth"] - used

        if len(queries) > remaining:
            logger.warning(f"Research depth limit reached: {used}/{setup['max_research_depth']} used, {len(queries)} requested")
            return f"Error: Research depth limit reached. Only {remaining}/{setup['max_research_depth']} queries remaining for this thread."

        research_depth_used[toolcall.fcall_ft_id] = used + len(queries)
        logger.info(f"Research depth updated: {research_depth_used[toolcall.fcall_ft_id]}/{setup['max_research_depth']} used")

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
            logger.debug(f"Initializing DDGS with region={region}, timelimit={timelimit}")
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        logger.debug(f"Executing search query: '{query}'")
                        results = list(ddgs.text(query, region=region, timelimit=timelimit, max_results=max_results))

                        if not results:
                            logger.warning(f"DDGS returned empty results for query '{query}' with region={region}, timelimit={timelimit}")

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
                        logger.info(f"Query '{query}' returned {len(results)} results")
                    except Exception as e:
                        logger.error(f"DDGS search exception for query '{query}': {type(e).__name__}: {e}", exc_info=True)
                        all_results.append({"query": query, "error": f"{type(e).__name__}: {str(e)}"})
        except Exception as e:
            logger.error(f"DDGS initialization error: {type(e).__name__}: {e}", exc_info=True)
            return f"Error: Failed to initialize search: {type(e).__name__}: {e}"

        successful_queries = len([r for r in all_results if "error" not in r])
        failed_queries = len([r for r in all_results if "error" in r])
        logger.info(f"web_research completed: {successful_queries} successful, {failed_queries} failed queries")
        return json.dumps(all_results, indent=2)

    @rcx.on_tool_call(READ_ARTICLE_TOOL.name)
    async def toolcall_read_article(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        urls = model_produced_args.get("urls", [])
        focus = model_produced_args.get("focus")

        logger.info(f"read_article called with {len(urls)} URLs, focus={focus}")

        if not urls:
            logger.warning("read_article called with no URLs")
            return "Error: No URLs provided."

        if not isinstance(urls, list):
            logger.error(f"read_article called with invalid urls type: {type(urls)}")
            return "Error: urls parameter must be a list."

        if len(urls) > 10:
            logger.warning(f"read_article called with {len(urls)} URLs, exceeding max of 10")
            return f"Error: Maximum 10 URLs allowed per call. You provided {len(urls)}."

        results = []
        for url in urls:
            try:
                logger.debug(f"Downloading article from {url}")
                article = Article(url)
                article.download()
                article.parse()

                result = {
                    "url": url,
                    "title": article.title,
                    "authors": article.authors,
                    "publish_date": str(article.publish_date) if article.publish_date else None,
                    "text": article.text[:5000],
                    "summary": article.text[:500] + "..." if len(article.text) > 500 else article.text,
                }
                results.append(result)
                logger.info(f"Successfully read article from {url}")
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"Error reading article {url}: {error_type}: {error_msg}")

                error_category = "unknown_error"
                user_message = error_msg

                if "404" in error_msg or "Not Found" in error_msg:
                    error_category = "http_404"
                    user_message = "Article not found (404). The URL may be invalid or the content has been removed."
                elif "403" in error_msg or "Forbidden" in error_msg:
                    error_category = "http_403"
                    user_message = "Access forbidden (403). The website may be blocking automated access."
                elif "timeout" in error_msg.lower():
                    error_category = "timeout"
                    user_message = "Request timed out. The website may be slow or unreachable."
                elif "connection" in error_msg.lower() or "unreachable" in error_msg.lower():
                    error_category = "connection_error"
                    user_message = "Connection error. The website may be down or unreachable."
                elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                    error_category = "ssl_error"
                    user_message = "SSL/Certificate error. The website may have security issues."

                results.append({
                    "url": url,
                    "error": user_message,
                    "error_type": error_category,
                    "error_details": error_msg
                })

        logger.info(f"read_article completed: {len([r for r in results if 'error' not in r])} successful, {len([r for r in results if 'error' in r])} failed")
        return json.dumps(results, indent=2)

    @rcx.on_tool_call(CREATE_RESEARCH_REPORT_TOOL.name)
    async def toolcall_create_research_report(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        path = model_produced_args["path"]
        report = model_produced_args["report"]

        logger.info(f"create_research_report called for path: {path}, topic: {report.get('topic', 'unknown')}")

        research_report_doc = {
            "research_report": {
                "meta": {
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "created_by": "deep_research_bot",
                },
                **report,
            }
        }

        try:
            fuser_id = ckit_external_auth.get_fuser_id_from_rcx(rcx, toolcall.fcall_ft_id)
            await pdoc_integration.pdoc_create(path, json.dumps(research_report_doc, indent=2), fuser_id)
            logger.info(f"Research report successfully created at {path}")
            return f"📊 Research report created at: {path}\n\nTopic: {report['topic']}\nConfidence: {report['confidence_level']}\nSources: {len(report['sources'])}"
        except Exception as e:
            logger.error(f"Failed to create research report at {path}: {e}")
            return f"Error: Failed to create research report: {str(e)}"

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
