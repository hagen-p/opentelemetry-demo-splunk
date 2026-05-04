#!/usr/bin/env python3
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""
Stub gRPC server implementing CartService and CheckoutService.
Provides minimal valid responses so shop-dc-shim can run standalone
without the full Astronomy Shop platform.
"""

import uuid
import logging
from concurrent import futures

import grpc
import demo_pb2
import demo_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stub-server")


class CartServiceServicer(demo_pb2_grpc.CartServiceServicer):
    """In-memory cart stub. Stores items per user_id."""

    def __init__(self):
        self.carts = {}

    def AddItem(self, request, context):
        uid = request.user_id
        if uid not in self.carts:
            self.carts[uid] = []
        self.carts[uid].append(request.item)
        log.info("AddItem user=%s product=%s qty=%d", uid, request.item.product_id, request.item.quantity)
        return demo_pb2.Empty()

    def GetCart(self, request, context):
        items = self.carts.get(request.user_id, [])
        return demo_pb2.Cart(user_id=request.user_id, items=items)

    def EmptyCart(self, request, context):
        self.carts.pop(request.user_id, None)
        return demo_pb2.Empty()


class CheckoutServiceServicer(demo_pb2_grpc.CheckoutServiceServicer):
    """Checkout stub. Returns a fake successful order for every PlaceOrder call."""

    def PlaceOrder(self, request, context):
        order_id = str(uuid.uuid4())
        tracking_id = "STUB-" + uuid.uuid4().hex[:8].upper()

        log.info(
            "PlaceOrder user=%s email=%s currency=%s -> order=%s tracking=%s",
            request.user_id,
            request.email,
            request.user_currency,
            order_id,
            tracking_id,
        )

        return demo_pb2.PlaceOrderResponse(
            order=demo_pb2.OrderResult(
                order_id=order_id,
                shipping_tracking_id=tracking_id,
                shipping_cost=demo_pb2.Money(currency_code="USD", units=5, nanos=990000000),
                shipping_address=request.address,
                items=[],
            )
        )


def serve(port=8080):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    demo_pb2_grpc.add_CartServiceServicer_to_server(CartServiceServicer(), server)
    demo_pb2_grpc.add_CheckoutServiceServicer_to_server(CheckoutServiceServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    log.info("Stub gRPC server starting on port %d (CartService + CheckoutService)", port)
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
