import socket
from topology import topology_reader
import selectors
import threading
import types
from message import Message
import pickle
from dijkstar import Graph, find_path
import math
import os

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
GRAPH = Graph()
NEIGHBOR_SOCKETS = {}
INF = math.inf
LINK_STATUS = {}


def update_routing_table(server_costs, sender_id, update=False):
    global ROUTING_TABLE

    for (s_id, n_id, cost) in server_costs:
        if (s_id, n_id) in LINK_STATUS and not LINK_STATUS[(s_id, n_id)]:
            return

        # if (s_id == MY_ID or n_id == MY_ID) and (s_id in ROUTING_TABLE and n_id in ROUTING_TABLE) and (s_id == MY_ID or n_id == MY_ID) and not update:
        #     if not math.isinf(cost):
        #         return


        if s_id in ROUTING_TABLE:
            found_n_id = False
            for index, item in enumerate(ROUTING_TABLE[s_id]):
                if item[0] == n_id:
                    found_n_id = True
                    GRAPH.get_node(s_id).update({n_id: cost})
                    ROUTING_TABLE[s_id][index] = (n_id, cost)
            if not found_n_id:
                GRAPH.add_edge(s_id, n_id, cost)
                ROUTING_TABLE[s_id].append((n_id, cost))
        else:
            GRAPH.add_edge(s_id, n_id, cost)
            ROUTING_TABLE[s_id] = [(n_id, cost)]

        if n_id in ROUTING_TABLE:
            found_n_id = False
            for index, item in enumerate(ROUTING_TABLE[n_id]):
                if item[0] == s_id:
                    found_n_id = True
                    GRAPH.get_node(n_id).update({s_id: cost})
                    ROUTING_TABLE[n_id][index] = (s_id, cost)
            if not found_n_id:
                GRAPH.add_edge(n_id, s_id, cost)
                ROUTING_TABLE[n_id].append((s_id, cost))
        

def _display():
    print(LOCAL_TOPOLOGY)
    keys = ROUTING_TABLE.keys()
    keys = sorted(keys)
    print(f'source_id next_hop_id cost shortest_cost')
    print(f'_________ ___________ ____ _____________')
    for key in keys:
        costs = ROUTING_TABLE[key]
        for (n_id, cost) in sorted(costs):
            print(f'    {key}          {n_id}       {cost if not math.isinf(cost) else "inf"}        { find_path(GRAPH, key, n_id).total_cost }')
    return 'display SUCCESS'


def _disable(neighbor_id):
    neighbor_id = int(neighbor_id)
    message = Message([], MY_PORT, MY_ID, _myip(), flag='disable')
    send_it(neighbor_id, pickle.dumps(message))
    LOCAL_TOPOLOGY.remove_neighbor(MY_ID, neighbor_id)
    update_routing_table([(MY_ID, neighbor_id, INF)], MY_ID)
    update_routing_table([(neighbor_id, MY_ID, INF)], MY_ID)
    LINK_STATUS[(MY_ID, neighbor_id)] = False
    LINK_STATUS[(neighbor_id, MY_ID)] = False
    return 'disable SUCCESS'

def _crash():
    message = Message([], MY_PORT, MY_ID, _myip(), flag='crash')
    for (n_id, _) in LOCAL_TOPOLOGY.neighbors[MY_ID]:
        send_it(n_id, pickle.dumps(message))
    LOCAL_TOPOLOGY.neighbors = {}
    print('SERVER CRASHED!')
    os._exit(1)
        

def _packets():
    global PACKETS_RECEIVED
    res = f'{PACKETS_RECEIVED} total messages received since last packet check'
    PACKETS_RECEIVED = 0
    return f'{res}\npackets SUCCESS'


def update_neighbors(message):
    for n_id, _ in LOCAL_TOPOLOGY.neighbors[MY_ID]:
        send_it(n_id, message)


def send_it(connection_id, message):
    address = LOCAL_TOPOLOGY.servers[connection_id]
    lsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.sendto(message, address)


def update_loop():
    while True:
        import time
        time.sleep(NUM_SECS)
        update_fields = [(key, n_id, cost) for key in ROUTING_TABLE.keys() for n_id, cost in ROUTING_TABLE[key] if n_id != MY_ID]
        update_neighbors(pickle.dumps(Message(update_fields, MY_PORT, MY_ID, _myip)))
        for key in COUNT_SINCE_RECEIVED.keys():
            print(f'{key}: {COUNT_SINCE_RECEIVED[key]}')
            if COUNT_SINCE_RECEIVED[key] >= 3:
                update_routing_table([(MY_ID, key, INF)], MY_ID)
                update_routing_table([(key, MY_ID, INF)], MY_ID)
                _step()
            COUNT_SINCE_RECEIVED[key] += 1


def _step():
    update_fields = [(key, n_id, cost) for key in ROUTING_TABLE.keys() for n_id, cost in ROUTING_TABLE[key] if n_id != MY_ID]
    update_neighbors(pickle.dumps(Message(update_fields, MY_PORT, MY_ID, _myip)))
    return f'step SUCCESS'


def _update(s_id_1, s_id_2, new_cost):
    if new_cost != 'inf':
        s_id_1, s_id_2, new_cost = map(int, [s_id_1, s_id_2, new_cost])
    else:
        new_cost = INF
        s_id_1, s_id_2 = map(int, [s_id_1, s_id_2])
    message = Message([(s_id_1, s_id_2, new_cost)], MY_PORT, MY_ID, _myip, flag='update')
    if s_id_1 != MY_ID:
        send_it(s_id_1, pickle.dumps(message))
    if s_id_2 != MY_ID:
        send_it(s_id_2, pickle.dumps(message))
    
    if s_id_1 == MY_ID:
        for (n_id, _) in LOCAL_TOPOLOGY.neighbors[MY_ID]:
            if s_id_2 == n_id:
                update_routing_table([(MY_ID, n_id, new_cost)], MY_ID)

    return f'update {s_id_1} {s_id_2} {new_cost} SUCCESS'


def _server(topology_file_path, routing_update_interval):
    global LOCAL_TOPOLOGY
    global MY_ID
    global MY_PORT
    global NUM_SECS
    global COUNT_SINCE_RECEIVED
    global GRAPH
    global LINK_STATUS
    NUM_SECS = int(routing_update_interval)
    my_ip = _myip()
    LOCAL_TOPOLOGY = topology_reader(topology_file_path)
    print(LOCAL_TOPOLOGY)
    for id, (ip, port) in LOCAL_TOPOLOGY.servers.items():
        if ip == my_ip:
            MY_ID = id
            MY_PORT = port
            run_server(port)
            for (n_id, cost) in LOCAL_TOPOLOGY.neighbors[MY_ID]:
                COUNT_SINCE_RECEIVED[n_id] = 0
                GRAPH.add_edge(MY_ID, n_id, cost)
                LINK_STATUS[(MY_ID, n_id)] = True
                LINK_STATUS[(n_id, MY_ID)] = True
            return f'topology gathered, server running: {(MY_ID, my_ip, MY_PORT)}'
    return f'Could not find ip in topology'


def _myip() -> None:
    try:
        # TODO: ifconfig eth0 or ipconfig
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
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
    update_routing_table([(MY_ID, n_id, cost) for n_id, cost in LOCAL_TOPOLOGY.neighbors[MY_ID]], MY_ID)
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
    if mask & selectors.EVENT_READ:
        recv_data = sock.recv(4096)  # Should be ready to read
        if recv_data:
            message = pickle.loads(recv_data)
            update_routing_table(message.update_fields, message.sender_id, update= (message.flag == 'update'))
            if message.flag == 'update':
                _step()
            # check if crash flag
            if message.flag == 'crash' or message.flag == 'disable':
                LOCAL_TOPOLOGY.remove_neighbor(MY_ID, message.sender_id)
                update_routing_table([(message.sender_id, MY_ID, INF), (MY_ID, message.sender_id, INF)], MY_ID)
                LINK_STATUS[(message.sender_id, MY_ID)] = False
                LINK_STATUS[(MY_ID, message.sender_id)] = False

                if message.flag == 'crash':
                    for (n_id, _) in ROUTING_TABLE[message.sender_id]:
                        update_routing_table([(message.sender_id, n_id, INF), (n_id, message.sender_id, INF)], MY_ID)
                        _step()
            else:
                PACKETS_RECEIVED += 1
                print(f'RECEIVED A MESSAGE FROM SERVER: {message.sender_id}')
                if message.sender_id in [n_id for (n_id, _) in LOCAL_TOPOLOGY.neighbors[MY_ID]]:
                    COUNT_SINCE_RECEIVED[message.sender_id] = 0


def general_loop():
    try:
        while True:
            events_to_check = DEFAULT_SELECTOR.select(timeout=None)
            for key, mask in events_to_check:
                if key:
                    service_connection(key, mask)
    except KeyboardInterrupt:
        print("caught keyboard interrupt, exiting")
    finally:
        DEFAULT_SELECTOR.close()

