import socket
import selectors
from types import SimpleNamespace
import errno

HOST = '127.0.0.1'
PORT = 8080
EVENTS = selectors.EVENT_READ | selectors.EVENT_WRITE

def accept(sel, sock, interlocutors):
	conn, _ = sock.accept()
	conn.setblocking(False)
	data = SimpleNamespace(buff = b'', client_socket = True)
	sel.register(conn, EVENTS, data)
	
	interlocutors[conn] = (None, None)

def close_sock(sock, closed_list, sel):
	closed_list.append(sock)
	sel.unregister(sock)
	sock.close()

def process_write(sock, data, interlocutors, closed_list, sel):
	if sock in closed_list:
		return
	if data.buff:
		try:
			sent = sock.send(data.buff)
			data.buff = data.buff[sent:]
		except:
			close_sock(sock, closed_list, sel)
	else:
		interlocutor, _ = interlocutors[sock]
		if interlocutor in closed_list:
			close_sock(sock, closed_list, sel)

def data_or_None(sock):
	try:
		data = sock.recv(1024)
		return data if data else None
	except:
		return None

def resend_to_interlocutor(sock, interlocutors, data):
	interlocutor, interlocutor_data = interlocutors[sock]
	if interlocutor is not None:
		interlocutor_data.buff += data

def service_connection(key, mask, interlocutors, closed_list, sel):
	sock = key.fileobj
	data = key.data
	if data.client_socket:
		if mask & selectors.EVENT_READ:
			recv_data = data_or_None(sock)
			if recv_data is None:
				close_sock(sock, closed_list, sel)
			else:
				conn_pos = recv_data.find(b'CONNECT')
				if conn_pos >= 0:
					recv_data = recv_data[(conn_pos + 8):]
					recv_data = recv_data[:recv_data.find(b' ')]
					host, port = recv_data.split(b':')
					
					try:
						serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
						serv.setblocking(False)
						serv.connect_ex((host, int(port)))
						serv_data = SimpleNamespace(buff = b'', client_socket = False)
						sel.register(serv, EVENTS, serv_data)
						
						interlocutors[sock] = (serv, serv_data)
						interlocutors[serv] = (sock, data)
						data.buff = b'HTTP/1.1 200 Connection established\r\nProxy-Agent: cool-proxy/0.1\r\n\r\n'
					except:
						data.buff = b'HTTP/1.1 502 Bad Gateway\r\nProxy-Agent: cool-proxy/0.1\r\n\r\n'
				else:
					resend_to_interlocutor(sock, interlocutors, recv_data)
		if mask & selectors.EVENT_WRITE:
			process_write(sock, data, interlocutors, closed_list, sel)
	else:
		if mask & selectors.EVENT_READ:
			recv_data = data_or_None(sock)
			if recv_data is None:
				close_sock(sock, closed_list, sel)
			else:
				resend_to_interlocutor(sock, interlocutors, recv_data)
		if mask & selectors.EVENT_WRITE:
			process_write(sock, data, interlocutors, closed_list, sel)

if __name__ == '__main__':
	sel = selectors.DefaultSelector()
	
	# client socket preparation
	lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	lsock.bind((HOST, PORT))
	lsock.listen()
	lsock.setblocking(False)
	sel.register(lsock, selectors.EVENT_READ, data = None)
	
	interlocutors = {}
	closed = []
	
	running = True
	while running:
		try:
			to_be_deleted = []
			for sock in closed:
				interlocutor, _ = interlocutors[sock]
				if (interlocutor is None) or (interlocutor in closed):
					to_be_deleted.append(sock)
			
			for sock in to_be_deleted:
				closed.remove(sock)
				del interlocutors[sock]
						
			events = sel.select(timeout = None)
			for key, mask in events:    #key.fileobj = socket, key.data = storage, mask contains events
				if key.data is None:
					accept(sel, key.fileobj, interlocutors)
				else:
					service_connection(key, mask, interlocutors, closed, sel)
		except KeyboardInterrupt:
			running = False
	
	selmap = sel.get_map()
	for i in selmap:
		selmap[i].fileobj.close()
	sel.close()
