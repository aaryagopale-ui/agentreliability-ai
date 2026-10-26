"""Order Processing Agent — Sample Independent Application for MVP Validation.

This sample simulates a realistic e-commerce order processing workflow:
1. Receive order data.
2. Verify customer credentials (includes secret auth token for redaction testing).
3. Check inventory for ordered items.
4. Retrieve warehouse location (nested tool call inside inventory check).
5. Calculate order total with tax and discounts.
6. Return order confirmation.

It uses the public AgentReliability SDK (`agentreliability`) to trace all executions,
tool calls, nested spans, inputs/outputs, and exceptions.
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from agentreliability import flush, trace_agent, trace_tool


class InventoryUnavailableError(Exception):
    """Raised when an item is out of stock or inventory service fails."""
    pass


class CustomerAuthenticationError(Exception):
    """Raised when customer credentials fail verification."""
    pass


# -----------------------------------------------------------------------------
# Tool Definitions
# -----------------------------------------------------------------------------

@trace_tool("verify_customer_credentials")
def verify_customer_credentials(customer_id: str, auth_token: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Verify customer credentials and session authenticity.
    
    Demonstrates SDK client-side secret redaction: 'auth_token' and 'api_key'
    will be replaced with '[REDACTED]' in the recorded trace.
    """
    if not customer_id:
        raise CustomerAuthenticationError("Missing customer ID.")
    if not auth_token or auth_token == "invalid_token":
        raise CustomerAuthenticationError(f"Customer {customer_id} failed credential check.")
    
    return {
        "customer_id": customer_id,
        "authenticated": True,
        "tier": "enterprise",
        "auth_token": auth_token,  # Redactor will sanitize this sensitive key
    }


@trace_tool("retrieve_warehouse_location")
def retrieve_warehouse_location(sku: str) -> Dict[str, Any]:
    """Retrieve the physical aisle/shelf location for an inventory item.
    
    Demonstrates nested tool execution: this tool is invoked by check_inventory,
    recording parent_call_id pointing to the check_inventory tool call.
    """
    locations = {
        "SKU-DESK-01": {"zone": "Aisle 4", "shelf": "B-12", "facility": "Warehouse-East"},
        "SKU-CHAIR-02": {"zone": "Aisle 9", "shelf": "D-03", "facility": "Warehouse-East"},
        "SKU-LAMP-03": {"zone": "Aisle 1", "shelf": "A-05", "facility": "Warehouse-West"},
    }
    loc = locations.get(sku, {"zone": "Aisle General", "shelf": "G-01", "facility": "Warehouse-Main"})
    return {"sku": sku, "location": loc}


@trace_tool("check_inventory")
def check_inventory(items: List[Dict[str, Any]], fail_inventory: bool = False, skip_warehouse: bool = False) -> Dict[str, Any]:
    """Check item stock and resolve warehouse locations.
    
    If fail_inventory is True, simulates a controlled failure (Scenario B).
    Calls retrieve_warehouse_location internally unless skip_warehouse is True (Scenario C).
    """
    if fail_inventory:
        raise InventoryUnavailableError("Inventory service unreachable for warehouse partition: SKU-ERR-999")
    
    inventory_results = []
    for item in items:
        sku = item.get("sku", "SKU-UNKNOWN")
        qty = item.get("quantity", 1)
        
        # Nested tool call inside check_inventory
        warehouse_info = None
        if not skip_warehouse:
            warehouse_info = retrieve_warehouse_location(sku)
        
        inventory_results.append({
            "sku": sku,
            "quantity_available": 100,
            "quantity_requested": qty,
            "in_stock": True,
            "warehouse": warehouse_info["location"] if warehouse_info else None,
        })
    
    return {
        "all_in_stock": True,
        "items": inventory_results,
    }


@trace_tool("calculate_total")
def calculate_total(items: List[Dict[str, Any]], discount_code: Optional[str] = None) -> Dict[str, Any]:
    """Calculate subtotal, discount, tax, and final USD amount."""
    unit_prices = {
        "SKU-DESK-01": 299.00,
        "SKU-CHAIR-02": 149.50,
        "SKU-LAMP-03": 45.00,
    }
    
    subtotal = sum(unit_prices.get(item["sku"], 50.0) * item.get("quantity", 1) for item in items)
    discount = 0.0
    if discount_code == "RELIABILITY20":
        discount = round(subtotal * 0.20, 2)
    
    tax = round((subtotal - discount) * 0.08, 2)
    total = round(subtotal - discount + tax, 2)
    
    return {
        "subtotal_usd": round(subtotal, 2),
        "discount_usd": discount,
        "tax_usd": tax,
        "total_usd": total,
    }


# -----------------------------------------------------------------------------
# Main Agent Workflow
# -----------------------------------------------------------------------------

@trace_agent("order_processing_agent", metadata={"version": "1.0.0", "service": "order-fulfillment"})
def process_order(
    order_data: Dict[str, Any],
    fail_inventory: bool = False,
    skip_warehouse: bool = False,
    modified_schema: bool = False,
) -> Dict[str, Any]:
    """Executes the full order processing agent workflow.
    
    Args:
        order_data: Input dictionary containing customer, items, and payment info.
        fail_inventory: If True, forces inventory lookup to raise an exception (Scenario B).
        skip_warehouse: If True, skips nested warehouse location tool (Scenario C).
        modified_schema: If True, modifies output schema keys to simulate regression (Scenario C).
    """
    customer_id = order_data.get("customer_id", "CUST-001")
    auth_token = order_data.get("auth_token", "secret_bearer_token_xyz123")
    items = order_data.get("items", [{"sku": "SKU-DESK-01", "quantity": 1}])
    discount_code = order_data.get("discount_code")

    # Step 1 & 2: Receive order and verify customer credentials
    cust_res = verify_customer_credentials(customer_id, auth_token, api_key="sk-live-secret-test-key-9999")
    
    # Step 3 & 4: Check inventory and retrieve warehouse location
    inv_res = check_inventory(items, fail_inventory=fail_inventory, skip_warehouse=skip_warehouse)
    
    # Step 5: Calculate total
    pricing = calculate_total(items, discount_code=discount_code)
    
    # Step 6: Return order confirmation
    confirmation_id = f"CONF-{uuid.uuid4().hex[:8].upper()}"
    
    if modified_schema:
        # Behavioral schema regression: omit standard 'total_usd' and rename 'confirmation_code'
        return {
            "order_status": "confirmed_v2",
            "reference_number": confirmation_id,  # Changed from confirmation_code
            "customer_tier": cust_res["tier"],
            "line_items_count": len(items),
            # 'total_usd' intentionally omitted
        }
    
    return {
        "order_status": "confirmed",
        "confirmation_code": confirmation_id,
        "customer_id": customer_id,
        "customer_tier": cust_res["tier"],
        "items_count": len(items),
        "total_usd": pricing["total_usd"],
        "currency": "USD",
    }


if __name__ == "__main__":
    import json
    
    print("Running Order Processing Agent directly...")
    sample_order = {
        "order_id": "ORD-5501",
        "customer_id": "CUST-4421",
        "auth_token": "token_abc123456789",
        "items": [
            {"sku": "SKU-DESK-01", "quantity": 1},
            {"sku": "SKU-CHAIR-02", "quantity": 2},
        ],
        "discount_code": "RELIABILITY20",
    }
    
    try:
        confirmation = process_order(sample_order)
        print("Success Confirmation:")
        print(json.dumps(confirmation, indent=2))
    except Exception as exc:
        print(f"Agent failed with error: {exc}")
    finally:
        flush()

