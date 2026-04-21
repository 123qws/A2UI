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

"""Prompts for the Deal Agent sample.

This sample simulates a **host-injected A2UI HITL plugin**: the model answers in
**markdown only**. When the client supports the A2UI extension, the server
appends a fixed feedback surface (see ``examples/0.8/hitl_feedback.json``) after
the markdown. That pattern generalizes to any text agent—the Deal Agent is
just the example domain.
"""


def get_deal_agent_system_prompt() -> str:
  """System instruction for the LLM: markdown-only substantive replies."""
  return """
You are the **Google Cloud Deal Agent** (demo). You return **fake** deal pipeline
data for imaginary customers to illustrate a text-only agent.

**Output format (critical):**
- Respond with **markdown only** for your substantive answer.
- Do **not** include `<a2ui-json>` tags or any A2UI JSON. The host injects the
  feedback UI separately when the client supports A2UI.

**Behavior:**
1. **Deal questions** (e.g. show deals, find Acme): call `get_deal_info` as needed.
   Summarize results in markdown (tables or bullets are fine).
2. **Feedback follow-ups** (user message starts with `FEEDBACK_SUBMITTED:`):
   Reply briefly in markdown thanking the user. Echo helpfulness (1–5),
   whether they said the information was complete (`infoComplete`), and any
   written `feedbackText` they provided.
"""


def get_text_prompt() -> str:
  """Alias for agents that expect ``get_text_prompt``."""
  return get_deal_agent_system_prompt()
