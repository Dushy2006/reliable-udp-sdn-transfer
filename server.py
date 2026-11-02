import socket
import json
import os
import hashlib

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 1400
CHUNK_SIZE = 1200

os.makedirs("received_files", exist_ok=True)

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind((HOST, PORT))

last_finish_packet = None
last_finish_client = None

print(f"UDP Server listening on port {PORT}...")

while True:
    print("\nWaiting for a file...")

    metadata, client_address = server.recvfrom(4096)

    if (metadata == last_finish_packet and
            client_address == last_finish_client):
        server.sendto(b"OK", client_address)
        continue

    try:
        info = json.loads(metadata.decode())

        if info.get("type") != "START":
            print("Invalid transfer request.")
            continue

        filename = os.path.basename(info["filename"])
        filesize = int(info["filesize"])

        if not filename or filesize < 0:
            print("Invalid file information.")
            continue

    except (json.JSONDecodeError, KeyError, ValueError):
        print("Invalid metadata.")
        continue

    print(f"Receiving: {filename}")
    print(f"File size: {filesize} bytes")

    output_path = os.path.join("received_files", filename)
    temp_path = output_path + ".part"

    server.sendto(b"READY", client_address)

    expected_seq = 0
    received_bytes = 0
    file_hash = hashlib.sha256()
    completed = False

    try:
        with open(temp_path, "wb") as output:
            while True:
                packet, address = server.recvfrom(4096)

                if address != client_address:
                    continue

                if packet == metadata:
                    server.sendto(b"READY", client_address)
                    continue

                if packet.startswith(b"D") and len(packet) >= 5:
                    seq = int.from_bytes(packet[1:5], "big")
                    data = packet[5:]

                    if seq == expected_seq:
                        if received_bytes + len(data) > filesize:
                            server.sendto(b"ERROR", client_address)
                            break

                        output.write(data)
                        file_hash.update(data)
                        received_bytes += len(data)
                        expected_seq += 1

                        ack = b"A" + seq.to_bytes(4, "big")
                        server.sendto(ack, client_address)

                    elif seq < expected_seq:
                        ack = b"A" + seq.to_bytes(4, "big")
                        server.sendto(ack, client_address)

                    else:
                        expected = b"N" + expected_seq.to_bytes(4, "big")
                        server.sendto(expected, client_address)

                elif packet.startswith(b"F") and len(packet) == 37:
                    total_packets = int.from_bytes(packet[1:5], "big")
                    received_hash = packet[5:37]

                    if (total_packets == expected_seq
                            and received_bytes == filesize
                            and file_hash.digest() == received_hash):

                        output.flush()
                        os.fsync(output.fileno())
                        completed = True
                        last_finish_packet = packet
                        last_finish_client = client_address
                        server.sendto(b"OK", client_address)
                        break

                    server.sendto(b"ERROR", client_address)
                    break

        if completed:
            os.replace(temp_path, output_path)
            print("File received successfully!")
            print(f"Saved to: {output_path}")
            print(f"Bytes received: {received_bytes}")
            print(f"SHA-256: {file_hash.hexdigest()}")
        else:
            print("Transfer failed.")

    except OSError as error:
        print(f"File error: {error}")

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
