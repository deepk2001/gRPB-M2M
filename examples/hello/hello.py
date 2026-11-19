"""Hello world for grpb-m2m: a gRPC-style call carried over MQTT.

    pip install grpb-m2m
    mosquitto                 # an MQTT broker on localhost:1883 (brew/apt install mosquitto)
    python hello.py
"""
import grpc
import grpb

BROKER = "localhost"   # where the MQTT broker runs


# --- server: answers "SayHello" calls -------------------------------------------------------
def say_hello(request: bytes, context) -> bytes:
    name = request.decode()
    return f"Hello, {name}!".encode()


server = grpb.MqttServer("greeter", host=BROKER)          # instead of grpc.server()
server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
    "demo.Greeter", {"SayHello": grpc.unary_unary_rpc_method_handler(say_hello)}),))
server.start()

# --- client: calls the server by its name, through the broker --------------------------------
with grpb.MqttChannel("greeter", host=BROKER) as channel:  # instead of grpc.insecure_channel()
    say_hello_rpc = channel.unary_unary("/demo.Greeter/SayHello")
    reply = say_hello_rpc(b"world", timeout=5, wait_for_ready=True)
    print(reply.decode())                                  # -> Hello, world!

server.stop(0).wait()
