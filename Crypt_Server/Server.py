import socket
from time import time, sleep

import Crypt_Server.Crypt as Crypt
from Crypto.Random import get_random_bytes


class KeyExchangeFailed(Exception):

    def __init__(self, *args):
        super().__init__(*args)


class Server:

    def __init__(self, ip, port, claves=None, bits=4096, unhandled_connections=5):
        """
        Set ups the server and generate the keys
        :param ip: Ip to bind
        :param port: Port to bind
        :param claves: Cryptographic keys to use(if None, it'll generate them)
        :param bits: Bits for generating the keys(These keys should be stronger than the client ones because is 
        your public key which provides the tunnel for the other key to travel and are the same across all the 
        clients)
        :param unhandled_connections: Number of non-accepted connections before starting refusing them
        """
        if claves is None:
            self.claves = Crypt.generate_rsa(bits)
        else:
            self.claves = claves
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind((ip, port))
        self.s.listen(unhandled_connections)

    def accept(self, timeout=None):
        self.s.settimeout(timeout)
        conn, addr = self.s.accept()
        return conn

    def key_exchange(self, conn, timeout=None, tunnel_anchor=1024 * 1024, token_size=32):
        """
        Accept a connection(this should be iterated to avoid unhandled connections)
        :param conn: Connection to handle
        :param timeout: Time to wait for a connection
        :param tunnel_anchor: Bits anchor for the key exchange
        :param token_size: Authentication token size to generate
        :raise KeyExchangeFailed
        :return: Connnection object or Timeout Exception if timeout met
        """
        conn.settimeout(timeout)
        try:
            aes_key = Crypt.generate_aes(32)
            conn.send(self.claves["PUBLIC"])
            public = Crypt.decrypt_rsa(conn.recv(tunnel_anchor), self.claves["PRIVATE"]).decode()
            server_token = get_random_bytes(token_size)
            conn.send(Crypt.encrypt_rsa(server_token, public))
            token = Crypt.decrypt_rsa(conn.recv(tunnel_anchor), self.claves["PRIVATE"])
            conn.send(Crypt.encrypt_rsa(aes_key, public))
        except:
            conn.close()
            raise KeyExchangeFailed("The key exchange failed. Connection closed")
        connection = Connection(conn, token, server_token, aes_key)
        return connection

    def __del__(self):
        self.s.close()


class InvalidToken(Exception):

    def __init__(self, *args):
        super().__init__(*args)


class DisconnectedClient(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class UnableToDecrypt(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class TooManyQueries(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class Connection:

    def __init__(self, conn, client_token, server_token, aes_key):
        """
        Connection object handling cryptography and authentication methods
        :param conn: Socket connection object
        :param client_token: Authentication token of the client
        :param server_token: Authentication token of the server
        """
        self.conn = conn
        self.client_token = client_token
        self.server_token = server_token
        self.aes_key = aes_key
        self.last_query = 0
        self.query_cooldown = 0

    def close(self):
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.conn.close()

    def set_query_cooldown(self, cooldown):
        self.query_cooldown = cooldown

    def send(self, msg, number_size=5):
        """
        Sends the given data to the client
        :param msg: Message to send(String)
        :param number_size: Size in bytes of integer representing the size of the message
        :raise DisconnectedClient
        :return: VOID
        """
        msg = self.server_token + msg.encode()
        msg = Crypt.encrypt_aes(msg, self.aes_key)
        leng = len(msg).to_bytes(number_size, "big")
        try:
            self.conn.send(leng+msg)
        except socket.error:
            self.close()
            raise DisconnectedClient("The client has been disconnected. Connection closed")

    def recv(self, timeout=None, number_size=5):
        """
        Receives data from the client and check the token
        :param timeout: Time to wait until exiting
        :param number_size: Size in bytes of integer representing the size of the message
        :raise UnableToDecrypt
        :raise DisconnectedClient
        :raise InvalidToken
        :return: Message received(String)
        """
        if time() - self.last_query < self.query_cooldown:
            raise TooManyQueries  # We simulate that there is nothing to read
        self.conn.settimeout(timeout)
        long = int.from_bytes(self.conn.recv(number_size), "big")
        msg = self.conn.recv(long)
        if msg == b"":
            self.close()
            raise DisconnectedClient("The client has been disconnected. Connection closed")
        try:
            msg = Crypt.decrypt_aes(msg, self.aes_key)
        except Exception:
            raise UnableToDecrypt("Unable to decrypt the client message")
        if self.client_token == msg[:len(self.client_token)]:
            msg = msg.replace(self.client_token, b"", 1)
        else:
            raise InvalidToken("The token provided by the client doesn't match the original one. Maybe an attempt"
                               "of man-in-the-middle?")
        self.last_query = time()
        return msg.decode()

    def get_conn(self):
        """
        Gets the Connection object from the socket module(This object should only be used to gather information
        of the client such as getting the address, never to send or receive directly as it would break the 
        protocol)
        :return: Connection Socket's object
        """
        return self.conn


if __name__ == "__main__":
    server = Server("localhost", 8001)
    con = server.accept()
    con = server.key_exchange(con)
    #con.set_query_cooldown(10)
    while True:
        tiempo = time()
        con.send("HOLA")
        con.recv()
        print(time() - tiempo)
        sleep(0.5)
    #while True: pass
