import socket
import sys
import logging
import threading

from config import *

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ProxyServer:
    def __init__(self, host="0.0.0.0", port=8888):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(MAX_CONNECTIONS)

    def run(self):
        logger.info(f"Proxy server started on {self.server.getsockname()}")
        while True:
            try:
                client_socket, client_address = self.server.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.start()
            except Exception as e:
                logger.error(f"Error on accept connection: {e}")

    def handle_client(self, client_socket):
        try:
            data = client_socket.recv(BUFFER_SIZE)
            if data:
                self.handle_client_request(client_socket, data)
            else:
                self.close_connection(client_socket)
        except Exception as e:
            logger.error(f"Error from handling request: {e}")
            self.close_connection(client_socket)

    def handle_client_request(self, client_socket, data):
        try:
            lines = data.split(b'\r\n')
            first_line = lines[0]
            method, url, _ = first_line.split(b' ', 2)

            if method == b"CONNECT":
                self.handle_connect(client_socket, url)
            else:
                self.handle_http(client_socket, data, url)

        except Exception as e:
            logger.error(f"Error from handling request: {e}")
            self.close_connection(client_socket)

    def handle_connect(self, client_socket, url):
        webserver, port = url.split(b':')
        webserver = webserver.decode()
        port = int(port)

        try:
            logger.info(f"We establish a CONNECT tunnel to {webserver}:{port}")
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((webserver, port))
            client_socket.send(b"HTTP/1.1 200 Connection established\r\n\r\n")

            def forward(source, destination):
                while True:
                    try:
                        data = source.recv(BUFFER_SIZE)
                        if not data:
                            break
                        destination.sendall(data)
                    except:
                        break
                source.close()
                destination.close()

            threading.Thread(target=forward, args=(client_socket, server_socket), daemon=True).start()
            threading.Thread(target=forward, args=(server_socket, client_socket), daemon=True).start()

        except Exception as e:
            logger.error(f"Error from establishing CONNECT tunnel: {e}")
            self.close_connection(client_socket)

    def handle_http(self, client_socket, data, url):
        try:
            http_pos = url.find(b'://')
            if http_pos == -1:
                temp = url
            else:
                temp = url[(http_pos + 3):]

            port_pos = temp.find(b':')
            webserver_pos = temp.find(b'/')
            if webserver_pos == -1:
                webserver_pos = len(temp)

            if port_pos == -1 or webserver_pos < port_pos:
                port = 80
                webserver = temp[:webserver_pos]
            else:
                port = int((temp[(port_pos + 1):])[:webserver_pos - port_pos - 1])
                webserver = temp[:port_pos]

            logger.info(f"Connecting to {webserver}:{port}")
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.connect((webserver, port))
            proxy_socket.send(data)

            def forward_response(proxy_socket, client_socket):
                while True:
                    try:
                        response = proxy_socket.recv(BUFFER_SIZE)
                        if not response:
                            break
                        client_socket.send(response)
                    except:
                        break
                self.close_connection(proxy_socket)
                self.close_connection(client_socket)

            threading.Thread(target=forward_response, args=(proxy_socket, client_socket), daemon=True).start()

        except Exception as e:
            logger.error(f"Error processing HTTP request: {e}")
            self.close_connection(client_socket)

    @staticmethod
    def close_connection(sock):
        try:
            sock.close()
        except:
            pass

if __name__ == '__main__':
    try:
        proxy = ProxyServer('0.0.0.0', 8888)
        proxy.run()
    except KeyboardInterrupt:
        logger.info("Server stopped.")
    sys.exit(0)
