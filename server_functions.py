import socket
from topology import topology_reader
import selectors
import threading
import time
import types
from message import Message
import pickle
import sys


LOCAL_TOPOLOGY = None
DEFAULT_SELECTOR = selectors.DefaultSelector()
EVENTS = selectors.EVENT_READ | selectors.EVENT_WRITE # the events to check for in our selector
MY_ID = -1
MY_PORT = -1
NUM_SECS = 0
MY_SOCK = None
PACKETS_RECEIVED = 0
ROUTING_TABLE = {}
COUNT_SINCE_RECEIVED = {}


def update_routing_table(server_costs, overwrite=False):
    global ROUTING_TABLE
    for (s_id, n_id, cost) in server_costs:
        if s_id in ROUTING_TABLE:
            found_n_id = False
            for index, item in enumerate(ROUTING_TABLE[s_id]):
                if item[0] == n_id:
                    found_n_id = True
                    ROUTING_TABLE[s_id][index] = (n_id, cost)
            if not found_n_id:
                ROUTING_TABLE[s_id].append((n_id, cost))
        else:
            ROUTING_TABLE[s_id] = [(n_id, cost)]

        if s_id in LOCAL_TOPOLOGY.neighbors:
            LOCAL_TOPOLOGY.update_cost(s_id, n_id, cost)
        

def _display():
    print(LOCAL_TOPOLOGY)
    keys = ROUTING_TABLE.keys()
    keys = sorted(keys)
    print(f'source_id next_hop_id cost')
    print(f'_________ ___________ ____')
    for key in keys:
        costs = ROUTING_TABLE[key]
        for (n_id, cost) in sorted(costs):
            print(f'    {key}          {n_id}       {cost if cost > 0 else "inf"}')
    return 'display SUCCESS'


def _disable(neighbor_id):
    neighbor_id = int(neighbor_id)
    message = Message([(MY_ID, neighbor_id, -1)], MY_PORT, MY_ID, _myip(), flag='disable')
    send_it(neighbor_id, pickle.dumps(message))
    LOCAL_TOPOLOGY.remove_neighbor(MY_ID, neighbor_id)
    update_routing_table([(MY_ID, neighbor_id, -1)])
    update_routing_table([(neighbor_id, MY_ID, -1)])
    return 'disable SUCCESS'

def _crash():
    for (n_id, _) in LOCAL_TOPOLOGY.neighbors[MY_ID]:
        # call disable for every neighbor
        _disable(n_id)
        

def _packets():
    global PACKETS_RECEIVED
    res = f'{PACKETS_RECEIVED} total messages received since last packet check'
    PACKETS_RECEIVED = 0
    return f'{res}\npackets SUCCESS'


def update_neighbors(message):
    for n_id, _ in LOCAL_TOPOLOGY.neighbors[MY_ID]:
        send_it(n_id, message)


def send_it(connection_id: str, message):
    address = LOCAL_TOPOLOGY.servers[connection_id]
    DEFAULT_SELECTOR.modify(MY_SOCK, events=EVENTS, data=types.SimpleNamespace(c_id=connection_id,addr=address, message=message))


def update_loop():
    while True:
        time.sleep(NUM_SECS)
        update_neighbors(pickle.dumps(Message([(MY_ID, n_id, cost) for key in ROUTING_TABLE.keys() for n_id, cost in ROUTING_TABLE[key] if n_id != MY_ID], MY_PORT, MY_ID, _myip)))
        for key in COUNT_SINCE_RECEIVED.keys():
            if COUNT_SINCE_RECEIVED[key] == 3:
                update_routing_table([(MY_ID, key, -1)])
            COUNT_SINCE_RECEIVED[key] += 1


def _step():
    update_neighbors(pickle.dumps(Message([(MY_ID, n_id, cost) for key in ROUTING_TABLE.keys() for n_id, cost in ROUTING_TABLE[key] if n_id != MY_ID], MY_PORT, MY_ID, _myip)))
    return f'step SUCCESS'


def _update(s_id_1, s_id_2, new_cost):
    if new_cost != 'inf':
        s_id_1, s_id_2, new_cost = map(int, [s_id_1, s_id_2, new_cost])
    else:
        new_cost = -1
        s_id_1, s_id_2 = map(int, [s_id_1, s_id_2])
    message = Message([(s_id_1, s_id_2, new_cost), (s_id_2, s_id_1, new_cost)], MY_PORT, MY_ID, _myip)
    if s_id_1 != MY_ID:
        send_it(s_id_1, pickle.dumps(message))
    if s_id_2 != MY_ID:
        send_it(s_id_2, pickle.dumps(message))
    
    if s_id_1 == MY_ID:
        for (n_id, _) in LOCAL_TOPOLOGY.neighbors[MY_ID]:
            if s_id_2 == n_id:
                update_routing_table([(MY_ID, n_id, new_cost)])

    return f'update {s_id_1} {s_id_2} {new_cost} SUCCESS'


def _server(topology_file_path, routing_update_interval):
    global LOCAL_TOPOLOGY
    global MY_ID
    global MY_PORT
    global NUM_SECS
    global COUNT_SINCE_RECEIVED
    NUM_SECS = int(routing_update_interval)
    my_ip = _myip()
    LOCAL_TOPOLOGY = topology_reader(topology_file_path)
    print(LOCAL_TOPOLOGY)
    for id, (ip, port) in LOCAL_TOPOLOGY.servers.items():
        if ip == my_ip:
            MY_ID = id
            MY_PORT = port
            run_server(port)
            for (n_id, _) in LOCAL_TOPOLOGY.neighbors[MY_ID]:
                COUNT_SINCE_RECEIVED[n_id] = 0
            return f'topology gathered, server running: {(MY_ID, my_ip, MY_PORT)}'
    return f'Could not find ip in topology'


def _myip() -> None:
    try:
        # TODO: ifconfig eth0 or ipconfig
        address_list = socket.gethostbyname_ex(socket.gethostname())[2]
        for address in address_list:
            if address != '127.0.0.1':
                return address
        print('Could not get IP address. Exiting ...')
        sys.exit(1)
    except:
        print('Error Getting IP.')


def run_server(port_number):
    global MY_SOCK
    lsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_bind = (_myip(), port_number)
    lsock.bind(server_bind)
    print("listening on", server_bind)
    lsock.setblocking(False)
    MY_SOCK = lsock
    DEFAULT_SELECTOR.register(lsock, selectors.EVENT_READ, data=None)
    update_routing_table([(MY_ID, n_id, cost) for n_id, cost in LOCAL_TOPOLOGY.neighbors[MY_ID]])
    gen_thread = threading.Thread(name='general_loop', target=general_loop)
    gen_thread.start()
    event_thread = threading.Thread(name='update_loop', target=update_loop)
    event_thread.start()


def service_connection(key, mask):
    '''
    service connection function, this is the server event loop
    '''
    global PACKETS_RECEIVED
    sock = key.fileobj
    data = key.data
    if mask & selectors.EVENT_READ:
        recv_data = sock.recv(4096)  # Should be ready to read
        if recv_data:
            message = pickle.loads(recv_data)
            update_routing_table(message.update_fields)
            # Check if message flag is disable, if so remove the link
            if message.flag == 'disable':
                LOCAL_TOPOLOGY.remove_neighbor(MY_ID, data.c_id)
                update_routing_table([(MY_ID, data.c_id, -1)])
            PACKETS_RECEIVED += 1
            print(f'RECEIVED A MESSAGE FROM SERVER: {data.c_id}')
            COUNT_SINCE_RECEIVED[data.c_id] = 0
    if mask & selectors.EVENT_WRITE:
        if data.message:
            sock.sendto(data.message, data.addr)
            data.message = None  # Should be ready to write

def general_loop():
    try:
        while True:
            events_to_check = DEFAULT_SELECTOR.select(timeout=None)
            for key, mask in events_to_check:
                if key.data:
                    service_connection(key, mask)
    except KeyboardInterrupt:
        print("caught keyboard interrupt, exiting")
    finally:
        DEFAULT_SELECTOR.close()

