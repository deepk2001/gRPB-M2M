"""Pick the transport for a sample app: gRPB-M2M over MQTT, or plain gRPC over HTTP/2.

This is the only place the two differ; servicers and stubs are the same generated code.
"""

from __future__ import annotations

import argparse
import os
from concurrent import futures
from typing import Any

import grpc

import grpb
from grpb.config import Config

TRANSPORTS = ("mqtt", "grpc")


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--transport", choices=TRANSPORTS, default=os.getenv("GRPB_TRANSPORT", "mqtt"),
                    help="mqtt = gRPB-M2M through the broker (default), grpc = plain gRPC over HTTP/2")


def describe(transport: str, cfg: Config) -> str:
    if transport == "mqtt":
        return f"mqtt://{cfg.broker_host}:{cfg.broker_port}/{cfg.server_id}"
    return f"grpc://{cfg.grpc_target}"


def open_channel(transport: str, cfg: Config, client_id: str | None = None) -> Any:
    if transport == "mqtt":
        return grpb.MqttChannel(cfg.server_id, cfg.broker_host, cfg.broker_port, client_id=client_id)
    return grpc.insecure_channel(cfg.grpc_target)


def make_server(transport: str, cfg: Config, port: int = 50051, max_workers: int = 32) -> Any:
    """An unstarted server; register servicers on it, then call start()."""
    if transport == "mqtt":
        return grpb.MqttServer(cfg.server_id, cfg.broker_host, cfg.broker_port, max_workers=max_workers)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))  # each stream holds a worker
    server.add_insecure_port(f"0.0.0.0:{port}")
    return server
