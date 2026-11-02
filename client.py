
import socket
import os
import sys
import json
import hashlib
import time

SERVER_IP = sys.argv[2] if len(sys.argv) == 3 else "127.0.0.1"
SERVER_PORT = 5001

CHUNK_SIZE = 1200
TIMEOUT = 1.0
MAX_RETRIES = 10

if len(sys.argv) not in (2, 3):
    print("Usage: python3 client.py <filename> [server_ip]")
    sys.exit(1)

filename = sys.argv[1]

if not os.path.isfile(filename):
    print("File not found!")
    sys.exit(1)

filesize = os.path.getsize(filename)

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client.settimeout(TIMEOUT)

server_address = (SERVER_IP, SERVER_PORT)

metadata = {
    "type": "START",
    "filename": os.path.basename(filename),
    "filesize": filesize
}

metadata_packet = json.dumps(metadata).encode()

def receive_ready():
    for attempt in range(MAX_RETRIES):
        client.sendto(metadata_packet, server_address)

        try:
            response, _ = client.recvfrom(4096)
            if response == b"READY":
                return True
        except socket.timeout:
            print("Waiting for server... retrying")

    return False

def send_packet(packet, expected_ack):
    for attempt in range(MAX_RETRIES):
        client.sendto(packet, server_address)

        try:
            response, _ = client.recvfrom(4096)

            if response == expected_ack:
                return True

        except socket.timeout:
            print(f"Timeout: retransmitting packet {expected_ack[1:]}")

    return False

print(f"Sending file: {filename}")
print(f"File size: {filesize} bytes")

try:
    if not receive_ready():
        print("Server did not respond.")
        sys.exit(1)

    print("Server is ready. Starting transfer...")

    sent = 0
    sequence = 0
    file_hash = hashlib.sha256()

    with open(filename, "rb") as file:
        while True:
            data = file.read(CHUNK_SIZE)

            if not data:
                break

            file_hash.update(data)

            packet = b"D" + sequence.to_bytes(4, "big") + data
            expected_ack = b"A" + sequence.to_bytes(4, "big")

            if not send_packet(packet, expected_ack):
                print(f"Failed to transfer packet {sequence}")
                sys.exit(1)

            sent += len(data)
            sequence += 1

            print(f"\rTransferred {sent}/{filesize} bytes", end="")

    finish_packet = (
        b"F" +
        sequence.to_bytes(4, "big") +
        file_hash.digest()
    )

    if not send_packet(finish_packet, b"OK"):
        print("\nServer did not confirm file completion.")
        sys.exit(1)

    print("\nTransfer completed successfully!")
    print(f"Total bytes sent: {sent}")
    print(f"SHA-256: {file_hash.hexdigest()}")

finally:
    client.close()
