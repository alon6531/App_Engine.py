import socket
import threading
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from Server_side import SqlDataBase, jsonDataBase
from Client_side.App.User import User
import json
import time


class Server:
    def __init__(self, host='192.168.1.212', port=65432, udp_port=12345):
        """
        Initialize the Server, generate keys, and start the server socket.
        """
        # Initialize the databases (SQL and JSON)
        self.sql_data_base = SqlDataBase.SqlDataBase()
        self.json_data_base = jsonDataBase.jsonDataBase()

        # Set host and ports for the server
        self.host = host
        self.port = port
        self.udp_port = udp_port
        self.players = []

        # Generate RSA keys (private and public) for encryption/decryption
        self.private_key, self.public_key = self.make_keys()
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # Print all users from the database (for debugging)
        self.sql_data_base.print_all_users()

        # Set up the server socket and start listening for incoming connections
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Server listening on {self.host}:{self.port}...")

        # Create UDP socket for receiving player updates
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.host, self.udp_port))
        print(f"UDP server listening on {self.host}:{self.udp_port}...")

        # Start UDP listener in a separate thread
        udp_thread = threading.Thread(target=self.listen_for_udp)
        udp_thread.daemon = True  # Ensures the thread exits when the main program stops
        udp_thread.start()

        # Start accepting incoming connections in a loop
        print("Server is running...")
        self.listen_for_clients()

    def make_keys(self):
        """
        Generate a new RSA key pair (private and public).
        """
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        return private_key, public_key

    def decrypt(self, encrypted_text):
        """
        Decrypt the encrypted message using the private key.
        """
        return self.private_key.decrypt(
            encrypted_text,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def listen_for_clients(self):
        """
        Accept incoming client connections and handle them using separate threads.
        """
        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"Connection established with {client_address}\n")
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address))
            client_thread.start()

    def listen_for_udp(self):
        """
        Listen for incoming UDP messages and handle them.
        """

        time.sleep(0.1)  # Adding a small delay of 100ms
        while True:
            if self.udp_socket.fileno() == -1:
                print("Socket is closed.")
                break
            # Receive data from the socket
            massage, client_address = self.udp_socket.recvfrom(1024)
            data = json.loads(massage.decode('utf-8'))
            action = data['action']


            print(f"Received UDP message from {client_address}: {action}\n")

            if action == "send_player_data":
                self.update_and_send_players(data, client_address)
            elif action == "logout":
                self.handle_logout_udp(data, client_address)




    def update_and_send_players(self, data, client_address):
        """
        Receive player data from a client (username, pos_x, pos_y) and send all players' information via UDP.
        """
        if not data:  # Check if the data is empty
            print("Received empty data, ignoring...")
            return  # Ignore if data is empty


        # Extract player info safely with validation
        username = data.get("username")
        pos_x = data.get("pos_x")
        pos_y = data.get("pos_y")

        print(f"Received via UDP -> username: {username}, x: {pos_x}, y: {pos_y}\n")

        # Update or add the player to the list
        player_updated = False
        for player in self.players:
            if player.username == username:
                player.pos_x = pos_x
                player.pos_y = pos_y
                player_updated = True
                print(f"Updated existing player: {username} with new position.")
                break

        if not player_updated:
            self.players.append(User(username, pos_x, pos_y))
            print(f"Added new player: {username}")

        # Prepare and send all players' information to the client
        players_data = {
            "num_players": len(self.players),
            "players": [{"username": player.username, "pos_x": player.pos_x, "pos_y": player.pos_y} for player in
                        self.players]
        }
        # Convert the players data to a JSON string and send it via UDP
        data_to_send = json.dumps(players_data)
        self.udp_socket.sendto(data_to_send.encode('utf-8'), client_address)
        print("All players' data sent successfully via UDP.\n")

    def handle_receive_stories(self, client_socket):
        """
        Handle the request for stories from the client using TCP.
        """
        print("Sending stories to client via TCP...\n")

        # Retrieve data from database
        titles, contents, usernames, pos_x, pos_y = self.json_data_base.receive_data()

        # Create dictionary with the data
        data = {
            "titles": titles or [],
            "contents": contents or [],
            "usernames": usernames or [],
            "pos_x": pos_x or [],
            "pos_y": pos_y or []
        }

        # Convert to JSON string
        json_data = json.dumps(data)

        try:
            # Send data through TCP socket
            client_socket.send(json_data.encode('utf-8'))
            print("Stories sent successfully.\n")
        except Exception as e:
            print(f"Error sending stories: {e}")



    def handle_client(self, client_socket, client_address):
        """
        Handle communication with a connected client.
        """
        try:
            # Receive the public key of the client and send the server's public key
            public_client_key_pem = client_socket.recv(1024)
            public_client_key = load_pem_public_key(public_client_key_pem)
            client_socket.send(self.public_key_pem)

            while True:
                action = client_socket.recv(1024).decode('utf-8')  # Receive the action from the client
                print(f"Action received: {action}\n")
                response = client_socket.send(f"Action received: {action}".encode('utf-8'))

                if action == 'login':
                    self.handle_login(client_socket)

                elif action == 'receive_stories':
                    self.handle_receive_stories(client_socket)

                elif action == 'register':
                    self.handle_register(client_socket)

                elif action == 'add_story':
                    self.handle_add_story(client_socket)

                elif action == 'logout':
                    self.handle_logout(client_socket)
                    break

        except Exception as e:
            print(f"Error with client {client_address}: {e}\n")

        finally:
            client_socket.close()
            print(f"Closed connection with {client_address}\n")

    def handle_login(self, client_socket):
        """
        Handle user login by checking credentials.
        """
        credentials = self.decrypt(client_socket.recv(1024)).decode()
        username, password = credentials.split(',')
        print(f"Login attempt for {username}\n")

        if self.sql_data_base.check_credentials(username, password):
            client_socket.send(b'True')  # Send success response
        else:
            client_socket.send(b'False')  # Send failure response



    def handle_register(self, client_socket):
        """
        Handle user registration and store new user in the database.
        """
        user_data = self.decrypt(client_socket.recv(1024)).decode()
        first_name, username, password = user_data.split(',')
        print(f"Registering user {first_name}, {username}\n")

        if self.sql_data_base.create_user(first_name, username, password):
            client_socket.send(b'Registration successful')
            self.sql_data_base.print_all_users()
        else:
            client_socket.send(b'Registration failed')

    def handle_add_story(self, client_socket):
        """
        Handle adding a new story from the client, now including pos_x and pos_y.
        """
        title = client_socket.recv(1024).decode()
        client_socket.send(b'title sent successfully')
        print(f"Received title: {title}\n")

        content = client_socket.recv(1024).decode()
        client_socket.send(b'content sent successfully')
        print(f"Received content: {content}\n")

        username = client_socket.recv(1024).decode()
        client_socket.send(b'username sent successfully')
        print(f"Received username: {username}\n")

        pos_x = int(client_socket.recv(1024).decode())  # Receive pos_x
        client_socket.send(b'pos_x sent successfully')
        print(f"Received pos_x: {pos_x}\n")

        pos_y = int(client_socket.recv(1024).decode())  # Receive pos_y
        client_socket.send(b'pos_y sent successfully')
        print(f"Received pos_y: {pos_y}\n")

        self.json_data_base.add_entry(title, content, username, pos_x, pos_y)
        print("Story added to database.\n")

    def handle_logout(self, client_socket):
        """
        Handle client logout and remove the player from the players list.
        """
        try:
            # Receive the username of the player who is logging out
            username = client_socket.recv(1024).decode('utf-8')
            print(f"Logout request received for {username}\n")

            # Handle logout logic here

            # Send response back to the client
            client_socket.send(b"Logout successful.")

        except Exception as e:
            print(f"Error during logout: {e}")
            client_socket.send(b"Error during logout.")

    def handle_logout_udp(self, data, client_address):
        """
        Handle client logout and remove the player from the players list.
        """
        try:
            # Receive the username of the player who is logging out
            username = data['username']
            print(f"Logout request received for {username}\n")

            # Find the player in the list and remove them
            player_found = False
            for player in self.players:
                if player.username == username:
                    self.players.remove(player)
                    player_found = True
                    print(f"Player {username} removed from the players list.")
                    break

            if player_found:
                self.udp_socket.sendto(b'Logout successful, you have been removed from the players list.', client_address)

            else:
                self.udp_socket.sendto(b'Player not found, could not log out.', client_address)

        except Exception as e:
            print(f"Error during logout: {e}")





# Main entry point for the server
if __name__ == "__main__":
    server = Server()  # Initialize and start the server
