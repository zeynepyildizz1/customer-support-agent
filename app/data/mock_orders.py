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
    "ORD-10435": {
            "customer_id": "CUST-004",
            "status": "delivered",
            "amount": 455.0,
            "tracking_number": "TRK-99284",
            "return_eligible": True,
        },
    "ORD-10436": {
            "customer_id": "CUST-005",
            "status": "processing",
            "amount": 670.0,
            "tracking_number": None,
            "return_eligible": False,
        },
    "ORD-10437": {
            "customer_id": "CUST-006",
            "status": "shipped",
            "amount": 2500.0,
            "tracking_number": "TRK-99285",
            "return_eligible": False,
        },
    "ORD-10438": {
                "customer_id": "CUST-007",
                "status": "delivered",
                "amount": 890.0,
                "tracking_number": "TRK-99286",
                "return_eligible": False,
            },
}


def get_order(order_id: str) -> dict | None:
    return MOCK_ORDERS.get(order_id)