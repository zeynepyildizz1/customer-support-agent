from langchain_core.tools import tool

from app.data.mock_orders import get_order as _get_order


@tool
def get_order_status(order_id: str) -> dict:
    """Verilen sipariş numarasına ait durum, tutar, kargo takip no ve iade uygunluğu bilgisini döner.
    Sipariş bulunamazsa 'not_found': True içeren bir sonuç döner."""
    order = _get_order(order_id)
    if order is None:
        return {"not_found": True, "order_id": order_id}
    return order