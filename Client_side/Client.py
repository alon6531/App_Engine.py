import socket
import json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from Client_side import Engine
from Client_side.App.User import User
import threading


class Client:
    def __init__(self, server_host='192.168.1.212', tcp_port=65432, udp_port=12345):
        """
        Initialize the Client by generating keys, connecting to the server,
        and starting the application engine.
        """
        self.server_host = server_host
        self.tcp_port = tcp_port
        self.udp_port = udp_port

        # Generate RSA keys
        self.private_key, self.public_key = self.make_keys()
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # Create TCP socket
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client_socket.connect((server_host, tcp_port))
            print(f"Connected to server at {server_host}:{tcp_port}")

            self.client_socket.send(self.public_key_pem)
            public_server_key_pem = self.client_socket.recv(1024)
            self.public_server_key = load_pem_public_key(public_server_key_pem)

            self.username = None
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            self.client_socket.close()
            raise

        # Create UDP socket
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            print(f"UDP server listening on {server_host}:{udp_port}...")
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            self.udp_socket.close()
            raise
        # Initialize the application engine
        self.app_engine = Engine.AppEngine(self)

    def make_keys(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        return private_key, public_key

    def encrypt(self, text):
        return self.public_server_key.encrypt(
            text.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def log_in(self, login_username, login_password):
        try:
            self.client_socket.send(b'login')
            response = self.client_socket.recv(1024).decode('utf-8')
            credentials = f"{login_username},{login_password}"
            self.client_socket.send(self.encrypt(credentials))
            response = self.client_socket.recv(1024).decode('utf-8')
            if response == 'True':
                print("Login successful!")
                self.username = login_username
                return True
            else:
                print("Login failed!")
                return False
        except Exception as e:
            print(f"Error during login: {e}")
            return False

    def register(self, user_name, username, password):
        try:
            self.client_socket.send(b'register')
            response = self.client_socket.recv(1024).decode('utf-8')
            user_data = f"{user_name},{username},{password}"
            self.client_socket.send(self.encrypt(user_data))
            response = self.client_socket.recv(1024).decode('utf-8')
            print(response)
        except Exception as e:
            print(f"Error during registration: {e}")

    def receive_stories(self):

        self.udp_socket.sendto(b'receive_stories', (self.server_host, self.udp_port))
        data, _ = self.udp_socket.recvfrom(4096)
        json_data = data.decode('utf-8')
        stories_data = json.loads(json_data)

        # Extract data into arrays
        titles = stories_data['titles']
        contents = stories_data['contents']
        usernames = stories_data['usernames']
        pos_x = stories_data['pos_x']
        pos_y = stories_data['pos_y']

        # Print or return the arrays as needed
        print("Received titles:", titles)
        print("Received contents:", contents)
        print("Received usernames:", usernames)
        print("Received pos_x:", pos_x)
        print("Received pos_y:", pos_y)

        # Return the extracted data as arrays
        return titles, contents, usernames, pos_x, pos_y

    def send_player_data(self, pos_x, pos_y):
        retries = 3  # Number of retry attempts
        attempt = 0

        while attempt < retries:
            try:
                # Send initial signal to server
                self.udp_socket.sendto(b'send_player_data', (self.server_host, self.udp_port))

                # Prepare the data to send (username, pos_x, pos_y)
                player_data = {
                    "username": self.username,
                    "pos_x": pos_x,
                    "pos_y": pos_y
                }

                # Convert the data to JSON and send it to the server
                data_to_send = json.dumps(player_data)
                self.udp_socket.sendto(data_to_send.encode('utf-8'), (self.server_host, self.udp_port))
                print(f"Sent player data to server: {player_data}\n")

                # Wait for the server's response (list of all players)
                data, _ = self.udp_socket.recvfrom(1024)

                # Decode and parse the server's response
                response = json.loads(data.decode('utf-8'))

                # Assuming the response contains the number of players and the list of users
                num_players = response.get('num_players', 0)  # Default to 0 if 'num_players' is not in the response
                print(response)

                # Extract players' information, default to an empty list if 'players' key is not found
                users_db = response.get('players', [])
                users = []
                for user in users_db:
                    username = user.get('username', 'Unknown')  # Default to 'Unknown' if username is not found
                    pos_x = user.get('pos_x', 0)  # Default to 0 if pos_x is not found
                    pos_y = user.get('pos_y', 0)  # Default to 0 if pos_y is not found
                    print(f"Username: {username}, Position: ({pos_x}, {pos_y})")
                    users.append(User(username, pos_x, pos_y))
                return num_players, users

            except Exception as e:
                print(f"Error sending/receiving player data (Attempt {attempt + 1}/{retries}): {e}")
                attempt += 1
                if attempt < retries:
                    print("Retrying...")
                    time.sleep(2)  # Optional: wait for 2 seconds before retrying
                else:
                    print("Max retries reached. Could not send player data.")
                    return None, None  # Return None if max retries are reached

    def logout(self):
        try:
            self.client_socket.send(b'logout')
            response = self.client_socket.recv(1024).decode('utf-8')
            self.client_socket.send(self.username.encode('utf-8'))
            response = self.client_socket.recv(1024).decode('utf-8')
            print(response)
        except Exception as e:
            print(f"Error during logout: {e}")
        finally:
            self.client_socket.close()
            print("Disconnected from server.")

    def get_user(self):
        return self.username

    def add_story(self, title, content, username, pos_x, pos_y):
        try:
            self.client_socket.send(b'add_story')
            response = self.client_socket.recv(1024).decode('utf-8')
            self.client_socket.send(title.encode())
            self.client_socket.recv(1024)
            self.client_socket.send(content.encode())
            self.client_socket.recv(1024)
            self.client_socket.send(username.encode())
            self.client_socket.recv(1024)
            self.client_socket.send(str(pos_x).encode())
            self.client_socket.recv(1024)
            self.client_socket.send(str(pos_y).encode())
            response = self.client_socket.recv(1024).decode('utf-8')
            print(response)
        except Exception as e:
            print(f"Error adding story: {e}")


# Main entry point
if __name__ == "__main__":
    try:
        client = Client()
    except Exception as e:
        print(f"Client failed to start: {e}")
