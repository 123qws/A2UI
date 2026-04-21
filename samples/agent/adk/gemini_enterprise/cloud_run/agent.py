# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
from typing import Any, Dict, List, Optional

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Part,
    TextPart,
)
from a2ui.a2a.extension import get_a2ui_agent_extension
from a2ui.a2a.parts import parse_response_to_parts
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.common_modifiers import remove_strict_validation
from a2ui.schema.constants import A2UI_CLOSE_TAG, A2UI_OPEN_TAG, VERSION_0_8
from a2ui.schema.manager import A2uiSchemaManager
import dotenv
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
import jsonschema
from prompt_builder import get_deal_agent_system_prompt
from tools import get_deal_info

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

dotenv.load_dotenv()

_FEEDBACK_QUERY_PREFIX = "FEEDBACK_SUBMITTED:"


class DealAgent:
  """Demo agent: markdown answers + optional host-injected A2UI HITL feedback.

  Injected payloads in ``examples/0.8/*.json`` follow A2UI v0.8 stream order:
  ``surfaceUpdate`` → ``dataModelUpdate`` (when needed) → ``beginRendering`` last,
  so clients can buffer structure and state before the first paint. See
  https://a2ui.org/specification/v0.8-a2ui/ Section 1.5.
  """

  def __init__(self, base_url: str):
    self.base_url = base_url
    self._agent_name = "deal_agent"
    self._user_id = "remote_agent"
    self._runner: Runner = self._build_runner(self._build_llm_agent())

    self._schema_managers: Dict[str, A2uiSchemaManager] = {}
    for version in [VERSION_0_8]:
      self._schema_managers[version] = self._build_schema_manager(version)

    self._agent_card = self._build_agent_card()

  @property
  def agent_card(self) -> AgentCard:
    return self._agent_card

  def _build_schema_manager(self, version: str) -> A2uiSchemaManager:
    return A2uiSchemaManager(
        version=version,
        catalogs=[
            BasicCatalog.get_config(
                version=version,
                examples_path=os.path.join(
                    os.path.dirname(__file__), f"examples/{version}"
                ),
            )
        ],
        schema_modifiers=[remove_strict_validation],
    )

  def _load_injected_a2ui(self, filename: str) -> List[Any]:
    path = os.path.join(os.path.dirname(__file__), "examples", VERSION_0_8, filename)
    with open(path, encoding="utf-8") as f:
      return json.load(f)

  def _build_agent_card(self) -> AgentCard:
    """Builds the AgentCard for this agent, describing its capabilities and skills."""
    extensions = []
    for version, sm in self._schema_managers.items():
      ext = get_a2ui_agent_extension(
          version,
          sm.accepts_inline_catalogs,
          sm.supported_catalog_ids,
      )
      extensions.append(ext)

    capabilities = AgentCapabilities(
        streaming=True,
        extensions=extensions,
    )
    skill = AgentSkill(
        id="find_deal",
        name="Find Deal Tool",
        description=(
            "Finds fake Google Cloud customer deal details and deal pipeline"
            " status."
        ),
        tags=["deals", "pipeline", "sales", "google cloud"],
        examples=[
            "Show deal status for Acme Retail Group",
            "List all open Google Cloud deals",
        ],
    )

    return AgentCard(
        name="Google Cloud Deal Agent",
        description=(
            "Markdown-first demo agent (Deal pipeline). When the client "
            "supports A2UI, the host appends a standard HITL feedback surface—"
            "the same pattern works for any text agent."
        ),
        url=self.base_url,
        version="1.0.0",
        default_input_modes=SUPPORTED_CONTENT_TYPES,
        default_output_modes=SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        preferred_transport="HTTP+JSON",
        skills=[skill],
    )

  def _build_runner(self, agent: LlmAgent) -> Runner:
    return Runner(
        app_name=self._agent_name,
        agent=agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
    return "Reviewing deal pipeline..."

  def _build_llm_agent(self) -> LlmAgent:
    return LlmAgent(
        model=os.getenv("MODEL", "gemini-2.5-flash"),
        name=self._agent_name,
        description=(
            "Returns fake Google Cloud customer deals as markdown (demo). "
            "No A2UI in model output."
        ),
        instruction=get_deal_agent_system_prompt(),
        tools=[get_deal_info],
    )

  async def fetch_response(
      self, query, session_id, ui_version: Optional[str] = None
  ) -> List[Part]:
    """Runs the text agent; injects A2UI for HITL when ``ui_version`` is set."""

    session_state = {"base_url": self.base_url}
    schema_manager = self._schema_managers.get(ui_version) if ui_version else None
    selected_catalog = (
        schema_manager.get_selected_catalog() if schema_manager else None
    )

    if ui_version and (not selected_catalog or not selected_catalog.catalog_schema):
      logger.error("--- DealAgent.fetch_response: A2UI schema not loaded. ---")
      return [
          Part(
              root=TextPart(
                  text=(
                      "I'm sorry, I'm facing an internal configuration error "
                      "with my UI components. Please contact support."
                  )
              )
          )
      ]

    session = await self._runner.session_service.get_session(
        app_name=self._agent_name,
        user_id=self._user_id,
        session_id=session_id,
    )
    if session is None:
      session = await self._runner.session_service.create_session(
          app_name=self._agent_name,
          user_id=self._user_id,
          state=session_state,
          session_id=session_id,
      )
    elif "base_url" not in session.state:
      session.state["base_url"] = self.base_url

    max_retries = 1
    attempt = 0
    current_query_text = query
    markdown_body = ""

    while attempt <= max_retries:
      attempt += 1
      logger.info(
          "--- DealAgent.fetch_response: Attempt"
          f" {attempt}/{max_retries + 1} for session {session_id} ---"
      )

      current_message = types.Content(
          role="user", parts=[types.Part.from_text(text=current_query_text)]
      )

      full_content_list: List[str] = []
      async for event in self._runner.run_async(
          user_id=self._user_id,
          session_id=session.id,
          new_message=current_message,
      ):
        if event.is_final_response():
          if event.content and event.content.parts:
            full_content_list.extend(
                [p.text for p in event.content.parts if p.text]
            )

      markdown_body = "".join(full_content_list).strip()

      if markdown_body:
        break

      if attempt <= max_retries:
        current_query_text = (
            "I received no response. Please try again. "
            f"Please retry the original request: '{query}'"
        )
        logger.info("Retrying after empty model response.")
      else:
        markdown_body = (
            "I'm sorry, I encountered an error and couldn't process your request."
        )

    if not ui_version:
      return [Part(root=TextPart(text=markdown_body))]

    # Host-injected A2UI (simulates a plugin wrapping any markdown agent).
    try:
      if query.strip().upper().startswith(_FEEDBACK_QUERY_PREFIX):
        injected = self._load_injected_a2ui("follow_success.json")
      else:
        injected = self._load_injected_a2ui("hitl_feedback.json")
      selected_catalog.validator.validate(injected)
    except (OSError, json.JSONDecodeError, jsonschema.exceptions.ValidationError) as e:
      logger.error("--- DealAgent.fetch_response: Injected A2UI invalid: %s ---", e)
      return [
          Part(
              root=TextPart(
                  text=(
                      "I'm sorry, I'm having trouble loading the feedback UI. "
                      "Here is the text response only:\n\n"
                      f"{markdown_body}"
                  )
              )
          )
      ]

    combined = (
        f"{markdown_body.rstrip()}\n\n"
        f"{A2UI_OPEN_TAG}\n{json.dumps(injected)}\n{A2UI_CLOSE_TAG}"
    )
    return parse_response_to_parts(
        combined, validator=selected_catalog.validator
    )
