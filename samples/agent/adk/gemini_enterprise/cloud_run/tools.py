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

logger = logging.getLogger(__name__)


def get_deal_info(customer: str = None, sector: str = "") -> str:
  """Returns fake Google Cloud customer deal data.

  'customer' is an optional customer name filter. 'sector' is an optional
  industry filter.
  """
  logger.info("--- TOOL CALLED: get_deal_info ---")
  logger.info(f"  - Customer: {customer}")
  logger.info(f"  - Sector: {sector}")

  results = []
  try:
    script_dir = os.path.dirname(__file__)
    file_path = os.path.join(script_dir, "deal_data.json")
    with open(file_path) as f:
      deal_data_str = f.read()
      all_deals = json.loads(deal_data_str)

    if customer is None:
      return json.dumps(all_deals)

    customer_lower = customer.lower()
    sector_lower = sector.lower() if sector else ""

    # Filter by customer name.
    results = [
        deal for deal in all_deals if customer_lower in deal["customerName"].lower()
    ]

    # If sector is provided, filter results further.
    if sector_lower:
      results = [
          deal for deal in results if sector_lower in deal["sector"].lower()
      ]

    logger.info(f"  - Success: Found {len(results)} matching deals.")

  except FileNotFoundError:
    logger.error(f"  - Error: deal_data.json not found at {file_path}")
  except json.JSONDecodeError:
    logger.error(f"  - Error: Failed to decode JSON from {file_path}")

  return json.dumps(results)
