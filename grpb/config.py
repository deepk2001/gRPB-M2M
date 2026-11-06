"""Connection settings shared by devices, tools and benchmarks.

Every value can be overridden with an environment variable, so the same code runs on a
laptop (everything on localhost) and on a Raspberry Pi (broker on the laptop's LAN IP).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    cse_id: str = "id-in"  # CSE-ID without the leading "/", as used in MQTT topics
    cse_name: str = "cse-in"  # CSEBase resource name, the root of structured paths
    cse_http: str = "http://127.0.0.1:8080"  # used only by HTTP/JSON interop checks
    request_timeout: float = 10.0
    grpc_target: str = "127.0.0.1:50051"  # plain gRPC (HTTP/2) demo hub / baseline
    server_id: str = "hub"  # gRPB-M2M server the examples talk to over MQTT

    @classmethod
    def from_env(cls) -> Config:
        host = os.getenv("GRPB_BROKER_HOST", cls.broker_host)
        return cls(
            grpc_target=os.getenv("GRPB_GRPC_TARGET", f"{host}:50051"),
            server_id=os.getenv("GRPB_SERVER_ID", cls.server_id),
            broker_host=host,
            broker_port=int(os.getenv("GRPB_BROKER_PORT", cls.broker_port)),
            cse_id=os.getenv("GRPB_CSE_ID", cls.cse_id),
            cse_name=os.getenv("GRPB_CSE_NAME", cls.cse_name),
            # Default the HTTP endpoint to the broker host: in the demo both run on the same machine.
            cse_http=os.getenv("GRPB_CSE_HTTP", f"http://{host}:8080"),
            request_timeout=float(os.getenv("GRPB_TIMEOUT", cls.request_timeout)),
        )
