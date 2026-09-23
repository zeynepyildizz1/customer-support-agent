MOCK_ORDERS = {
    "ORD-10432": {
        "customer_id": "CUST-001",
        "status": "shipped",
        "amount": 1250.0,
        "tracking_number": "TRK-99281",
        "return_eligible": True,
    },
    "ORD-10433": {
        "customer_id": "CUST-002",
        "status": "delivered",
        "amount": 340.0,
        "tracking_number": "TRK-99282",
        "return_eligible": True,
    },
    "ORD-10434": {
        "customer_id": "CUST-003",
        "status": "processing",
        "amount": 89.0,
        "tracking_number": None,
        "return_eligible": False,
    },
}


def get_order(order_id: str) -> dict | None:
    return MOCK_ORDERS.get(order_id)