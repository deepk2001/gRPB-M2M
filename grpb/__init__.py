"""gRPB-M2M: gRPC-style typed contracts with Protobuf encoding, carried over MQTT.

Generated gRPC stubs and servicers work unchanged; only the channel and the server change:

    import grpb
    channel = grpb.MqttChannel("hub", host="broker.local")      # instead of grpc.insecure_channel()
    server = grpb.MqttServer("hub", host="broker.local")        # instead of grpc.server()
"""

from .channel import MqttChannel, MqttRpcError
from .server import MqttServer

__version__ = "0.1.0"
__all__ = ["MqttChannel", "MqttRpcError", "MqttServer", "__version__"]
