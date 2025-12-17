import asyncio
import logging
from typing import Dict, Any

from flexus_client_kit import ckit_client
from flexus_client_kit import ckit_cloudtool
from flexus_client_kit import ckit_bot_exec
from flexus_client_kit import ckit_shutdown
from flexus_client_kit import ckit_ask_model
from flexus_client_kit import ckit_kanban
from flexus_client_kit.integrations import fi_pdoc
from flexus_simple_bots.deepresearch import deepresearch_install
from flexus_simple_bots.version_common import SIMPLE_BOTS_COMMON_VERSION

logger = logging.getLogger("bot_deepresearch")

BOT_NAME = "deepresearch"
BOT_VERSION = SIMPLE_BOTS_COMMON_VERSION

# Tools: web is a cloudtool (handled by backend), flexus_policy_document is inprocess
TOOLS = [
    fi_pdoc.POLICY_DOCUMENT_TOOL,
]


async def deepresearch_main_loop(fclient: ckit_client.FlexusClient, rcx: ckit_bot_exec.RobotContext) -> None:
    """Main loop for the deepresearch bot."""
    # Mix defaults with user's custom setup (even though we have zero setup fields)
    setup = ckit_bot_exec.official_setup_mixing_procedure(deepresearch_install.deepresearch_setup_schema, rcx.persona.persona_setup)

    # Initialize policy document integration
    pdoc_integration = fi_pdoc.IntegrationPdoc(rcx, rcx.persona.ws_root_group_id)

    # Handler: when a message is updated in the database
    @rcx.on_updated_message
    async def updated_message_in_db(msg: ckit_ask_model.FThreadMessageOutput):
        logger.info(f"Message updated: {msg.ftm_belongs_to_ft_id} alt={msg.ftm_alt} num={msg.ftm_num}")

    # Handler: when a thread is updated
    @rcx.on_updated_thread
    async def updated_thread_in_db(th: ckit_ask_model.FThreadOutput):
        logger.info(f"Thread updated: {th.ft_id}")

    # Handler: when a kanban task is updated
    @rcx.on_updated_task
    async def updated_task_in_db(t: ckit_kanban.FPersonaKanbanTaskOutput):
        logger.info(f"Task updated: {t.ktask_id} - {t.ktask_title}")

    # Handler: policy documents (for saving research reports)
    @rcx.on_tool_call(fi_pdoc.POLICY_DOCUMENT_TOOL.name)
    async def toolcall_pdoc(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        """Handle policy document operations (read/write research reports)."""
        return await pdoc_integration.called_by_model(toolcall, model_produced_args)

    # Main event loop
    try:
        while not ckit_shutdown.shutdown_event.is_set():
            await rcx.unpark_collected_events(sleep_if_no_work=10.0)
    finally:
        logger.info(f"{rcx.persona.persona_id} exit")


def main():
    """Entry point for the deepresearch bot."""
    scenario_fn = ckit_bot_exec.parse_bot_args()
    fclient = ckit_client.FlexusClient(ckit_client.bot_service_name(BOT_NAME, BOT_VERSION), endpoint="/v1/jailed-bot")

    asyncio.run(ckit_bot_exec.run_bots_in_this_group(
        fclient,
        marketable_name=BOT_NAME,
        marketable_version_str=BOT_VERSION,
        bot_main_loop=deepresearch_main_loop,
        inprocess_tools=TOOLS,
        scenario_fn=scenario_fn,
        install_func=deepresearch_install.install,
    ))


if __name__ == "__main__":
    main()
